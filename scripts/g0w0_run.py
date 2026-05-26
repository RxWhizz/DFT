#!/usr/bin/env python3
"""G0W0 quasi-particle correction on top of the PBE groundstate.

Reads g0w0_pbe.gpw (from g0w0_groundstate.py) and runs G0W0 to correct the
VBM and CBM quasi-particle energies. Writes g0w0_summary.json with the GW gap.

Resumable: GPAW caches partial Σ(q) results in JSON files; re-running continues
from the last completed q-point.

Usage (from dft/ root):
    mpirun -n 22 .venv/bin/python3 scripts/g0w0_run.py --mat CsPbI3
    mpirun -n 22 .venv/bin/python3 scripts/g0w0_run.py --mat MAPbI3 --ppa
"""

import argparse
import json
import pathlib

import numpy as np
from gpaw.response.g0w0 import G0W0


def _load_meta(gw_dir: pathlib.Path) -> dict:
    meta_path = gw_dir / "g0w0_pbe_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"{meta_path} not found — run g0w0_groundstate.py first")
    return json.loads(meta_path.read_text())


def _extract_gap(result, n_occ: int, n_bands_start: int) -> dict:
    """Extract GW fundamental gap from G0W0Outputs.

    qp_skn shape: (nspins, nkpts, n_corrected_bands)
    band index in full set = n_bands_start + n_corrected_index
    VBM = band n_occ-1  →  corrected index = (n_occ-1) - n_bands_start
    CBM = band n_occ    →  corrected index = n_occ - n_bands_start
    """
    qp = result.qp_skn   # (nspins, nkpts, nbands_corrected)
    eps = result.eps_skn  # KS eigenvalues, same shape

    i_vbm = (n_occ - 1) - n_bands_start
    i_cbm = n_occ - n_bands_start

    vbm_qp  = float(qp[0, :, i_vbm].max())
    cbm_qp  = float(qp[0, :, i_cbm].min())
    vbm_ks  = float(eps[0, :, i_vbm].max())
    cbm_ks  = float(eps[0, :, i_cbm].min())

    gap_gw  = max(0.0, cbm_qp - vbm_qp)
    gap_pbe = max(0.0, cbm_ks - vbm_ks)

    z_vbm = float(result.Z_skn[0, :, i_vbm].mean())
    z_cbm = float(result.Z_skn[0, :, i_cbm].mean())

    return {
        "gap_gw_eV":      round(gap_gw,  4),
        "gap_pbe_eV":     round(gap_pbe, 4),
        "vbm_gw_eV":      round(vbm_qp,  4),
        "cbm_gw_eV":      round(cbm_qp,  4),
        "vbm_ks_eV":      round(vbm_ks,  4),
        "cbm_ks_eV":      round(cbm_ks,  4),
        "delta_gw_eV":    round(gap_gw - gap_pbe, 4),
        "Z_vbm_mean":     round(z_vbm,   4),
        "Z_cbm_mean":     round(z_cbm,   4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="G0W0 quasi-particle corrections")
    parser.add_argument("--mat",     required=True, help="e.g. CsPbI3")
    parser.add_argument("--workdir", default="calculations/top8_r2scan")
    parser.add_argument("--ecut",    type=float, default=100.0, help="G0W0 ecut eV")
    parser.add_argument("--ppa",     action="store_true",
                        help="Use Plasmon-Pole Approximation (faster for 12-atom cells)")
    parser.add_argument("--no-extrap", action="store_true",
                        help="Disable ecut extrapolation (faster but less accurate)")
    args = parser.parse_args()

    dft_root = pathlib.Path(__file__).parent.parent
    gw_dir   = dft_root / args.workdir / args.mat / "06_r2scan" / "g0w0"
    gpw_path = gw_dir / "g0w0_pbe.gpw"
    summ_out = gw_dir / "g0w0_summary.json"

    if not gpw_path.exists():
        raise FileNotFoundError(f"{gpw_path} not found — run g0w0_groundstate.py first")

    meta    = _load_meta(gw_dir)
    n_occ   = meta["n_occ"]
    n_start = n_occ - 1    # first corrected band = VBM
    n_stop  = n_occ + 1    # last corrected band (exclusive) = CBM+1

    print(f"[g0w0] {args.mat}: n_occ={n_occ}  bands=({n_start},{n_stop})")
    print(f"[g0w0] ecut={args.ecut} eV  ppa={args.ppa}  extrapolation={not args.no_extrap}")

    out_prefix = str(gw_dir / "g0w0")

    gw_kwargs: dict = dict(
        calc=str(gpw_path),
        filename=out_prefix,
        ecut=args.ecut,
        ecut_extrapolation=not args.no_extrap,
        bands=(n_start, n_stop),
        integrate_gamma="WS",
        ppa=args.ppa,
        nblocksmax=True,   # distribuye chi0_wGG entre ranks para reducir RAM
    )
    if args.no_extrap:
        gw_kwargs["nbands"] = meta["nbands_gw"]

    gw = G0W0(**gw_kwargs)

    result = gw.calculate()

    gap_data = _extract_gap(result, n_occ, n_start)

    summary = {
        "mat":     args.mat,
        "ppa":     args.ppa,
        "ecut_gw": args.ecut,
        **gap_data,
        "n_occ":   n_occ,
        "ef_pbe_eV": meta["ef_eV"],
    }
    summ_out.write_text(json.dumps(summary, indent=2))

    print(f"\n[g0w0] {args.mat} results:")
    print(f"[g0w0]   gap PBE = {gap_data['gap_pbe_eV']:.4f} eV")
    print(f"[g0w0]   gap GW  = {gap_data['gap_gw_eV']:.4f} eV")
    print(f"[g0w0]   Δ_GW    = {gap_data['delta_gw_eV']:+.4f} eV")
    print(f"[g0w0]   Z_VBM/CBM = {gap_data['Z_vbm_mean']:.3f} / {gap_data['Z_cbm_mean']:.3f}")
    print(f"[g0w0]   Summary → {summ_out.name}")


if __name__ == "__main__":
    main()
