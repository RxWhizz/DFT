"""Genera results_report.md desde.npy/.gpw."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CALC = ROOT / "calculations" / "alpha"


# Helpers

def _load(path: Path):
    """Carga.npy; falta → None."""
    p = Path(path)
    return np.load(str(p)) if p.exists() else None


def _gpw(path: Path):
    """Carga GPAW; falta → None."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        from gpaw import GPAW
        return GPAW(str(p), txt=None)
    except Exception:
        return None


def _status(exists: bool) -> str:
    return "✓" if exists else "pendiente"


def _section(title: str) -> str:
    line = "-" * len(title)
    return f"\n## {title}\n"


def _gap_tipo(value: str | None) -> str:
    """Traduce tipo gap si viene de JSON."""
    mapping = {"direct": "directo", "indirect": "indirecto"}
    return mapping.get(str(value or "N/A").lower(), str(value or "N/A"))


# Constructores sección

def section_structure() -> str:
    out = _section("Estructura")
    calc = _gpw(CALC / "01_relax" / "relax.gpw")
    if calc is None:
        return out + "_relax.gpw no encontrado_\n"

    atoms = calc.get_atoms()
    cell = atoms.cell
    a = cell.diagonal()
    vol = atoms.get_volume()
    syms = atoms.get_chemical_symbols()
    pos = atoms.get_positions()

    # Enlaces celda primitiva.
    from itertools import combinations
    bonds = {}
    for i, j in combinations(range(len(atoms)), 2):
        pair = tuple(sorted([syms[i], syms[j]]))
        d = atoms.get_distance(i, j, mic=True)
        key = f"{pair[0]}-{pair[1]}"
        if key not in bonds or d < bonds[key]:
            bonds[key] = d

    out += f"| Parámetro | Valor |\n|---|---|\n"
    out += f"| Fórmula | CsPbI₃ (fase α, Pm-3m) |\n"
    out += f"| Constante red a | {a[0]:.4f} Å |\n"
    out += f"| Volumen | {vol:.3f} Å³ |\n"
    out += f"| Átomos celda | {len(atoms)} (Cs×1, Pb×1, I×3) |\n"
    for key, d in sorted(bonds.items()):
        out += f"| d({key}) | {d:.4f} Å |\n"
    return out


