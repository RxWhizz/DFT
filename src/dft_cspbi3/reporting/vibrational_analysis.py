"""Generate vibrational_analysis.md from Hessian and phonon results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


def generate_vibrational_report(
    hessian_result: Optional[object] = None,
    phonon_result: Optional[object] = None,
    stability_report: Optional[object] = None,
    phase: str = "unknown",
    output_dir: str | Path = "./reports",
    filename: str = "vibrational_analysis.md",
) -> Path:
    """Write vibrational_analysis.md and return its path.

    At least one of *hessian_result* or *phonon_result* must be provided.

    Args:
        hessian_result: HessianResult from validation.hessian.
        phonon_result:  PhononResult from validation.phonons.
        stability_report: StabilityReport from validation.stability.
        phase: Crystal phase label (alpha/gamma/delta).
        output_dir: Output directory.
        filename: Report filename.

    Returns:
        Path to the written report.
    """
    if hessian_result is None and phonon_result is None:
        raise ValueError("At least one of hessian_result or phonon_result must be provided.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    lines: list[str] = []
    _h = lines.append

    _h(f"# Vibrational Analysis Report — {phase}")
    _h(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    # -----------------------------------------------------------------------
    # Stability summary
    # -----------------------------------------------------------------------
    if stability_report is not None:
        cls = stability_report.classification.value.upper()
        icon = {"stable": "✅", "metastable": "⚠", "unstable": "❌", "unknown": "❓"}.get(
            stability_report.classification.value, "❓"
        )
        _h(f"\n## Stability Classification: {icon} {cls}")
        _h(f"\n{stability_report.diagnosis}")
        if stability_report.recommendations:
            _h("\n**Recommendations:**")
            for rec in stability_report.recommendations:
                _h(f"- {rec}")

    # -----------------------------------------------------------------------
    # Hessian section
    # -----------------------------------------------------------------------
    if hessian_result is not None:
        h = hessian_result
        _h("\n## 1. Hessian Matrix Analysis (Γ-point)")
        _h(f"\n- Atoms: {h.n_atoms}")
        _h(f"- DOF: {3 * h.n_atoms}")
        _h(f"- Finite-difference step: {h.delta_Ang:.4f} Å")
        _h(f"- Initial fmax: {h.fmax_initial_eV_Ang:.4f} eV/Å "
           f"({'OK' if h.forces_converged else 'WARNING: too large'})")

        _h("\n### 1.1 Eigenvalue Spectrum")
        _h("\n| Mode | Eigenvalue (eV/Å²) | Classification |")
        _h("|------|--------------------|----------------|")
        for i, ev in enumerate(h.eigenvalues):
            if abs(ev) <= 0.05:
                cls_str = "translational (zero)"
            elif ev < 0:
                cls_str = "⚠ **NEGATIVE** (instability)"
            else:
                cls_str = "positive (stable)"
            _h(f"| {i + 1:3d} | {ev:+12.6f} | {cls_str} |")

        _h("\n### 1.2 Summary")
        _h(f"\n| Property | Value |")
        _h("|----------|-------|")
        _h(f"| Minimum eigenvalue | {h.min_eigenvalue:+.6f} eV/Å² |")
        _h(f"| Negative eigenvalues | {h.n_negative} |")
        _h(f"| Near-zero eigenvalues | {h.n_zero} |")
        stable_str = "✅ Stable minimum" if h.stable else "❌ Saddle point"
        _h(f"| Assessment | {stable_str} |")

        if h.flags:
            _h(f"\n**Flags:** `{'`, `'.join(h.flags)}`")

    # -----------------------------------------------------------------------
    # Phonon section
    # -----------------------------------------------------------------------
    if phonon_result is not None:
        ph = phonon_result
        _h("\n## 2. Phonon Frequencies (Supercell Method)")
        sc = ph.supercell
        _h(f"\n- Unit cell atoms: {ph.n_atoms_unit_cell}")
        _h(f"- Supercell: {sc[0]}×{sc[1]}×{sc[2]}")
        _h(f"- Finite-difference step: {ph.delta_Ang:.4f} Å")
        _h(f"- Expected phonon branches: {3 * ph.n_atoms_unit_cell}")

        _h("\n### 2.1 Imaginary Modes")
        if ph.n_imaginary == 0:
            _h("\n✅ No imaginary phonon frequencies detected. Structure is dynamically stable.")
        else:
            _h(f"\n❌ {ph.n_imaginary} imaginary mode(s) detected:")
            _h(f"\n- Most negative frequency: **{ph.max_imaginary_cm1:.1f} cm⁻¹**")

        _h("\n### 2.2 Frequency Range")
        freqs = ph.frequencies_cm1.flatten()
        real_freqs = freqs[freqs > 1.0]   # exclude near-zero translational
        imag_freqs = freqs[freqs < -10.0]

        _h(f"\n| Property | Value |")
        _h("|----------|-------|")
        _h(f"| Min real frequency | {real_freqs.min():.1f} cm⁻¹" if real_freqs.size else "| Min real frequency | N/A |")
        _h(f"| Max real frequency | {real_freqs.max():.1f} cm⁻¹" if real_freqs.size else "| Max real frequency | N/A |")
        if imag_freqs.size:
            _h(f"| Imaginary (worst) | {imag_freqs.min():.1f} cm⁻¹ |")
        _h(f"| N imaginary (>10 cm⁻¹) | {ph.n_imaginary} |")

        if ph.flags:
            _h(f"\n**Flags:** `{'`, `'.join(ph.flags)}`")

    # -----------------------------------------------------------------------
    # Structural diagnosis
    # -----------------------------------------------------------------------
    _h("\n## 3. Structural Diagnosis")

    all_stable = True
    if hessian_result is not None and not hessian_result.stable:
        all_stable = False
    if phonon_result is not None and not phonon_result.stable:
        all_stable = False

    if all_stable:
        _h(
            "\nThe structure passes all vibrational stability checks. "
            "It represents a true local energy minimum and is suitable for "
            "subsequent property calculations (DOS, band structure, transport)."
        )
    else:
        _h(
            "\n⚠ **The structure has one or more dynamic instabilities.** "
            "Results from electronic structure calculations (band gap, DOS) "
            "derived from this geometry may be unreliable. "
            "The instability must be resolved before accepting DFT results."
        )
        _h(
            "\n**Possible causes for perovskite halides:**\n"
            "- Suppressed octahedral tilting (cubic constraint on tilted phase)\n"
            "- Missing A-site orientational disorder (FA⁺, MA⁺ fixed in average position)\n"
            "- Wrong phase (e.g. computing δ geometry with α structure)\n"
            "- Insufficient relaxation (residual forces too large)\n"
        )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
