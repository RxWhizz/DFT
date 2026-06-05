"""Generador heurístico de candidatos ABX3.

Genera composiciones puras y mixtas en los sitios A, B y X de perovskitas
haluro. No inventa etiquetas — solo propone composiciones y descriptores
estructurales derivados de radios iónicos y electronegatividades publicadas.

Uso:
    from buho.generator.heuristic_generator import HeuristicGenerator
    gen = HeuristicGenerator("config/generator.yaml")
    candidates = gen.generate()
    gen.save_jsonl(candidates, "data/raw/generated_candidates.jsonl")
"""
from __future__ import annotations

import hashlib
import itertools
import json
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from ml_surrogate.features import (
    CHARGES,
    ELECTRONEG,
    IONIC_RADII,
    goldschmidt,
    lattice_est,
    octahedral_factor,
)

ORGANIC_A = {"MA", "FA"}


@dataclass
class GeneratedCandidate:
    """Un candidato ABX3 generado heurísticamente.

    Campos:
        formula             Fórmula legible, e.g. "Cs0.5FA0.5PbI3"
        reduced_formula     Forma canónica normalizada (ordenada + redondeada)
        composition_dict    Átomos por fórmula unitaria, e.g. {"Cs":0.5,"FA":0.5,"Pb":1,"I":3}
        A_site_species      Lista de cationes A, e.g. ["Cs","FA"]
        B_site_species      Lista de cationes B, e.g. ["Pb"]
        X_site_species      Lista de aniones X, e.g. ["I"]
        fractions           {"A":{sp:f}, "B":{sp:f}, "X":{sp:f}}
        candidate_id        SHA1 de reduced_formula (estable ante reordenamientos)
        generation_mode     "pure"|"A_mixed"|"B_mixed"|"X_mixed"|"multi_mixed"
        tolerance_t         Factor de tolerancia de Goldschmidt
        oct_factor          Factor octaédrico μ = r_B / r_X_eff
        a0_est_A            Parámetro de red estimado (Å)
        vol_est_A3          Volumen estimado por fórmula unitaria (Å³)
        is_organic_A        True si algún A-site es MA o FA
        metadata            Reproducibilidad: fecha, hostname, versión Python, config_hash
    """

    formula: str
    reduced_formula: str
    composition_dict: dict
    A_site_species: list
    B_site_species: list
    X_site_species: list
    fractions: dict
    candidate_id: str
    generation_mode: str
    tolerance_t: float
    oct_factor: float
    a0_est_A: float
    vol_est_A3: float
    is_organic_A: bool
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GeneratedCandidate":
        return cls(**d)


def _canonical_id(fractions: dict) -> str:
    """SHA1 estable de la composición canónica."""
    parts = []
    for site in ("A", "B", "X"):
        site_fracs = fractions.get(site, {})
        for sp in sorted(site_fracs):
            parts.append(f"{site}:{sp}:{round(site_fracs[sp], 3)}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _effective_r(species: list[str], fracs: dict[str, float], table: dict) -> float:
    return sum(fracs[sp] * table[sp] for sp in species)


def _reduced_formula(fractions: dict) -> str:
    parts = []
    for site in ("A", "B", "X"):
        for sp in sorted(fractions.get(site, {})):
            f = fractions[site][sp]
            parts.append(f"{sp}{f:.3g}" if abs(f - 1.0) > 1e-6 else sp)
    return "".join(parts)


def _build_formula(A_sp: list, B_sp: list, X_sp: list,
                   A_f: dict, B_f: dict, X_f: dict) -> str:
    def site_str(species, fracs):
        if len(species) == 1:
            return species[0]
        return "".join(f"{sp}{fracs[sp]:.2g}" for sp in sorted(species))

    return site_str(A_sp, A_f) + site_str(B_sp, B_f) + site_str(X_sp, X_f) + "3"


def _metadata(config_hash: str) -> dict:
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "hostname": platform.node(),
        "python_version": sys.version.split()[0],
        "config_hash": config_hash,
    }


