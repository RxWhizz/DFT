#!/usr/bin/env python3
"""PDOS per element/orbital for each U in the fine r²SCAN+U scan.

Reads PAW projections directly from the GPW Reader — no need for a
MPI-matched WFS. Works in serial (1 rank) or any MPI count.

Computes: Sn-5s, Sn-5p, I-5p, Cs-6s PDOS and saves to .npz files.

Usage:
    .venv/bin/python3 scripts/u_scan_pdos.py --mat CsSnI3
"""

import argparse
import pathlib

import numpy as np
from gpaw import GPAW
from gpaw.io import Reader

U_SCAN = [2.0, 2.25, 2.5, 2.75]


def _stem(u_ev: float) -> str:
    return f"u_scan_U{f'{u_ev:.2f}'.replace('.', 'p')}"


def _gaussian(e_grid, centers, weights, width):
    dos = np.zeros(len(e_grid))
    for e0, w in zip(centers, weights):
        dos += w * np.exp(-0.5 * ((e_grid - e0) / width) ** 2)
    return dos / (width * np.sqrt(2 * np.pi))


def _atom_proj_slices(calc):
    """Return {atom_index: slice_into_flat_proj_array} from setup.l_j."""
    slices = {}
    offset = 0
    for a, setup in enumerate(calc.wfs.setups):
        n = sum(2 * l + 1 for l in setup.l_j)
        slices[a] = slice(offset, offset + n)
        offset += n
    return slices


def _l_proj_indices(setup, l_want):
    """Flat indices within a single atom's projector block for angular momentum l_want."""
    idx, offset = [], 0
    for l in setup.l_j:
        for _m in range(2 * l + 1):
            if l == l_want:
                idx.append(offset)
            offset += 1
    return idx


def compute_pdos(gpw_path, emin=-7.0, emax=5.0, npts=2000, width=0.1):
    """PDOS via PAW projections read directly from GPW file (serial-safe)."""
    # Load calculator (FakeWFS is fine — we only need setups and atoms)
    calc = GPAW(str(gpw_path), txt=None)

    # Read raw arrays from file (bypasses WFS distribution)
    reader = Reader(str(gpw_path))
    wfs_r  = reader.wave_functions

    eigenvalues  = wfs_r.eigenvalues    # (nspins, nk, nbands)  [eV absolute]
    projections  = wfs_r.projections    # (nspins, nk, nbands, nprojs_total)
    kweights     = wfs_r.kpts.weights   # (nk,)  IBZ weights, sum=1
    ef           = float(wfs_r.fermi_levels[0])

    nspins, nk, nbands = eigenvalues.shape

    e_grid = np.linspace(emin, emax, npts)   # relative to EF
    e_abs  = e_grid + ef

    syms       = calc.atoms.get_chemical_symbols()
    sn_idx     = [i for i, s in enumerate(syms) if s == "Sn"]
    halide_idx = [i for i, s in enumerate(syms) if s in ("I", "Br")]
    cs_idx     = [i for i, s in enumerate(syms) if s == "Cs"]

    atom_slices = _atom_proj_slices(calc)

    total    = np.zeros(npts)
    sn_s     = np.zeros(npts)
    sn_p     = np.zeros(npts)
    halide_p = np.zeros(npts)
    cs_s     = np.zeros(npts)

    for s in range(nspins):
        for k in range(nk):
            w   = kweights[k] / nspins
            eig = eigenvalues[s, k]          # (nbands,)
            total += _gaussian(e_abs, eig, [w] * nbands, width)

            def _contrib(atom_list, l_want):
                contrib = np.zeros(npts)
                for a in atom_list:
                    setup  = calc.wfs.setups[a]
                    l_ids  = _l_proj_indices(setup, l_want)
                    if not l_ids:
                        continue
                    aslice = atom_slices[a]
                    P_ni   = projections[s, k, :, aslice]   # (nbands, nprojs_a)
                    pw     = np.sum(np.abs(P_ni[:, l_ids]) ** 2, axis=1)  # (nbands,)
                    contrib += _gaussian(e_abs, eig, w * pw, width)
                return contrib

            sn_s     += _contrib(sn_idx,     0)
            sn_p     += _contrib(sn_idx,     1)
            halide_p += _contrib(halide_idx, 1)
            cs_s     += _contrib(cs_idx,     0)

    reader.close()
    return e_grid, ef, total, sn_s, sn_p, halide_p, cs_s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mat",     required=True)
    parser.add_argument("--workdir", default="calculations/top8_r2scan")
    args = parser.parse_args()

    dft_root = pathlib.Path(__file__).parent.parent
    scan_dir = dft_root / args.workdir / args.mat / "06_r2scan" / "u_scan"

    for u_ev in U_SCAN:
        stem    = _stem(u_ev)
        gpw     = scan_dir / f"{stem}.gpw"
        npz_out = scan_dir / f"{stem}_dos.npz"

        print(f"\n[pdos] U={u_ev} eV  ← {gpw.name}")

        if not gpw.exists() or gpw.stat().st_size < 100:
            print(f"[pdos]   {gpw.name} not found — skipping")
            continue

        try:
            e_grid, ef, total, sn_s, sn_p, halide_p, cs_s = compute_pdos(gpw)

            save_kw = dict(energies=e_grid, ef=ef, total=total,
                           sn_s=sn_s, sn_p=sn_p, halide_p=halide_p)
            if cs_s.any():
                save_kw["cs_s"] = cs_s
            np.savez(npz_out, **save_kw)

            # Quick character check at VBM/CBM
            vbm_i = np.searchsorted(e_grid, -0.05)
            cbm_i = np.searchsorted(e_grid,  0.05)
            print(f"[pdos]   EF = {ef:.4f} eV")
            print(f"[pdos]   VBM (~0 eV) Sn-s/halide-p: {sn_s[vbm_i]:.3f} / {halide_p[vbm_i]:.3f}")
            print(f"[pdos]   CBM (~0 eV) Sn-p/halide-p: {sn_p[cbm_i]:.3f} / {halide_p[cbm_i]:.3f}")
            print(f"[pdos]   Saved → {npz_out.name}")

        except Exception as exc:
            import traceback
            print(f"[pdos]   ERROR: {exc}")
            traceback.print_exc()

    print("\n[pdos] Done. Plot with:")
    print("  import numpy as np, matplotlib.pyplot as plt")
    print("  d = np.load('u_scan_U2p50_dos.npz')")
    print("  plt.plot(d['energies'], d['sn_s'], label='Sn-5s')")
    print("  plt.plot(d['energies'], d['halide_p'], label='halide-p')")
    print("  plt.axvline(0, ls='--', c='k')  # EF")


if __name__ == "__main__":
    main()
