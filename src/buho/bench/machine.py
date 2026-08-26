"""Detección de la máquina y planificación del barrido slots×cores.

Los scripts de benchmark llevaban los splits escritos a mano —`SPLITS_44` y
`SPLITS_88`— porque se escribieron para un Xeon concreto de 44 núcleos físicos
y 88 lógicos. En otra máquina no miden nada útil. Aquí se derivan de la
topología real.
"""
from __future__ import annotations

import hashlib
import platform
import re
import socket
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import psutil


@dataclass(frozen=True)
class Machine:
    """Lo que hace falta saber para planificar un barrido."""

    hostname: str
    cpu_model: str
    physical_cores: int
    logical_cores: int
    sockets: int
    numa_nodes: int
    ram_total_gb: float

    @property
    def fingerprint(self) -> str:
        """Identifica el *hardware*, no la sesión.

        No incluye el hostname: la misma máquina renombrada sigue teniendo el
        mismo rendimiento, y dos nodos idénticos de un clúster comparten
        calibración legítimamente.
        """
        crudo = (f"{self.cpu_model}|{self.physical_cores}|{self.logical_cores}"
                 f"|{self.sockets}|{round(self.ram_total_gb)}")
        return hashlib.sha256(crudo.encode()).hexdigest()[:12]

    @property
    def hyperthreading(self) -> bool:
        return self.logical_cores > self.physical_cores

    def as_dict(self) -> dict:
        d = asdict(self)
        d["fingerprint"] = self.fingerprint
        return d

    def describe(self) -> str:
        ht = f" ({self.logical_cores} lógicos)" if self.hyperthreading else ""
        numa = f", {self.numa_nodes} nodos NUMA" if self.numa_nodes > 1 else ""
        return (f"{self.cpu_model} — {self.physical_cores} núcleos físicos{ht}"
                f"{numa}, {self.ram_total_gb:.0f} GB RAM")


def _lscpu() -> dict[str, str]:
    """Campos de `lscpu`, o vacío si no está (macOS, Windows, contenedor pelado)."""
    try:
        salida = subprocess.run(["lscpu"], capture_output=True, text=True,
                                timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    campos = {}
    for linea in salida.splitlines():
        if ":" in linea:
            clave, valor = linea.split(":", 1)
            campos[clave.strip().lower()] = valor.strip()
    return campos


def _modelo_cpu(campos: dict[str, str]) -> str:
    if campos.get("model name"):
        return campos["model name"]
    try:
        texto = Path("/proc/cpuinfo").read_text(errors="replace")
        m = re.search(r"^model name\s*:\s*(.+)$", texto, re.M)
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "desconocida"


def _entero(campos: dict[str, str], clave: str, defecto: int) -> int:
    try:
        return int(campos[clave])
    except (KeyError, ValueError):
        return defecto


def detect() -> Machine:
    campos = _lscpu()
    fisicos = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1
    logicos = psutil.cpu_count(logical=True) or fisicos
    return Machine(
        hostname=socket.gethostname(),
        cpu_model=_modelo_cpu(campos),
        physical_cores=fisicos,
        logical_cores=logicos,
        sockets=_entero(campos, "socket(s)", 1),
        numa_nodes=_entero(campos, "numa node(s)", 1),
        ram_total_gb=round(psutil.virtual_memory().total / 2**30, 1),
    )


# ── Planificación del barrido ────────────────────────────────────────────────

@dataclass(frozen=True)
class Split:
    """Un reparto: `slots` jobs concurrentes de `cores` núcleos MPI cada uno."""

    slots: int
    cores: int

    @property
    def total_cores(self) -> int:
        return self.slots * self.cores

    def __str__(self) -> str:
        return f"{self.slots}x{self.cores}"


def budgets_for(machine: Machine, *, incluir_hyperthreading: bool = True) -> list[int]:
    """Presupuestos de núcleos a barrer.

    El físico siempre; el lógico solo si hay hyperthreading, porque en cargas
    limitadas por ancho de banda de memoria —como el SCF de GPAW— suele restar
    en vez de sumar, y merece medirse en lugar de suponerse.
    """
    presupuestos = [machine.physical_cores]
    if incluir_hyperthreading and machine.hyperthreading:
        presupuestos.append(machine.logical_cores)
    return presupuestos


def splits_for(budget: int, *, max_splits: int = 9, cobertura_min: float = 0.85) -> list[Split]:
    """Repartos a probar para un presupuesto de núcleos.

    Se prefieren los **divisores exactos** —usan la máquina entera y son los que
    uno escribiría a mano—, y solo si no llegan a `max_splits` se rellena con
    casi-divisores. Se descarta lo que dejaría ocioso más del 15 %: medir un
    reparto que no usa la máquina no responde a la pregunta.
    """
    if budget < 1:
        return []

    exactos = [Split(s, budget // s) for s in range(1, budget + 1) if budget % s == 0]

    if len(exactos) < max_splits:
        # Rellenar con casi-divisores, los de mejor cobertura primero.
        # Un casi-divisor que repite el `cores` de un exacto mide lo mismo con
        # un slot menos: 43x1 no añade nada sobre 44x1.
        ocupados = {sp.slots for sp in exactos}
        cubiertos = {sp.cores for sp in exactos}
        casi = [
            Split(s, budget // s)
            for s in range(1, budget + 1)
            if s not in ocupados and budget // s >= 1
            and (budget // s) not in cubiertos
            and s * (budget // s) >= budget * cobertura_min
        ]
        casi.sort(key=lambda sp: -sp.total_cores)
        candidatos = sorted(exactos + casi[: max_splits - len(exactos)],
                            key=lambda sp: sp.slots)
    else:
        candidatos = exactos

    if max_splits <= 1:
        # Un solo reparto: el que más núcleos usa por job, que es el punto de
        # partida natural para una prueba rápida.
        return candidatos[:1]

    if len(candidatos) <= max_splits:
        return candidatos

    # Muestreo logarítmico sobre el número de slots: interesan los extremos —un
    # job usando todo, y un job por núcleo— y unos pocos intermedios.
    import math

    elegidos: dict[int, Split] = {}
    ultimo = len(candidatos) - 1
    for i in range(max_splits):
        frac = i / (max_splits - 1)
        idx = min(round(math.exp(frac * math.log(len(candidatos)))) - 1, ultimo)
        elegidos.setdefault(max(0, idx), candidatos[max(0, idx)])
    elegidos.setdefault(0, candidatos[0])
    elegidos.setdefault(ultimo, candidatos[ultimo])
    return sorted(elegidos.values(), key=lambda sp: sp.slots)


def ram_limit_gb(machine: Machine, *, margen: float = 0.85) -> float:
    """Techo de RAM antes de abortar un reparto.

    Estaba fijo en 52 GB, ajustado a mano a una máquina de 63. Se deja un 15 %
    para el sistema: un OOM no solo pierde la medición, se lleva por delante lo
    que hubiera corriendo.
    """
    return round(machine.ram_total_gb * margen, 1)
