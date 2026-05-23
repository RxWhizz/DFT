"""Kinetic Monte Carlo (BKL algorithm) para defect/ion evolution en CsPbI₃."""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Physical constants
_KB_EV = 8.617333e-5      # Boltzmann constant [eV/K]
_Q_C   = 1.602e-19

# Attempt frequency ν₀ [Hz] - default
_DEFAULT_NU0_HZ = 1e12


@dataclass
class KMCEvent:
    """A único lattice event (defect hop, capture, generación, recombination)."""
    name: str
    rate_Hz: float
    barrier_eV: float
    defect_type: str
    event_type: str


@dataclass
class KMCSnapshot:
    """State kMC lattice en dado time."""
    time_s: float
    n_events: int
    defect_counts: dict[str, int]
    recombination_events: int
    hop_events: int
    capture_events: int


@dataclass
class KMCResult:
    """Output kMC simulation ejecuta."""

    temperature_K: float
    total_time_s: float
    n_steps: int
    snapshots: list[KMCSnapshot]
    mean_defect_counts: dict[str, float]
    total_recombinations: int
    total_hops: int
    photostability_label: str
    flags: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"kMC T={self.temperature_K}K t={self.total_time_s:.1e}s "
            f"steps={self.n_steps} {self.photostability_label} "
            f"recomb={self.total_recombinations}"
        )


class KMCLattice:
    """Minimal kMC lattice para ionic defect migration en CsPbI₃."""

    def __init__(
        self,
        n_sites: int,
        events: list[KMCEvent],
        temperature_K: float,
        generation_rate_cm3s: float = 0.0,
        nu0_Hz: float = _DEFAULT_NU0_HZ,
    ) -> None:
        self.n_sites = n_sites
        self.temperature_K = temperature_K
        self.generation_rate_cm3s = generation_rate_cm3s
        self.nu0_Hz = nu0_Hz

        # Construye event list con Arrhenius rates
        self.events: list[KMCEvent] = []
        for ev in events:
            rate = nu0_Hz * math.exp(-ev.barrier_eV / (_KB_EV * temperature_K))
            self.events.append(KMCEvent(
                name=ev.name, rate_Hz=rate,
                barrier_eV=ev.barrier_eV,
                defect_type=ev.defect_type,
                event_type=ev.event_type,
            ))

        # Add photogeneration event si rate > 0
        if generation_rate_cm3s > 0.0:
            self.events.append(KMCEvent(
                name="photogeneration",
                rate_Hz=generation_rate_cm3s,
                barrier_eV=0.0,
                defect_type="electron-hole",
                event_type="generation",
            ))

        # Defect population counts
        self.defect_counts: dict[str, int] = {
            ev.defect_type: 0 for ev in self.events if ev.event_type == "hop"
        }
        # Seed initial population
        for key in self.defect_counts:
            self.defect_counts[key] = 1

        # Counters
        self.recombination_events = 0
        self.hop_events = 0
        self.capture_events = 0
        self.time_s = 0.0

    @classmethod
    def from_atoms(
        cls,
        atoms,
        barriers: dict[str, float],
        temperature_K: float = 300.0,
        generation_rate_cm3s: float = 0.0,
        nu0_Hz: float = _DEFAULT_NU0_HZ,
    ) -> "KMCLattice":
        """Construye KMCLattice desde ASE Atoms y dict barrier heights."""
        events = []
        for name, barrier_eV in barriers.items():
            parts = name.split("_")
            defect_type = "_".join(parts[:2]) if len(parts) >= 2 else name
            event_type  = parts[-1] if parts[-1] in ("hop", "capture", "recombination") else "hop"
            events.append(KMCEvent(
                name=name,
                rate_Hz=0.0,
                barrier_eV=barrier_eV,
                defect_type=defect_type,
                event_type=event_type,
            ))
        return cls(
            n_sites=len(atoms),
            events=events,
            temperature_K=temperature_K,
            generation_rate_cm3s=generation_rate_cm3s,
            nu0_Hz=nu0_Hz,
        )

    def _total_rate(self) -> float:
        return sum(ev.rate_Hz for ev in self.events)

    def _select_event(self, K: float) -> KMCEvent:
        """Select event j proportional k_j / K (cumsum método)."""
        u = random.random() * K
        cumsum = 0.0
        for ev in self.events:
            cumsum += ev.rate_Hz
            if cumsum >= u:
                return ev
        return self.events[-1]

    def step(self) -> KMCEvent:
        """Advance kMC by one event."""
        K = self._total_rate()
        if K < 1e-100:
            self.time_s += 1e-6
            return self.events[0]

        # Time advance (BKL)
        u1 = max(random.random(), 1e-15)
        self.time_s += -math.log(u1) / K

        ev = self._select_event(K)

        if ev.event_type == "hop":
            self.hop_events += 1
            # Hop
        elif ev.event_type == "capture":
            self.capture_events += 1
            # Capture
            if self.defect_counts.get("electron-hole", 0) > 0:
                self.defect_counts["electron-hole"] = (
                    self.defect_counts.get("electron-hole", 0) - 1
                )
                self.recombination_events += 1
        elif ev.event_type == "generation":
            self.defect_counts["electron-hole"] = (
                self.defect_counts.get("electron-hole", 0) + 1
            )

        return ev


