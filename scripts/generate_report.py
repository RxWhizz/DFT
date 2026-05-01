"""Generate results_report.md from all available .npy and .gpw outputs.

Usage:
    python3 scripts/generate_report.py
    python3 scripts/generate_report.py --out my_report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CALC = ROOT / "calculations" / "alpha"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(path: Path):
    """Load .npy or return None if missing."""
    p = Path(path)
    return np.load(str(p)) if p.exists() else None


def _gpw(path: Path):
    """Load GPAW calculator or return None if missing."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        from gpaw import GPAW
        return GPAW(str(p), txt=None)
    except Exception:
        return None


def _status(exists: bool) -> str:
    return "✓" if exists else "pending"


def _section(title: str) -> str:
    line = "-" * len(title)
    return f"\n## {title}\n"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def section_structure() -> str:
    out = _section("Structure")
    calc = _gpw(CALC / "01_relax" / "relax.gpw")
    if calc is None:
        return out + "_relax.gpw not found_\n"

    atoms = calc.get_atoms()
    cell = atoms.cell
    a = cell.diagonal()
    vol = atoms.get_volume()
    syms = atoms.get_chemical_symbols()
    pos = atoms.get_positions()

    # Bond lengths (primitive cell: Cs@0, Pb@1, I@2,3,4)
    from itertools import combinations
    bonds = {}
    for i, j in combinations(range(len(atoms)), 2):
        pair = tuple(sorted([syms[i], syms[j]]))
        d = atoms.get_distance(i, j, mic=True)
        key = f"{pair[0]}-{pair[1]}"
        if key not in bonds or d < bonds[key]:
            bonds[key] = d

    out += f"| Parameter | Value |\n|---|---|\n"
    out += f"| Formula | CsPbI₃ (α-phase, Pm-3m) |\n"
    out += f"| Lattice constant a | {a[0]:.4f} Å |\n"
    out += f"| Volume | {vol:.3f} Å³ |\n"
    out += f"| Atoms in cell | {len(atoms)} (Cs×1, Pb×1, I×3) |\n"
    for key, d in sorted(bonds.items()):
        out += f"| d({key}) | {d:.4f} Å |\n"
    return out


def section_electronic() -> str:
    out = _section("Electronic Structure")

    # --- SCF ---
    calc_scf = _gpw(CALC / "02_scf" / "scf.gpw")
    out += "### SCF (PBE)\n"
    if calc_scf:
        e_tot = calc_scf.get_potential_energy()
        ef = calc_scf.get_fermi_level()
        n_elec = int(calc_scf.get_number_of_electrons())
        nk = len(calc_scf.get_bz_k_points())
        nb = calc_scf.get_number_of_bands()
        out += f"| Quantity | Value |\n|---|---|\n"
        out += f"| Total energy | {e_tot:.6f} eV |\n"
        out += f"| Fermi level | {ef:.4f} eV |\n"
        out += f"| Valence electrons | {n_elec} |\n"
        out += f"| k-points (BZ) | {nk} |\n"
        out += f"| Bands | {nb} |\n"
    else:
        out += "_scf.gpw not found_\n"

    # --- Band structure (PBE) ---
    out += "\n### Band Structure (PBE)\n"
    calc_bands = _gpw(CALC / "03_bands" / "bands.gpw")
    if calc_bands:
        ef_b = calc_bands.get_fermi_level()
        nk_b = len(calc_bands.get_bz_k_points())
        eigs = np.array([calc_bands.get_eigenvalues(k) for k in range(nk_b)])
        e = eigs - ef_b
        vbm = float(e[e < 0].max())
        cbm = float(e[e > 0].min())
        gap = cbm - vbm
        out += f"| Quantity | Value |\n|---|---|\n"
        out += f"| VBM (rel. Eᶠ) | {vbm:+.4f} eV |\n"
        out += f"| CBM (rel. Eᶠ) | {cbm:+.4f} eV |\n"
        out += f"| Band gap (PBE) | **{gap:.4f} eV** |\n"
        out += f"| Gap type | Direct (R-point) |\n"
        out += f"| k-points on path | {nk_b} |\n"
    else:
        out += "_bands.gpw not found_\n"

    # --- SOC ---
    out += "\n### Spin-Orbit Coupling (perturbative, PBE+SOC)\n"
    soc = _load(CALC / "05_soc" / "soc_eigenvalues.npy")
    if soc is not None:
        n_occ = 44
        vbm_soc = float(soc[:, n_occ - 1].max())
        cbm_soc = float(soc[:, n_occ].min())
        gap_soc = cbm_soc - vbm_soc
        soc_shift = gap_soc - (gap if calc_bands else float("nan"))
        out += f"| Quantity | Value |\n|---|---|\n"
        out += f"| Band gap (PBE+SOC) | **{gap_soc:.4f} eV** |\n"
        out += f"| SOC gap correction | {soc_shift:+.4f} eV |\n"
        out += f"| SOC bands | {soc.shape[1]} (2× original) |\n"
        out += f"| k-points | {soc.shape[0]} |\n"
        sp = _load(CALC / "05_soc" / "soc_spin_projections.npy")
        if sp is not None:
            out += f"| Spin projection shape | {sp.shape} |\n"
    else:
        out += "_soc_eigenvalues.npy not found_\n"

    # --- HSE06 ---
    out += "\n### HSE06 Hybrid Functional\n"
    hse_gpw = CALC / "06_hse06" / "hse06.gpw"
    if hse_gpw.exists():
        calc_hse = _gpw(hse_gpw)
        if calc_hse:
            n_occ_h = int(calc_hse.get_number_of_electrons()) // 2
            nk_h = len(calc_hse.get_bz_k_points())
            eigs_h = np.array([calc_hse.get_eigenvalues(k) for k in range(nk_h)])
            ef_h = calc_hse.get_fermi_level()
            e_h = eigs_h - ef_h
            vbm_h = float(e_h[e_h < 0].max())
            cbm_h = float(e_h[e_h > 0].min())
            gap_h = cbm_h - vbm_h
            out += f"| Quantity | Value |\n|---|---|\n"
            out += f"| Band gap (HSE06) | **{gap_h:.4f} eV** |\n"
            out += f"| Gap type | Direct (R-point) |\n"
            out += f"| Exp. reference | ~1.73 eV |\n"
    else:
        out += "_Status: pending — hse06.gpw not yet generated_\n"

    return out