class HeuristicGenerator:
    """Genera candidatos ABX3 puros y mixtos desde un archivo de configuración YAML.

    Parámetros
    ----------
    config_path : ruta al YAML de configuración (config/generator.yaml)
    random_seed : semilla para reproducibilidad en modos mixtos
    """

    def __init__(self, config_path: str | Path, random_seed: Optional[int] = None):
        cfg_path = Path(config_path)
        with open(cfg_path) as f:
            self._cfg = yaml.safe_load(f)
        self._config_hash = hashlib.sha1(cfg_path.read_bytes()).hexdigest()[:8]
        self._seed = random_seed if random_seed is not None else self._cfg.get("random_seed", 42)
        self._rng = np.random.RandomState(self._seed)

        cs = self._cfg["chemical_space"]
        self._A_sites: list[str] = cs["A_sites"]
        self._B_sites: list[str] = cs["B_sites"]
        self._X_sites: list[str] = cs["X_sites"]

        gen = self._cfg["generation"]
        self._fractions: list[float] = [float(f) for f in gen["fractions"]]
        self._modes: dict = gen.get("modes", {
            "pure": True, "A_mixed": True, "B_mixed": True,
            "X_mixed": True, "multi_mixed": False,
        })

    # ── Public API ──────────────────────────────────────────────────────────────

    def generate(self) -> list[GeneratedCandidate]:
        """Genera todos los candidatos configurados y elimina duplicados."""
        candidates: list[GeneratedCandidate] = []

        if self._modes.get("pure", True):
            candidates.extend(self._generate_pure())

        if self._modes.get("A_mixed", True):
            candidates.extend(self._generate_A_mixed())

        if self._modes.get("B_mixed", True):
            candidates.extend(self._generate_B_mixed())

        if self._modes.get("X_mixed", True):
            candidates.extend(self._generate_X_mixed())

        if self._modes.get("multi_mixed", False):
            candidates.extend(self._generate_multi_mixed())

        return self._deduplicate(candidates)

    @staticmethod
    def save_jsonl(candidates: list[GeneratedCandidate], path: str | Path) -> None:
        """Guarda candidatos en formato JSONL (un JSON por línea)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            for c in candidates:
                f.write(json.dumps(c.to_dict()) + "\n")

    @staticmethod
    def load_jsonl(path: str | Path) -> list[GeneratedCandidate]:
        """Carga candidatos desde JSONL."""
        candidates = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    candidates.append(GeneratedCandidate.from_dict(json.loads(line)))
        return candidates

    # ── Generation modes ────────────────────────────────────────────────────────

    def _generate_pure(self) -> list[GeneratedCandidate]:
        result = []
        for A, B, X in itertools.product(self._A_sites, self._B_sites, self._X_sites):
            c = self._make_candidate(
                A_sp=[A], B_sp=[B], X_sp=[X],
                A_f={A: 1.0}, B_f={B: 1.0}, X_f={X: 1.0},
                mode="pure",
            )
            if c is not None:
                result.append(c)
        return result

    def _generate_A_mixed(self) -> list[GeneratedCandidate]:
        result = []
        for (A1, A2), B, X in itertools.product(
            itertools.combinations(self._A_sites, 2),
            self._B_sites,
            self._X_sites,
        ):
            for f in self._fractions:
                if abs(f - 0.0) < 1e-9 or abs(f - 1.0) < 1e-9:
                    continue
                c = self._make_candidate(
                    A_sp=[A1, A2], B_sp=[B], X_sp=[X],
                    A_f={A1: f, A2: round(1.0 - f, 3)},
                    B_f={B: 1.0}, X_f={X: 1.0},
                    mode="A_mixed",
                )
                if c is not None:
                    result.append(c)
        return result

    def _generate_B_mixed(self) -> list[GeneratedCandidate]:
        result = []
        for A, (B1, B2), X in itertools.product(
            self._A_sites,
            itertools.combinations(self._B_sites, 2),
            self._X_sites,
        ):
            for f in self._fractions:
                if abs(f - 0.0) < 1e-9 or abs(f - 1.0) < 1e-9:
                    continue
                c = self._make_candidate(
                    A_sp=[A], B_sp=[B1, B2], X_sp=[X],
                    A_f={A: 1.0},
                    B_f={B1: f, B2: round(1.0 - f, 3)},
                    X_f={X: 1.0},
                    mode="B_mixed",
                )
                if c is not None:
                    result.append(c)
        return result

    def _generate_X_mixed(self) -> list[GeneratedCandidate]:
        result = []
        # 2-component X mixtures
        for A, B, (X1, X2) in itertools.product(
            self._A_sites,
            self._B_sites,
            itertools.combinations(self._X_sites, 2),
        ):
            for f in self._fractions:
                if abs(f - 0.0) < 1e-9 or abs(f - 1.0) < 1e-9:
                    continue
                c = self._make_candidate(
                    A_sp=[A], B_sp=[B], X_sp=[X1, X2],
                    A_f={A: 1.0}, B_f={B: 1.0},
                    X_f={X1: f, X2: round(1.0 - f, 3)},
                    mode="X_mixed",
                )
                if c is not None:
                    result.append(c)
        # 3-component X mixtures (I+Br+Cl) with discrete fractions
        if len(self._X_sites) >= 3:
            for A, B in itertools.product(self._A_sites, self._B_sites):
                for xI in self._fractions:
                    for xBr in self._fractions:
                        xCl = round(1.0 - xI - xBr, 3)
                        if xCl < 0.05 or xCl > 0.95:
                            continue
                        X_sp = [x for x, f in zip(
                            self._X_sites, [xI, xBr, xCl]) if f > 0.01]
                        X_f = {x: f for x, f in zip(
                            self._X_sites, [xI, xBr, xCl]) if f > 0.01}
                        if len(X_sp) < 3:
                            continue  # already covered by 2-component
                        c = self._make_candidate(
                            A_sp=[A], B_sp=[B], X_sp=X_sp,
                            A_f={A: 1.0}, B_f={B: 1.0}, X_f=X_f,
                            mode="X_mixed",
                        )
                        if c is not None:
                            result.append(c)
        return result

    def _generate_multi_mixed(self) -> list[GeneratedCandidate]:
        """A-site + X-site mixtos simultáneamente."""
        result = []
        for (A1, A2), B, (X1, X2) in itertools.product(
            itertools.combinations(self._A_sites, 2),
            self._B_sites,
            itertools.combinations(self._X_sites, 2),
        ):
            for fA, fX in itertools.product(self._fractions, self._fractions):
                if abs(fA - 0.0) < 1e-9 or abs(fA - 1.0) < 1e-9:
                    continue
                if abs(fX - 0.0) < 1e-9 or abs(fX - 1.0) < 1e-9:
                    continue
                c = self._make_candidate(
                    A_sp=[A1, A2], B_sp=[B], X_sp=[X1, X2],
                    A_f={A1: fA, A2: round(1.0 - fA, 3)},
                    B_f={B: 1.0},
                    X_f={X1: fX, X2: round(1.0 - fX, 3)},
                    mode="multi_mixed",
                )
                if c is not None:
                    result.append(c)
        return result

    # ── Core builder ────────────────────────────────────────────────────────────

    def _make_candidate(
        self,
        A_sp: list[str], B_sp: list[str], X_sp: list[str],
        A_f: dict[str, float], B_f: dict[str, float], X_f: dict[str, float],
        mode: str,
    ) -> Optional[GeneratedCandidate]:
        """Construye un candidato verificando carga y disponibilidad de datos."""
        # Verificar que todas las especies tienen datos
        for sp in A_sp + B_sp + X_sp:
            if sp not in IONIC_RADII or sp not in CHARGES:
                return None

        # Neutralidad de carga: sum(q_A * f_A) + sum(q_B * f_B) + 3*sum(q_X * f_X) = 0
        q_A_eff = sum(CHARGES[sp] * A_f[sp] for sp in A_sp)
        q_B_eff = sum(CHARGES[sp] * B_f[sp] for sp in B_sp)
        q_X_eff = sum(CHARGES[sp] * X_f[sp] for sp in X_sp)
        if abs(q_A_eff + q_B_eff + 3.0 * q_X_eff) > 0.05:
            return None

        # Radios efectivos
        r_A = _effective_r(A_sp, A_f, IONIC_RADII)
        r_B = _effective_r(B_sp, B_f, IONIC_RADII)
        r_X = _effective_r(X_sp, X_f, IONIC_RADII)

        t = goldschmidt(r_A, r_B, r_X)
        mu = octahedral_factor(r_B, r_X)
        a0 = lattice_est(r_B, r_X)
        vol = a0 ** 3

        fractions = {"A": dict(A_f), "B": dict(B_f), "X": dict(X_f)}
        cid = _canonical_id(fractions)
        red = _reduced_formula(fractions)
        formula = _build_formula(A_sp, B_sp, X_sp, A_f, B_f, X_f)

        comp = {}
        for sp, f in A_f.items():
            comp[sp] = comp.get(sp, 0.0) + f
        for sp, f in B_f.items():
            comp[sp] = comp.get(sp, 0.0) + f
        for sp, f in X_f.items():
            comp[sp] = comp.get(sp, 0.0) + 3.0 * f

        return GeneratedCandidate(
            formula=formula,
            reduced_formula=red,
            composition_dict=comp,
            A_site_species=list(A_sp),
            B_site_species=list(B_sp),
            X_site_species=list(X_sp),
            fractions=fractions,
            candidate_id=cid,
            generation_mode=mode,
            tolerance_t=round(t, 5),
            oct_factor=round(mu, 5),
            a0_est_A=round(a0, 4),
            vol_est_A3=round(vol, 3),
            is_organic_A=any(sp in ORGANIC_A for sp in A_sp),
            metadata=_metadata(self._config_hash),
        )

    @staticmethod
    def _deduplicate(candidates: list[GeneratedCandidate]) -> list[GeneratedCandidate]:
        seen: set[str] = set()
        unique = []
        for c in candidates:
            if c.candidate_id not in seen:
                seen.add(c.candidate_id)
                unique.append(c)
        return unique
