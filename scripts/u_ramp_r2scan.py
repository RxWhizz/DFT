#!/usr/bin/env python3
"""U-ramping r²SCAN+U for Sn-based perovskites.

Adiabatically ramps Hubbard U on Sn-5s: 0 → 1 → 2 → 3.5 eV, using each
converged GPW as warm start for the next stage. Avoids DFT+U double-well
oscillation by following the correct minimum continuously from U=0.

Usage (from dft/ root):
    mpirun -n 22 .venv/bin/python3 scripts/u_ramp_r2scan.py --mat CsSnI3
    mpirun -n 22 .venv/bin/python3 scripts/u_ramp_r2scan.py --mat MASnI3 --dry-run

Stages:
    U=0.0 eV  cold start from relax_sym.gpw / relax.gpw  → u_ramp_U0p0.gpw
    U=1.0 eV  warm from U=0  → u_ramp_U1p0.gpw
    U=2.0 eV  warm from U=1  → u_ramp_U2p0.gpw
    U=3.5 eV  warm from U=2  → r2scan.gpw + r2scan.txt  (full audited params)

Intermediate stages use fast convergence criteria (density=1e-2, beta=0.05,
maxiter=500). The final stage reads all params from configs/default_params.yaml.
If a stage's output GPW already exists it is skipped, so the script is resumable.
"""

import argparse
import pathlib
import sys

import yaml
from ase.io import read
from gpaw import GPAW, PW
from gpaw.eigensolvers import Davidson

# Ramp stages in eV; last value is the production target
U_STAGES = [0.0, 1.0, 2.0, 3.0, 3.2, 3.4, 3.5]


def _sn_setups(u_ev: float) -> dict:
    """Dudarev setups dict for given U on Sn-5s (empty = no DFT+U)."""
    return {} if u_ev == 0.0 else {"Sn": f":s,{u_ev}"}


def _stage_stem(u_ev: float) -> str:
    return f"u_ramp_U{f'{u_ev:.1f}'.replace('.', 'p')}"


def _common_params(r2cfg: dict) -> dict:
    """GPAW params shared across all stages: mode, xc, kpts, occupations, eigensolver."""
    return {
        "mode": PW(r2cfg.get("ecut", 450)),
        "xc": r2cfg.get("xc", "MGGA_X_R2SCAN+MGGA_C_R2SCAN"),
        "kpts": {"size": r2cfg.get("kpts", [6, 6, 6]), "gamma": True},
        "occupations": {
            "name": "fermi-dirac",
            "width": r2cfg.get("occupations", {}).get("width", 0.2),
        },
        "eigensolver": Davidson(niter=3),
        "parallel": {"domain": 1},  # required for MGGA: no domain decomp
    }


def _fast_params(txt: pathlib.Path) -> dict:
    """Loose convergence for intermediate U stages — speed over accuracy."""
    return {
        "convergence": {"density": 1e-2, "eigenstates": 1e-5, "energy": 1e-3},
        "mixer": {"backend": "msr1", "beta": 0.05, "nmaxold": 10},
        "maxiter": 500,
        "txt": str(txt),
    }


def _final_params(r2cfg: dict, txt: pathlib.Path) -> dict:
    """Full audited params from config for the production U=3.5 stage."""
    conv = r2cfg.get("convergence", {})
    return {
        "convergence": {
            "density": conv.get("density", 1e-4),
            "eigenstates": conv.get("eigenstates", 1e-6),
            "energy": conv.get("energy", 1e-5),
        },
        "mixer": dict(r2cfg.get("mixer", {})),
        "maxiter": int(r2cfg.get("maxiter", 2000)),
        "txt": str(txt),
    }


def _run_stage(
    prev_gpw: "pathlib.Path | None",
    cold_src: pathlib.Path,
    kwargs: dict,
    out_gpw: pathlib.Path,
    dry_run: bool,
) -> None:
    # U-ramp always changes setups between stages, so GPAW(prev_gpw, setups=new)
    # crashes before writing anything. Use ase.io.read to carry over the structure
    # only; each stage starts with fresh density but with smaller U (tractable).
    src = prev_gpw if (prev_gpw is not None and prev_gpw.exists()) else cold_src
    print(f"[u_ramp]   structure from {src.name} → {out_gpw.name}")

    if dry_run:
        print("[u_ramp]   DRY RUN — skipping GPAW call")
        out_gpw.write_bytes(b"dry_run")
        return

    atoms = read(str(src))
    calc = GPAW(**kwargs)
    atoms.calc = calc
    atoms.get_potential_energy()
    calc.write(str(out_gpw))
    print(f"[u_ramp]   Wrote {out_gpw.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="U-ramp r²SCAN+U for Sn-based perovskites")
    parser.add_argument("--mat", required=True, help="e.g. CsSnI3")
    parser.add_argument("--workdir", default="calculations/top8_r2scan")
    parser.add_argument("--config", default="configs/default_params.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dft_root = pathlib.Path(__file__).parent.parent
    work_mat = dft_root / args.workdir / args.mat
    r2cfg = yaml.safe_load((dft_root / args.config).read_text())["r2scan"]

    # Cold-start source: prefer relax_sym (FA materials), fallback to relax
    relax_sym = work_mat / "01_relax_sym" / "relax_sym.gpw"
    relax = work_mat / "01_relax" / "relax.gpw"
    cold_src = relax_sym if relax_sym.exists() else relax
    if not cold_src.exists():
        sys.exit(
            f"ERROR: no source GPW for {args.mat}: tried {relax_sym} and {relax}"
        )

    out_dir = work_mat / "06_r2scan"
    out_dir.mkdir(parents=True, exist_ok=True)

    final_gpw = out_dir / "r2scan.gpw"
    if final_gpw.exists():
        print(f"[u_ramp] {args.mat}: r2scan.gpw already exists — nothing to do")
        sys.exit(0)

    common = _common_params(r2cfg)
    prev_gpw: "pathlib.Path | None" = None

    for u_ev in U_STAGES:
        is_final = u_ev == U_STAGES[-1]

        if is_final:
            out_gpw = out_dir / "r2scan.gpw"
            out_txt = out_dir / "r2scan.txt"
            stage_params = _final_params(r2cfg, out_txt)
        else:
            stem = _stage_stem(u_ev)
            out_gpw = out_dir / f"{stem}.gpw"
            out_txt = out_dir / f"{stem}.txt"
            stage_params = _fast_params(out_txt)

        print(f"\n[u_ramp] {args.mat}  U={u_ev} eV{'  (FINAL)' if is_final else ''}")
        print(f"[u_ramp]   setups={_sn_setups(u_ev)}")
        print(f"[u_ramp]   mixer={stage_params['mixer']}  maxiter={stage_params['maxiter']}")
        print(f"[u_ramp]   convergence={stage_params['convergence']}")

        if out_gpw.exists():
            print(f"[u_ramp]   {out_gpw.name} already exists — skipping")
        else:
            kwargs = {**common, **stage_params, "setups": _sn_setups(u_ev)}
            _run_stage(prev_gpw, cold_src, kwargs, out_gpw, args.dry_run)

        prev_gpw = out_gpw

    print(f"\n[u_ramp] {args.mat}: U-ramp complete")


if __name__ == "__main__":
    main()