def section_effective_masses() -> str:
    out = _section("Effective Masses and Structural Metrics")
    path = CALC / "10_effective_masses" / "electronic_analysis.json"
    if not path.exists():
        return out + "_Status: pending — effective_masses step not yet run_\n"

    data = json.loads(path.read_text())
    out += "| Quantity | Value |\n|---|---|\n"
    out += f"| Gap type | {data.get('gap_type', 'N/A')} |\n"
    out += f"| Gap | {data.get('gap_eV', 0.0):.4f} eV |\n"
    out += f"| Direct gap | {data.get('direct_gap_eV', 0.0):.4f} eV |\n"
    out += f"| VBM k-point | {data.get('vbm_kpt_frac')} |\n"
    out += f"| CBM k-point | {data.get('cbm_kpt_frac')} |\n"
    out += f"| Electron effective mass | {data.get('m_e_m0', 0.0):.3f} m₀ |\n"
    out += f"| Hole effective mass | {data.get('m_h_m0', 0.0):.3f} m₀ |\n"
    out += f"| Reduced mass | {data.get('m_reduced_m0', 0.0):.3f} m₀ |\n"
    out += f"| Goldschmidt tolerance factor t | {data.get('tolerance_factor', 0.0):.3f} |\n"
    out += f"| Octahedral factor μ | {data.get('octahedral_factor', 0.0):.3f} |\n"
    out += f"| Mean Pb-I bond | {data.get('mean_bx_bond_Ang', 0.0):.4f} Å |\n"
    out += f"| Pb-I bond variance | {data.get('bx_bond_variance', 0.0):.4e} Å² |\n"

    flags = data.get("flags_gap", []) + data.get("flags_masses", []) + data.get("flags_structural", [])
    out += f"| Flags | {', '.join(flags) if flags else 'none'} |\n"
    return out


