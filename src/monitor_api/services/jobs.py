"""Acceso a los artefactos de un job: logs, trazas SCF y metadatos."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Los job_id del pipeline son hashes hex, pero algunos runners usan nombres
# legibles. Se admite un conjunto conservador y se prohíbe cualquier separador:
# el id llega por la URL y `runs_dir / job_id` con "../.." saldría del árbol.
_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# Nombres de log conocidos, en orden de preferencia.
_LOG_NAMES = ("r2scan.txt", "relax.txt", "scf.txt", "gpaw.txt", "out.txt")

MAX_TAIL_LINES = 2000


class UnsafeJobIdError(ValueError):
    """El identificador no es utilizable como nombre de directorio."""


_BATCH_DIR_RE = re.compile(r"^batch_\d+$")


def resolve_job_dir(runs_dir: Path, job_id: str) -> Path | None:
    """Directorio del job, o None si no existe. Lanza UnsafeJobIdError si es hostil."""
    if not _SAFE_JOB_ID.match(job_id) or job_id in {".", ".."}:
        raise UnsafeJobIdError(job_id)

    candidate = (runs_dir / job_id).resolve()
    root = runs_dir.resolve()
    # Cinturón y tirantes: aunque el regex ya excluye separadores, se confirma
    # que el resultado sigue dentro del árbol de runs.
    if root != candidate and root not in candidate.parents:
        raise UnsafeJobIdError(job_id)
    if candidate.is_dir():
        return candidate

    # `runs_dir` se fija al arrancar el motor. En cuanto el runner trabaja sobre
    # otro lote, sus trabajos existen pero no se resuelven aquí: el detalle y el
    # log daban 404 para todo lo que se estuviera calculando. Se buscan también
    # en los lotes hermanos, con la misma comprobación de contención.
    if _BATCH_DIR_RE.match(runs_dir.name):
        raiz = runs_dir.parent.resolve()
        for hermano in sorted(raiz.glob("batch_*"), key=lambda d: d.stat().st_mtime,
                              reverse=True):
            otro = (hermano / job_id).resolve()
            if raiz != otro and raiz not in otro.parents:
                continue
            if otro.is_dir():
                return otro
    return None


@dataclass(frozen=True)
class LogRef:
    label: str
    relative_path: str
    size_bytes: int
    mtime: float


def _read_status(job_dir: Path) -> dict[str, Any]:
    try:
        return json.loads((job_dir / "status.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def discover_logs(job_dir: Path) -> list[LogRef]:
    """Logs del job, etiquetados por el sub-cálculo al que pertenecen.

    El cliente elige por `label` de esta lista; nunca se construye una ruta a
    partir de texto libre.
    """
    seen: set[Path] = set()
    refs: list[LogRef] = []

    def add(path: Path, label: str) -> None:
        if path in seen or not path.is_file():
            return
        seen.add(path)
        st = path.stat()
        refs.append(
            LogRef(
                label=label,
                relative_path=str(path.relative_to(job_dir)),
                size_bytes=st.st_size,
                mtime=st.st_mtime,
            )
        )

    # 1. Etiquetas declaradas en status.json (Fase 2A).
    for entry in _read_status(job_dir).get("labels_expected") or []:
        rel = entry.get("relative_dir")
        if not rel:
            continue
        for name in _LOG_NAMES:
            add(job_dir / rel / name, str(entry.get("label") or rel))

    # 2. Convenciones conocidas del pipeline.
    for path in sorted(job_dir.glob("u_scan/*/r2scan.txt")):
        add(path, path.parent.name)
    for path in sorted(job_dir.glob("*/r2scan.txt")):
        add(path, path.parent.name)

    # 3. Cualquier .txt/.log suelto en la raíz del job.
    for path in sorted(job_dir.glob("*.txt")) + sorted(job_dir.glob("*.log")):
        add(path, path.stem)

    return refs


def read_log_tail(job_dir: Path, label: str | None, tail: int) -> dict[str, Any]:
    """Últimas `tail` líneas del log elegido."""
    logs = discover_logs(job_dir)
    if not logs:
        return {"label": None, "lines": [], "total_lines": 0, "available": []}

    ref = next((r for r in logs if r.label == label), logs[0]) if label else logs[0]
    path = job_dir / ref.relative_path

    tail = max(1, min(tail, MAX_TAIL_LINES))
    try:
        # Los logs de GPAW llegan a decenas de MB; se leen por líneas y se
        # conserva solo la cola en memoria.
        from collections import deque

        with path.open("r", encoding="utf-8", errors="replace") as fh:
            buffer: deque[str] = deque(maxlen=tail)
            total = 0
            for line in fh:
                buffer.append(line.rstrip("\n"))
                total += 1
    except OSError as exc:
        return {"label": ref.label, "lines": [f"<no se pudo leer: {exc}>"],
                "total_lines": 0, "available": [r.label for r in logs]}

    return {
        "label": ref.label,
        "path": ref.relative_path,
        "lines": list(buffer),
        "total_lines": total,
        "available": [r.label for r in logs],
    }


def _scf_rate_s(points: list[dict]) -> float | None:
    """Segundos por iteración a partir de las últimas marcas de reloj."""
    if len(points) < 2:
        return None

    def secs(clock: str) -> int:
        h, m, s = (int(x) for x in clock.split(":"))
        return h * 3600 + m * 60 + s

    # Pares consecutivos de las últimas iteraciones. El emparejamiento
    # `zip(points[-6:-1], points[-5:])` que había en router.py se desalinea
    # cuando hay menos de 6 puntos: compara cada punto consigo mismo, todos los
    # deltas salen 0 y el ritmo quedaba en None justo en los jobs cortos.
    recientes = points[-6:]
    deltas = []
    for prev, cur in zip(recientes, recientes[1:]):
        try:
            d = secs(cur["clock"]) - secs(prev["clock"])
        except (KeyError, ValueError):
            continue
        if d < 0:
            d += 86400  # cruce de medianoche
        if 0 < d < 3600:
            deltas.append(d)
    return round(sum(deltas) / len(deltas), 1) if deltas else None


def job_traces(job_dir: Path) -> dict[str, Any]:
    """Series SCF por etiqueta más el resumen de frames de Fase 2A."""
    from buho.phase2_force.self_heal import parse_scf_points

    labels = []
    for ref in discover_logs(job_dir):
        points = parse_scf_points(job_dir / ref.relative_path)
        if not points:
            continue
        labels.append(
            {
                "label": ref.label,
                "path": ref.relative_path,
                "n_iters": len(points),
                "rate_s_per_iter": _scf_rate_s(points),
                "points": points,
            }
        )

    return {"labels": labels, "frames": job_frames(job_dir)}


def job_frames(job_dir: Path) -> list[dict[str, Any]]:
    """Frames rattled etiquetados con DFT (energía, fuerza máxima, tiempo)."""
    frames: list[dict[str, Any]] = []
    for path in sorted(job_dir.glob("*/frame_*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        frames.append(
            {
                "label": path.parent.name,
                "config_index": data.get("config_index"),
                "status": data.get("status"),
                "energy_ev": data.get("energy_eV"),
                "energy_per_atom_ev": data.get("energy_per_atom_eV"),
                "forces_max_eva": data.get("forces_max_eVA"),
                "n_atoms": data.get("n_atoms"),
                "kpts": data.get("kpts"),
                "elapsed_s": data.get("elapsed_s"),
                "finished_at": data.get("finished_at"),
            }
        )
    frames.sort(key=lambda f: (f["label"], f["config_index"] if f["config_index"] is not None else -1))
    return frames


def job_metadata(job_dir: Path) -> dict[str, Any]:
    """metadata.json y status.json tal cual, más qué archivos existen."""
    def load(name: str) -> dict[str, Any]:
        try:
            return json.loads((job_dir / name).read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    artefactos = sorted(
        str(p.relative_to(job_dir))
        for p in job_dir.rglob("*")
        if p.is_file() and p.suffix in {".cif", ".extxyz", ".json", ".txt", ".py", ".yaml"}
    )
    return {
        "metadata": load("metadata.json"),
        "status": load("status.json"),
        "artifacts": artefactos[:200],
    }