def section_electronic() -> str:
    out = _section("Estructura Electrónica")

    # SCF
    calc_scf = _gpw(CALC / "02_scf" / "scf.gpw")
    out += "### SCF (PBE)\n"
    if calc_scf:
        e_tot = calc_scf.get_potential_energy()
        ef = calc_scf.get_fermi_level()
        n_elec = int(calc_scf.get_number_of_electrons())
        nk = len(calc_scf.get_bz_k_points())
        nb = calc_scf.get_number_of_bands()
        out += f"| Magnitud | Valor |\n|---|---|\n"
        out += f"| Energía total | {e_tot:.6f} eV |\n"
        out += f"| Nivel Fermi | {ef:.4f} eV |\n"
        out += f"| Electrones valencia | {n_elec} |\n"
        out += f"| puntos k (BZ) | {nk} |\n"
        out += f"| Bandas | {nb} |\n"
    else:
        out += "_scf.gpw no encontrado_\n"

    # Bandas (PBE)
    out += "\n### Bandas (PBE)\n"
    calc_bands = _gpw(CALC / "03_bands" / "bands.gpw")
    if calc_bands:
        ef_b = calc_bands.get_fermi_level()
        nk_b = len(calc_bands.get_bz_k_points())
        eigs = np.array([calc_bands.get_eigenvalues(k) for k in range(nk_b)])
        e = eigs - ef_b
        vbm = float(e[e < 0].max())
        cbm = float(e[e > 0].min())
        gap = cbm - vbm
        out += f"| Magnitud | Valor |\n|---|---|\n"
        out += f"| VBM (rel. Eᶠ) | {vbm:+.4f} eV |\n"
        out += f"| CBM (rel. Eᶠ) | {cbm:+.4f} eV |\n"
        out += f"| Gap (PBE) | **{gap:.4f} eV** |\n"
        out += f"| Tipo gap | Directo (punto R) |\n"
        out += f"| puntos k ruta | {nk_b} |\n"
    else:
        out += "_bands.gpw no encontrado_\n"

    # SOC
    out += "\n### SOC perturbativo (PBE+SOC)\n"
    soc = _load(CALC / "05_soc" / "soc_eigenvalues.npy")
    if soc is not None:
        n_occ = 44
        vbm_soc = float(soc[:, n_occ - 1].max())
        cbm_soc = float(soc[:, n_occ].min())
        gap_soc = cbm_soc - vbm_soc
        soc_shift = gap_soc - (gap if calc_bands else float("nan"))
        out += f"| Magnitud | Valor |\n|---|---|\n"
        out += f"| Gap (PBE+SOC) | **{gap_soc:.4f} eV** |\n"
        out += f"| Corrección gap SOC | {soc_shift:+.4f} eV |\n"
        out += f"| Bandas SOC | {soc.shape[1]} (2× original) |\n"
        out += f"| puntos k | {soc.shape[0]} |\n"
        sp = _load(CALC / "05_soc" / "soc_spin_projections.npy")
        if sp is not None:
            out += f"| Forma proyección espín | {sp.shape} |\n"
    else:
        out += "_soc_eigenvalues.npy no encontrado_\n"

    # HSE06
    out += "\n### Funcional Híbrido HSE06\n"
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
            out += f"| Magnitud | Valor |\n|---|---|\n"
            out += f"| Gap (HSE06) | **{gap_h:.4f} eV** |\n"
            out += f"| Tipo gap | Directo (punto R) |\n"
            out += f"| Ref. exp. | ~1.73 eV |\n"
    else:
        out += "_Estado: pendiente - hse06.gpw no generado_\n"

    return out


def section_effective_masses() -> str:
    out = _section("Masas Efectivas y Métricas Estructurales")
    path = CALC / "10_effective_masses" / "electronic_analysis.json"
    if not path.exists():
        return out + "_Estado: pendiente - paso effective_masses no corrido_\n"

    data = json.loads(path.read_text())
    out += "| Magnitud | Valor |\n|---|---|\n"
    out += f"| Tipo gap | {_gap_tipo(data.get('gap_type'))} |\n"
    out += f"| Gap | {data.get('gap_eV', 0.0):.4f} eV |\n"
    out += f"| Gap directo | {data.get('direct_gap_eV', 0.0):.4f} eV |\n"
    out += f"| punto k VBM | {data.get('vbm_kpt_frac')} |\n"
    out += f"| punto k CBM | {data.get('cbm_kpt_frac')} |\n"
    out += f"| Masa efectiva electrón | {data.get('m_e_m0', 0.0):.3f} m₀ |\n"
    out += f"| Masa efectiva hueco | {data.get('m_h_m0', 0.0):.3f} m₀ |\n"
    out += f"| Masa reducida | {data.get('m_reduced_m0', 0.0):.3f} m₀ |\n"
    out += f"| Factor tolerancia Goldschmidt t | {data.get('tolerance_factor', 0.0):.3f} |\n"
    out += f"| Factor octaédrico μ | {data.get('octahedral_factor', 0.0):.3f} |\n"
    out += f"| Enlace Pb-I medio | {data.get('mean_bx_bond_Ang', 0.0):.4f} Å |\n"
    out += f"| Varianza enlace Pb-I | {data.get('bx_bond_variance', 0.0):.4e} Å² |\n"

    flags = data.get("flags_gap", []) + data.get("flags_masses", []) + data.get("flags_structural", [])
    out += f"| Flags | {', '.join(flags) if flags else 'ninguno'} |\n"
    return out