def section_vibrational() -> str:
    out = _section("Vibrational Properties")

    # --- Hessian (Γ-point) ---
    out += "### Γ-Point Hessian (finite-displacement, ASE)\n"
    H = _load(CALC / "07_vibrational" / "hessian" / "hessian.npy")
    if H is not None:
        calc_r = _gpw(CALC / "01_relax" / "relax.gpw")
        masses = calc_r.get_atoms().get_masses() if calc_r else None
        if masses is not None:
            m_rep = np.repeat(masses, 3)
            D = H / np.sqrt(np.outer(m_rep, m_rep))
            eigvals = np.linalg.eigvalsh(D)
            eVA2amu = 1.602176634e-19 / (1e-20 * 1.66053906660e-27)
            freqs = np.sign(eigvals) * np.sqrt(np.abs(eigvals) * eVA2amu) / (2 * np.pi * 2.998e10)
            n_imag = int(np.sum(freqs < -10.0))
            out += f"| Quantity | Value |\n|---|---|\n"
            out += f"| Modes at Γ | {len(freqs)} (3N, N=5) |\n"
            out += f"| Imaginary modes (< −10 cm⁻¹) | {n_imag} |\n"
            out += f"| Acoustic range | {freqs[:3].min():.1f} – {freqs[:3].max():.1f} cm⁻¹ |\n"
            out += f"| Optical range | {freqs[3:].min():.1f} – {freqs[3:].max():.1f} cm⁻¹ |\n"
            out += f"\n**All Γ-point frequencies (cm⁻¹):**\n\n"
            out += "| Mode | Freq (cm⁻¹) | Character |\n|---|---|---|\n"
            chars = ["acoustic"] * 3 + ["optical"] * (len(freqs) - 3)
            for i, (f, c) in enumerate(zip(freqs, chars)):
                flag = " ⚠ imaginary" if f < -10 else ""
                out += f"| {i+1:2d} | {f:8.2f} | {c}{flag} |\n"
    else:
        out += "_hessian.npy not found_\n"

    # --- Phonopy force sets ---
    out += "\n### Phonopy Force Sets (Δ = 0.02 Å, 2×2×2 supercell)\n"
    phonon_dir = CALC / "07_vibrational" / "phonons"
    forces = []
    for i in range(3):
        f = _load(phonon_dir / f"forces_{i:03d}.npy")
        forces.append(f)

    n_done = sum(1 for f in forces if f is not None)
    out += f"| Displacements computed | {n_done} / 3 |\n"

    if n_done > 0:
        out += f"\n| Disp | Atom | Max\\|F\\| (eV/Å) | Mean\\|F\\| (eV/Å) | ASR residual | ASR (%) |\n"
        out += "|---|---|---|---|---|---|\n"

        disp_yaml = phonon_dir / "phonopy_disp.yaml"
        atom_labels = {}
        if disp_yaml.exists():
            try:
                import yaml
                with open(disp_yaml) as fh:
                    d = yaml.safe_load(fh)
                for idx, disp in enumerate(d["displacements"]):
                    atom_labels[idx] = f"atom {disp['atom']}  {disp['displacement']}"
            except Exception:
                pass

        for i, f in enumerate(forces):
            if f is None:
                out += f"| {i} | — | pending | — | — | — |\n"
                continue
            fmax = float(np.abs(f).max())
            fmean = float(np.abs(f).mean())
            asr = float(np.abs(f.sum(axis=0)).max())
            asr_pct = asr / fmax * 100 if fmax > 0 else 0.0
            label = atom_labels.get(i, f"disp {i}")
            out += f"| {i} | {label} | {fmax:.5f} | {fmean:.5f} | {asr:.2e} | {asr_pct:.3f}% |\n"

    # --- Phonopy result (post-processing) ---
    freq_file = phonon_dir / "phonon_frequencies_phonopy.npy"
    if freq_file.exists():
        out += "\n### Phonon Dispersion (Phonopy + ASR)\n"
        freqs_cm1 = np.load(str(freq_file))
        n_imag = int(np.sum(freqs_cm1 < -10.0))
        out += f"| Quantity | Value |\n|---|---|\n"
        out += f"| q-points on path | {freqs_cm1.shape[0]} |\n"
        out += f"| Branches | {freqs_cm1.shape[1]} |\n"
        out += f"| Min frequency | {freqs_cm1.min():.2f} cm⁻¹ |\n"
        out += f"| Max frequency | {freqs_cm1.max():.2f} cm⁻¹ |\n"
        out += f"| Imaginary modes (< −10 cm⁻¹) | {n_imag} |\n"
        if n_imag == 0:
            out += f"| Stability | **Dynamically stable** ✓ |\n"
        else:
            worst = float(freqs_cm1[freqs_cm1 < -10.0].min())
            out += f"| Stability | ⚠ {n_imag} imaginary mode(s), worst: {worst:.1f} cm⁻¹ |\n"
    else:
        out += "\n_Phonon dispersion: pending (force set incomplete)_\n"

    return out


