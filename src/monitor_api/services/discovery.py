"""Servicio del bucle autónomo de descubrimiento.

El bucle corre como **subproceso desacoplado**, no como hilo del servidor. Es la
misma decisión que ya tomaba el runner de DFT, y por el mismo motivo: cribar
decenas de miles de candidatos con pandas satura un núcleo durante minutos, y
con el GIL eso dejaba sin turno al event loop de asyncio. La API se quedaba
muda —primero timeouts, después el listener caído— justo mientras había algo
que monitorizar, que es lo único que esta aplicación existe para hacer.

La comunicación entre los dos procesos ya existía: el bucle escribe
`state.json` y el servidor lo lee.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .. import paths, platform_caps

log = logging.getLogger(__name__)

_lock = threading.Lock()

SPACE_OVERRIDE_REL = "data/discovery/space_config.json"
#: Dónde se anota el subproceso vivo, para reconocerlo tras reiniciar el monitor.
PID_REL = "data/discovery/loop.pid.json"
LOG_REL = "data/discovery/loop.log"
#: Config efectiva volcada a disco para el subproceso: lleva el override del
#: espacio químico, que hasta ahora solo vivía en memoria del servidor.
EFFECTIVE_CFG_REL = "data/discovery/effective_config.yaml"
MODE_DEFAULTS = {
    "pure": True,
    "A_mixed": True,
    "B_mixed": True,
    "X_mixed": True,
    "multi_mixed": False,
}
SITE_SPECIES = {
    "A_sites": ("Cs", "Rb", "K", "MA", "FA"),
    "B_sites": ("Pb", "Sn", "Ge", "Bi", "In"),
    "X_sites": ("I", "Br", "Cl"),
}


def config_path() -> Path:
    """Discovery config, preferring user data but falling back to bundled config."""
    data_cfg = paths.resolve_data("config/generator.yaml")
    if data_cfg.is_file():
        return data_cfg
    return paths.bundle_file("config", "generator.yaml")


def _space_config_path() -> Path:
    return paths.resolve_data(SPACE_OVERRIDE_REL)


def _base_config() -> dict[str, Any]:
    cfg_path = config_path()
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _saved_override() -> dict[str, Any]:
    override_path = _space_config_path()
    if not override_path.is_file():
        return {}
    try:
        return json.loads(override_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("Discovery space override corrupto: %s", override_path)
        return {}


def _effective_config(update: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _base_config()
    saved = _saved_override()
    if saved:
        cfg = _apply_space_update(cfg, saved)
    if update:
        cfg = _apply_space_update(cfg, _validate_space_update(update))
    return cfg


def build_loop():
    """Construye el bucle con las rutas efectivas del monitor.

    Público porque lo usa también el subproceso (`launcher --discovery-loop`):
    así los dos lados resuelven raíces y configuración por el mismo camino, en
    vez de que el subproceso caiga en los valores por defecto del repositorio y
    escriba el estado donde el servidor no lo está mirando.
    """
    from buho.discovery import DiscoveryLoop

    return DiscoveryLoop(
        config_path=_effective_config(),
        config_source_path=config_path(),
        project_root=paths.data_root(),
        data_root=paths.data_root(),
        # Escritura en la raíz de datos: antes era `find_resource("models").parent`,
        # que congelado es el directorio de extracción del binario. Los modelos
        # reentrenados acababan dentro de la instalación — se perdían al
        # actualizar y fallaban si la app estaba en un sitio de solo lectura.
        models_root=paths.data_root(),
        # Los de fábrica viajan en el binario; se leen de ahí.
        bundle_root=paths.bundle_root(),
    )


#: Alias interno histórico; el módulo entero lo usaba con este nombre.
_loop = build_loop


# ── Subproceso del bucle ──────────────────────────────────────────────────────


def _pid_file() -> Path:
    return paths.resolve_data(PID_REL)


def _log_file() -> Path:
    return paths.resolve_data(LOG_REL)


def _leer_pid() -> dict[str, Any]:
    ruta = _pid_file()
    if not ruta.is_file():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _vivo(pid: int | None) -> bool:
    """Si el subproceso del bucle sigue corriendo de verdad.

    Se comprueba el PID, no solo el fichero: si el proceso muere de golpe el
    fichero se queda, y sin esto la interfaz mostraría un bucle fantasma para
    siempre y no dejaría lanzar otro.
    """
    if not pid:
        return False
    try:
        import psutil

        proc = psutil.Process(int(pid))
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return False
        # El PID puede haberse reciclado para otro proceso cualquiera.
        return "discovery-loop" in " ".join(proc.cmdline()) or "--discovery-loop" in " ".join(proc.cmdline())
    except Exception:  # noqa: BLE001 - psutil ausente o proceso inaccesible
        return False


def _cola_log(lineas: int = 40) -> str:
    ruta = _log_file()
    if not ruta.is_file():
        return ""
    try:
        contenido = ruta.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(contenido[-lineas:]).strip()


def _background() -> dict[str, Any]:
    """Estado del subproceso, para el bloque `background` de la respuesta."""
    info = _leer_pid()
    pid = info.get("pid")
    corriendo = _vivo(pid)
    salida: dict[str, Any] = {"running": corriendo, "pid": pid if corriendo else None}

    if not corriendo and info:
        # Terminó. Si fue por un fallo, el log es lo único que lo explica.
        cola = _cola_log()
        if info.get("expected_exit"):
            salida["last_error"] = None
        elif cola and ("Traceback" in cola or "ERROR" in cola or "falló" in cola):
            salida["last_error"] = cola[-1500:]
        else:
            salida["last_error"] = None
        salida["log"] = str(_log_file())
    else:
        salida["last_error"] = None
    return salida


def _comando_bucle(*, start_runner: bool, dry_run: bool, use_mlff: bool | None,
                   max_rounds: int | None) -> list[str]:
    """Argv para relanzar este mismo ejecutable en modo bucle.

    Congelado, `sys.executable` es el propio binario y no hay un `python -m` al
    que llamar; desde el código fuente hay que pasar por `-m monitor_api`. Las
    dos rutas acaban en `launcher.main()` con `--discovery-loop`.
    """
    if paths.is_frozen():
        argv = [sys.executable]
    else:
        interprete = platform_caps.runner_python() or sys.executable
        argv = [interprete, "-m", "monitor_api"]

    argv += ["--discovery-loop", "--data-root", str(paths.data_root()),
             "--log-level", "info"]
    if not start_runner:
        argv.append("--no-runner")
    if dry_run:
        argv.append("--dry-run")
    if use_mlff is False:
        argv.append("--no-mlff")
    if max_rounds is not None:
        argv += ["--max-rounds", str(max_rounds)]
    return argv


def available_species() -> dict[str, list[str]]:
    from ml_surrogate.features import CHARGES, IONIC_RADII

    species = sorted(set(CHARGES).intersection(IONIC_RADII))
    known = set(species)
    return {key: [sp for sp in values if sp in known] for key, values in SITE_SPECIES.items()}


def current_config() -> dict[str, Any]:
    cfg = _effective_config()
    preview = _config_payload(cfg)
    preview["source"] = str(_space_config_path()) if _saved_override() else str(config_path())
    preview["override_saved"] = bool(_saved_override())
    preview["available_species"] = available_species()
    return preview


def preview_config(update: dict[str, Any] | None = None) -> dict[str, Any]:
    from buho.discovery import ChemicalSpaceEnumerator

    cfg = _effective_config(update)
    candidates, stats = ChemicalSpaceEnumerator(cfg).enumerate(physical_viable_only=True)
    payload = current_config() if update is None else _config_payload(cfg)
    payload["preview"] = {
        **stats.as_dict(),
        "mode_counts": {str(k): int(v) for k, v in Counter(c.generation_mode for c in candidates).items()},
    }
    return payload


def save_config(update: dict[str, Any]) -> dict[str, Any]:
    if _vivo(_leer_pid().get('pid')):
        raise RuntimeError("Pausa el protocolo antes de cambiar el espacio químico.")
    normalized = _validate_space_update(update)
    path = _space_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return preview_config()


def _validate_space_update(update: dict[str, Any]) -> dict[str, Any]:
    from ml_surrogate.features import CHARGES, IONIC_RADII

    out: dict[str, Any] = {}
    available = set(CHARGES).intersection(IONIC_RADII)
    available_by_site = {key: set(values) for key, values in available_species().items()}

    for key in ("A_sites", "B_sites", "X_sites"):
        if key not in update:
            continue
        raw = update.get(key) or []
        if not isinstance(raw, list):
            raise ValueError(f"{key} debe ser una lista.")
        values = []
        seen = set()
        for item in raw:
            species = str(item).strip()
            if not species:
                continue
            if species not in available:
                raise ValueError(f"{species} no tiene radios/cargas en las tablas internas.")
            if species not in available_by_site[key]:
                site = key.removesuffix("_sites")
                raise ValueError(f"{species} no está habilitado para el sitio {site}.")
            charge = CHARGES[species]
            if key == "X_sites" and charge >= 0:
                raise ValueError(f"{species} no puede ir en X porque no es anión.")
            if key != "X_sites" and charge <= 0:
                raise ValueError(f"{species} no puede ir en {key[0]} porque no es catión.")
            if species not in seen:
                values.append(species)
                seen.add(species)
        if not values:
            raise ValueError(f"{key} no puede quedar vacío.")
        out[key] = values

    numeric = {
        "min_fraction": 0.05,
        "max_fraction": 0.95,
        "fraction_step": 0.01,
    }
    for key in numeric:
        if key in update:
            try:
                out[key] = float(update[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} debe ser numérico.") from None

    min_fraction = float(out.get("min_fraction", update.get("min_fraction", numeric["min_fraction"])))
    max_fraction = float(out.get("max_fraction", update.get("max_fraction", numeric["max_fraction"])))
    fraction_step = float(out.get("fraction_step", update.get("fraction_step", numeric["fraction_step"])))
    if not (0.0 < min_fraction <= max_fraction < 1.0):
        raise ValueError("Las fracciones deben cumplir 0 < mínima <= máxima < 1.")
    if not (0.0 < fraction_step <= 1.0):
        raise ValueError("fraction_step debe estar entre 0 y 1.")

    from buho.discovery.space import fraction_grid

    if not fraction_grid(min_fraction, max_fraction, fraction_step):
        raise ValueError("El rango y paso no producen fracciones de mezcla.")

    if "dft_per_round" in update:
        try:
            dft_per_round = int(update["dft_per_round"])
        except (TypeError, ValueError):
            raise ValueError("dft_per_round debe ser entero.") from None
        if not 1 <= dft_per_round <= 500:
            raise ValueError("dft_per_round debe estar entre 1 y 500.")
        out["dft_per_round"] = dft_per_round

    if "include_multi_mixed" in update:
        out["include_multi_mixed"] = bool(update["include_multi_mixed"])

    if "modes" in update:
        raw_modes = update.get("modes") or {}
        if not isinstance(raw_modes, dict):
            raise ValueError("modes debe ser un objeto.")
        modes = {key: bool(raw_modes.get(key, MODE_DEFAULTS[key])) for key in MODE_DEFAULTS}
        if not any(modes.values()):
            raise ValueError("Activa al menos un modo de generación.")
        out["modes"] = modes
        out.setdefault("include_multi_mixed", modes["multi_mixed"])

    return out


def _apply_space_update(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    cs = cfg.setdefault("chemical_space", {})
    for key in ("A_sites", "B_sites", "X_sites"):
        if key in update:
            cs[key] = list(update[key])

    gen = cfg.setdefault("generation", {})
    modes = dict(gen.get("modes", {}) or {})
    if "modes" in update:
        modes.update({key: bool(value) for key, value in update["modes"].items()})
    if "include_multi_mixed" in update:
        modes["multi_mixed"] = bool(update["include_multi_mixed"])
    if modes:
        gen["modes"] = modes

    discovery = cfg.setdefault("discovery", {})
    space = discovery.setdefault("space", {})
    for key in ("min_fraction", "max_fraction", "fraction_step", "include_multi_mixed"):
        if key in update:
            space[key] = update[key]
    if "modes" in update and "include_multi_mixed" not in update:
        space["include_multi_mixed"] = bool(modes.get("multi_mixed", False))
    if "dft_per_round" in update:
        discovery["dft_per_round"] = update["dft_per_round"]
    return cfg


def _config_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    from buho.discovery.space import fraction_grid

    cs = cfg.get("chemical_space", {}) or {}
    gen = cfg.get("generation", {}) or {}
    modes = {key: bool((gen.get("modes", {}) or {}).get(key, default)) for key, default in MODE_DEFAULTS.items()}
    discovery = cfg.get("discovery", {}) or {}
    space = discovery.get("space", {}) or {}
    min_fraction = float(space.get("min_fraction", 0.05))
    max_fraction = float(space.get("max_fraction", 0.95))
    fraction_step = float(space.get("fraction_step", 0.01))
    return {
        "A_sites": list(cs.get("A_sites", [])),
        "B_sites": list(cs.get("B_sites", [])),
        "X_sites": list(cs.get("X_sites", [])),
        "modes": modes,
        "min_fraction": min_fraction,
        "max_fraction": max_fraction,
        "fraction_step": fraction_step,
        "fraction_values": fraction_grid(min_fraction, max_fraction, fraction_step),
        "include_multi_mixed": bool(space.get("include_multi_mixed", modes.get("multi_mixed", False))),
        "dft_per_round": int(discovery.get("dft_per_round", 30)),
        "override_path": str(_space_config_path()),
    }


def status() -> dict[str, Any]:
    payload = _loop().status()
    payload["background"] = _background()
    return payload


def init(*, reset: bool = False) -> dict[str, Any]:
    if reset and _vivo(_leer_pid().get('pid')):
        raise RuntimeError("Pausa el protocolo antes de reiniciar la criba.")
    payload = _loop().init_space(reset=reset)
    payload["background"] = _background()
    return payload


def start(
    *,
    start_runner: bool = True,
    dry_run: bool = False,
    use_mlff: bool | None = None,
    max_rounds: int | None = None,
) -> dict[str, Any]:
    """Lanza el bucle como subproceso desacoplado, o devuelve el ya vivo."""
    with _lock:
        if _vivo(_leer_pid().get("pid")):
            return status()

        argv = _comando_bucle(
            start_runner=start_runner, dry_run=dry_run,
            use_mlff=use_mlff, max_rounds=max_rounds,
        )

        registro = _log_file()
        registro.parent.mkdir(parents=True, exist_ok=True)
        # Se trunca en cada arranque: interesa el error de ESTA ejecución, y un
        # log que crece sin fin acaba siendo imposible de leer desde la GUI.
        salida = registro.open("w", encoding="utf-8", errors="replace")

        entorno = os.environ.copy()
        entorno["DFT_DATA_ROOT"] = str(paths.data_root())
        if not paths.is_frozen():
            # El subproceso importa monitor_api y buho del árbol de fuentes.
            src = paths.bundle_root() / "src"
            previo = entorno.get("PYTHONPATH", "")
            entorno["PYTHONPATH"] = f"{src}{os.pathsep}{previo}" if previo else str(src)

        # Desacoplado a propósito: cerrar el monitor no debe abortar una ronda
        # a medias, igual que no aborta los cálculos DFT.
        if sys.platform == "win32":
            extra = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
        else:
            extra = {"start_new_session": True}

        try:
            proc = subprocess.Popen(
                argv, stdout=salida, stderr=subprocess.STDOUT,
                cwd=str(paths.data_root()), env=entorno, **extra,
            )
        except OSError as exc:
            salida.close()
            raise RuntimeError(f"No se pudo lanzar el bucle: {exc}") from exc
        finally:
            salida.close()

        _pid_file().write_text(
            json.dumps({
                "pid": proc.pid,
                "started_at": time.time(),
                "argv": argv,
                "log": str(registro),
            }, indent=2),
            encoding="utf-8",
        )
        log.info("bucle de descubrimiento lanzado (pid %s)", proc.pid)

    return status()


def stop() -> dict[str, Any]:
    """Detiene el subproceso del bucle, si lo hay."""
    with _lock:
        info = _leer_pid()
        pid = info.get("pid")
        if _vivo(pid):
            try:
                import psutil

                proc = psutil.Process(int(pid))
                for hijo in proc.children(recursive=True):
                    hijo.terminate()
                proc.terminate()
                proc.wait(timeout=20)
            except Exception:  # noqa: BLE001
                log.warning("no se pudo terminar limpiamente el bucle pid=%s", pid)
        info["expected_exit"] = True
        _pid_file().write_text(json.dumps(info, indent=2), encoding="utf-8")
    return status()


def pause() -> dict[str, Any]:
    payload = _loop().pause()
    payload["background"] = _background()
    return payload


def resume() -> dict[str, Any]:
    payload = _loop().resume()
    payload["background"] = _background()
    return payload


def frontier(limit: int = 100) -> dict[str, Any]:
    return {"items": _loop().frontier(limit=limit)}


def export() -> dict[str, Any]:
    return _loop().export()


def reset_background_for_tests() -> None:
    """Olvida el subproceso anotado, si ya no existe.

    Se niega a borrar el registro de un proceso VIVO. Antes no comprobaba nada y
    la propia suite de tests, al correr contra la raíz de datos real, borró el
    fichero de un bucle en marcha: el proceso seguía cribando pero la API lo
    daba por muerto. Un ayudante de tests no puede tener ese poder.
    """
    with _lock:
        if _vivo(_leer_pid().get("pid")):
            log.warning("reset_background_for_tests: hay un bucle vivo, no se toca")
            return
        try:
            _pid_file().unlink(missing_ok=True)
        except OSError:
            pass