def section_vibrational() -> str:
    out = _section("Propiedades Vibracionales")

    # Hessiano (Γ-point)
    out += "### Hessiano Γ (desplazamiento finito, ASE)\n"
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
            out += f"| Magnitud | Valor |\n|---|---|\n"
            out += f"| Modos en Γ | {len(freqs)} (3N, N=5) |\n"
            out += f"| Modos imaginarios (< -10 cm⁻¹) | {n_imag} |\n"
            out += f"| Rango acústico | {freqs[:3].min():.1f} – {freqs[:3].max():.1f} cm⁻¹ |\n"
            out += f"| Rango óptico | {freqs[3:].min():.1f} – {freqs[3:].max():.1f} cm⁻¹ |\n"
            out += f"\n**Frecuencias Γ (cm⁻¹):**\n\n"
            out += "| Modo | Frec (cm⁻¹) | Carácter |\n|---|---|---|\n"
            chars = ["acústico"] * 3 + ["óptico"] * (len(freqs) - 3)
            for i, (f, c) in enumerate(zip(freqs, chars)):
                flag = " ⚠ imaginario" if f < -10 else ""
                out += f"| {i+1:2d} | {f:8.2f} | {c}{flag} |\n"
    else:
        out += "_hessian.npy no encontrado_\n"

    # Phonopy fuerza sets
    out += "\n### Fuerzas Phonopy (Δ = 0.02 Å, supercelda 2×2×2)\n"
    phonon_dir = CALC / "07_vibrational" / "phonons"
    forces = []
    for i in range(3):
        f = _load(phonon_dir / f"forces_{i:03d}.npy")
        forces.append(f)

    n_done = sum(1 for f in forces if f is not None)
    out += f"| Desplazamientos calculados | {n_done} / 3 |\n"

    if n_done > 0:
        out += f"\n| Disp | Átomo | Máx\\|F\\| (eV/Å) | Media\\|F\\| (eV/Å) | Residual ASR | ASR (%) |\n"
        out += "|---|---|---|---|---|---|\n"

        disp_yaml = phonon_dir / "phonopy_disp.yaml"
        atom_labels = {}
        if disp_yaml.exists():
            try:
                import yaml
                with open(disp_yaml) as fh:
                    d = yaml.safe_load(fh)
                for idx, disp in enumerate(d["displacements"]):
                    atom_labels[idx] = f"átomo {disp['atom']}  {disp['displacement']}"
            except Exception:
                pass

        for i, f in enumerate(forces):
            if f is None:
                out += f"| {i} | — | pendiente | — | — | — |\n"
                continue
            fmax = float(np.abs(f).max())
            fmean = float(np.abs(f).mean())
            asr = float(np.abs(f.sum(axis=0)).max())
            asr_pct = asr / fmax * 100 if fmax > 0 else 0.0
            label = atom_labels.get(i, f"disp {i}")
            out += f"| {i} | {label} | {fmax:.5f} | {fmean:.5f} | {asr:.2e} | {asr_pct:.3f}% |\n"

    # Resultado Phonopy.
    freq_file = phonon_dir / "phonon_frequencies_phonopy.npy"
    if freq_file.exists():
        out += "\n### Dispersión Fonónica (Phonopy + ASR)\n"
        freqs_cm1 = np.load(str(freq_file))
        n_imag = int(np.sum(freqs_cm1 < -10.0))
        out += f"| Magnitud | Valor |\n|---|---|\n"
        out += f"| puntos q ruta | {freqs_cm1.shape[0]} |\n"
        out += f"| Ramas | {freqs_cm1.shape[1]} |\n"
        out += f"| Frecuencia mín | {freqs_cm1.min():.2f} cm⁻¹ |\n"
        out += f"| Frecuencia máx | {freqs_cm1.max():.2f} cm⁻¹ |\n"
        out += f"| Modos imaginarios (< -10 cm⁻¹) | {n_imag} |\n"
        if n_imag == 0:
            out += f"| Estabilidad | **Dinámicamente estable** ✓ |\n"
        else:
            peor = float(freqs_cm1[freqs_cm1 < -10.0].min())
            out += f"| Estabilidad | ⚠ {n_imag} modos imaginarios, peor: {peor:.1f} cm⁻¹ |\n"
    else:
        out += "\n_Dispersión fonónica: pendiente (fuerzas incompletas)_\n"

    return out


