"""Historial circular de métricas de hardware.

`sysmetrics.collect()` da una foto instantánea, que basta para un mensaje de
Telegram pero no para dibujar una sparkline. Aquí se muestrea en segundo plano
y se guarda una ventana reciente en memoria.

El muestreo va a un hilo porque `psutil.cpu_percent(interval=...)` bloquea, y
bloquear el event loop cada pocos segundos degradaría los WebSocket.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import asdict, dataclass

from .sysmetrics import collect

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 10
# 360 muestras × 10 s = 1 hora de historial.
DEFAULT_MAXLEN = 360


@dataclass(frozen=True)
class MetricsSample:
    t: float
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    core_temp_max: float
    gpu_temp_max: float | None


class MetricsHistory:
    def __init__(self, maxlen: int = DEFAULT_MAXLEN):
        self._buf: deque[MetricsSample] = deque(maxlen=maxlen)

    def __len__(self) -> int:
        return len(self._buf)

    def samples(self, since_sec: float | None = None) -> list[dict]:
        """Muestras como dicts, opcionalmente solo las de los últimos N segundos."""
        items = list(self._buf)
        if since_sec is not None:
            cutoff = time.time() - since_sec
            items = [s for s in items if s.t >= cutoff]
        return [asdict(s) for s in items]

    def sample_now(self) -> MetricsSample:
        m = collect()
        sample = MetricsSample(
            t=time.time(),
            cpu_percent=round(m.cpu_percent, 1),
            ram_percent=round(m.ram_percent, 1),
            ram_used_gb=round(m.ram_used_gb, 1),
            core_temp_max=round(m.core_temp_max, 1),
            gpu_temp_max=round(max(m.gpu_temps), 1) if m.gpu_temps else None,
        )
        self._buf.append(sample)
        return sample

    async def run_forever(self, interval: int = DEFAULT_INTERVAL_SEC) -> None:
        log.info("Muestreo de métricas cada %ss (ventana de %d muestras)",
                 interval, self._buf.maxlen)
        while True:
            try:
                await asyncio.to_thread(self.sample_now)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("No se pudo muestrear el hardware: %s", exc)
            await asyncio.sleep(interval)
