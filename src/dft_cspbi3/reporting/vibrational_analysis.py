"""Genera vibrational_analysis.md desde Hessian y phonon."""

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
    """Escribe vibrational_analysis.md; devuelve ruta."""
    if hessian_result is None and phonon_result is None:
        raise ValueError("Falta hessian_result o phonon_result.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    lines: list[str] = []
    _h = lines.append

    _h(f"# Reporte analisis vibracional — {phase}")
    _h(f"\n*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    # Resumen estabilidad.
    if stability_report is not None:
        cls = stability_report.classification.value.upper()
        icon = {"stable": "✅", "metastable": "⚠", "unstable": "❌", "unknown": "❓"}.get(
            stability_report.classification.value, "❓"
        )
        _h(f"\n## Clasificacion estabilidad: {icon} {cls}")
        _h(f"\n{stability_report.diagnosis}")
        if stability_report.recommendations:
            _h("\n**Recomendaciones:**")
            for rec in stability_report.recommendations:
                _h(f"- {rec}")

    # Seccion Hessian.
    if hessian_result is not None:
        h = hessian_result
        _h("\n## 1. Analisis matriz Hessian (Γ)")
        _h(f"\n- Atomos: {h.n_atoms}")
        _h(f"- DOF: {3 * h.n_atoms}")
        _h(f"- Paso diferencias finitas: {h.delta_Ang:.4f} Å")
        _h(f"- Initial fmax: {h.fmax_initial_eV_Ang:.4f} eV/Å "
           f"({'OK' if h.forces_converged else 'ALERTA: alto'})")

        _h("\n### 1.1 Espectro autovalores")
        _h("\n| Modo | Autovalor (eV/Å²) | Clasificacion |")
        _h("|------|--------------------|----------------|")
        for i, ev in enumerate(h.eigenvalues):
            if abs(ev) <= 0.05:
                cls_str = "traslacional (cero)"
            elif ev < 0:
                cls_str = "⚠ **NEGATIVO** (instability)"
            else:
                cls_str = "positivo (stable)"
            _h(f"| {i + 1:3d} | {ev:+12.6f} | {cls_str} |")

        _h("\n### 1.2 Resumen")
        _h(f"\n| Propiedad | Valor |")
        _h("|----------|-------|")
        _h(f"| Autovalor minimo | {h.min_eigenvalue:+.6f} eV/Å² |")
        _h(f"| Autovalores negativos | {h.n_negative} |")
        _h(f"| Autovalores cerca cero | {h.n_zero} |")
        stable_str = "✅ minimo stable" if h.stable else "❌ punto silla"
        _h(f"| Evaluacion | {stable_str} |")

        if h.flags:
            _h(f"\n**Flags:** `{'`, `'.join(h.flags)}`")

    # Seccion phonon.
    if phonon_result is not None:
        ph = phonon_result
        _h("\n## 2. Frecuencias phonon (supercelda)")
        sc = ph.supercell
        _h(f"\n- Atomos celda unitaria: {ph.n_atoms_unit_cell}")
        _h(f"- Supercell: {sc[0]}×{sc[1]}×{sc[2]}")
        _h(f"- Paso diferencias finitas: {ph.delta_Ang:.4f} Å")
        _h(f"- Ramas phonon esperadas: {3 * ph.n_atoms_unit_cell}")

        _h("\n### 2.1 Modos imaginarios")
        if ph.n_imaginary == 0:
            _h("\n✅ Sin frecuencias phonon imaginarias. Estructura dinamicamente stable.")
        else:
            _h(f"\n❌ {ph.n_imaginary} modos imaginarios detectados: instability.")
            _h(f"\n- Frecuencia mas negativa: **{ph.max_imaginary_cm1:.1f} cm⁻¹**")

        _h("\n### 2.2 Rango frecuencia")
        freqs = ph.frequencies_cm1.flatten()
        real_freqs = freqs[freqs > 1.0]
        imag_freqs = freqs[freqs < -10.0]

        _h(f"\n| Propiedad | Valor |")
        _h("|----------|-------|")
        _h(f"| Frecuencia real min | {real_freqs.min():.1f} cm⁻¹" if real_freqs.size else "| Frecuencia real min | N/A |")
        _h(f"| Frecuencia real max | {real_freqs.max():.1f} cm⁻¹" if real_freqs.size else "| Frecuencia real max | N/A |")
        if imag_freqs.size:
            _h(f"| Imaginaria peor | {imag_freqs.min():.1f} cm⁻¹ |")
        _h(f"| N imaginarias (>10 cm⁻¹) | {ph.n_imaginary} |")

        if ph.flags:
            _h(f"\n**Flags:** `{'`, `'.join(ph.flags)}`")

    # Diagnostico estructural.
    _h("\n## 3. Diagnostico estructural")

    all_stable = True
    if hessian_result is not None and not hessian_result.stable:
        all_stable = False
    if phonon_result is not None and not phonon_result.stable:
        all_stable = False

    if all_stable:
        _h(
            "\nEstructura pasa checks vibracionales. "
            "Representa minimo local stable. "
            "Apta para DOS, bandas, transporte."
        )
    else:
        _h(
            "\n⚠ **Estructura con una o mas instability dinamicas.** "
            "Bandgap/DOS desde esta geometria pueden fallar. "
            "Resolver instability antes de aceptar DFT."
        )
        _h(
            "\n**Causas posibles en haluros perovskita:**\n"
            "- Inclinacion octaedrica suprimida\n"
            "- Desorden sitio A ausente (FA⁺, MA⁺ fijos)\n"
            "- Fase incorrecta (δ usando estructura α)\n"
            "- Relajacion insuficiente; fuerzas residuales altas\n"
        )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