def section_loto() -> str:
    out = _section("Corrección LO-TO (Cargas Born + ε∞)")

    Z = _load(CALC / "08_loto" / "born_charges.npy")
    eps = _load(CALC / "08_loto" / "dielectric_tensor.npy")

    if Z is None or eps is None:
        out += "_Estado: pendiente - born_charges.npy / dielectric_tensor.npy no encontrados_\n"
        return out

    calc_r = _gpw(CALC / "01_relax" / "relax.gpw")
    syms = calc_r.get_atoms().get_chemical_symbols() if calc_r else [f"átomo{i}" for i in range(len(Z))]

    out += "### Tensor Dieléctrico (ε∞)\n\n"
    out += f"| | x | y | z |\n|---|---|---|---|\n"
    for i, row in enumerate(eps):
        label = ["x", "y", "z"][i]
        out += f"| {label} | {row[0]:.4f} | {row[1]:.4f} | {row[2]:.4f} |\n"
    out += f"\nPromedio isotrópico: ε∞ = {np.trace(eps)/3:.4f}\n"

    out += "\n### Cargas Efectivas Born Z* (diagonal)\n\n"
    out += f"| Átomo | Z*_xx | Z*_yy | Z*_zz | Media |Z*| |\n|---|---|---|---|---|\n"
    for i, (sym, Zi) in enumerate(zip(syms, Z)):
        out += (f"| {sym}{i+1} | {Zi[0,0]:+.4f} | {Zi[1,1]:+.4f} | {Zi[2,2]:+.4f} "
                f"| {np.abs(Zi).mean():.4f} |\n")

    # Regla suma acústica en Z*.
    Z_sum = Z.sum(axis=0)
    asr_max = float(np.abs(Z_sum).max())
    out += f"\nASR carga Born (Σ Z* → 0), elemento máx: {asr_max:.4f} e\n"
    if asr_max < 0.1:
        out += "(ASR OK ✓)\n"
    else:
        out += "(⚠ Violación ASR - revisar LOTO)\n"

    return out


def section_pes() -> str:
    out = _section("Barrido PES Modo Casi-Cero/Negativo")
    pes_dir = CALC / "07_vibrational" / "pes"
    q_path = pes_dir / "pes_displacements.npy"
    e_path = pes_dir / "pes_energies.npy"
    if not (q_path.exists() and e_path.exists()):
        return out + "_Estado: pendiente - PES no corrido_\n"

    q = np.load(str(q_path))
    e = np.load(str(e_path))
    i_min = int(np.argmin(e))
    i_max = int(np.argmax(e))
    span_mev = float((e.max() - e.min()) * 1000.0)

    # Misma detección determinista que analysis.pes.
    i_saddle = i_max
    double_well = False
    barrera_mev = 0.0
    q_saddle = 0.0
    q_min1 = q[0]
    q_min2 = q[-1]
    if 0 < i_saddle < len(e) - 1:
        i_left = int(np.argmin(e[:i_saddle]))
        i_right = int(np.argmin(e[i_saddle + 1:])) + i_saddle + 1
        barrera_mev = float((e[i_saddle] - max(e[i_left], e[i_right])) * 1000.0)
        double_well = barrera_mev > 10.0
        q_saddle = float(q[i_saddle])
        q_min1 = float(q[i_left])
        q_min2 = float(q[i_right])

    n_cache = len([p for p in (pes_dir / "scan_mode0").glob("E_*.npy") if p.stem != "E_ref"])
    out += "| Magnitud | Valor |\n|---|---|\n"
    out += f"| Puntos calculados | {len(e)} ({n_cache} energías SCF cacheadas) |\n"
    out += f"| Rango Q | {q.min():+.3f} a {q.max():+.3f} Å |\n"
    out += f"| Mínimo E(Q)-E(0) | {e[i_min]:.6f} eV en Q = {q[i_min]:+.3f} Å |\n"
    out += f"| Máximo E(Q)-E(0) | {e[i_max]:.6f} eV en Q = {q[i_max]:+.3f} Å |\n"
    out += f"| Rango energía | {span_mev:.2f} meV |\n"
    out += f"| Doble pozo detectado | {'sí' if double_well else 'no'} |\n"
    out += f"| Barrera criterio | {barrera_mev:.1f} meV |\n"
    if double_well:
        out += f"| Q silla | {q_saddle:+.3f} Å |\n"
        out += f"| Q mínimos | {q_min1:+.3f}, {q_min2:+.3f} Å |\n"
        out += "| CI-NEB | debe lanzarse por workflow |\n"
    else:
        out += "| CI-NEB | no lanzado (sin doble pozo) |\n"
    out += f"| Gráfica | `{pes_dir.relative_to(ROOT)}/pes_scan.png` |\n"
    return out


