"""Qué está haciendo el sistema ahora mismo, y cuánto le queda.

Las vistas mostraban recuentos por estado —12 pendientes, 2 corriendo— pero no
respondían a la pregunta de un vistazo: *¿está pasando algo?*. Y sin una
estimación de tiempo, un lote de cincuenta jobs es una barra que no se mueve.

La estimación sale de lo medido, no de una constante: la mediana del tiempo real
de los jobs ya convergidos. Cuando no hay con qué estimar se dice, en vez de
inventar un número que alguien usaría para planificar.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

# Estados que significan «este job todavía va a consumir tiempo».
PENDIENTES = ("pending",)
ACTIVOS = ("running", "stalled", "oscillating")


def _elapsed_de(job_dir: Path) -> float | None:
    """Segundos que tardó un job, si su status.json lo guardó."""
    try:
        d = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if d.get("status") != "converged":
        return None
    s = d.get("elapsed_s")
    if isinstance(s, (int, float)) and s > 0:
        return float(s)
    m = d.get("elapsed_min")
    if isinstance(m, (int, float)) and m > 0:
        return float(m) * 60.0
    return None


def duracion_tipica(batch_dir: Path | None, raiz: Path | None = None,
                    minimo: int = 3) -> tuple[float | None, int]:
    """Mediana del tiempo por job, y cuántas muestras la sostienen.

    Se prefiere el lote activo: distintos lotes usan sistemas de distinto
    tamaño y mezclarlos daría una estimación que no corresponde a ninguno. Si
    ese lote aún no tiene suficientes jobs terminados, se amplía a los demás.
    """
    def muestrear(base: Path) -> list[float]:
        vistos = []
        for st in base.glob("*/status.json"):
            v = _elapsed_de(st.parent)
            if v is not None:
                vistos.append(v)
        return vistos

    muestras: list[float] = []
    if batch_dir is not None and batch_dir.is_dir():
        muestras = muestrear(batch_dir)

    if len(muestras) < minimo and raiz is not None and raiz.is_dir():
        for otro in sorted(raiz.glob("batch_*"), reverse=True):
            if batch_dir is not None and otro == batch_dir:
                continue
            muestras.extend(muestrear(otro))
            if len(muestras) >= minimo * 4:
                break

    if len(muestras) < minimo:
        return None, len(muestras)
    return statistics.median(muestras), len(muestras)


def formatear(segundos: float | None) -> str | None:
    """`4830` → `1 h 20 min`. Sin decimales falsos: nadie planifica al segundo."""
    if segundos is None or segundos < 0:
        return None
    s = int(segundos)
    if s < 60:
        return f"{s} s"
    if s < 600:
        # Por debajo de diez minutos los segundos importan: decir «1 min» de 100
        # segundos es un 40 % de error, y esta cifra sostiene la estimación.
        return f"{s // 60} min {s % 60} s" if s % 60 else f"{s // 60} min"
    minutos, horas = (s // 60) % 60, s // 3600
    if horas >= 24:
        dias, resto = horas // 24, horas % 24
        return f"{dias} d {resto} h" if resto else f"{dias} d"
    if horas:
        return f"{horas} h {minutos} min" if minutos else f"{horas} h"
    return f"{minutos} min"


def _estado_cribado() -> dict[str, Any] | None:
    """Ejecución de cribado en marcha, si la hay."""
    try:
        from .screening import list_runs
    except ImportError:
        return None
    try:
        for run in list_runs():
            if getattr(run, "status", None) == "running":
                return {"run_id": run.run_id, "stage": getattr(run, "stage", None)}
    except Exception:
        return None
    return None


def _estado_barrido() -> dict[str, Any] | None:
    try:
        from .bench import _leer_progreso, _vivo
    except ImportError:
        return None
    prog = _leer_progreso()
    if prog.get("status") == "running" and _vivo(prog.get("pid")):
        return {"done": prog.get("done", 0), "total": prog.get("total", 0),
                "current": prog.get("current")}
    return None


def describe(poller) -> dict[str, Any]:
    """Actividad actual del sistema con su tiempo estimado."""
    from .. import paths
    from .control import _raiz_batches

    snaps = list(getattr(poller, "snapshots", {}).values())
    cfg = getattr(poller, "cfg", {}) or {}

    n_pend = sum(1 for s in snaps if s.status in PENDIENTES)
    n_act = sum(1 for s in snaps if s.status in ACTIVOS)
    n_hechos = sum(1 for s in snaps if s.status in ("converged", "failed",
                                                    "skipped_duplicate"))
    total = len(snaps)

    base: dict[str, Any] = {
        "activity": "idle",
        "label": "En reposo",
        "detail": None,
        "eta_seconds": None,
        "eta_text": None,
        "eta_basis": None,
        "progress": None,
        "n_pending": n_pend,
        "n_active": n_act,
        "n_done": n_hechos,
        "total": total,
        "running_jobs": [],
    }

    # El cribado y el barrido son cortos y excluyentes con el DFT en la práctica,
    # pero si coinciden manda lo que el usuario acaba de lanzar.
    barrido = _estado_barrido()
    if barrido:
        hechos, tot = barrido["done"], barrido["total"]
        base.update(
            activity="benchmark",
            label="Calibrando rendimiento",
            detail=(f"reparto {barrido['current']} — {hechos} de {tot}"
                    if barrido.get("current") else "preparando la medición"),
            progress=(hechos / tot) if tot else None,
        )
        return base

    cribado = _estado_cribado()
    if cribado:
        base.update(
            activity="generating",
            label="Generando candidatos",
            detail=cribado.get("stage") or "cascada de cribado en curso",
        )
        return base

    # ── DFT ─────────────────────────────────────────────────────────────────
    # Primero lo que corre de verdad. El poller vigila un único `runs_dir`
    # fijado al arrancar; si el runner trabaja sobre otro lote —lo normal en
    # cuanto se lanza un batch nuevo— sus jobs no están en los snapshots y el
    # sistema parecía «en reposo» con veinte procesos GPAW calculando.
    raiz = _raiz_batches(poller)
    batch = None

    runners = [r for r in runners_activos() if r.get("batch")]
    if runners:
        batch = runners[0]["batch"]
        conteo = contar_lote(batch)
        n_pend = conteo.get("pending", 0)
        n_act = sum(conteo.get(k, 0) for k in ACTIVOS)
        n_hechos = sum(conteo.get(k, 0) for k in ("converged", "failed",
                                                  "skipped_duplicate"))
        total = sum(conteo.values())
        base.update(n_pending=n_pend, n_active=n_act, n_done=n_hechos, total=total)

        # Se cuenta en jobs, no en procesos: cada job son N rangos MPI, y decir
        # «20 procesos» junto a «2 en paralelo» en la estimación se contradice.
        # Los trabajos vivos del lote activo, para que el panel de log sepa a
        # cuáles pedir la cola. Los snapshots del poller no sirven: solo cubren
        # el `runs_dir` fijado al arrancar.
        base["running_jobs"] = _trabajos_calculando(batch)

        vivos = n_calculos_vivos()
        detalle = f"{batch.name} — {n_act} job(s) calculando, {n_pend} en cola"
        if vivos:
            detalle += f" · {vivos} procesos MPI"
        base.update(
            activity="dft",
            label="DFT en curso",
            detail=detalle,
            progress=(n_hechos / total) if total else None,
        )
    else:
        if n_act == 0 and n_pend == 0:
            return base

        activo = n_act > 0
        base.update(
            activity="dft" if activo else "queued",
            label="DFT en curso" if activo else "DFT en cola",
            detail=f"{n_act} calculando, {n_pend} en cola",
            progress=(n_hechos / total) if total else None,
        )

        # El lote activo: el que contiene algún job sin terminar. Los snapshots
        # no llevan su ruta, así que se resuelve el id contra el árbol de runs.
        from .jobs import UnsafeJobIdError, resolve_job_dir

        for snap in snaps:
            if snap.status not in ACTIVOS + PENDIENTES:
                continue
            try:
                d = resolve_job_dir(getattr(poller, "runs_dir", None), snap.job_id)
            except (UnsafeJobIdError, TypeError, AttributeError):
                d = None
            if d is not None:
                batch = Path(d).parent
                break

    tipico, n_muestras = duracion_tipica(batch, raiz)
    if tipico is None:
        base["eta_basis"] = (
            f"sin datos suficientes ({n_muestras} job(s) con tiempo medido)")
        return base

    # Concurrencia real: lo que de verdad corre, o lo configurado si aún no
    # arrancó ninguno. Dividir por 1 cuando hay 8 slots daría 8× de más.
    slots = int(cfg.get("runner_slots", 0) or 0)
    concurrencia = max(n_act, slots, 1)

    restante_activos = 0.0
    for s in snaps:
        if s.status not in ACTIVOS:
            continue
        transcurrido = (getattr(s, "elapsed_min", None) or 0) * 60
        restante_activos = max(restante_activos, max(0.0, tipico - transcurrido))

    eta = restante_activos + (n_pend / concurrencia) * tipico
    base.update(
        eta_seconds=round(eta),
        eta_text=formatear(eta),
        eta_basis=(f"mediana de {n_muestras} job(s) terminados "
                   f"({formatear(tipico)} cada uno), {concurrencia} en paralelo"),
    )
    return base


# ── Qué está corriendo de verdad ─────────────────────────────────────────────

_CACHE: dict[str, Any] = {"t": 0.0, "valor": None}
_CACHE_TTL = 3.0     # el recuento lee decenas de status.json en un disco lento


def runners_activos() -> list[dict[str, Any]]:
    """Runners vivos y sobre qué lote trabaja cada uno.

    El poller vigila un único `runs_dir`, fijado al arrancar. Si el runner
    trabaja sobre otro lote —lo normal en cuanto se lanza un batch nuevo— sus
    jobs no aparecen en los snapshots y el sistema parecía en reposo con veinte
    procesos GPAW calculando.
    """
    import psutil

    encontrados = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            argv = proc.info["cmdline"] or []
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if not any("buho_relax_runner" in a or "phase2_force" in a for a in argv):
            continue
        batch = None
        for bandera in ("--relax-dir", "--batch-dir", "--runs-dir"):
            if bandera in argv:
                i = argv.index(bandera)
                if i + 1 < len(argv):
                    batch = Path(argv[i + 1])
                break
        encontrados.append({"pid": proc.info["pid"], "batch": batch})
    return encontrados


def n_calculos_vivos() -> int:
    """Procesos GPAW en marcha."""
    import psutil

    n = 0
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmd = " ".join(proc.info["cmdline"] or ())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "input.py" in cmd and "grep" not in cmd:
            n += 1
    return n


def contar_lote(batch_dir: Path) -> dict[str, int]:
    """Recuento de estados leyendo los status.json del lote."""
    ahora = time.time()
    clave = str(batch_dir)
    if _CACHE["valor"] and _CACHE.get("clave") == clave and ahora - _CACHE["t"] < _CACHE_TTL:
        return _CACHE["valor"]

    conteo: dict[str, int] = {}
    try:
        for st in batch_dir.glob("*/status.json"):
            try:
                estado = json.loads(st.read_text(encoding="utf-8")).get("status", "unknown")
            except (OSError, json.JSONDecodeError):
                estado = "unknown"
            conteo[estado] = conteo.get(estado, 0) + 1
    except OSError:
        pass

    _CACHE.update(t=ahora, clave=clave, valor=conteo)
    return conteo


def _trabajos_calculando(batch_dir: Path, limite: int = 12) -> list[dict[str, Any]]:
    """Trabajos del lote que están en marcha, los más recientes primero.

    Se lee del disco y no de los snapshots porque el poller vigila un único
    directorio: con el runner en otro lote, la lista salía vacía mientras la
    máquina calculaba.
    """
    encontrados = []
    for status in batch_dir.glob("*/status.json"):
        try:
            d = json.loads(status.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("status") not in ACTIVOS:
            continue
        try:
            mtime = status.stat().st_mtime
        except OSError:
            mtime = 0.0
        encontrados.append((mtime, {
            "job_id": status.parent.name,
            "formula": d.get("formula") or status.parent.name,
            "status": d.get("status"),
            "batch": batch_dir.name,
        }))
    encontrados.sort(key=lambda x: x[0], reverse=True)
    return [j for _, j in encontrados[:limite]]
