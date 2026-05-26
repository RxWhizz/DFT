#!/usr/bin/env python3
"""PBE groundstate with empty bands for G0W0 input.

Reads the relaxed structure (relax_sym.gpw → relax.gpw priority), runs a tight
PBE SCF with nbands=4×n_occ (includes occupied + empty bands needed for G0W0).
Writes the GPW with mode='all' (wavefunctions included — required by G0W0).

Avoids diagonalize_full_hamiltonian() which crashes in ScaLAPACK parallel mode.
Instead sets nbands in the GPAW constructor so Davidson handles all bands during SCF.

Usage (from dft/ root):
    mpirun -n 22 .venv/bin/python3 scripts/g0w0_groundstate.py --mat CsPbI3
    mpirun -n 22 .venv/bin/python3 scripts/g0w0_groundstate.py --mat CsPbI3 --dry-run
"""

import argparse
import json
import pathlib

from ase.io import read
from gpaw import GPAW, PW, FermiDirac
from gpaw.eigensolvers import Davidson

NBANDS_FACTOR = 4   # fallback when --nbands not given


def _find_seed(work_mat: pathlib.Path) -> pathlib.Path:
    candidates = [
        work_mat / "01_relax_sym" / "relax_sym.gpw",
        work_mat / "01_relax" / "relax.gpw",
    ]
    seed = next((p for p in candidates if p.exists()), None)
    if seed is None:
        raise FileNotFoundError(f"No relaxed GPW found for {work_mat.name}")
    return seed


def main() -> None:
    parser = argparse.ArgumentParser(description="PBE groundstate for G0W0")
    parser.add_argument("--mat",     required=True, help="e.g. CsPbI3")
    parser.add_argument("--workdir", default="calculations/top8_r2scan")
    parser.add_argument("--ecut",    type=float, default=600.0, help="PW cutoff eV")
    parser.add_argument("--nbands",  type=int,   default=0,
                        help="Total bands including empty (0 = NBANDS_FACTOR × n_occ)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dft_root = pathlib.Path(__file__).parent.parent
    work_mat = dft_root / args.workdir / args.mat
    gw_dir   = work_mat / "06_r2scan" / "g0w0"
    gw_dir.mkdir(parents=True, exist_ok=True)

    out_gpw  = gw_dir / "g0w0_pbe.gpw"
    out_txt  = gw_dir / "g0w0_pbe.txt"
    meta_out = gw_dir / "g0w0_pbe_meta.json"

    if out_gpw.exists() and out_gpw.stat().st_size > 1_000_000:
        print(f"[g0w0_gs] {out_gpw.name} already exists ({out_gpw.stat().st_size//1024} KB) — skipping")
        return

    seed = _find_seed(work_mat)
    print(f"[g0w0_gs] {args.mat}: seed = {seed.relative_to(dft_root)}")
    print(f"[g0w0_gs] ecut={args.ecut} eV  output → {out_gpw.relative_to(dft_root)}")

    if args.dry_run:
        print("[g0w0_gs] DRY RUN — skipping GPAW call")
        out_gpw.write_bytes(b"dry_run")
        return

    # Read n_electrons from relaxed GPW (no SCF — just reads the setup info)
    calc_ref = GPAW(str(seed), txt=None)
    n_electrons = calc_ref.get_number_of_electrons()
    del calc_ref

    n_occ     = int(round(n_electrons / 2))
    nbands_gw = args.nbands if args.nbands > 0 else NBANDS_FACTOR * n_occ

    print(f"[g0w0_gs] n_electrons={n_electrons:.0f}  n_occ={n_occ}  nbands_gw={nbands_gw}")

    atoms = read(str(seed))

    calc = GPAW(
        mode=PW(args.ecut),
        xc="PBE",
        kpts={"size": [6, 6, 6], "gamma": True},
        occupations=FermiDirac(0.01),
        eigensolver=Davidson(niter=3),
        nbands=nbands_gw,
        parallel={"domain": 1},
        convergence={"density": 1e-6, "eigenstates": 1e-8, "energy": 1e-7},
        txt=str(out_txt),
    )
    atoms.calc = calc
    atoms.get_potential_energy()

    calc.write(str(out_gpw), mode="all")

    # Extract PBE gap for reference
    ef = calc.get_fermi_level()
    try:
        from ase.dft.bandgap import bandgap as ase_bandgap
        gap_pbe, _, _ = ase_bandgap(calc)
    except Exception:
        gap_pbe = None

    meta = {
        "mat":        args.mat,
        "n_occ":      n_occ,
        "nbands_gw":  nbands_gw,
        "ef_eV":      round(ef, 6),
        "gap_pbe_eV": round(float(gap_pbe), 4) if gap_pbe is not None else None,
        "ecut_eV":    args.ecut,
        "seed":       str(seed.relative_to(dft_root)),
    }
    meta_out.write_text(json.dumps(meta, indent=2))

    print(f"[g0w0_gs] EF={ef:.4f} eV  gap_PBE={gap_pbe} eV")
    print(f"[g0w0_gs] Written: {out_gpw.name}  ({out_gpw.stat().st_size//1024} KB)")
    print(f"[g0w0_gs] Metadata: {meta_out.name}")


if __name__ == "__main__":
    main()