def section_optical() -> str:
    out = _section("Propiedades Ópticas")
    opt_dir = CALC / "11_optical"
    omega_path = opt_dir / "optical_frequencies.npy"

    if not omega_path.exists():
        out += "_Estado: pendiente - paso óptico no corrido_\n"
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

    # Revisa flag scissor en CSV.
    scissor_str = "N/A"
    csv_path = opt_dir / "dielectric_function.csv"
    if csv_path.exists():
        try:
            first = csv_path.read_text().splitlines()[0]
            if "scissor" in first.lower() or "eshift" in first.lower():
                scissor_str = first
        except Exception:
            pass

    out += f"_RPA, respuesta lineal GPAW · scissor: {scissor_str}_\n\n"
    out += "### Métricas Clave\n\n"
    out += f"| Magnitud | Valor |\n|---|---|\n"
    out += f"| ε∞ (ω → 0) | {eps_inf:.4f} |\n" if eps_inf else "| ε∞ | N/A |\n"
    out += f"| Inicio absorción | {onset_eV:.3f} eV |\n" if onset_eV else "| Inicio absorción | no alcanzado |\n"

    for e in [1.5, 2.0, 2.5, 3.0]:
        a = float(np.interp(e, omega, alpha))
        out += f"| α @ {e} eV | {a:.3e} cm⁻¹ |\n"

    out += f"| Score visible AM1.5G | {score:.4f} [0–1] |\n"

    pv = "**prometedor** ✓" if (onset_eV and onset_eV < 2.0 and score > 0.05) else "marginal / pendiente"
    out += f"| Criterio PV (α ≥ 10⁴ cm⁻¹) | {pv} |\n"

    # Tabla muestreada.
    out += "\n### Función Dieléctrica (muestreada)\n\n"
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

    # Guarda CSV completo.
    csv_out = opt_dir / "optical_spectrum_table.csv"
    try:
        header_csv = "omega_eV,eps1,eps2,n,k,alpha_cm1"
        data = np.column_stack([omega, eps1, eps2, n_w, k_w, alpha])
        np.savetxt(str(csv_out), data, delimiter=",", header=header_csv, comments="")
        out += f"\n_Espectro completo guardado en [{csv_out.name}]({csv_out.relative_to(ROOT)}) para graficar._\n"
    except Exception:
        pass

    return out


