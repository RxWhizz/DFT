#!/usr/bin/env python3
"""SOC single-point + DOS/PDOS for each U value in the fine r²SCAN+U scan.

Run after u_scan_r2scan.py. For each converged GPW in u_scan/:
  1. Perturbative SOC eigenvalues (theta=phi=0, scale=1)
  2. SOC-corrected fundamental gap (target: 1.2–1.5 eV for CsSnI3)
  3. Total DOS and element/orbital PDOS saved as .npz for plotting
  4. Summary table: U | gap_r2scan | gap_SOC | delta_SOC

Outputs (in <workdir>/<mat>/06_r2scan/u_scan/):
  u_scan_U2pXX_dos.npz   — energy, total_dos, sn_s, sn_p, i_p, cs_s arrays
  u_scan_soc_summary.json — gap table per U value

Usage:
    mpirun -n 4 .venv/bin/python3 scripts/u_scan_soc_dos.py --mat CsSnI3
"""

import argparse
import json
import pathlib
import sys

import numpy as np
import yaml
from gpaw import GPAW
from gpaw.spinorbit import soc_eigenstates

U_SCAN = [2.0, 2.25, 2.5, 2.75]


def _stem(u_ev: float) -> str:
    return f"u_scan_U{f'{u_ev:.2f}'.replace('.', 'p')}"


# ── SOC gap ────────────────────────────────────────────────────────────────────

def compute_soc_gap(calc: GPAW) -> dict:
    """Perturbative SOC gap from a converged r²SCAN+U calculator."""
    # ignore_xc_potential=True: MGGA (r²SCAN) doesn't implement calculate_spherical
    # needed for SOC radial potential. XC contribution to SOC is small (~meV);
    # kinetic+Hartree terms dominate the spin-orbit splitting.
    soc = soc_eigenstates(calc, scale=1.0, theta=0.0, phi=0.0,
                          ignore_xc_potential=True)
    e_kn = soc.eigenvalues()          # (nk, 2*nbands) in eV
    ef = calc.get_fermi_level()

    occ   = e_kn[e_kn <= ef]
    unocc = e_kn[e_kn > ef]

    if len(occ) == 0 or len(unocc) == 0:
        return {"gap_soc_eV": 0.0, "vbm_eV": None, "cbm_eV": None, "metallic": True}

    vbm = float(occ.max())
    cbm = float(unocc.min())
    gap = round(max(0.0, cbm - vbm), 4)

    return {
        "gap_soc_eV": gap,
        "vbm_eV":     round(vbm - ef, 4),   # relative to EF
        "cbm_eV":     round(cbm - ef, 4),
        "metallic":   False,
    }


# ── DOS / PDOS ─────────────────────────────────────────────────────────────────

def _gaussian_dos(energies_grid, eigenvalues, weights, width=0.1):
    """Gaussian-broadened DOS on a uniform energy grid."""
    dos = np.zeros(len(energies_grid))
    for e, w in zip(eigenvalues, weights):
        dos += w * np.exp(-0.5 * ((energies_grid - e) / width) ** 2)
    dos /= (width * np.sqrt(2 * np.pi))
    return dos


