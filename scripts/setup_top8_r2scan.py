#!/usr/bin/env python3
"""Create top8_r2scan workdir — symlink PBE relax only, create fresh output dirs.

Usage (run from dft/ root):
    python scripts/setup_top8_r2scan.py
    python scripts/setup_top8_r2scan.py --pbe-dir calculations/top8_pbe --r2scan-dir calculations/top8_r2scan

PBE geometry (01_relax/relax.gpw) is valid for r²SCAN: lattice parameters differ <1%.
Band topology (03_bands/) is NOT symlinked — r²SCAN bands are computed fresh via
the r2scan_bands step to avoid propagating the M-point k-path bug from PBE.
"""
from __future__ import annotations

import argparse
from pathlib import Path

MATERIALS = [
    "MAPbI3", "MASnI3", "FAPbI3", "FASnI3",
    "CsSnI3", "CsPbI3", "FAPbBr3", "FASnBr3",
]


def setup(pbe_dir: Path, r2scan_dir: Path, *, overwrite: bool = False) -> None:
    r2scan_dir.mkdir(parents=True, exist_ok=True)

    for mat in MATERIALS:
        pbe_mat = pbe_dir / mat
        r2scan_mat = r2scan_dir / mat
        r2scan_mat.mkdir(exist_ok=True)

        def _symlink(link: Path, target: Path, label: str) -> None:
            if not target.exists():
                print(f"  WARNING: PBE {label} not found for {mat}: {target}")
                return
            if link.exists() or link.is_symlink():
                if overwrite:
                    link.unlink()
                else:
                    print(f"  {mat}/{label} already linked — skip (use --overwrite to replace)")
                    return
            link.symlink_to(target)
            print(f"  {mat}/{label} -> {target}")

        # Symlink relax dir (atomic positions; k-point topology is NOT reused)
        _symlink(r2scan_mat / "01_relax", (pbe_mat / "01_relax").resolve(), "01_relax")

        # Symlink PBE SCF dir — needed by compute_effective_masses_nscf (fixdensity+GGA only)
        _symlink(r2scan_mat / "02_scf", (pbe_mat / "02_scf").resolve(), "02_scf")

        # Fresh output dirs computed with r²SCAN
        for d in ("06_r2scan", "10_effective_masses", "12_score"):
            (r2scan_mat / d).mkdir(exist_ok=True)

        print(f"  {mat}: ready")

    print(f"\nWorkdir created: {r2scan_dir.resolve()}")
    print("Next step: run calculations/top8_r2scan/run_top8_r2scan.sh")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pbe-dir", default="calculations/top8_pbe", type=Path)
    parser.add_argument("--r2scan-dir", default="calculations/top8_r2scan", type=Path)
    parser.add_argument("--overwrite", action="store_true", help="Replace existing symlinks")
    args = parser.parse_args()
    setup(args.pbe_dir, args.r2scan_dir, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
