#!/usr/bin/env python3
"""Non-SCF band structure calculation along high-symmetry path for top-8 perovskitas.

Usa fixed_density() de GPAW master para mantener la densidad SCF mientras diagonaliza
en el camino de alta simetría. Para cada material guarda:
  06_r2scan/bands_path_eigs.npy     — (nspins, nk_path, nbands) en eV absolutos
  06_r2scan/bands_path_kpts.npy     — (nk_path, 3) coordenadas k en recíproco
  06_r2scan/bands_path_xcoords.npy  — (nk_path,) coordenadas lineales para plot
  06_r2scan/bands_path_special.json — {label: xcoord} para puntos de alta simetría
  06_r2scan/bands_path_soc_eigs.npy — (nk_path, 2*nbands) SOC perturbativo

Uso:
    .venv/bin/python scripts/band_calc.py --mat CsSnI3
    .venv/bin/python scripts/band_calc.py --mat all
    .venv/bin/python scripts/band_calc.py --mat CsPbI3 --pbe  # usa g0w0_pbe.gpw
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TOP8 = ROOT / "calculations" / "top8_r2scan"

NPOINTS = 80   # k-points en el camino

# GPW source y parámetros para cada material
MATERIALS: dict[str, dict] = {
    "CsSnI3":  {
        "gpw": "06_r2scan/u_scan/u_scan_U2p50.gpw",
        "is_pb": False, "natoms": 5,
    },
    "MASnI3":  {
        "gpw": "06_r2scan/u_scan/u_scan_U2p50.gpw",
        "is_pb": False, "natoms": 12,
    },
    "FASnI3":  {
        "gpw": "06_r2scan/u_scan/u_scan_U2p50.gpw",
        "is_pb": False, "natoms": 12,
    },
    "FASnBr3": {
        "gpw": "06_r2scan/u_scan/u_scan_U2p50.gpw",
        "is_pb": False, "natoms": 12,
    },
    # Pb: usan PBE desde g0w0_pbe.gpw (CsPbI3) o PBE fresco (organics)
    "CsPbI3":  {
        "gpw": "06_r2scan/r2scan.gpw",   # ASE-readable; g0w0_pbe.gpw tiene 88 bandas mode='all' → LCAO→PW muy lento
        "is_pb": True, "natoms": 5, "needs_pbe_scf": True,
    },
    "MAPbI3":  {
        "gpw": "06_r2scan/r2scan.gpw",   # ASE-readable solo
        "is_pb": True, "natoms": 12, "needs_pbe_scf": True,
    },
    "FAPbI3":  {
        "gpw": "06_r2scan/r2scan.gpw",
        "is_pb": True, "natoms": 12, "needs_pbe_scf": True,
    },
    "FAPbBr3": {
        "gpw": "06_r2scan/r2scan.gpw",
        "is_pb": True, "natoms": 12, "needs_pbe_scf": True,
    },
}


def _band_path_str(atoms) -> str:
    """Determina el camino BZ para la celda del material."""
    cell = atoms.cell
    lengths = cell.lengths()
    angles = cell.angles()
    # Cúbico: a≈b≈c, α≈β≈γ≈90
    if (lengths.max() - lengths.min()) < 0.15 and all(abs(a - 90) < 3 for a in angles):
        return "GXMGR"   # camino estándar cúbico sin salto X|M
    # Tetragonal: a≈b≠c
    if abs(lengths[0] - lengths[1]) < 0.1 and abs(lengths[0] - lengths[2]) > 0.1:
        return "GXMGZRAZ"   # sin cola XR
    # Ortorrómbico: fallback
    return "GXSYGZURTZ"


def _xcoords_from_path(bs) -> tuple[np.ndarray, list[float], list[str]]:
    """Extrae coordenadas lineales y puntos especiales del objeto BandStructure de ASE."""
    from ase.spectrum.band_structure import BandStructure
    path = bs.path
    # xcoords, special_xcoords, labels
    xcoords, xsp, labels = path.get_linear_kpoint_axis()
    xcoords = np.asarray(xcoords, dtype=float)
    if xcoords[-1] > 0:
        xcoords = xcoords / xcoords[-1]
    xsp_norm = [x / path.get_linear_kpoint_axis()[0][-1]
                if path.get_linear_kpoint_axis()[0][-1] > 0 else x
                for x in xsp]
    return xcoords, xsp_norm, labels


def run_band_calc(mat: str, force: bool = False) -> bool:
    """Ejecuta el cálculo de bandas para un material. Retorna True si exitoso."""
    from gpaw import GPAW

    mat_dir = TOP8 / mat
    cfg = MATERIALS[mat]
    gpw_path = mat_dir / cfg["gpw"]
    out_dir = mat_dir / "06_r2scan"

    eigs_out = out_dir / "bands_path_eigs.npy"
    if eigs_out.exists() and not force:
        print(f"  [bands] {mat}: ya calculado ({eigs_out.name}), usa --force para recalcular")
        return True

    if cfg.get("needs_pbe_scf"):
        print(f"  [bands] {mat}: requiere PBE SCF previo — ver run_pbe_scf()")
        return _run_pbe_band(mat, mat_dir, out_dir, gpw_path)

    if not gpw_path.exists():
        print(f"  [bands] {mat}: GPW no encontrado ({gpw_path})")
        return False

    print(f"  [bands] {mat}: cargando {gpw_path.name} …")
    calc_scf = GPAW(str(gpw_path), txt=None)
    atoms = calc_scf.atoms
    ef_scf = calc_scf.get_fermi_level()
    print(f"  [bands] {mat}: EF={ef_scf:.4f} eV, celda={atoms.cell.lengths().round(3)}")

    path_str = _band_path_str(atoms)
    print(f"  [bands] {mat}: camino BZ = {path_str}, npoints={NPOINTS}")

    txt_out = out_dir / "bands_path_calc.txt"
    calc_bs = calc_scf.fixed_density(
        kpts={"path": path_str, "npoints": NPOINTS},
        symmetry="off",
        convergence={"eigenstates": 1e-5},   # más rápido que default 1e-6
        txt=str(txt_out),
    )
    atoms.calc = calc_bs
    atoms.get_potential_energy()

    ef_bs = calc_bs.get_fermi_level()
    bs = calc_bs.band_structure()

    # bs.energies: (nspins, nk_path, nbands) en eV (relativo a EF del BS calc)
    # Guardar en absolutos: bs.energies + EF del BS
    eigs_abs = bs.energies + ef_bs   # (nspins, nk_path, nbands) eV absolutos

    # n_occ: número de bandas ocupadas (electrones de valencia / 2 para spin-unpolarized)
    nvalence = int(calc_bs.get_number_of_electrons())
    nspins_calc = calc_bs.get_number_of_spins()
    n_occ = nvalence // (2 // nspins_calc)  # divide por 2 solo si nspin=1

    # Coordenadas k lineales
    xcoords, xsp_norm, labels = _xcoords_from_path(bs)
    special = {lb: xc for lb, xc in zip(labels, xsp_norm)}

    np.save(str(out_dir / "bands_path_eigs.npy"), eigs_abs)
    np.save(str(out_dir / "bands_path_xcoords.npy"), xcoords)
    (out_dir / "bands_path_special.json").write_text(json.dumps({
        "special_xcoords": xsp_norm,
        "labels": labels,
        "ef_eV": ef_bs,
        "ef_scf_eV": ef_scf,
        "path": path_str,
        "n_occ": n_occ,
    }, indent=2))

    nk_path = eigs_abs.shape[1]
    print(f"  [bands] {mat}: bandas guardadas, nk={nk_path}, EF={ef_bs:.4f} eV")
    print(f"  [bands] {mat}: rango energías = {eigs_abs.min():.2f}–{eigs_abs.max():.2f} eV")

    # --- SOC perturbativo en los k-points del camino ---
    _run_soc_on_bs_calc(mat, calc_bs, ef_bs, out_dir)

    return True


def _run_soc_on_bs_calc(mat: str, calc_bs, ef_bs: float, out_dir: Path) -> None:
    """SOC perturbativo sobre los k-points del camino de bandas."""
    try:
        from gpaw.spinorbit import soc_eigenstates
        is_sn = "Sn" in mat
        soc = soc_eigenstates(
            calc_bs,
            scale=1.0, theta=0.0, phi=0.0,
            ignore_xc_potential=is_sn,  # Sn usa r²SCAN (MGGA) → True; Pb usa PBE → False
        )
        e_kn = soc.eigenvalues()   # (nk_path, 2*nbands) en eV absolutos
        np.save(str(out_dir / "bands_path_soc_eigs.npy"), e_kn)

        occ = e_kn[e_kn <= ef_bs]; unocc = e_kn[e_kn > ef_bs]
        gap = float(unocc.min()) - float(occ.max()) if len(occ) and len(unocc) else 0.0
        print(f"  [soc] {mat}: gap SOC (path) = {gap:.3f} eV")
    except Exception as exc:
        print(f"  [soc] {mat}: SOC falló ({exc})")


def _run_pbe_band(mat: str, mat_dir: Path, out_dir: Path, r2scan_gpw: Path) -> bool:
    """Para Pb organics: PBE SCF en kgrid + fixed_density bands."""
    from gpaw import GPAW, PW
    from gpaw.eigensolvers import Davidson
    from ase.io import read

    pbe_scf_gpw = out_dir / "pbe_scf.gpw"

    # 1. Leer átomos del GPW antiguo con ASE (no necesita cargar calculadora GPAW)
    print(f"  [bands] {mat}: leyendo átomos de {r2scan_gpw.name} …")
    try:
        atoms = read(str(r2scan_gpw))
    except Exception as exc:
        print(f"  [bands] {mat}: ERROR leyendo átomos: {exc}")
        return False

    # 2. PBE SCF con kgrid 6x6x6 (si no existe ya)
    if not pbe_scf_gpw.exists():
        print(f"  [bands] {mat}: corriendo PBE SCF 6x6x6 …")
        calc_pbe = GPAW(
            mode=PW(450),
            xc="PBE",
            kpts={"size": [6, 6, 6], "gamma": True},
            occupations={"name": "fermi-dirac", "width": 0.1},
            eigensolver=Davidson(niter=3),
            convergence={"density": 1e-4, "eigenstates": 1e-6},
            txt=str(out_dir / "pbe_scf.txt"),
        )
        atoms.calc = calc_pbe
        atoms.get_potential_energy()
        calc_pbe.write(str(pbe_scf_gpw))
        print(f"  [bands] {mat}: PBE SCF guardado → {pbe_scf_gpw.name}")
    else:
        print(f"  [bands] {mat}: PBE SCF ya existe, cargando …")

    calc_scf = GPAW(str(pbe_scf_gpw), txt=None)
    atoms = calc_scf.atoms
    ef_scf = calc_scf.get_fermi_level()

    path_str = _band_path_str(atoms)
    print(f"  [bands] {mat}: camino = {path_str}")

    calc_bs = calc_scf.fixed_density(
        kpts={"path": path_str, "npoints": NPOINTS},
        symmetry="off",
        convergence={"eigenstates": 1e-5},
        txt=str(out_dir / "bands_path_calc.txt"),
    )
    atoms.calc = calc_bs
    atoms.get_potential_energy()

    ef_bs = calc_bs.get_fermi_level()
    bs = calc_bs.band_structure()
    eigs_abs = bs.energies + ef_bs

    nvalence = int(calc_bs.get_number_of_electrons())
    nspins_calc = calc_bs.get_number_of_spins()
    n_occ = nvalence // (2 // nspins_calc)

    xcoords, xsp_norm, labels = _xcoords_from_path(bs)
    np.save(str(out_dir / "bands_path_eigs.npy"), eigs_abs)
    np.save(str(out_dir / "bands_path_xcoords.npy"), xcoords)
    (out_dir / "bands_path_special.json").write_text(json.dumps({
        "special_xcoords": xsp_norm,
        "labels": labels,
        "ef_eV": ef_bs,
        "ef_scf_eV": float(calc_scf.get_fermi_level()),
        "path": path_str,
        "xc": "PBE",
        "n_occ": n_occ,
    }, indent=2))

    print(f"  [bands] {mat}: bandas PBE guardadas, EF={ef_bs:.4f} eV")

    # SOC con PBE (no MGGA, no ignore_xc_potential)
    _run_soc_on_bs_calc(mat, calc_bs, ef_bs, out_dir)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mat", default="all",
                        help="Nombre del material o 'all'")
    parser.add_argument("--force", action="store_true",
                        help="Recalcular aunque ya exista el .npy")
    args = parser.parse_args()

    mats = list(MATERIALS.keys()) if args.mat == "all" else [args.mat]

    for mat in mats:
        if mat not in MATERIALS:
            print(f"Material desconocido: {mat}")
            continue
        print(f"\n{'='*50}")
        print(f"=== {mat} ===")
        ok = run_band_calc(mat, force=args.force)
        print(f"  → {'OK' if ok else 'FALLO'}")

    print("\nBand calcs completados.")


if __name__ == "__main__":
    main()
