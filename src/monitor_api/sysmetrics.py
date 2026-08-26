"""Métricas de hardware del sistema: CPU, RAM, temperatura, GPU."""
from __future__ import annotations

from dataclasses import dataclass, field

import psutil


@dataclass
class SysMetrics:
    cpu_percent: float              # uso total promedio (%)
    cpu_per_core: list[float]       # uso por núcleo (%)
    ram_used_gb: float
    ram_total_gb: float
    ram_percent: float
    pkg_temps: list[float]          # temp de cada socket CPU (°C)
    core_temp_max: float            # núcleo más caliente (°C)
    nvme_temp: float | None         # temp NVMe Composite (°C)
    gpu_temps: list[float]          # temp bordes GPU AMD (°C)


def collect() -> SysMetrics:
    cpu_per = psutil.cpu_percent(interval=0.4, percpu=True)
    cpu_total = sum(cpu_per) / len(cpu_per) if cpu_per else 0.0

    vm = psutil.virtual_memory()
    ram_used  = round(vm.used  / 1e9, 1)
    ram_total = round(vm.total / 1e9, 1)

    # En Windows psutil ni siquiera define esta función: sin la guarda,
    # /api/system daba 500 y tumbaba la tira de hardware de la vista Live.
    leer_sensores = getattr(psutil, "sensors_temperatures", None)
    try:
        temps = leer_sensores() if leer_sensores else {}
    except (AttributeError, OSError, RuntimeError):
        temps = {}

    # CPU packages y núcleos
    pkg_temps: list[float] = []
    core_max = 0.0
    for entry in temps.get("coretemp", []):
        if entry.label.startswith("Package id"):
            pkg_temps.append(entry.current)
        elif entry.label.startswith("Core"):
            if entry.current > core_max:
                core_max = entry.current

    # NVMe
    nvme_temp: float | None = None
    for entry in temps.get("nvme", []):
        if entry.label == "Composite":
            nvme_temp = entry.current
            break

    # GPU AMD (edge = diodo de borde, más representativo)
    gpu_temps = [e.current for e in temps.get("amdgpu", []) if e.label == "edge"]

    return SysMetrics(
        cpu_percent=round(cpu_total, 1),
        cpu_per_core=[round(x, 1) for x in cpu_per],
        ram_used_gb=ram_used,
        ram_total_gb=ram_total,
        ram_percent=round(vm.percent, 1),
        pkg_temps=[round(t, 1) for t in pkg_temps],
        core_temp_max=round(core_max, 1),
        nvme_temp=round(nvme_temp, 1) if nvme_temp is not None else None,
        gpu_temps=[round(t, 1) for t in gpu_temps],
    )


def format_telegram(m: SysMetrics) -> str:
    """Genera bloque de texto HTML para incluir en mensaje Telegram."""
    pkg_str = "  ".join(f"PKG{i}: {t}°C" for i, t in enumerate(m.pkg_temps))
    gpu_str = "  ".join(f"GPU{i}: {t}°C" for i, t in enumerate(m.gpu_temps))
    nvme_str = f"  NVMe: {m.nvme_temp}°C" if m.nvme_temp is not None else ""

    lines = [
        "🖥️ <b>Sistema</b>",
        f"CPU: <b>{m.cpu_percent:.0f}%</b>   RAM: <b>{m.ram_used_gb}/{m.ram_total_gb} GB</b> ({m.ram_percent:.0f}%)",
    ]
    if pkg_str:
        lines.append(f"🌡 {pkg_str}   núcleo max: {m.core_temp_max}°C{nvme_str}")
    if gpu_str:
        lines.append(f"🎮 {gpu_str}")
    return "\n".join(lines)
