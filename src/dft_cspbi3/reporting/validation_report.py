"""Genera validation_report.md desde resultados DFT."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


# Datos entrada


@dataclass
class ValidationData:
    """Datos agregados para reporte validacion."""

    # Sistema.
    phase: str
    formula: str
    n_atoms: int
    volume_ang3: float
    # Parametros DFT.
    xc: str
    ecut_eV: float
    kpts: list[int]
    # Resultados.
    total_energy_eV: float
    fermi_level_eV: float
    bandgap_eV: Optional[float]
    electronic_type: str
    # Objetos validacion; None si paso omitido.
    scf_report: Optional[object] = None          # SCFReport
    physical_checks: Optional[object] = None
    soc_report: Optional[object] = None          # SOCReport
    convergence_ecut_df: Optional[object] = None
    convergence_kpts_df: Optional[object] = None
    scissor_result: Optional[object] = None
    extra_flags: list[str] = field(default_factory=list)


# Generador reporte


def generate_validation_report(
    data: ValidationData,
    output_dir: str | Path = "./reports",
    filename: str = "validation_report.md",
) -> Path:
    """Escribe validation_report.md desde *data*; devuelve ruta."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    lines: list[str] = []
    _h = lines.append

    # Cabecera.
    _h(f"# Reporte validacion DFT — {data.phase}-{data.formula}")
    _h(f"\n*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    # Junta flags.
    all_flags: list[str] = list(data.extra_flags)
    for obj_name in ("scf_report", "physical_checks", "soc_report"):
        obj = getattr(data, obj_name)
        if obj is not None and hasattr(obj, "flags"):
            all_flags.extend(obj.flags)

    if all_flags:
        _h("\n## ⚠ Flags criticos\n")
        for flag in all_flags:
            _h(f"- `{flag}`")
        _h(
            "\n> Resultados con flags requieren revision. "
            "`SCF_DID_NOT_CONVERGE` o `ENERGY_NOT_NEGATIVE` "
            "→ calculo invalido."
        )

    # Sistema.
    _h("\n## 1. Sistema")
    _h("\n| Propiedad | Valor |")
    _h("|----------|-------|")
    _h(f"| Fase | {data.phase} |")
    _h(f"| Formula | {data.formula} |")
    _h(f"| N atomos | {data.n_atoms} |")
    _h(f"| Volumen | {data.volume_ang3:.3f} Å³ |")

    # Parametros DFT.
    _h("\n## 2. Parametros DFT")
    _h("\n| Parametro | Valor |")
    _h("|-----------|-------|")
    _h(f"| Funcional XC | {data.xc} |")
    _h(f"| Corte ondas planas | {data.ecut_eV} eV |")
    _h(f"| k-point mesh | {data.kpts[0]}×{data.kpts[1]}×{data.kpts[2]} |")
    _h(f"| Metodo PAW | GPAW (libxc) |")
    _h(f"| Condiciones borde | Periodicas (3D) |")

    # Convergencia SCF.
    _h("\n## 3. Convergencia SCF")
    if data.scf_report is not None:
        r = data.scf_report
        status = "✅ Convergido" if r.converged else "❌ NO CONVERGIO"
        osc = "⚠ Oscila" if r.oscillating else "✅ estable"
        _h(f"\n| Revision | Resultado |")
        _h("|-------|--------|")
        _h(f"| Flag convergencia | {status} |")
        _h(f"| Iteraciones | {r.iterations} |")
        _h(f"| Final |ΔE| | {r.final_energy_change_eV:.2e} eV |")
        _h(f"| Oscilacion | {osc} |")
        if r.flags:
            _h(f"\n**Flags:** `{'`, `'.join(r.flags)}`")
    else:
        _h("\n*Validacion SCF no ejecutada.*")

    # Checks fisicos.
    _h("\n## 4. Consistencia fisica")
    if data.physical_checks is not None:
        pc = data.physical_checks
        _h(f"\n| Revision | Valor | Estado |")
        _h("|-------|-------|--------|")
        neg_ok = "✅" if pc.energy_negative else "❌"
        _h(f"| Energia total | {pc.energy_eV:.6f} eV | {neg_ok} negativa |")
        _h(f"| Nivel Fermi | {pc.fermi_level_eV:.4f} eV | ✅ |")
        occ_ok = "✅" if pc.occupations_consistent else "❌"
        _h(f"| N electrones | {pc.n_electrons:.1f} | ✅ |")
        _h(f"| Σ ocupaciones | {pc.occupations_sum:.3f} | {occ_ok} consistente |")
    else:
        _h(f"\n| Propiedad | Valor |")
        _h("|----------|-------|")
        _h(f"| Energia total | {data.total_energy_eV:.6f} eV |")
        _h(f"| Nivel Fermi | {data.fermi_level_eV:.4f} eV |")

    # Estructura electronica.
    _h("\n## 5. Estructura electronica y correccion bandgap")
    _h(f"\n| Propiedad | Valor |")
    _h("|----------|-------|")
    _h(f"| Clasificacion | {data.electronic_type} |")
    if data.bandgap_eV is not None:
        _h(f"| Eg(PBE) | {data.bandgap_eV:.4f} eV |")

    if data.soc_report is not None and data.soc_report.gap_soc_eV is not None:
        sr_soc = data.soc_report
        _h(f"| Eg(PBE+SOC) | {sr_soc.gap_soc_eV:.4f} eV |")
        if sr_soc.chi_soc_eV is not None:
            _h(f"| χSOC | {sr_soc.chi_soc_eV:+.4f} eV (calculado) |")

    if data.scissor_result is not None:
        sr = data.scissor_result
        chi_hse_lbl = f"{sr.chi_hse:+.4f} eV ({sr.chi_hse_source})"
        _h(f"| χHSE | {chi_hse_lbl} |")
        _h(f"| Eg(PBE+scissor) [Strategy A] | {sr.e_corrected:.4f} eV |")

        if sr.e_hse_soc is not None:
            _h(f"| **Eg(HSE06+SOC) [Strategy B — primary]** | **{sr.e_hse_soc:.4f} eV** |")
            if sr.delta_additivity is not None:
                sign = "+" if sr.delta_additivity >= 0 else ""
            _h(f"| δ_add (B − A) | {sign}{sr.delta_additivity:.4f} eV |")
            if sr.mae_vs_hse_soc is not None:
                _h(f"| MAE vs exp (HSE06+SOC) | {sr.mae_vs_hse_soc:.4f} eV |")
        else:
            _h("| Eg(HSE06+SOC) | ⚠ pendiente calculo HSE06 |")

        if sr.e_experimental is not None:
            _h(f"| Experimental | {sr.e_experimental:.4f} eV ({_get_exp_ref(sr.phase)}) |")
        if sr.mae_vs_experiment is not None:
            primary_mae = sr.mae_vs_hse_soc if sr.mae_vs_hse_soc is not None else sr.mae_vs_experiment
            method_lbl = "HSE06+SOC" if sr.mae_vs_hse_soc is not None else "scissor"
            _h(f"| MAE vs exp ({method_lbl}) | {primary_mae:.4f} eV |")

    # Pruebas convergencia.
    _h("\n## 6. Pruebas convergencia")
    if data.convergence_ecut_df is not None:
        df = data.convergence_ecut_df
        _h("\n### 6.1 Corte ondas planas")
        _h("\n| Ecut (eV) | E/atom (eV) | |ΔE| (meV/atom) |")
        _h("|-----------|-------------|----------------|")
        for _, row in df.iterrows():
            flag = " ← ref" if row["ecut_eV"] == df["ecut_eV"].max() else ""
            _h(
                f"| {row['ecut_eV']:.0f} | "
                f"{row['energy_per_atom_eV']:.6f} | "
                f"{abs(row['delta_meV_per_atom']):.3f}{flag} |"
            )
    else:
        _h("\n*Prueba convergencia Ecut no ejecutada.*")

    if data.convergence_kpts_df is not None:
        df = data.convergence_kpts_df
        _h("\n### 6.2 Muestreo k-point")
        _h("\n| Mesh | N k-points | |ΔE| (meV/atom) |")
        _h("|------|-----------|----------------|")
        for _, row in df.iterrows():
            mesh = f"{int(row['kx'])}×{int(row['ky'])}×{int(row['kz'])}"
            _h(
                f"| {mesh} | {int(row['nkpts_total'])} | "
                f"{abs(row['delta_meV_per_atom']):.3f} |"
            )
    else:
        _h("\n*Prueba convergencia k-point no ejecutada.*")

    # Validacion SOC.
    if data.soc_report is not None:
        r = data.soc_report
        _h("\n## 7. Acoplamiento spin-orbita (SOC)")
        applied = "✅ Aplicado" if r.soc_applied else "❌ No aplicado"
        plaus = "✅ Plausible" if r.chi_soc_plausible else "❌ Fuera rango"
        split = "✅ Detectado" if r.splitting_detected else "❌ No detectado"
        spurs = "❌ Presente" if r.spurious_magnetisation else "✅ Ninguna"
        _h(f"\n| Revision | Resultado |")
        _h("|-------|--------|")
        _h(f"| SOC aplicado | {applied} |")
        _h(f"| Gap sin SOC | {_fmt_opt(r.gap_no_soc_eV, '.4f')} eV |")
        _h(f"| Gap con SOC | {_fmt_opt(r.gap_soc_eV, '.4f')} eV |")
        _h(f"| χSOC | {_fmt_opt(r.chi_soc_eV, '+.4f')} eV | {plaus} |")
        _h(f"| Desdoblamiento spin | {split} |")
        _h(f"| Magnetizacion espuria | {spurs} |")

    # Resumen validez.
    _h("\n## 8. Validez global")
    critical_flags = [f for f in all_flags if any(
        kw in f for kw in ("NOT_CONVERGE", "ENERGY_NOT_NEGATIVE", "OCC_INCONSISTENT")
    )]
    if critical_flags:
        _h("\n**ESTADO / STATUS: ❌ INVALID**")
        _h("\nProblemas criticos:\n")
        for f in critical_flags:
            _h(f"- `{f}`")
    else:
        _h("\n**ESTADO / STATUS: ✅ VALID**")
        if all_flags:
            _h(f"\n*{len(all_flags)} advertencias no criticas. Ver flags.*")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


# Helpers.


def _fmt_opt(value, fmt: str) -> str:
    """Formatea float opcional; N/A si None."""
    if value is None:
        return "N/A"
    return f"{value:{fmt}}"


_EXP_REFS = {
    "alpha": "Sutton et al. ACS Energy Lett. 2018",
    "gamma": "Steele et al. JACS 2019",
    "delta": "Sutton et al. ACS Energy Lett. 2018",
}


def _get_exp_ref(phase: str) -> str:
    return _EXP_REFS.get(phase, "ver metodologia")
