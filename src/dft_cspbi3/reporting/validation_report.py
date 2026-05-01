"""Generate validation_report.md from DFT calculation results.

Aggregates:
  - DFT parameters
  - SCF convergence status
  - Physical checks (energy, electrons, occupations)
  - Bandgap and electronic structure type
  - Convergence tests (Ecut and k-points), if run
  - SOC validation, if applied
  - Critical flags (INVALID markers)
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Input data container
# ---------------------------------------------------------------------------


@dataclass
class ValidationData:
    """Aggregated inputs for the validation report."""

    # System
    phase: str
    formula: str
    n_atoms: int
    volume_ang3: float
    # DFT parameters
    xc: str
    ecut_eV: float
    kpts: list[int]
    # Results
    total_energy_eV: float
    fermi_level_eV: float
    bandgap_eV: Optional[float]
    electronic_type: str                         # "semiconductor", "metallic", etc.
    # Validation objects (can be None if step was skipped)
    scf_report: Optional[object] = None          # SCFReport
    physical_checks: Optional[object] = None     # PhysicalChecks
    soc_report: Optional[object] = None          # SOCReport
    convergence_ecut_df: Optional[object] = None # pd.DataFrame
    convergence_kpts_df: Optional[object] = None # pd.DataFrame
    scissor_result: Optional[object] = None      # ScissorResult
    extra_flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------


def generate_validation_report(
    data: ValidationData,
    output_dir: str | Path = "./reports",
    filename: str = "validation_report.md",
) -> Path:
    """Write validation_report.md from *data* and return its path.

    Args:
        data: Populated ValidationData instance.
        output_dir: Directory where the report will be written.
        filename: Output filename.

    Returns:
        Path to the generated report file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    lines: list[str] = []
    _h = lines.append

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------
    _h(f"# DFT Validation Report — {data.phase}-{data.formula}")
    _h(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    # Collect all flags across all validation objects
    all_flags: list[str] = list(data.extra_flags)
    for obj_name in ("scf_report", "physical_checks", "soc_report"):
        obj = getattr(data, obj_name)
        if obj is not None and hasattr(obj, "flags"):
            all_flags.extend(obj.flags)

    if all_flags:
        _h("\n## ⚠ Critical Flags\n")
        for flag in all_flags:
            _h(f"- `{flag}`")
        _h(
            "\n> Results marked with flags should be reviewed before publication. "
            "Calculations with `SCF_DID_NOT_CONVERGE` or `ENERGY_NOT_NEGATIVE` "
            "**must** be considered invalid."
        )

    # -----------------------------------------------------------------------
    # System information
    # -----------------------------------------------------------------------
    _h("\n## 1. System")
    _h("\n| Property | Value |")
    _h("|----------|-------|")
    _h(f"| Phase | {data.phase} |")
    _h(f"| Formula | {data.formula} |")
    _h(f"| N atoms | {data.n_atoms} |")
    _h(f"| Volume | {data.volume_ang3:.3f} Å³ |")

    # -----------------------------------------------------------------------
    # DFT parameters
    # -----------------------------------------------------------------------
    _h("\n## 2. DFT Parameters")
    _h("\n| Parameter | Value |")
    _h("|-----------|-------|")
    _h(f"| XC functional | {data.xc} |")
    _h(f"| Plane-wave cutoff | {data.ecut_eV} eV |")
    _h(f"| k-point mesh | {data.kpts[0]}×{data.kpts[1]}×{data.kpts[2]} |")
    _h(f"| PAW method | GPAW (libxc) |")
    _h(f"| Boundary conditions | Periodic (3D) |")

    # -----------------------------------------------------------------------
    # SCF convergence
    # -----------------------------------------------------------------------
    _h("\n## 3. SCF Convergence")
    if data.scf_report is not None:
        r = data.scf_report
        status = "✅ Converged" if r.converged else "❌ NOT CONVERGED"
        osc = "⚠ Oscillating" if r.oscillating else "✅ Stable"
        _h(f"\n| Check | Result |")
        _h("|-------|--------|")
        _h(f"| Convergence flag | {status} |")
        _h(f"| Iterations | {r.iterations} |")
        _h(f"| Final |ΔE| | {r.final_energy_change_eV:.2e} eV |")
        _h(f"| Oscillation | {osc} |")
        if r.flags:
            _h(f"\n**Flags:** `{'`, `'.join(r.flags)}`")
    else:
        _h("\n*SCF validation not performed.*")

    # -----------------------------------------------------------------------
    # Physical checks
    # -----------------------------------------------------------------------
    _h("\n## 4. Physical Consistency")
    if data.physical_checks is not None:
        pc = data.physical_checks
        _h(f"\n| Check | Value | Status |")
        _h("|-------|-------|--------|")
        neg_ok = "✅" if pc.energy_negative else "❌"
        _h(f"| Total energy | {pc.energy_eV:.6f} eV | {neg_ok} negative |")
        _h(f"| Fermi level | {pc.fermi_level_eV:.4f} eV | ✅ |")
        occ_ok = "✅" if pc.occupations_consistent else "❌"
        _h(f"| N electrons | {pc.n_electrons:.1f} | ✅ |")
        _h(f"| Σ occupations | {pc.occupations_sum:.3f} | {occ_ok} consistent |")
    else:
        _h(f"\n| Property | Value |")
        _h("|----------|-------|")
        _h(f"| Total energy | {data.total_energy_eV:.6f} eV |")
        _h(f"| Fermi level | {data.fermi_level_eV:.4f} eV |")

    # -----------------------------------------------------------------------
    # Electronic structure
    # -----------------------------------------------------------------------
    _h("\n## 5. Electronic Structure & Band Gap Corrections")
    _h(f"\n| Property | Value |")
    _h("|----------|-------|")
    _h(f"| Classification | {data.electronic_type} |")
    if data.bandgap_eV is not None:
        _h(f"| Eg(PBE) | {data.bandgap_eV:.4f} eV |")

    if data.soc_report is not None and data.soc_report.gap_soc_eV is not None:
        sr_soc = data.soc_report
        _h(f"| Eg(PBE+SOC) | {sr_soc.gap_soc_eV:.4f} eV |")
        if sr_soc.chi_soc_eV is not None:
            _h(f"| χSOC | {sr_soc.chi_soc_eV:+.4f} eV (computed) |")

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
            _h("| Eg(HSE06+SOC) | ⚠ pending HSE06 calculation |")

        if sr.e_experimental is not None:
            _h(f"| Experimental | {sr.e_experimental:.4f} eV ({_get_exp_ref(sr.phase)}) |")
        if sr.mae_vs_experiment is not None:
            primary_mae = sr.mae_vs_hse_soc if sr.mae_vs_hse_soc is not None else sr.mae_vs_experiment
            method_lbl = "HSE06+SOC" if sr.mae_vs_hse_soc is not None else "scissor"
            _h(f"| MAE vs exp ({method_lbl}) | {primary_mae:.4f} eV |")

    # -----------------------------------------------------------------------
    # Convergence tests
    # -----------------------------------------------------------------------
    _h("\n## 6. Convergence Tests")
    if data.convergence_ecut_df is not None:
        df = data.convergence_ecut_df
        _h("\n### 6.1 Plane-wave Cutoff")
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
        _h("\n*Ecut convergence test not performed.*")

    if data.convergence_kpts_df is not None:
        df = data.convergence_kpts_df
        _h("\n### 6.2 k-point Sampling")
        _h("\n| Mesh | N k-points | |ΔE| (meV/atom) |")
        _h("|------|-----------|----------------|")
        for _, row in df.iterrows():
            mesh = f"{int(row['kx'])}×{int(row['ky'])}×{int(row['kz'])}"
            _h(
                f"| {mesh} | {int(row['nkpts_total'])} | "
                f"{abs(row['delta_meV_per_atom']):.3f} |"
            )
    else:
        _h("\n*k-point convergence test not performed.*")

    # -----------------------------------------------------------------------
    # SOC validation
    # -----------------------------------------------------------------------
    if data.soc_report is not None:
        r = data.soc_report
        _h("\n## 7. Spin-Orbit Coupling (SOC)")
        applied = "✅ Applied" if r.soc_applied else "❌ Not applied"
        plaus = "✅ Plausible" if r.chi_soc_plausible else "❌ Out of range"
        split = "✅ Detected" if r.splitting_detected else "❌ Not detected"
        spurs = "❌ Present" if r.spurious_magnetisation else "✅ None"
        _h(f"\n| Check | Result |")
        _h("|-------|--------|")
        _h(f"| SOC applied | {applied} |")
        _h(f"| Gap no-SOC | {_fmt_opt(r.gap_no_soc_eV, '.4f')} eV |")
        _h(f"| Gap with SOC | {_fmt_opt(r.gap_soc_eV, '.4f')} eV |")
        _h(f"| χSOC | {_fmt_opt(r.chi_soc_eV, '+.4f')} eV | {plaus} |")
        _h(f"| Spin splitting | {split} |")
        _h(f"| Spurious magnetisation | {spurs} |")

    # -----------------------------------------------------------------------
    # Validity summary
    # -----------------------------------------------------------------------
    _h("\n## 8. Overall Validity")
    critical_flags = [f for f in all_flags if any(
        kw in f for kw in ("NOT_CONVERGE", "ENERGY_NOT_NEGATIVE", "OCC_INCONSISTENT")
    )]
    if critical_flags:
        _h("\n**STATUS: ❌ INVALID**")
        _h("\nThe following critical issues were found:\n")
        for f in critical_flags:
            _h(f"- `{f}`")
    else:
        _h("\n**STATUS: ✅ VALID**")
        if all_flags:
            _h(f"\n*{len(all_flags)} non-critical warning(s) present — see Section flags.*")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_opt(value, fmt: str) -> str:
    """Format an optional float, returning 'N/A' if None."""
    if value is None:
        return "N/A"
    return f"{value:{fmt}}"


_EXP_REFS = {
    "alpha": "Sutton et al. ACS Energy Lett. 2018",
    "gamma": "Steele et al. JACS 2019",
    "delta": "Sutton et al. ACS Energy Lett. 2018",
}


def _get_exp_ref(phase: str) -> str:
    return _EXP_REFS.get(phase, "see methodology")