def section_device_optics() -> str:
    """Sección óptica Beer-Lambert."""
    optical_dir = CALC / "11_optical"
    gen_path = optical_dir / "device_generation_rate.npy"
    x_path   = optical_dir / "device_x_cm.npy"

    out = _section("Óptica Dispositivo (Beer-Lambert)")

    if not (optical_dir / "optical_frequencies.npy").exists():
        return out + "_Estado: pendiente - paso óptico no corrido_\n"

    if not gen_path.exists():
        # Calcula al vuelo si hay .npy óptico.
        try:
            sys.path.insert(0, str(ROOT / "src"))
            from dft_cspbi3.analysis.optical_device import compute_device_optics
            result = compute_device_optics(optical_dir, thickness_nm=500.0)
        except Exception as exc:
            return out + f"_Óptica dispositivo falló: {exc}_\n"
    else:
        try:
            sys.path.insert(0, str(ROOT / "src"))
            from dft_cspbi3.analysis.optical_device import compute_device_optics
            result = compute_device_optics(optical_dir, thickness_nm=500.0)
        except Exception as exc:
            return out + f"_Recarga óptica dispositivo falló: {exc}_\n"

    if result is None:
        return out + "_Estado: pendiente - faltan .npy_\n"

    out += "| Magnitud | Valor |\n|---|---|\n"
    out += f"| Espesor absorbedor | {result.thickness_cm * 1e7:.0f} nm |\n"
    out += f"| Eficiencia óptica η_opt | {result.optical_efficiency:.4f} |\n"
    out += f"| Flujo fotones absorbidos | {result.absorbed_photon_flux:.3e} fotones/cm²/s |\n"
    out += f"| Flujo fotones incidente (AM1.5G) | {result.incident_photon_flux:.3e} fotones/cm²/s |\n"
    out += f"| Límite J_sc (IQE=1) | **{result.jsc_limit_mA_cm2:.2f} mA/cm²** |\n"
    if result.flags:
        out += f"\n_Flags: {', '.join(result.flags)}_\n"
    return out


def section_soc_hse06() -> str:
    """Sección gap HSE06+SOC."""
    soc_dir  = CALC / "05_soc"
    hse_eigs = soc_dir / "soc_hse06_eigenvalues.npy"
    hse_gpw  = CALC / "06_hse06" / "hse06.gpw"

    out = _section("HSE06 + Acoplamiento Espín-Órbita")

    if not hse_gpw.exists():
        return out + "_Estado: pendiente - hse06.gpw no generado_\n"

    if not hse_eigs.exists():
        return out + "_Estado: pendiente - paso soc_hse06 no corrido_\n"

    eigs = _load(hse_eigs)
    if eigs is None:
        return out + "_Estado: archivo ilegible_\n"

    ef = float(np.median(eigs.flatten()))
    occupied   = eigs[eigs < ef]
    unoccupied = eigs[eigs >= ef]
    if len(occupied) and len(unoccupied):
        gap = float(unoccupied.min() - occupied.max())
        vbm = float(occupied.max())
        cbm = float(unoccupied.min())
        out += "| Magnitud | Valor |\n|---|---|\n"
        out += f"| Gap (HSE06+SOC) | **{gap:.4f} eV** |\n"
        out += f"| VBM (rel. E_F aprox) | {vbm - ef:.4f} eV |\n"
        out += f"| CBM (rel. E_F aprox) | {cbm - ef:.4f} eV |\n"
        out += f"| Bandas SOC | {eigs.shape[-1]} |\n"
    else:
        out += "_No pude extraer gap desde autovalores_\n"
    return out


def section_formation_energy() -> str:
    out = _section("Energía Formación")
    path = CALC / "09_formation_energy" / "formation_energy.json"
    if not path.exists():
        return out + "_Estado: pendiente - paso formation_energy no corrido_\n"

    data = json.loads(path.read_text())
    out += "| Magnitud | Valor |\n|---|---|\n"
    out += f"| ΔHf | **{data['delta_Hf_eV']:+.6f} eV/f.u.** |\n"
    out += f"| E(CsPbI₃) | {data['E_perovskite_per_fu_eV']:.6f} eV/f.u. |\n"
    out += f"| E(CsI) | {data['E_CsI_per_fu_eV']:.6f} eV/f.u. |\n"
    out += f"| E(PbI₂) | {data['E_PbI2_per_fu_eV']:.6f} eV/f.u. |\n"
    out += f"| Estabilidad vs CsI + PbI₂ | {'estable' if data.get('stable') else 'inestable'} |\n"
    estabilidad = "STABLE" if data.get("stable") else "UNSTABLE"
    out += f"| Resumen | ΔHf = {data['delta_Hf_eV']:+.3f} eV/f.u. → {estabilidad} vs descomposición binaria |\n"
    return out


