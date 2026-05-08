"""
Compute HSE06-corrected DOS via non_self_consistent_eigenvalues on a 12x12x12 k-mesh.

Steps:
  1. Re-diagonalize PBE on 12x12x12 from scf.gpw with symmetry, write dos_wfs_sym.gpw with mode='all'
  2. Run non_self_consistent_eigenvalues (HSE06) on dos_wfs_sym.gpw
  3. Compute and save HSE06-corrected DOS arrays
"""

import sys
import time
import re
import numpy as np
from pathlib import Path

sys.path.insert(0, "src")

from gpaw.mpi import world

SCF_GPW       = Path("calculations/alpha/02_scf/scf.gpw")
DOS_WFS_GPW   = Path("calculations/alpha/04_dos/dos_wfs.gpw")
NSC_WFS_GPW   = Path("calculations/alpha/04_dos/dos_wfs_sym.gpw")
NSC_WFS_TXT   = Path("calculations/alpha/04_dos/dos_wfs_sym.txt")
NSC_EIG_PATH  = Path("calculations/alpha/06_hse06/hse06_nsc_dos_eigenvalues.npy")
NSC_TXT       = Path("calculations/alpha/06_hse06/hse06_nsc_dos.txt")
DOS_HSE_DIR   = Path("calculations/alpha/04_dos")
DOS_KPTS       = [12, 12, 12]
SYMMETRY_ON    = {"point_group": True, "time_reversal": True}
MAX_IBZKPTS    = 200


def _validate_ibz(calc, label: str) -> int:
    kd = calc.wfs.kd
    nibz = int(kd.nibzkpts)
    nbz = int(getattr(kd, "nbzkpts", len(kd.bzk_kc)))
    print(f"  {label}: {nibz} irreducible k-points out of {nbz} total")
    if nibz > MAX_IBZKPTS:
        raise RuntimeError(
            f"{label} has {nibz} irreducible k-points. "
            "Symmetry reduction did not take effect; refusing the HSE06 NSC run."
        )
    return nibz


def _validate_ibz_from_log(log_path: Path, label: str) -> int | None:
    if not log_path.exists():
        return None
    text = log_path.read_text(errors="ignore")
    matches = re.findall(r"(\d+) k-points in the irreducible part", text)
    if not matches:
        return None
    nibz = int(matches[-1])
    print(f"  {label}: {nibz} irreducible k-points (from GPAW log)")
    if nibz > MAX_IBZKPTS:
        raise RuntimeError(
            f"{label} has {nibz} irreducible k-points. "
            "Symmetry reduction did not take effect; refusing the HSE06 NSC run."
        )
    return nibz


def _existing_nsc_is_usable() -> bool:
    if not NSC_EIG_PATH.exists():
        return False
    eig = np.load(str(NSC_EIG_PATH), mmap_mode="r")
    n_kpts = int(eig.shape[1])
    if n_kpts > MAX_IBZKPTS:
        print(f"[REGEN] {NSC_EIG_PATH} has {n_kpts} k-points; expected symmetry-reduced mesh")
        return False
    return True


# ── Step 1: PBE non-SCF on 12x12x12 with symmetry-reduced wavefunctions ───────
if DOS_WFS_GPW.exists():
    print(f"[KEEP] Existing full-mesh DOS checkpoint left untouched: {DOS_WFS_GPW}")

regenerated_wfs = False
if NSC_WFS_GPW.exists():
    from gpaw import GPAW
    _validate_ibz(GPAW(str(NSC_WFS_GPW), txt=None), "existing HSE06 NSC wavefunction mesh")
    print(f"[SKIP] {NSC_WFS_GPW} already exists")
else:
    from gpaw import GPAW
    print("=" * 60)
    print("Step 1: PBE non-SCF diagonalisation on 12x12x12 with symmetry (mode='all')")
    print("=" * 60)
    t0 = time.time()
    calc = GPAW(
        str(SCF_GPW),
        fixdensity=True,
        kpts={"size": DOS_KPTS, "gamma": True},
        symmetry=SYMMETRY_ON,
        txt=str(NSC_WFS_TXT),
    )
    atoms = calc.get_atoms()
    atoms.get_potential_energy()
    _validate_ibz(calc, "new HSE06 NSC wavefunction mesh")
    calc.write(str(NSC_WFS_GPW), mode="all")
    world.barrier()
    regenerated_wfs = True
    print(f"Saved {NSC_WFS_GPW}  ({NSC_WFS_GPW.stat().st_size / 1e9:.2f} GB)")
    print(f"Step 1 elapsed: {(time.time()-t0)/60:.1f} min")