def run_kmc(
    lattice: KMCLattice,
    total_time_s: float = 1e-6,
    max_steps: int = 1_000_000,
    snapshot_interval: int = 1000,
    seed: Optional[int] = 42,
) -> KMCResult:
    """Ejecuta BKL kinetic Monte Carlo until total_time_s o max_steps."""
    if seed is not None:
        random.seed(seed)

    snapshots: list[KMCSnapshot] = []
    step_count = 0
    flags: list[str] = []

    while lattice.time_s < total_time_s and step_count < max_steps:
        lattice.step()
        step_count += 1

        if step_count % snapshot_interval == 0:
            snapshots.append(KMCSnapshot(
                time_s=lattice.time_s,
                n_events=step_count,
                defect_counts=dict(lattice.defect_counts),
                recombination_events=lattice.recombination_events,
                hop_events=lattice.hop_events,
                capture_events=lattice.capture_events,
            ))

    if step_count >= max_steps:
        flags.append(f"MAX_STEPS_REACHED:{max_steps}")

    # Time-averaged defect counts desde snapshots
    mean_counts: dict[str, float] = {}
    if snapshots:
        for key in snapshots[0].defect_counts:
            mean_counts[key] = float(np.mean([s.defect_counts.get(key, 0) for s in snapshots]))

    # Photostability label
    total_hops = lattice.hop_events
    total_recomb = lattice.recombination_events
    if total_hops == 0:
        label = "stable"
    elif total_recomb > total_hops * 0.5:
        label = "unstable"
    elif total_hops > 100:
        label = "degrading"
    else:
        label = "stable"

    result = KMCResult(
        temperature_K=lattice.temperature_K,
        total_time_s=lattice.time_s,
        n_steps=step_count,
        snapshots=snapshots,
        mean_defect_counts=mean_counts,
        total_recombinations=total_recomb,
        total_hops=total_hops,
        photostability_label=label,
        flags=flags,
    )
    logger.info("%s", result.summary)
    return result


def save_kmc_result(result: KMCResult, work_dir: Path) -> None:
    """Persist kMC resultado as text resumen y numpy time-series."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f"temperature_K = {result.temperature_K}",
        f"total_time_s = {result.total_time_s:.3e}",
        f"n_steps = {result.n_steps}",
        f"photostability = {result.photostability_label}",
        f"total_hops = {result.total_hops}",
        f"total_recombinations = {result.total_recombinations}",
        f"mean_defect_counts = {result.mean_defect_counts}",
        f"flags = {result.flags}",
    ]
    (work_dir / "kmc_summary.txt").write_text("\n".join(lines))

    if result.snapshots:
        times = np.array([s.time_s for s in result.snapshots])
        hops  = np.array([s.hop_events for s in result.snapshots])
        recomb = np.array([s.recombination_events for s in result.snapshots])
        np.save(str(work_dir / "kmc_times.npy"), times)
        np.save(str(work_dir / "kmc_hops.npy"), hops)
        np.save(str(work_dir / "kmc_recombinations.npy"), recomb)

    logger.info("kMC result saved to %s", work_dir)
