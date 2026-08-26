"""Calibración de rendimiento por máquina.

El barrido medía el reparto óptimo y escribía `reports/sweep_benchmark.json`,
que **no leía nadie**: el informe de rendimiento consume un `.log` distinto. La
medición costaba horas y moría ahí, mientras `runner_slots` y `runner_cores`
seguían puestos a mano en la configuración del monitor.

Aquí se guarda indexada por huella de hardware, de modo que:

* cambiar de máquina no invalida la calibración de la anterior;
* dos nodos idénticos de un clúster comparten la suya;
* el monitor puede comparar lo que tiene configurado con lo que se midió.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .machine import Machine, Split, detect

VERSION_ESQUEMA = 1


def calibration_path(data_root: Path | str | None = None) -> Path:
    """Dónde vive el archivo de calibración."""
    if data_root is None:
        entorno = os.environ.get("DFT_DATA_ROOT")
        data_root = Path(entorno) if entorno else Path.cwd()
    return Path(data_root) / "data" / "bench" / "calibration.json"


@dataclass(frozen=True)
class Calibration:
    """Lo que el barrido averiguó sobre una máquina."""

    fingerprint: str
    machine: dict[str, Any]
    measured_at: str
    best: Split
    budget: int
    throughput: float
    peak_ram_gb: float
    results: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": VERSION_ESQUEMA,
            "fingerprint": self.fingerprint,
            "machine": self.machine,
            "measured_at": self.measured_at,
            "best": {"slots": self.best.slots, "cores": self.best.cores},
            "budget": self.budget,
            "throughput": self.throughput,
            "peak_ram_gb": self.peak_ram_gb,
            "results": self.results,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Calibration":
        mejor = d.get("best") or {}
        return cls(
            fingerprint=d["fingerprint"],
            machine=d.get("machine", {}),
            measured_at=d.get("measured_at", ""),
            best=Split(int(mejor.get("slots", 1)), int(mejor.get("cores", 1))),
            budget=int(d.get("budget", 0)),
            throughput=float(d.get("throughput", 0.0)),
            peak_ram_gb=float(d.get("peak_ram_gb", 0.0)),
            results=list(d.get("results", [])),
        )


def _leer_todo(ruta: Path) -> dict[str, Any]:
    if not ruta.is_file():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def save(cal: Calibration, data_root: Path | str | None = None) -> Path:
    """Guarda la calibración sin pisar la de otras máquinas."""
    ruta = calibration_path(data_root)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    todo = _leer_todo(ruta)
    todo[cal.fingerprint] = cal.as_dict()
    # Escritura atómica: un barrido dura horas y perder el archivo por un corte
    # a mitad de `write_text` sería especialmente cruel.
    tmp = ruta.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(todo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(ruta)
    return ruta


def load(machine: Machine | None = None,
         data_root: Path | str | None = None) -> Calibration | None:
    """Calibración de esta máquina, o None si nunca se midió."""
    machine = machine or detect()
    entrada = _leer_todo(calibration_path(data_root)).get(machine.fingerprint)
    if not entrada:
        return None
    try:
        return Calibration.from_dict(entrada)
    except (KeyError, TypeError, ValueError):
        return None


def recommended(machine: Machine | None = None,
                data_root: Path | str | None = None) -> Split | None:
    """El reparto medido como óptimo, si lo hay."""
    cal = load(machine, data_root)
    return cal.best if cal else None


def build(machine: Machine, budget: int, resultados: list[dict[str, Any]]) -> Calibration | None:
    """Construye la calibración a partir de los resultados de un barrido.

    Solo cuentan los repartos donde **todos** los slots terminaron: uno que
    perdió jobs por OOM puede exhibir un throughput alto y engañoso.
    """
    validos = [r for r in resultados
               if r.get("throughput") and r.get("n_ok") == r.get("slots")]
    if not validos:
        return None
    mejor = max(validos, key=lambda r: r["throughput"])
    return Calibration(
        fingerprint=machine.fingerprint,
        machine=machine.as_dict(),
        measured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        best=Split(int(mejor["slots"]), int(mejor["cores"])),
        budget=budget,
        throughput=float(mejor["throughput"]),
        peak_ram_gb=float(mejor.get("peak_ram_gb", 0.0)),
        results=resultados,
    )
