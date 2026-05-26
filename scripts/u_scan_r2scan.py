#!/usr/bin/env python3
"""Fine Hubbard U scan on Sn-5s with r²SCAN for Sn-based perovskites.

Scans U = 2.0, 2.25, 2.5, 2.75 eV using full convergence params (density=1e-4).
Each point restarts structure from the previous converged checkpoint.
U=3.0–3.5 left as overcorrection reference if those GPWs already exist.

Outputs (in <workdir>/<mat>/06_r2scan/u_scan/):
  u_scan_U2p00.gpw / .txt   converged checkpoint + log per U value
  u_scan_summary.json       energy, gap, n_iters per U value (appended live)

Usage (from dft/ root):
    mpirun -n 22 .venv/bin/python3 scripts/u_scan_r2scan.py --mat CsSnI3
    mpirun -n 22 .venv/bin/python3 scripts/u_scan_r2scan.py --mat CsSnI3 --dry-run
"""

import argparse
import json
import pathlib
import sys

import yaml
from ase.io import read
from gpaw import GPAW, PW
from gpaw.eigensolvers import Davidson

# Fine scan range: 2.0 → 2.75 eV in 0.25 eV steps
U_SCAN = [2.0, 2.25, 2.5, 2.75]


def _sn_setups(u_ev: float) -> dict:
    return {"Sn": f":s,{u_ev}"}


def _stem(u_ev: float) -> str:
    return f"u_scan_U{f'{u_ev:.2f}'.replace('.', 'p')}"


def _calc_params(r2cfg: dict, txt: pathlib.Path) -> dict:
    """Full audited r²SCAN params — same as production U=3.5 stage."""
    conv = r2cfg.get("convergence", {})
    return {
        "mode": PW(r2cfg.get("ecut", 450)),
        "xc": r2cfg.get("xc", "MGGA_X_R2SCAN+MGGA_C_R2SCAN"),
        "kpts": {"size": r2cfg.get("kpts", [6, 6, 6]), "gamma": True},
        "occupations": {
            "name": "fermi-dirac",
            "width": r2cfg.get("occupations", {}).get("width", 0.2),
        },
        "eigensolver": Davidson(niter=3),
        "parallel": {"domain": 1},
        "convergence": {
            "density": conv.get("density", 1e-4),
            "eigenstates": conv.get("eigenstates", 1e-6),
            "energy": conv.get("energy", 1e-5),
        },
        "mixer": dict(r2cfg.get("mixer", {})),
        "maxiter": int(r2cfg.get("maxiter", 2000)),
        "txt": str(txt),
    }


def _extract_gap(calc: GPAW) -> "tuple[float | None, str]":
    """Return (gap_eV, transition_str). Handles metallic case gracefully."""
    try:
        from ase.dft.bandgap import bandgap as ase_bandgap
        gap, p1, p2 = ase_bandgap(calc)
        if gap < 1e-3:
            return 0.0, "metallic"
        s1, k1, n1 = p1
        s2, k2, n2 = p2
        kpts = calc.get_ibz_k_points()
        k1c = kpts[k1].tolist()
        k2c = kpts[k2].tolist()
        direct = (k1 == k2)
        typ = "direct" if direct else "indirect"
        transition = f"({n1}→{n2})  {[round(x,2) for x in k1c]}→{[round(x,2) for x in k2c]}  [{typ}]"
        return round(float(gap), 4), transition
    except Exception as exc:
        return None, f"gap extraction failed: {exc}"