# ── Step 2: non_self_consistent_eigenvalues (HSE06) ──────────────────────────
if not regenerated_wfs and _existing_nsc_is_usable():
    print(f"[SKIP] {NSC_EIG_PATH} already exists with symmetry-reduced k-points")
else:
    from gpaw import GPAW
    from gpaw.hybrids.eigenvalues import non_self_consistent_eigenvalues
    print("=" * 60)
    print("Step 2: non_self_consistent_eigenvalues (HSE06) on 12x12x12")
    print("=" * 60)
    t0 = time.time()
    calc_pbe = GPAW(
        str(NSC_WFS_GPW),
        txt=str(NSC_TXT),
    )
    n_ibz = _validate_ibz_from_log(NSC_TXT, "HSE06 NSC input mesh")
    eig_pbe, vxc_pbe, vxc_hse = non_self_consistent_eigenvalues(
        calc_pbe, xcname="HSE06"
    )
    eig_hse = eig_pbe - vxc_pbe + vxc_hse
    if eig_hse.shape[1] > MAX_IBZKPTS:
        raise RuntimeError(
            f"NSC eigenvalue shape has {eig_hse.shape[1]} k-points. "
            "Symmetry reduction did not take effect."
        )
    if n_ibz is not None and eig_hse.shape[1] != n_ibz:
        raise RuntimeError(
            f"NSC eigenvalue shape has {eig_hse.shape[1]} k-points, "
            f"but GPAW reports {n_ibz} irreducible k-points."
        )
    if world.rank == 0:
        tmp_eig = NSC_EIG_PATH.with_suffix(".tmp.npy")
        np.save(str(tmp_eig), eig_hse)
        tmp_eig.replace(NSC_EIG_PATH)
    world.barrier()
    print(f"Saved {NSC_EIG_PATH}  shape={eig_hse.shape}")
    print(f"Step 2 elapsed: {(time.time()-t0)/60:.1f} min")

# ── Step 3: Compute HSE06-corrected DOS ─────────────────────────────────────
print("=" * 60)
print("Step 3: Computing HSE06-corrected DOS")
print("=" * 60)

from gpaw import GPAW
eig_hse = np.load(str(NSC_EIG_PATH))   # shape (n_spin, n_kpts_irr, n_bands)

calc = GPAW(str(NSC_WFS_GPW), txt=None)
_validate_ibz(calc, "HSE06 DOS postprocess mesh")

# k-point weights (irreducible BZ)
kd = calc.wfs.kd
weights = np.array([kd.weight_k[k] for k in range(kd.nibzkpts)])  # sum = 1

n_spin, n_kpts, n_bands = eig_hse.shape
if len(weights) != n_kpts:
    raise RuntimeError(
        f"DOS weights have {len(weights)} k-points, but HSE eigenvalues have {n_kpts}."
    )
print(f"  eigenvalues: {n_spin} spin, {n_kpts} irreducible k-pts, {n_bands} bands")

# EF
vbm_hse = -np.inf
cbm_hse = np.inf
n_occ = int(calc.get_number_of_electrons()) // 2
for s in range(n_spin):
    for k in range(n_kpts):
        vbm_hse = max(vbm_hse, eig_hse[s, k, n_occ - 1])
        cbm_hse = min(cbm_hse, eig_hse[s, k, n_occ])
ef_hse = 0.5 * (vbm_hse + cbm_hse)
gap_hse = cbm_hse - vbm_hse
print(f"  VBM={vbm_hse:.4f} eV  CBM={cbm_hse:.4f} eV  gap={gap_hse:.4f} eV  Ef={ef_hse:.4f} eV")

# Energia
e_min = eig_hse.min() - 1.0
e_max = eig_hse.max() + 1.0
n_pts = 4000
eta = 0.05   # Gaussian smearing, eV
energies = np.linspace(e_min, e_max, n_pts)

dos_hse = np.zeros(n_pts)
for s in range(n_spin):
    for k in range(n_kpts):
        for n in range(n_bands):
            dos_hse += weights[k] * np.exp(-0.5 * ((energies - eig_hse[s, k, n]) / eta) ** 2)
dos_hse /= eta * np.sqrt(2 * np.pi)

# Guardado
np.save(str(DOS_HSE_DIR / "dos_hse_energies.npy"), energies - ef_hse)
np.save(str(DOS_HSE_DIR / "dos_hse_values.npy"), dos_hse)
np.save(str(DOS_HSE_DIR / "vbm_cbm_hse.npy"), np.array([vbm_hse - ef_hse, cbm_hse - ef_hse]))

print(f"  Saved dos_hse_energies.npy, dos_hse_values.npy, vbm_cbm_hse.npy")
print(f"  HSE06 DOS gap: {gap_hse:.4f} eV")
print("Done.")
