"""Filtros fisicoquímicos para candidatos ABX3 generados.

Aplica filtros en orden de costo computacional creciente:
  1. Validez de especies (datos disponibles)
  2. Neutralidad de carga
  3. Factor de tolerancia de Goldschmidt
  4. Factor octaédrico
  5. Volumen estimado
  6. Deduplicación por reduced_formula

Todos los rangos son configurables desde YAML.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from buho.generator.heuristic_generator import GeneratedCandidate


@dataclass
class FilterResult:
    """Resultado de aplicar el pipeline de filtros."""

    passed: list[GeneratedCandidate] = field(default_factory=list)
    rejected: list[tuple[GeneratedCandidate, str]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def n_passed(self) -> int:
        return len(self.passed)

    @property
    def n_rejected(self) -> int:
        return len(self.rejected)

    def summary(self) -> str:
        lines = [f"Passed: {self.n_passed}  Rejected: {self.n_rejected}"]
        for k, v in self.stats.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)


class PhysicalFilter:
    """Aplica filtros físicos a una lista de GeneratedCandidate.

    Parámetros
    ----------
    config : dict con sección "filters" del YAML (goldschmidt, octahedral, volume_A3)
    """

    def __init__(self, config: dict):
        f = config.get("filters", {})
        gold = f.get("goldschmidt", {})
        oct_ = f.get("octahedral", {})
        vol  = f.get("volume_A3", {})

        self.t_min: float = float(gold.get("min", 0.80))
        self.t_max: float = float(gold.get("max", 1.10))
        self.mu_min: float = float(oct_.get("min", 0.40))
        self.mu_max: float = float(oct_.get("max", 0.90))
        self.vol_min: float = float(vol.get("min", 50.0))
        self.vol_max: float = float(vol.get("max", 2000.0))

    # ── Pipeline ────────────────────────────────────────────────────────────────

    def apply(self, candidates: list[GeneratedCandidate]) -> FilterResult:
        """Aplica todos los filtros en orden; cuenta rechazos por etapa."""
        result = FilterResult()
        counts = {
            "invalid_species": 0,
            "charge_imbalance": 0,
            "goldschmidt": 0,
            "octahedral": 0,
            "volume": 0,
            "duplicate": 0,
        }

        seen_ids: set[str] = set()
        for c in candidates:
            ok, reason = self._check_species(c)
            if not ok:
                result.rejected.append((c, reason))
                counts["invalid_species"] += 1
                continue

            ok, reason = self._check_charge(c)
            if not ok:
                result.rejected.append((c, reason))
                counts["charge_imbalance"] += 1
                continue

            ok, reason = self._check_goldschmidt(c)
            if not ok:
                result.rejected.append((c, reason))
                counts["goldschmidt"] += 1
                continue

            ok, reason = self._check_octahedral(c)
            if not ok:
                result.rejected.append((c, reason))
                counts["octahedral"] += 1
                continue

            ok, reason = self._check_volume(c)
            if not ok:
                result.rejected.append((c, reason))
                counts["volume"] += 1
                continue

            if c.candidate_id in seen_ids:
                result.rejected.append((c, "duplicate"))
                counts["duplicate"] += 1
                continue

            seen_ids.add(c.candidate_id)
            result.passed.append(c)

        result.stats = counts
        result.stats["total_in"] = len(candidates)
        result.stats["total_passed"] = result.n_passed
        return result

    # ── Individual checks ───────────────────────────────────────────────────────

    def _check_species(self, c: GeneratedCandidate) -> tuple[bool, str]:
        from ml_surrogate.features import IONIC_RADII, CHARGES
        for sp in c.A_site_species + c.B_site_species + c.X_site_species:
            if sp not in IONIC_RADII:
                return False, f"radio iónico desconocido: {sp}"
            if sp not in CHARGES:
                return False, f"carga desconocida: {sp}"
        return True, ""

    def _check_charge(self, c: GeneratedCandidate) -> tuple[bool, str]:
        from ml_surrogate.features import CHARGES
        A_f = c.fractions.get("A", {})
        B_f = c.fractions.get("B", {})
        X_f = c.fractions.get("X", {})
        q = (sum(CHARGES[sp] * A_f.get(sp, 0) for sp in c.A_site_species)
           + sum(CHARGES[sp] * B_f.get(sp, 0) for sp in c.B_site_species)
           + 3.0 * sum(CHARGES[sp] * X_f.get(sp, 0) for sp in c.X_site_species))
        if abs(q) > 0.05:
            return False, f"carga neta={q:.3f}"
        return True, ""

    def _check_goldschmidt(self, c: GeneratedCandidate) -> tuple[bool, str]:
        t = c.tolerance_t
        if not (self.t_min <= t <= self.t_max):
            return False, f"t={t:.3f} fuera de [{self.t_min},{self.t_max}]"
        return True, ""

    def _check_octahedral(self, c: GeneratedCandidate) -> tuple[bool, str]:
        mu = c.oct_factor
        if not (self.mu_min <= mu <= self.mu_max):
            return False, f"μ={mu:.3f} fuera de [{self.mu_min},{self.mu_max}]"
        return True, ""

    def _check_volume(self, c: GeneratedCandidate) -> tuple[bool, str]:
        v = c.vol_est_A3
        if not (self.vol_min <= v <= self.vol_max):
            return False, f"vol={v:.1f} Å³ fuera de [{self.vol_min},{self.vol_max}]"
        return True, ""