def section_loto() -> str:
    out = _section("LO-TO Correction (Born Charges + ε∞)")

    Z = _load(CALC / "08_loto" / "born_charges.npy")
    eps = _load(CALC / "08_loto" / "dielectric_tensor.npy")

    if Z is None or eps is None:
        out += "_Status: pending — born_charges.npy / dielectric_tensor.npy not found_\n"
        return out

    calc_r = _gpw(CALC / "01_relax" / "relax.gpw")
    syms = calc_r.get_atoms().get_chemical_symbols() if calc_r else [f"atom{i}" for i in range(len(Z))]

    out += "### Dielectric Tensor (ε∞)\n\n"
    out += f"| | x | y | z |\n|---|---|---|---|\n"
    for i, row in enumerate(eps):
        label = ["x", "y", "z"][i]
        out += f"| {label} | {row[0]:.4f} | {row[1]:.4f} | {row[2]:.4f} |\n"
    out += f"\nIsotropic average: ε∞ = {np.trace(eps)/3:.4f}\n"

    out += "\n### Born Effective Charges Z* (diagonal elements)\n\n"
    out += f"| Atom | Z*_xx | Z*_yy | Z*_zz | Mean |Z*| |\n|---|---|---|---|---|\n"
    for i, (sym, Zi) in enumerate(zip(syms, Z)):
        out += (f"| {sym}{i+1} | {Zi[0,0]:+.4f} | {Zi[1,1]:+.4f} | {Zi[2,2]:+.4f} "
                f"| {np.abs(Zi).mean():.4f} |\n")

    # Acoustic sum rule on Z*
    Z_sum = Z.sum(axis=0)
    asr_max = float(np.abs(Z_sum).max())
    out += f"\nBorn charge ASR (Σ Z* → 0), max element: {asr_max:.4f} e\n"
    if asr_max < 0.1:
        out += "(ASR satisfied ✓)\n"
    else:
        out += "(⚠ ASR violation — check LOTO calculation)\n"

    return out


def section_pes() -> str:
    out = _section("Quasi-Zero/Negative-Mode PES Scan")
    pes_dir = CALC / "07_vibrational" / "pes"
    q_path = pes_dir / "pes_displacements.npy"
    e_path = pes_dir / "pes_energies.npy"
    if not (q_path.exists() and e_path.exists()):
        return out + "_Status: pending — PES scan not yet run_\n"

    q = np.load(str(q_path))
    e = np.load(str(e_path))
    i_min = int(np.argmin(e))
    i_max = int(np.argmax(e))
    span_mev = float((e.max() - e.min()) * 1000.0)

    # Mirror the deterministic detector in analysis.pes for report consistency.
    i_saddle = i_max
    double_well = False
    barrier_mev = 0.0
    q_saddle = 0.0
    q_min1 = q[0]
    q_min2 = q[-1]
    if 0 < i_saddle < len(e) - 1:
        i_left = int(np.argmin(e[:i_saddle]))
        i_right = int(np.argmin(e[i_saddle + 1:])) + i_saddle + 1
        barrier_mev = float((e[i_saddle] - max(e[i_left], e[i_right])) * 1000.0)
        double_well = barrier_mev > 10.0
        q_saddle = float(q[i_saddle])
        q_min1 = float(q[i_left])
        q_min2 = float(q[i_right])

    n_cache = len([p for p in (pes_dir / "scan_mode0").glob("E_*.npy") if p.stem != "E_ref"])
    out += "| Quantity | Value |\n|---|---|\n"
    out += f"| Points computed | {len(e)} ({n_cache} cached SCF energies) |\n"
    out += f"| Q range | {q.min():+.3f} to {q.max():+.3f} Å |\n"
    out += f"| Minimum E(Q)-E(0) | {e[i_min]:.6f} eV at Q = {q[i_min]:+.3f} Å |\n"
    out += f"| Maximum E(Q)-E(0) | {e[i_max]:.6f} eV at Q = {q[i_max]:+.3f} Å |\n"
    out += f"| Energy span | {span_mev:.2f} meV |\n"
    out += f"| Double well detected | {'yes' if double_well else 'no'} |\n"
    out += f"| Barrier for criterion | {barrier_mev:.1f} meV |\n"
    if double_well:
        out += f"| Saddle Q | {q_saddle:+.3f} Å |\n"
        out += f"| Minima Q | {q_min1:+.3f}, {q_min2:+.3f} Å |\n"
        out += "| CI-NEB | should be launched by workflow |\n"
    else:
        out += "| CI-NEB | not launched (no double well) |\n"
    out += f"| Plot | `{pes_dir.relative_to(ROOT)}/pes_scan.png` |\n"
    return out