def section_defects() -> str:
    """Sección energía defectos."""
    defect_dir  = CALC / "13_defects"
    result_file = defect_dir / "defect_formation_energies.txt"

    out = _section("Defectos Puntuales (Intrínsecos)")

    if not result_file.exists():
        return out + (
            "_Estado: pendiente - defectos no corridos_\n\n"
            "**Defectos planeados**: V_I, I_i, V_Pb, V_Cs, Pb_I, I_Pb "
            "(2×2×2 supercelda, MACE geometría + DFT single-point)\n"
        )

    lines = result_file.read_text().splitlines()
    out += "\n".join(lines) + "\n"
    return out


def section_migration() -> str:
    """Sección barreras iónicas."""
    mig_dir = CALC / "14_migration"
    out = _section("Migración Iónica (CI-NEB)")

    if not mig_dir.exists():
        return out + (
            "_Estado: pendiente - NEB no corrido_\n\n"
            "**Rutas planeadas**: V_I ⟨100⟩, V_I ⟨110⟩, I_i ⟨100⟩, V_Cs ⟨100⟩\n"
            "Literatura: V_I barrera ≈ 0.1–0.25 eV (Azpiroz 2015)\n"
        )

    # Busca resúmenes por ruta.
    neb_dirs = sorted(mig_dir.glob("V_I_*/"))
    if not neb_dirs:
        return out + "_Estado: pendiente - sin resultados NEB_\n"

    out += "| Ruta | Barrera ida (meV) | Barrera vuelta (meV) | Convergido |\n"
    out += "|------|-------------------|-------------------|-----------|\n"
    for d in neb_dirs:
        log_files = list(d.glob("neb_*.txt"))
        label = d.name
        out += f"| {label} | — | — | — |\n"
    return out


def section_kmc() -> str:
    """Sección fotoestabilidad kMC."""
    kmc_dir = CALC / "15_kmc"
    out = _section("Monte Carlo Cinético (Fotoestabilidad)")

    summary_file = kmc_dir / "kmc_summary.txt"
    if not summary_file.exists():
        return out + (
            "_Estado: pendiente - requiere barreras NEB (L4)_\n\n"
            "**Método**: algoritmo BKL, O(N) por evento\n"
            "**Entradas**: barrera salto V_I, tasa fotogeneración G(x)\n"
        )

    lines = summary_file.read_text().splitlines()
    out += "```\n" + "\n".join(lines) + "\n```\n"
    return out


