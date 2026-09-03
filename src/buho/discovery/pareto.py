"""Pareto utilities for multi-objective photovoltaic discovery."""

from __future__ import annotations

import math
from collections.abc import Iterable

import pandas as pd


def _finite_float(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _dominates(a: Iterable[float], b: Iterable[float]) -> bool:
    """True when ``a`` is at least as good as ``b`` in all max objectives."""
    better_or_equal = True
    strictly_better = False
    for va, vb in zip(a, b):
        if va < vb:
            better_or_equal = False
            break
        if va > vb:
            strictly_better = True
    return better_or_equal and strictly_better


def pareto_front(
    df: pd.DataFrame,
    objectives: list[str],
    *,
    max_input: int = 5000,
    sort_by: str = "acquisition_score",
    limit: int | None = None,
) -> pd.DataFrame:
    """Return the non-dominated rows for max-oriented objective columns.

    For the full chemical space, the function first keeps the best ``max_input``
    rows by acquisition score. This keeps the skyline calculation bounded while
    preserving the chemically interesting frontier.
    """
    if df.empty or not objectives:
        return df.head(0).copy()

    work = df.copy()
    for col in objectives:
        if col not in work:
            work[col] = 0.0
        work[col] = work[col].map(lambda x: _finite_float(x) or 0.0)

    if sort_by in work:
        work = work.sort_values(sort_by, ascending=False).head(max_input)

    frontier: list[tuple[int, tuple[float, ...]]] = []
    for idx, row in work.iterrows():
        values = tuple(float(row[col]) for col in objectives)
        if any(_dominates(existing_values, values) for _, existing_values in frontier):
            continue
        frontier = [
            (existing_idx, existing_values)
            for existing_idx, existing_values in frontier
            if not _dominates(values, existing_values)
        ]
        frontier.append((idx, values))

    indices = [idx for idx, _ in frontier]
    out = work.loc[indices].copy()
    if sort_by in out:
        out = out.sort_values(sort_by, ascending=False)
    if limit is not None:
        out = out.head(limit)
    return out.reset_index(drop=True)