def compute_dos_pdos(
    calc: GPAW,
    emin: float = -7.0,
    emax: float = 5.0,
    npts: int = 2000,
    width: float = 0.1,
) -> dict:
    """
    Total DOS and Sn-s/Sn-p/I-p/Cs-s PDOS via PAW projections.
    Falls back to total-DOS-only if projections are unavailable.
    """
    ef = calc.get_fermi_level()
    e_grid = np.linspace(emin, emax, npts)            # relative to EF
    e_abs  = e_grid + ef

    syms = calc.atoms.get_chemical_symbols()
    sn_idx     = [i for i, s in enumerate(syms) if s == "Sn"]
    halide_idx = [i for i, s in enumerate(syms) if s in ("I", "Br")]
    cs_idx     = [i for i, s in enumerate(syms) if s == "Cs"]

    kweights = calc.get_k_point_weights()
    nspins   = calc.get_number_of_spins()
    nk       = len(kweights)

    # Collect eigenvalues and k-weights (for total DOS)
    all_eig, all_w = [], []
    for k in range(nk):
        for s in range(nspins):
            eig = calc.get_eigenvalues(kpt=k, spin=s)
            w   = kweights[k] / nspins
            all_eig.extend(eig)
            all_w.extend([w] * len(eig))

    total_dos = _gaussian_dos(e_abs, all_eig, all_w, width=width)

    result = {"energies": e_grid, "total": total_dos}

    # PDOS via PAW projections (PW mode)
    try:
        # P_ani shape: nbands × n_projectors per atom per k/spin
        # orbital character indexed by projector index i:
        #   GPAW orders projectors as (n, l, m) → s: l=0, p: l=1
        def proj_dos(atom_indices, l_filter):
            """Sum projected DOS for given atom indices and angular momentum l."""
            pdos = np.zeros(len(e_abs))
            for k in range(nk):
                for s in range(nspins):
                    kpt = calc.wfs.kpt_qs[s][k]
                    eig = calc.get_eigenvalues(kpt=k, spin=s)
                    w   = kweights[k] / nspins
                    for a in atom_indices:
                        P_ni = kpt.projections.array[a]  # (nbands, nprojs)
                        setup = calc.wfs.setups[a]
                        # Find projector indices with angular momentum l_filter
                        l_indices = [
                            i for i, (n, l, m) in
                            enumerate(zip(setup.n_j, setup.l_j,
                                          [m for l in setup.l_j
                                           for m in range(-l, l + 1)]))
                            if l == l_filter
                        ]
                        if not l_indices:
                            continue
                        proj_weight = np.sum(np.abs(P_ni[:, l_indices]) ** 2, axis=1)
                        for n, (e_n, pw) in enumerate(zip(eig, proj_weight)):
                            pdos += w * pw * np.exp(
                                -0.5 * ((e_abs - e_n) / width) ** 2
                            ) / (width * np.sqrt(2 * np.pi))
            return pdos

        result["sn_s"]     = proj_dos(sn_idx,     l_filter=0)
        result["sn_p"]     = proj_dos(sn_idx,     l_filter=1)
        result["halide_p"] = proj_dos(halide_idx, l_filter=1)
        if cs_idx:
            result["cs_s"] = proj_dos(cs_idx, l_filter=0)
        print("[u_scan_soc]   PDOS computed via PAW projections")

    except Exception as exc:
        print(f"[u_scan_soc]   PDOS via projections failed ({exc}) — total DOS only")

    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOC + DOS/PDOS for each U in the r²SCAN fine scan"
    )
    parser.add_argument("--mat",       required=True, help="e.g. CsSnI3")
    parser.add_argument("--workdir",   default="calculations/top8_r2scan")
    parser.add_argument("--no-dos",    action="store_true",
                        help="Skip DOS/PDOS (SOC gap only, faster)")
    parser.add_argument("--gap-min",   type=float, default=None,
                        help="Lower bound of target SOC gap (eV)")
    parser.add_argument("--gap-max",   type=float, default=None,
                        help="Upper bound of target SOC gap (eV)")
    args = parser.parse_args()

    dft_root  = pathlib.Path(__file__).parent.parent
    scan_dir  = dft_root / args.workdir / args.mat / "06_r2scan" / "u_scan"
    summ_path = scan_dir / "u_scan_summary.json"

    if not summ_path.exists():
        sys.exit(f"ERROR: {summ_path} not found — run u_scan_r2scan.py first")

    r2scan_summary = json.loads(summ_path.read_text())
    soc_summary: dict = {}

    # Per-material target SOC gap ranges (experimental references)
    _TARGET = {
        "CsSnI3":  (1.2, 1.5),
        "MASnI3":  (1.1, 1.4),
        "FASnI3":  (1.2, 1.5),
        "FASnBr3": (1.8, 2.3),
    }
    gap_min, gap_max = (args.gap_min, args.gap_max) if args.gap_min else \
                       _TARGET.get(args.mat, (1.2, 1.5))

    for u_ev in U_SCAN:
        key  = f"U{u_ev:.2f}"
        stem = _stem(u_ev)
        gpw  = scan_dir / f"{stem}.gpw"

        print(f"\n[u_scan_soc] {args.mat}  U={u_ev} eV")

        if not gpw.exists() or gpw.stat().st_size < 100:
            print(f"[u_scan_soc]   {gpw.name} not found — skipping")
            continue

        calc = GPAW(str(gpw), txt=None)

        # SOC gap
        soc_data = compute_soc_gap(calc)
        gap_r2   = r2scan_summary.get(key, {}).get("gap_eV")
        gap_soc  = soc_data["gap_soc_eV"]
        delta    = round(gap_soc - gap_r2, 4) if gap_r2 is not None else None

        print(f"[u_scan_soc]   gap r²SCAN+U = {gap_r2} eV")
        print(f"[u_scan_soc]   gap SOC      = {gap_soc} eV  (Δ = {delta:+.4f} eV)")
        print(f"[u_scan_soc]   VBM = EF{soc_data['vbm_eV']:+.3f} eV  "
              f"CBM = EF{soc_data['cbm_eV']:+.3f} eV")

        soc_summary[key] = {
            "u_ev":            u_ev,
            "gap_r2scan_eV":   gap_r2,
            "gap_soc_eV":      gap_soc,
            "delta_soc_eV":    delta,
            "vbm_rel_ef":      soc_data["vbm_eV"],
            "cbm_rel_ef":      soc_data["cbm_eV"],
            "in_target_range": gap_min <= gap_soc <= gap_max if gap_soc else False,
        }

        # DOS / PDOS
        if not args.no_dos:
            dos_data = compute_dos_pdos(calc)
            npz_path = scan_dir / f"{stem}_dos.npz"
            save_kwargs = dict(
                energies   = dos_data["energies"],
                ef         = calc.get_fermi_level(),
                total      = dos_data["total"],
                sn_s       = dos_data.get("sn_s",     np.array([])),
                sn_p       = dos_data.get("sn_p",     np.array([])),
                halide_p   = dos_data.get("halide_p", np.array([])),
            )
            if "cs_s" in dos_data:
                save_kwargs["cs_s"] = dos_data["cs_s"]
            np.savez(npz_path, **save_kwargs)
            print(f"[u_scan_soc]   DOS saved → {npz_path.name}")

    # Write SOC summary
    soc_path = scan_dir / "u_scan_soc_summary.json"
    soc_path.write_text(json.dumps(soc_summary, indent=2))

    # Print summary table
    print(f"\n{'─'*62}")
    print(f"{'U (eV)':>8} {'gap r²SCAN':>12} {'gap SOC':>10} {'ΔSOC':>8}  target?")
    print(f"{'─'*62}")
    for key in sorted(soc_summary):
        v = soc_summary[key]
        flag = " ✓" if v.get("in_target_range") else ""
        print(f"{v['u_ev']:>8.2f} {str(v['gap_r2scan_eV']):>12} "
              f"{v['gap_soc_eV']:>10} {v['delta_soc_eV']:>+8.4f}{flag}")
    print(f"{'─'*62}")
    print(f"\n[u_scan_soc] SOC summary → {soc_path}")


if __name__ == "__main__":
    main()
