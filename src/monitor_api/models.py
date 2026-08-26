from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

JobStatusLiteral = Literal[
    "pending", "running", "converged", "partial", "failed", "stalled", "oscillating", "stopped",
    # Terminal escrito por el pipeline de Fase 2A y reconocido por
    # scripts/phase2_mace_cycle.py (TERMINAL). Faltaba aquí, así que
    # snapshot_job() lanzaba ValidationError y el poller descartaba en silencio
    # esos jobs: no aparecían ni en la API ni en los reportes de Telegram.
    "skipped_duplicate",
    "unknown",
]


class JobStatus(BaseModel):
    job_id: str
    formula: str
    status: JobStatusLiteral
    pid: Optional[int] = None
    start_time: Optional[str] = None
    elapsed_min: Optional[float] = None
    mpi_cores: Optional[int] = None


class PingResponse(BaseModel):
    job_id: str
    alive: bool
    current_step: Optional[int] = None       # SCF iter o FIRE step
    step_type: Optional[str] = None          # "FIRE" | "SCF"
    energy_ev: Optional[float] = None
    fmax_ev_ang: Optional[float] = None
    memory_rss_mb: Optional[int] = None
    t_iter_s: Optional[float] = None
    eta_min: Optional[float] = None
    log_last_line: Optional[str] = None
    status: JobStatusLiteral = "unknown"


class StatsResponse(JobStatus):
    energy_history: list[float] = []
    fmax_history: list[float] = []
    scf_iter_history: list[int] = []
    n_fire_steps: int = 0
    n_scf_iters: int = 0
    is_oscillating: bool = False
    stall_minutes: Optional[float] = None
    final_energy_ev: Optional[float] = None


class SummaryResponse(BaseModel):
    n_pending: int
    n_running: int
    n_converged: int
    n_failed: int
    n_stalled: int
    n_oscillating: int
    n_skipped_duplicate: int = 0
    total: int
    convergence_rate: Optional[float] = None  # converged / (converged + failed)


class WsEvent(BaseModel):
    job_id: str
    event: Literal[
        "STARTED", "CONVERGED", "FAILED", "STOPPED", "STALLED", "OSCILLATING", "PING"
    ]
    timestamp: str
    data: dict = {}
