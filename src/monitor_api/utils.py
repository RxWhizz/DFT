"""Utilidades de formato para fórmulas de perovskitas."""
from __future__ import annotations

import re

_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")

# Convierte dígitos (incluye decimales) que siguen a una letra a subíndice Unicode
_NUM_RE = re.compile(r"(?<=[A-Za-z])(\d+(?:\.\d+)?)")


def fmt_formula(formula: str) -> str:
    """FA0.75MA0.25PbBr3  →  FA₀.₇₅MA₀.₂₅PbBr₃"""
    return _NUM_RE.sub(lambda m: m.group().translate(_SUB), formula)