def section_optical() -> str:
    out = _section("Optical Properties")
    opt_dir = CALC / "11_optical"
    omega_path = opt_dir / "optical_frequencies.npy"

    if not omega_path.exists():
        out += "_Status: pending — optical step not yet run_\n"
        return out

    omega = np.load(str(omega_path))
    eps1  = np.load(str(opt_dir / "eps1.npy"))
    eps2  = np.load(str(opt_dir / "eps2.npy"))
    alpha = np.load(str(opt_dir / "absorption_cm1.npy"))

    n_path = opt_dir / "n_omega.npy"
    k_path = opt_dir / "k_omega.npy"
    if n_path.exists():
        n_w = np.load(str(n_path))
        k_w = np.load(str(k_path))
    else:
        sqrt_eps = np.sqrt(eps1 + 1j * eps2)
        n_w = np.real(sqrt_eps)
        k_w = np.imag(sqrt_eps)

    onset_mask = alpha > 1e4
    onset_eV   = float(omega[onset_mask][0]) if onset_mask.any() else None
    eps_inf    = float(eps1[1]) if len(eps1) > 1 else None

    # AM1.5G score
    _AM15G_EV   = np.array([0.31,0.50,0.75,1.00,1.25,1.50,1.75,2.00,
                             2.25,2.50,2.75,3.00,3.25,3.50,3.75,4.00,4.25,4.50])
    _AM15G_WATT = np.array([8,52,180,430,650,740,750,680,
                            600,520,440,360,270,190,120,70,35,12], dtype=float)
    irr_w  = np.interp(omega, _AM15G_EV, _AM15G_WATT, left=0.0, right=0.0)
    norm   = float(np.trapezoid(_AM15G_WATT, _AM15G_EV)) * 1e5
    if onset_eV is not None:
        num = float(np.trapezoid(alpha * irr_w * (omega >= onset_eV), omega))
    else:
        num = 0.0
    score = min(num / norm, 1.0) if norm > 0 else 0.0

    # Check for scissor flag in CSV header (best effort)
    scissor_str = "N/A"
    csv_path = opt_dir / "dielectric_function.csv"
    if csv_path.exists():
        try:
            first = csv_path.read_text().splitlines()[0]
            if "scissor" in first.lower() or "eshift" in first.lower():
                scissor_str = first
        except Exception:
            pass

    out += f"_RPA, GPAW linear response · scissor: {scissor_str}_\n\n"
    out += "### Key Metrics\n\n"
    out += f"| Quantity | Value |\n|---|---|\n"
    out += f"| ε∞ (ω → 0) | {eps_inf:.4f} |\n" if eps_inf else "| ε∞ | N/A |\n"
    out += f"| Absorption onset | {onset_eV:.3f} eV |\n" if onset_eV else "| Absorption onset | not reached |\n"

    for e in [1.5, 2.0, 2.5, 3.0]:
        a = float(np.interp(e, omega, alpha))
        out += f"| α @ {e} eV | {a:.3e} cm⁻¹ |\n"

    out += f"| AM1.5G visible score | {score:.4f} [0–1] |\n"

    pv = "**prometedor** ✓" if (onset_eV and onset_eV < 2.0 and score > 0.05) else "marginal / pendiente"
    out += f"| Criterio PV (α ≥ 10⁴ cm⁻¹) | {pv} |\n"

    # Sampled table at representative energies
    out += "\n### Dielectric Function (sampled)\n\n"
    out += "| ω (eV) | ε₁ | ε₂ | n | k | α (cm⁻¹) |\n|---|---|---|---|---|---|\n"
    sample_eV = [0.5, 1.0, 1.5, 1.73, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    for e in sample_eV:
        if e > omega.max():
            continue
        e1 = float(np.interp(e, omega, eps1))
        e2 = float(np.interp(e, omega, eps2))
        nv = float(np.interp(e, omega, n_w))
        kv = float(np.interp(e, omega, k_w))
        av = float(np.interp(e, omega, alpha))
        out += f"| {e:.2f} | {e1:.4f} | {e2:.4f} | {nv:.4f} | {kv:.4f} | {av:.3e} |\n"

    # Save full CSV table for external plotting
    csv_out = opt_dir / "optical_spectrum_table.csv"
    try:
        header_csv = "omega_eV,eps1,eps2,n,k,alpha_cm1"
        data = np.column_stack([omega, eps1, eps2, n_w, k_w, alpha])
        np.savetxt(str(csv_out), data, delimiter=",", header=header_csv, comments="")
        out += f"\n_Full spectrum saved to [{csv_out.name}]({csv_out.relative_to(ROOT)}) for plotting._\n"
    except Exception:
        pass

    return out


def section_device_optics() -> str:
    """Beer-Lambert device optics section: G(x), η_opt, J_sc limit."""
    optical_dir = CALC / "11_optical"
    gen_path = optical_dir / "device_generation_rate.npy"
    x_path   = optical_dir / "device_x_cm.npy"

    out = _section("Device Optics (Beer-Lambert)")

    if not (optical_dir / "optical_frequencies.npy").exists():
        return out + "_Status: pending — optical step not yet run_\n"

    if not gen_path.exists():
        # Compute on-the-fly if optical npy exists
        try:
            sys.path.insert(0, str(ROOT / "src"))
            from dft_cspbi3.analysis.optical_device import compute_device_optics
            result = compute_device_optics(optical_dir, thickness_nm=500.0)
        except Exception as exc:
            return out + f"_Device optics failed: {exc}_\n"
    else:
        try:
            sys.path.insert(0, str(ROOT / "src"))
            from dft_cspbi3.analysis.optical_device import compute_device_optics
            result = compute_device_optics(optical_dir, thickness_nm=500.0)
        except Exception as exc:
            return out + f"_Device optics reload failed: {exc}_\n"

    if result is None:
        return out + "_Status: pending — required .npy files missing_\n"

    out += "| Quantity | Value |\n|---|---|\n"
    out += f"| Absorber thickness | {result.thickness_cm * 1e7:.0f} nm |\n"
    out += f"| Optical efficiency η_opt | {result.optical_efficiency:.4f} |\n"
    out += f"| Absorbed photon flux | {result.absorbed_photon_flux:.3e} photons/cm²/s |\n"
    out += f"| Incident photon flux (AM1.5G) | {result.incident_photon_flux:.3e} photons/cm²/s |\n"
    out += f"| J_sc limit (IQE=1) | **{result.jsc_limit_mA_cm2:.2f} mA/cm²** |\n"
    if result.flags:
        out += f"\n_Flags: {', '.join(result.flags)}_\n"
    return out


def section_soc_hse06() -> str:
    """HSE06+SOC band gap section."""
    soc_dir  = CALC / "05_soc"
    hse_eigs = soc_dir / "soc_hse06_eigenvalues.npy"
    hse_gpw  = CALC / "06_hse06" / "hse06.gpw"

    out = _section("HSE06 + Spin-Orbit Coupling")

    if not hse_gpw.exists():
        return out + "_Status: pending — hse06.gpw not yet generated_\n"

    if not hse_eigs.exists():
        return out + "_Status: pending — soc_hse06 step not yet run_\n"

    eigs = _load(hse_eigs)
    if eigs is None:
        return out + "_Status: file unreadable_\n"

    ef = float(np.median(eigs.flatten()))
    occupied   = eigs[eigs < ef]
    unoccupied = eigs[eigs >= ef]
    if len(occupied) and len(unoccupied):
        gap = float(unoccupied.min() - occupied.max())
        vbm = float(occupied.max())
        cbm = float(unoccupied.min())
        out += "| Quantity | Value |\n|---|---|\n"
        out += f"| Band gap (HSE06+SOC) | **{gap:.4f} eV** |\n"
        out += f"| VBM (rel. E_F approx) | {vbm - ef:.4f} eV |\n"
        out += f"| CBM (rel. E_F approx) | {cbm - ef:.4f} eV |\n"
        out += f"| SOC bands | {eigs.shape[-1]} |\n"
    else:
        out += "_Could not extract gap from eigenvalue array_\n"
    return out


def section_formation_energy() -> str:
    out = _section("Formation Energy")
    path = CALC / "09_formation_energy" / "formation_energy.json"
    if not path.exists():
        return out + "_Status: pending — formation_energy step not yet run_\n"

    data = json.loads(path.read_text())
    out += "| Quantity | Value |\n|---|---|\n"
    out += f"| ΔHf | **{data['delta_Hf_eV']:+.6f} eV/f.u.** |\n"
    out += f"| E(CsPbI₃) | {data['E_perovskite_per_fu_eV']:.6f} eV/f.u. |\n"
    out += f"| E(CsI) | {data['E_CsI_per_fu_eV']:.6f} eV/f.u. |\n"
    out += f"| E(PbI₂) | {data['E_PbI2_per_fu_eV']:.6f} eV/f.u. |\n"
    out += f"| Stability vs CsI + PbI₂ | {'stable' if data.get('stable') else 'unstable'} |\n"
    out += f"| Summary | {data.get('summary', '')} |\n"
    return out


def section_defects() -> str:
    """Defect formation energies section."""
    defect_dir  = CALC / "13_defects"
    result_file = defect_dir / "defect_formation_energies.txt"

    out = _section("Point Defects (Intrinsic)")

    if not result_file.exists():
        return out + (
            "_Status: pending — defect calculations not yet run_\n\n"
            "**Defects planned**: V_I, I_i, V_Pb, V_Cs, Pb_I, I_Pb "
            "(2×2×2 supercell, MACE geometry + DFT single-point)\n"
        )

    lines = result_file.read_text().splitlines()
    out += "\n".join(lines) + "\n"
    return out


def section_migration() -> str:
    """Ion migration barriers section."""
    mig_dir = CALC / "14_migration"
    out = _section("Ionic Migration (CI-NEB)")

    if not mig_dir.exists():
        return out + (
            "_Status: pending — NEB calculations not yet run_\n\n"
            "**Routes planned**: V_I ⟨100⟩, V_I ⟨110⟩, I_i ⟨100⟩, V_Cs ⟨100⟩\n"
            "Literature: V_I barrier ≈ 0.1–0.25 eV (Azpiroz 2015)\n"
        )

    # Look for individual path summaries
    neb_dirs = sorted(mig_dir.glob("V_I_*/"))
    if not neb_dirs:
        return out + "_Status: pending — no NEB results found_\n"

    out += "| Path | Barrier fwd (meV) | Barrier rev (meV) | Converged |\n"
    out += "|------|-------------------|-------------------|-----------|\n"
    for d in neb_dirs:
        log_files = list(d.glob("neb_*.txt"))
        label = d.name
        out += f"| {label} | — | — | — |\n"
    return out


def section_kmc() -> str:
    """kMC photostability section."""
    kmc_dir = CALC / "15_kmc"
    out = _section("Kinetic Monte Carlo (Photostability)")

    summary_file = kmc_dir / "kmc_summary.txt"
    if not summary_file.exists():
        return out + (
            "_Status: pending — requires NEB barriers (L4) as input_\n\n"
            "**Method**: BKL algorithm, O(N) per event\n"
            "**Inputs**: V_I hop barrier, G(x) photogeneration rate\n"
        )

    lines = summary_file.read_text().splitlines()
    out += "```\n" + "\n".join(lines) + "\n```\n"
    return out


def section_aimd() -> str:
    """MACE-AIMD thermal stability section."""
    aimd_dir = CALC / "16_aimd_mlip"
    out = _section("Thermal Stability (MACE-AIMD Screening)")

    if not aimd_dir.exists():
        return out + (
            "_Status: pending — install mace-torch and run screen_thermal_stability()_\n\n"
            "**Method**: NVT Langevin + MACE-MP-0, 10 ps/temperature\n"
            "**Temperatures**: 300/400/500/600 K\n"
            "**Costo**: ~5 min/T en CPU\n"
        )

    summaries = sorted(aimd_dir.glob("*/aimd_*K_summary.txt"))
    if not summaries:
        return out + "_Status: running or no summaries found_\n"

    out += "| T (K) | RMSD final (Å) | RDF Pb-I peak (Å) | Label |\n"
    out += "|-------|----------------|-------------------|-------|\n"
    for sf in summaries:
        data = {}
        for line in sf.read_text().splitlines():
            if " = " in line:
                k, v = line.split(" = ", 1)
                data[k.strip()] = v.strip()
        T       = data.get("T_K", "?")
        rmsd    = data.get("rmsd_final_Ang", "?")
        peak    = data.get("pbi_rdf_peak_Ang", "?")
        label   = data.get("label", "?")
        out += f"| {T} | {rmsd} | {peak} | {label} |\n"
    return out


def section_qha() -> str:
    """Quasi-Harmonic Approximation section."""
    qha_dir   = CALC / "15_qha"
    gibbs_npy = qha_dir / "qha_gibbs.npy"
    alpha_npy = qha_dir / "qha_alpha.npy"
    temps_npy = qha_dir / "qha_temperatures.npy"

    out = _section("Quasi-Harmonic Approximation (QHA)")

    if not gibbs_npy.exists():
        return out + (
            "_Status: pending — requires phonon force sets at 6 volumes (~42 h)_\n\n"
            "**Outputs**: G(T), α(T) thermal expansion, C_p(T), V_eq(T), B₀\n"
            "**Validity**: T < ~320 K (mode-softening limit for α-phase)\n"
        )

    T_arr = _load(temps_npy)
    G_arr = _load(gibbs_npy)
    a_arr = _load(alpha_npy)

    if T_arr is None or G_arr is None:
        return out + "_Status: QHA npy files unreadable_\n"

    # Tabulate a few representative temperatures
    out += "| T (K) | G(T) (eV/cell) | α(T) (1/K) |\n|---|---|---|\n"
    for i, T in enumerate(T_arr):
        if int(T) % 100 == 0:
            G = float(G_arr[i]) if i < len(G_arr) else float("nan")
            a = float(a_arr[i]) if a_arr is not None and i < len(a_arr) else float("nan")
            out += f"| {T:.0f} | {G:.4f} | {a:.3e} |\n"
    return out


def section_status() -> str:
    out = _section("Calculation Status")
    steps = {
        "01 Relax":         CALC / "01_relax" / "relax.gpw",
        "02 SCF":           CALC / "02_scf" / "scf.gpw",
        "03 Bands":         CALC / "03_bands" / "bands.gpw",
        "04 DOS":           CALC / "04_dos" / "dos.gpw",
        "05 SOC":           CALC / "05_soc" / "soc_eigenvalues.npy",
        "05 HSE06+SOC":     CALC / "05_soc" / "soc_hse06_eigenvalues.npy",
        "06 HSE06":         CALC / "06_hse06" / "hse06.gpw",
        "07 Hessian":       CALC / "07_vibrational" / "hessian" / "hessian.npy",
        "07 Phonons (disp 0)": CALC / "07_vibrational" / "phonons" / "forces_000.npy",
        "07 Phonons (disp 1)": CALC / "07_vibrational" / "phonons" / "forces_001.npy",
        "07 Phonons (disp 2)": CALC / "07_vibrational" / "phonons" / "forces_002.npy",
        "07 Phonons (dispersion)": CALC / "07_vibrational" / "phonons" / "phonon_frequencies_phonopy.npy",
        "07 PES":           CALC / "07_vibrational" / "pes" / "pes_energies.npy",
        "08 LOTO":          CALC / "08_loto" / "born_charges.npy",
        "09 Formation energy": CALC / "09_formation_energy" / "formation_energy.json",
        "10 Effective masses": CALC / "10_effective_masses" / "electronic_analysis.json",
        "11 Optical":       CALC / "11_optical" / "optical_frequencies.npy",
        "11 Device optics": CALC / "11_optical" / "device_generation_rate.npy",
        "13 Defects":       CALC / "13_defects" / "defect_formation_energies.txt",
        "14 Migration NEB": CALC / "14_migration",
        "15 kMC":           CALC / "15_kmc" / "kmc_summary.txt",
        "15 QHA":           CALC / "15_qha" / "qha_gibbs.npy",
        "16 AIMD-MLIP":     CALC / "16_aimd_mlip",
    }
    out += f"| Step | Status |\n|---|---|\n"
    for name, path in steps.items():
        out += f"| {name} | {_status(Path(path).exists())} |\n"
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_report() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"# α-CsPbI₃ DFT Results Report\n\n"
    header += f"_Generated: {now}_  \n"
    header += f"_Method: GPAW · PBE-PW · PAW · Phonopy_\n"

    return (
        header
        + section_status()
        + section_structure()
        + section_electronic()
        + section_effective_masses()
        + section_vibrational()
        + section_pes()
        + section_loto()
        + section_optical()
        + section_device_optics()
        + section_soc_hse06()
        + section_formation_energy()
        + section_defects()
        + section_migration()
        + section_kmc()
        + section_aimd()
        + section_qha()
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="results_report.md")
    args = parser.parse_args()

    import os
    os.chdir(ROOT)

    report = build_report()
    out_path = ROOT / args.out
    out_path.write_text(report)
    print(f"Report written to {out_path}")
