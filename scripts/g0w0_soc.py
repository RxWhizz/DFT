#!/usr/bin/env python3
"""SOC perturbative correction on top of G0W0 quasi-particle gaps.

Strategy (additive corrections, same as r²SCAN+U+SOC):
  gap_GW+SOC = gap_GW + Δ_SOC
  Δ_SOC      = gap_SOC_PBE - gap_PBE

SOC is applied to the PBE wavefunctions (g0w0_pbe.gpw). The GW quasi-particle
shift is then added as a rigid correction.  This is the standard perturbative
GW+SOC approach used in perovskite literature (Brivio et al., Filip et al.).

Reads:  g0w0/g0w0_pbe.gpw       — PBE wavefunctions
        g0w0/g0w0_summary.json   — GW gap and Δ_GW
Writes: g0w0/g0w0_soc.json      — combined GW+SOC gap

Usage (serial — SOC needs no MPI for perturbative mode):
    .venv/bin/python3 scripts/g0w0_soc.py --mat CsPbI3
    mpirun -n 4 .venv/bin/python3 scripts/g0w0_soc.py --mat MAPbI3
"""

import argparse
import json
import pathlib

import numpy as np
from gpaw import GPAW
from gpaw.spinorbit import soc_eigenstates


def _compute_soc_gap(gpw_path: pathlib.Path) -> dict:
    """Perturbative SOC gap from a PBE GPW file."""
    calc = GPAW(str(gpw_path), txt=None)
    # PBE implements calculate_spherical → no ignore_xc_potential needed
    soc = soc_eigenstates(calc, scale=1.0, theta=0.0, phi=0.0)
    e_kn = soc.eigenvalues()   # full BZ, shape (nkpts_bz, 2*nbands)
    ef   = calc.get_fermi_level()

    occ   = e_kn[e_kn <= ef]
    unocc = e_kn[e_kn > ef]

    if len(occ) == 0 or len(unocc) == 0:
        return {"gap_soc_pbe_eV": 0.0, "metallic": True}

    vbm = float(occ.max())
    cbm = float(unocc.min())
    gap = round(max(0.0, cbm - vbm), 4)

    return {
        "gap_soc_pbe_eV": gap,
        "vbm_soc_rel_ef": round(vbm - ef, 4),
        "cbm_soc_rel_ef": round(cbm - ef, 4),
        "metallic":       False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="SOC correction on G0W0 gaps")
    parser.add_argument("--mat",     required=True, help="e.g. CsPbI3")
    parser.add_argument("--workdir", default="calculations/top8_r2scan")
    args = parser.parse_args()

    dft_root = pathlib.Path(__file__).parent.parent
    gw_dir   = dft_root / args.workdir / args.mat / "06_r2scan" / "g0w0"
    gpw_path = gw_dir / "g0w0_pbe.gpw"
    gw_summ  = gw_dir / "g0w0_summary.json"
    soc_out  = gw_dir / "g0w0_soc.json"

    if not gpw_path.exists():
        raise FileNotFoundError(f"{gpw_path} not found — run g0w0_groundstate.py first")
    if not gw_summ.exists():
        raise FileNotFoundError(f"{gw_summ} not found — run g0w0_run.py first")

    gw_data = json.loads(gw_summ.read_text())
    gap_gw  = gw_data["gap_gw_eV"]
    gap_pbe = gw_data["gap_pbe_eV"]

    print(f"[g0w0_soc] {args.mat}: computing PBE+SOC gap...")
    soc_data = _compute_soc_gap(gpw_path)
    gap_soc_pbe = soc_data["gap_soc_pbe_eV"]

    delta_soc    = round(gap_soc_pbe - gap_pbe, 4)  # SOC correction (negative for Pb/Sn)
    gap_gw_soc   = round(max(0.0, gap_gw + delta_soc), 4)

    print(f"[g0w0_soc]   gap PBE       = {gap_pbe:.4f} eV")
    print(f"[g0w0_soc]   gap GW        = {gap_gw:.4f} eV  (Δ_GW = {gap_gw-gap_pbe:+.4f})")
    print(f"[g0w0_soc]   gap PBE+SOC   = {gap_soc_pbe:.4f} eV  (Δ_SOC = {delta_soc:+.4f})")
    print(f"[g0w0_soc]   gap GW+SOC    = {gap_gw_soc:.4f} eV")

    result = {
        "mat":              args.mat,
        "gap_pbe_eV":       gap_pbe,
        "gap_gw_eV":        gap_gw,
        "gap_soc_pbe_eV":   gap_soc_pbe,
        "gap_gw_soc_eV":    gap_gw_soc,
        "delta_gw_eV":      round(gap_gw - gap_pbe, 4),
        "delta_soc_eV":     delta_soc,
        "vbm_soc_rel_ef":   soc_data.get("vbm_soc_rel_ef"),
        "cbm_soc_rel_ef":   soc_data.get("cbm_soc_rel_ef"),
        "metallic":         soc_data.get("metallic", False),
    }
    soc_out.write_text(json.dumps(result, indent=2))
    print(f"[g0w0_soc]   Saved → {soc_out.name}")


if __name__ == "__main__":
    main()
