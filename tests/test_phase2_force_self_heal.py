"""Tests del parser SCF usado por el self-heal de no-SCF-stall en Fase 2A.

El self-heal de oscilación U-scan se eliminó (ya no hay Hubbard U; ver bitácora 2026-06-09).
Queda el detector de no-SCF-stall, que parsea las líneas `iter:` del log r2scan.txt.
"""
from __future__ import annotations

from buho.phase2_force.self_heal import parse_scf_points


def _write_scf(path, energies, dens=-1.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["maxiter: 333"]
    for idx, energy in enumerate(energies, start=1):
        lines.append(f"iter: {idx:3d} 12:{idx % 60:02d}:00 {energy: .6f} -3.00 {dens: .2f}")
    path.write_text("\n".join(lines) + "\n")


def test_parse_scf_points_ignores_maxiter(tmp_path):
    log = tmp_path / "pbe" / "r2scan.txt"
    _write_scf(log, [-1.0, -2.0])
    points = parse_scf_points(log)
    assert [point["iter"] for point in points] == [1, 2]
    assert points[-1]["energy"] == -2.0
