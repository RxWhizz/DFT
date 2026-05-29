"""Validacion y generacion simple de candidatos ABX3."""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from math import sqrt
from typing import Iterable


DEFAULT_A_SITE = ("Cs", "Rb", "K", "MA", "FA")
DEFAULT_B_SITE = ("Pb", "Sn", "Ge")
DEFAULT_X_SITE = ("I", "Br", "Cl")

_SITE_PATTERN = re.compile(r"^[A-Z][a-z]?$|^(MA|FA)$")
_SQRT2 = sqrt(2.0)


@dataclass(frozen=True)
class ABX3Candidate:
    """Candidato composicional ABX3."""

    A: str
    B: str
    X: str

    @property
    def formula(self) -> str:
        """Formula compacta ABX3."""
        return f"{self.A}{self.B}{self.X}3"


def validate_site_label(label: str, site: str) -> str:
    """Valida una etiqueta de sitio A, B o X."""
    value = str(label).strip()
    if not value:
        raise ValueError(f"Sitio {site} vacio")
    if not _SITE_PATTERN.match(value):
        raise ValueError(f"Etiqueta invalida para sitio {site}: {label!r}")
    return value


def validate_abx3(A: str, B: str, X: str) -> ABX3Candidate:
    """Valida una composicion ABX3 y devuelve un candidato."""
    candidate = ABX3Candidate(
        A=validate_site_label(A, "A"),
        B=validate_site_label(B, "B"),
        X=validate_site_label(X, "X"),
    )
    if candidate.A == candidate.B:
        raise ValueError("Los sitios A y B deben ser distintos")
    if candidate.X not in DEFAULT_X_SITE:
        raise ValueError(f"Haluro X no soportado: {candidate.X!r}")
    return candidate


def goldschmidt_tolerance_factor(r_A: float, r_B: float, r_X: float) -> float:
    """Calcula el factor de tolerancia de Goldschmidt."""
    if r_A <= 0 or r_B <= 0 or r_X <= 0:
        raise ValueError("Los radios ionicos deben ser positivos")
    return (r_A + r_X) / (_SQRT2 * (r_B + r_X))


def generate_abx3_candidates(
    a_site: Iterable[str] = DEFAULT_A_SITE,
    b_site: Iterable[str] = DEFAULT_B_SITE,
    x_site: Iterable[str] = DEFAULT_X_SITE,
) -> list[ABX3Candidate]:
    """Genera candidatos ABX3 puros desde listas de sitios."""
    candidates: list[ABX3Candidate] = []
    for A, B, X in product(a_site, b_site, x_site):
        candidates.append(validate_abx3(A, B, X))
    return candidates


def candidate_from_mapping(data: dict[str, object]) -> ABX3Candidate:
    """Construye un candidato desde un diccionario con A, B y X."""
    missing = {"A", "B", "X"} - set(data)
    if missing:
        raise ValueError(f"Faltan campos ABX3: {sorted(missing)}")
    return validate_abx3(str(data["A"]), str(data["B"]), str(data["X"]))