def section_aimd() -> str:
    """Sección estabilidad MACE-AIMD."""
    aimd_dir = CALC / "16_aimd_mlip"
    out = _section("Estabilidad Térmica (Screening MACE-AIMD)")

    if not aimd_dir.exists():
        return out + (
            "_Estado: pendiente - instalar mace-torch y correr screen_thermal_stability()_\n\n"
            "**Método**: NVT Langevin + MACE-MP-0, 10 ps/temperatura\n"
            "**Temperaturas**: 300/400/500/600 K\n"
            "**Costo**: ~5 min/T en CPU\n"
        )

    summaries = sorted(aimd_dir.glob("*/aimd_*K_summary.txt"))
    if not summaries:
        return out + "_Estado: corriendo o sin resúmenes_\n"

    out += "| T (K) | RMSD final (Å) | RDF Pb-I peak (Å) | Etiqueta |\n"
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
    """Sección QHA."""
    qha_dir   = CALC / "15_qha"
    gibbs_npy = qha_dir / "qha_gibbs.npy"
    alpha_npy = qha_dir / "qha_alpha.npy"
    temps_npy = qha_dir / "qha_temperatures.npy"

    out = _section("Aproximación Cuasiarmónica (QHA)")

    if not gibbs_npy.exists():
        return out + (
            "_Estado: pendiente - requiere fonones en 6 volúmenes (~42 h)_\n\n"
            "**Salidas**: G(T), α(T) expansión térmica, C_p(T), V_eq(T), B₀\n"
            "**Validez**: T < ~320 K (límite modo blando fase α)\n"
        )

    T_arr = _load(temps_npy)
    G_arr = _load(gibbs_npy)
    a_arr = _load(alpha_npy)

    if T_arr is None or G_arr is None:
        return out + "_Estado: .npy QHA ilegibles_\n"

    # Tabla temperaturas representativas.
    out += "| T (K) | G(T) (eV/celda) | α(T) (1/K) |\n|---|---|---|\n"
    for i, T in enumerate(T_arr):
        if int(T) % 100 == 0:
            G = float(G_arr[i]) if i < len(G_arr) else float("nan")
            a = float(a_arr[i]) if a_arr is not None and i < len(a_arr) else float("nan")
            out += f"| {T:.0f} | {G:.4f} | {a:.3e} |\n"
    return out


def section_status() -> str:
    out = _section("Estado Cálculo")
    steps = {
        "01 Relax":         CALC / "01_relax" / "relax.gpw",
        "02 SCF":           CALC / "02_scf" / "scf.gpw",
        "03 Bandas":         CALC / "03_bands" / "bands.gpw",
        "04 DOS":           CALC / "04_dos" / "dos.gpw",
        "05 SOC":           CALC / "05_soc" / "soc_eigenvalues.npy",
        "05 HSE06+SOC":     CALC / "05_soc" / "soc_hse06_eigenvalues.npy",
        "06 HSE06":         CALC / "06_hse06" / "hse06.gpw",
        "07 Hessiano":       CALC / "07_vibrational" / "hessian" / "hessian.npy",
        "07 Fonones (disp 0)": CALC / "07_vibrational" / "phonons" / "forces_000.npy",
        "07 Fonones (disp 1)": CALC / "07_vibrational" / "phonons" / "forces_001.npy",
        "07 Fonones (disp 2)": CALC / "07_vibrational" / "phonons" / "forces_002.npy",
        "07 Fonones (dispersión)": CALC / "07_vibrational" / "phonons" / "phonon_frequencies_phonopy.npy",
        "07 PES":           CALC / "07_vibrational" / "pes" / "pes_energies.npy",
        "08 LOTO":          CALC / "08_loto" / "born_charges.npy",
        "09 Energía formación": CALC / "09_formation_energy" / "formation_energy.json",
        "10 Masas efectivas": CALC / "10_effective_masses" / "electronic_analysis.json",
        "11 Óptica":       CALC / "11_optical" / "optical_frequencies.npy",
        "11 Óptica dispositivo": CALC / "11_optical" / "device_generation_rate.npy",
        "13 Defectos":       CALC / "13_defects" / "defect_formation_energies.txt",
        "14 Migración NEB": CALC / "14_migration",
        "15 kMC":           CALC / "15_kmc" / "kmc_summary.txt",
        "15 QHA":           CALC / "15_qha" / "qha_gibbs.npy",
        "16 AIMD-MLIP":     CALC / "16_aimd_mlip",
    }
    out += f"| Paso | Estado |\n|---|---|\n"
    for name, path in steps.items():
        out += f"| {name} | {_status(Path(path).exists())} |\n"
    return out


# Main

def build_report() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"# Reporte Resultados DFT α-CsPbI₃\n\n"
    header += f"_Generado: {now}_  \n"
    header += f"_Método: GPAW · PBE-PW · PAW · Phonopy_\n"

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
    print(f"Reporte escrito en {out_path}")
