"""Autonomous discovery loop service for the monitor API."""

from __future__ import annotations

import copy
import json
import logging
import threading
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .. import paths

log = logging.getLogger(__name__)

_lock = threading.Lock()
_thread: threading.Thread | None = None
_last_error: str | None = None

SPACE_OVERRIDE_REL = "data/discovery/space_config.json"
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


def _loop():
    from buho.discovery import DiscoveryLoop

    models_parent = paths.find_resource("models").parent
    return DiscoveryLoop(
        config_path=_effective_config(),
        config_source_path=config_path(),
        project_root=paths.data_root(),
        data_root=paths.data_root(),
        models_root=models_parent,
    )


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
    if _thread is not None and _thread.is_alive():
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
    payload["background"] = {
        "running": _thread is not None and _thread.is_alive(),
        "last_error": _last_error,
    }
    return payload


def init(*, reset: bool = False) -> dict[str, Any]:
    if reset and _thread is not None and _thread.is_alive():
        raise RuntimeError("Pausa el protocolo antes de reiniciar la criba.")
    payload = _loop().init_space(reset=reset)
    payload["background"] = {
        "running": _thread is not None and _thread.is_alive(),
        "last_error": _last_error,
    }
    return payload


def start(
    *,
    start_runner: bool = True,
    dry_run: bool = False,
    use_mlff: bool | None = None,
    max_rounds: int | None = None,
) -> dict[str, Any]:
    """Start the loop in the background, or return the running status."""
    global _thread, _last_error

    with _lock:
        if _thread is not None and _thread.is_alive():
            return status()

        _last_error = None

        def _target() -> None:
            global _last_error
            try:
                _loop().run_forever(
                    start_runner=start_runner,
                    dry_run=dry_run,
                    use_mlff=use_mlff,
                    max_rounds=max_rounds,
                )
            except Exception as exc:  # background workers must not die silently
                log.exception("Discovery loop failed")
                _last_error = f"{type(exc).__name__}: {exc}"

        _thread = threading.Thread(target=_target, name="perovowl-discovery", daemon=True)
        _thread.start()

    return status()


def pause() -> dict[str, Any]:
    payload = _loop().pause()
    payload["background"] = {
        "running": _thread is not None and _thread.is_alive(),
        "last_error": _last_error,
    }
    return payload


def resume() -> dict[str, Any]:
    payload = _loop().resume()
    payload["background"] = {
        "running": _thread is not None and _thread.is_alive(),
        "last_error": _last_error,
    }
    return payload


def frontier(limit: int = 100) -> dict[str, Any]:
    return {"items": _loop().frontier(limit=limit)}


def export() -> dict[str, Any]:
    return _loop().export()


def reset_background_for_tests() -> None:
    global _thread, _last_error
    with _lock:
        _thread = None
        _last_error = None