def _count_iters(txt_path: pathlib.Path) -> int:
    return sum(1 for ln in txt_path.read_text().splitlines()
               if ln.startswith("|iter:") and "iter:" in ln)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine U scan r²SCAN for Sn perovskites")
    parser.add_argument("--mat", required=True, help="e.g. CsSnI3")
    parser.add_argument("--workdir", default="calculations/top8_r2scan")
    parser.add_argument("--config", default="configs/default_params.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dft_root = pathlib.Path(__file__).parent.parent
    work_mat = dft_root / args.workdir / args.mat
    r2cfg = yaml.safe_load((dft_root / args.config).read_text())["r2scan"]

    scan_dir = work_mat / "06_r2scan" / "u_scan"
    scan_dir.mkdir(parents=True, exist_ok=True)
    summary_path = scan_dir / "u_scan_summary.json"

    # Load existing partial results so the script is resumable
    summary: dict = (json.loads(summary_path.read_text())
                     if summary_path.exists() else {})

    # Seed structure: prefer u_ramp U=2.0 checkpoint, then pre_r2scan (PBEsol+U),
    # then relax_sym / relax
    r2scan_u2  = work_mat / "06_r2scan" / "u_ramp_U2p0.gpw"
    pre_r2scan = work_mat / "06_r2scan" / "pre_r2scan.gpw"
    relax_sym  = work_mat / "01_relax_sym" / "relax_sym.gpw"
    relax      = work_mat / "01_relax" / "relax.gpw"
    seed = next((p for p in [r2scan_u2, pre_r2scan, relax_sym, relax] if p.exists()), None)
    if seed is None:
        sys.exit(f"ERROR: no source GPW for {args.mat}")

    prev_gpw: "pathlib.Path | None" = None

    for u_ev in U_SCAN:
        key = f"U{u_ev:.2f}"
        stem = _stem(u_ev)
        out_gpw = scan_dir / f"{stem}.gpw"
        out_txt = scan_dir / f"{stem}.txt"

        print(f"\n[u_scan] {args.mat}  U={u_ev} eV")
        print(f"[u_scan]   setups={_sn_setups(u_ev)}")

        if out_gpw.exists() and out_gpw.stat().st_size > 100:
            print(f"[u_scan]   {out_gpw.name} already exists — skipping")
            prev_gpw = out_gpw
            continue

        src = prev_gpw if (prev_gpw is not None and prev_gpw.exists()) else seed
        print(f"[u_scan]   structure from {src.name} → {out_gpw.name}")

        kwargs = {**_calc_params(r2cfg, out_txt), "setups": _sn_setups(u_ev)}
        print(f"[u_scan]   mixer={kwargs['mixer']}  maxiter={kwargs['maxiter']}")
        print(f"[u_scan]   convergence={kwargs['convergence']}")

        if args.dry_run:
            print("[u_scan]   DRY RUN — skipping GPAW call")
            out_gpw.write_bytes(b"dry_run")
            prev_gpw = out_gpw
            continue

        atoms = read(str(src))
        calc = GPAW(**kwargs)
        atoms.calc = calc
        atoms.get_potential_energy()
        calc.write(str(out_gpw))

        energy = calc.get_potential_energy()
        gap, transition = _extract_gap(calc)
        n_iters = _count_iters(out_txt)

        result = {
            "u_ev": u_ev,
            "energy_eV": round(energy, 6),
            "gap_eV": gap,
            "transition": transition,
            "n_iters": n_iters,
            "converged": n_iters < int(r2cfg.get("maxiter", 2000)),
        }
        summary[key] = result
        summary_path.write_text(json.dumps(summary, indent=2))

        print(f"[u_scan]   E={energy:.4f} eV  gap={gap} eV  iters={n_iters}")
        print(f"[u_scan]   transition: {transition}")
        prev_gpw = out_gpw

    # Final summary table
    print(f"\n[u_scan] {args.mat}: scan complete")
    print(f"[u_scan] Summary: {summary_path}")
    print(f"\n{'U (eV)':>8} {'E (eV)':>12} {'gap (eV)':>10} {'iters':>7} {'converged':>10}")
    print("-" * 55)
    for key in sorted(summary):
        v = summary[key]
        print(f"{v['u_ev']:>8.2f} {v['energy_eV']:>12.4f} "
              f"{str(v.get('gap_eV','?')):>10} {v.get('n_iters','?'):>7} "
              f"{'yes' if v.get('converged') else 'no':>10}")


if __name__ == "__main__":
    main()
