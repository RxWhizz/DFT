"""Utilidades gráficas: bandas, DOS, convergencia."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "legend.fontsize": 10,
    "figure.dpi": 100,
})

# Color palette para PDOS - covers common haluro perovskita elements
_BASE_PDOS_COLORS: dict[str, str] = {
    "I":  "#2176AE",   # blue - I 5p dominates VBM en lead iodide perovskites
    "Pb": "#D62828",   # red - Pb 6p dominates CBM
    "Cs": "#888888",
    "Br": "#0D6E3A",
    "Cl": "#8B0000",
    "Sn": "#B5460F",
    "Ge": "#7A3300",
    "Rb": "#666666",
    "K":  "#444444",
    "MA": "#9B59B6",
    "FA": "#6C3483",
}

_AUTO_COLORS = [
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3",
    "#ff7f00", "#a65628", "#f781bf", "#999999",
]

# Backwards-compatible alias
PDOS_COLORS = _BASE_PDOS_COLORS

OUTPUT_DPI = 300


def get_pdos_colors(elements: list[str]) -> dict[str, str]:
    """Devuelve colores por elemento."""
    result: dict[str, str] = {}
    auto_pool = [c for c in _AUTO_COLORS if c not in _BASE_PDOS_COLORS.values()]
    for el in elements:
        if el in _BASE_PDOS_COLORS:
            result[el] = _BASE_PDOS_COLORS[el]
        else:
            result[el] = auto_pool.pop(0) if auto_pool else "#333333"
    return result


def plot_band_structure(
    bs,
    soc_eigs: Optional[np.ndarray] = None,
    scissor_shift: float = 0.0,
    title: str = "",
    energy_window: tuple[float, float] = (-4.0, 4.0),
    output_prefix: str = "band_structure",
    output_dir: str | Path = ".",
) -> plt.Figure:
    """Grafica bandas ASE + SOC/scissor opcional."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    energies = bs.energies.copy()
    ef = bs.reference

    # Aplica scissor conduction bands
    if scissor_shift != 0.0:
        cb_mask = energies > ef
        energies[cb_mask] += scissor_shift

    # Relative VBM
    energies -= ef
    kx = np.linspace(0, 1, energies.shape[1])

    fig, ax = plt.subplots(figsize=(7, 5))

    for spin in range(energies.shape[0]):
        color = "#1f4e79" if spin == 0 else "#c00000"
        for band in range(energies.shape[2]):
            ax.plot(kx, energies[spin, :, band], color=color, lw=1.2, alpha=0.85)

    if soc_eigs is not None:
        kx_soc = np.linspace(0, 1, soc_eigs.shape[0])
        for band_idx in range(soc_eigs.shape[1]):
            ax.plot(
                kx_soc,
                soc_eigs[:, band_idx] - ef,
                color="#e85d04",
                lw=0.9,
                alpha=0.7,
                linestyle="--",
                label="SOC" if band_idx == 0 else "",
            )

    # Mark VBM y CBM
    try:
        vbm = float(energies[energies <= 0].max())
        cbm = float(energies[energies > 0].min())
        gap = cbm - vbm
        ax.axhline(vbm, color="navy", lw=0.6, ls=":")
        ax.axhline(cbm, color="darkred", lw=0.6, ls=":")
        ax.annotate(
            f"Eg = {gap:.2f} eV",
            xy=(0.75, (vbm + cbm) / 2),
            xycoords=("axes fraction", "data"),
            fontsize=10,
            color="black",
            va="center",
        )
    except ValueError:
        pass

    # High-symmetry k-point vertical lines (si disponible)
    if hasattr(bs, "path") and bs.path is not None:
        try:
            special_k = bs.path.special_points
            xcoords, labels = bs.path.get_linear_kpoint_axis()
            for xc, lab in zip(xcoords, labels):
                ax.axvline(xc, color="black", lw=0.6, ls="-", alpha=0.5)
            ax.set_xticks(xcoords)
            ax.set_xticklabels([r"$\Gamma$" if l == "G" else l for l in labels])
        except Exception:
            ax.set_xlabel("ruta k (u.a.)")
    else:
        ax.set_xlabel("ruta k (u.a.)")

    ax.axhline(0, color="black", lw=0.8, ls="--", alpha=0.4)
    ax.set_ylim(energy_window)
    ax.set_ylabel("Energía - VBM (eV)")
    ax.set_xlim(0, 1)
    if title:
        ax.set_title(title)
    if soc_eigs is not None:
        ax.legend(loc="upper right")

    fig.tight_layout()

    for ext in ("png", "pdf"):
        fig.savefig(output_dir / f"{output_prefix}.{ext}", dpi=OUTPUT_DPI)

    return fig


def plot_dos(
    energies: np.ndarray,
    total_dos: np.ndarray,
    pdos_dict: dict[str, np.ndarray],
    title: str = "",
    energy_window: tuple[float, float] = (-6.0, 4.0),
    output_prefix: str = "dos",
    output_dir: str | Path = ".",
    pdos_colors: Optional[dict[str, str]] = None,
) -> plt.Figure:
    """Grafica DOS total + PDOS."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    colors = pdos_colors if pdos_colors is not None else get_pdos_colors(list(pdos_dict.keys()))

    fig, ax = plt.subplots(figsize=(6, 5))

    # Total DOS
    ax.plot(energies, total_dos, color="black", lw=1.5, label="DOS total")

    # PDOS
    for sym, pdos in pdos_dict.items():
        color = colors.get(sym, "gray")
        ax.fill_between(energies, 0, pdos, alpha=0.35, color=color)
        ax.plot(energies, pdos, color=color, lw=1.0, label=f"{sym} PDOS")

    ax.axvline(0, color="black", lw=1.0, ls="--", alpha=0.6, label="$E_F$")

    ax.set_xlim(energy_window)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Energía (eV)")
    ax.set_ylabel("DOS (estados/eV/celda)")
    ax.legend(loc="upper left", framealpha=0.8)
    if title:
        ax.set_title(title)

    fig.tight_layout()

    for ext in ("png", "pdf"):
        fig.savefig(output_dir / f"{output_prefix}.{ext}", dpi=OUTPUT_DPI)

    return fig


def plot_convergence(
    df,
    param: str = "ecut_eV",
    ylabel: str = "ΔE (meV/átomo)",
    threshold_meV: float = 1.0,
    title: str = "",
    output_prefix: str = "convergence",
    output_dir: str | Path = ".",
) -> plt.Figure:
    """Grafica convergencia energía vs Ecut/k."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(6, 4))

    x = df[param].values
    y = df["delta_meV_per_atom"].abs().values

    ax.plot(x, y, "o-", color="#1f4e79", lw=1.8, ms=6, label="|ΔE|")
    ax.axhline(threshold_meV, color="crimson", lw=1.2, ls="--",
               label=f"umbral {threshold_meV} meV/átomo")

    xlabel_map = {
        "ecut_eV": "Corte ondas planas (eV)",
        "nkpts_total": "Puntos k totales (Nx·Ny·Nz)",
    }
    ax.set_xlabel(xlabel_map.get(param, param))
    ax.set_ylabel(ylabel)
    ax.set_ylim(bottom=0)
    ax.legend()
    if title:
        ax.set_title(title)

    fig.tight_layout()

    for ext in ("png", "pdf"):
        fig.savefig(output_dir / f"{output_prefix}.{ext}", dpi=OUTPUT_DPI)

    return fig


# Dispersion fonon + plots comparativos.

def plot_phonon_dispersion(
    result,
    title: str = "Dispersión fonónica",
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Panel fonones + DOS."""
    freqs = result.frequencies_cm1
    nq, nbranch = freqs.shape

    has_dos = result.dos_frequencies_cm1 is not None and result.dos_weights is not None

    if has_dos:
        fig, (ax_disp, ax_dos) = plt.subplots(
            1, 2, figsize=(8, 5), gridspec_kw={"width_ratios": [3, 1]},
            sharey=True,
        )
    else:
        fig, ax_disp = plt.subplots(figsize=(6, 5))

    q_idx = np.arange(nq)

    for b in range(nbranch):
        color = "steelblue" if freqs[:, b].min() >= -10 else "#d32f2f"
        ax_disp.plot(q_idx, freqs[:, b], lw=0.9, color=color, alpha=0.85)

    ax_disp.axhline(0, color="k", lw=0.8, ls="--", alpha=0.5)
    ax_disp.set_xlim(0, nq - 1)
    ax_disp.set_ylabel("Frecuencia (cm⁻¹)")
    ax_disp.set_xlabel("ruta q")
    ax_disp.set_title(title)

    if has_dos:
        ax_dos.plot(result.dos_weights, result.dos_frequencies_cm1,
                    color="steelblue", lw=1.2)
        ax_dos.fill_betweenx(result.dos_frequencies_cm1, 0, result.dos_weights,
                              alpha=0.25, color="steelblue")
        ax_dos.axhline(0, color="k", lw=0.8, ls="--", alpha=0.5)
        ax_dos.set_xlabel("DOS")
        ax_dos.tick_params(left=False)

    fig.tight_layout()

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        for ext in ("png", "pdf"):
            fig.savefig(output_path.with_suffix(f".{ext}"), dpi=OUTPUT_DPI)

    return fig


def plot_phonon_comparison(
    result_old,
    result_new,
    output_dir: Path = Path("."),
    label_old: str = "ASE Δ=0.05 Å",
    label_new: str = "Phonopy Δ=0.02 Å",
) -> plt.Figure:
    """Compara dos PhononResult."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(11, 7))
    gs = fig.add_gridspec(2, 2, height_ratios=[3, 1], hspace=0.35, wspace=0.3)

    ax_old = fig.add_subplot(gs[0, 0])
    ax_new = fig.add_subplot(gs[0, 1], sharey=ax_old)
    ax_dos = fig.add_subplot(gs[1, :])

    def _draw_dispersion(ax, result, label):
        freqs = result.frequencies_cm1
        nq = freqs.shape[0]
        q = np.arange(nq)
        for b in range(freqs.shape[1]):
            is_imag = freqs[:, b].min() < -10
            ax.plot(q, freqs[:, b], lw=0.85,
                    color="#d32f2f" if is_imag else "steelblue", alpha=0.8)
        ax.axhline(0, color="k", lw=0.8, ls="--", alpha=0.5)
        ax.set_xlim(0, nq - 1)
        ax.set_title(label, fontsize=11)
        ax.set_ylabel("Frecuencia (cm⁻¹)")
        ax.set_xlabel("ruta q")
        n_im = result.n_imaginary
        tag = f"{n_im} imag." if n_im else "estable"
        ax.text(0.97, 0.03, tag, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=9, color="#d32f2f" if n_im else "green")

    _draw_dispersion(ax_old, result_old, label_old)
    _draw_dispersion(ax_new, result_new, label_new)

    for result, label, color in [
        (result_old, label_old, "#d32f2f"),
        (result_new, label_new, "steelblue"),
    ]:
        if result.dos_frequencies_cm1 is not None:
            ax_dos.plot(result.dos_frequencies_cm1, result.dos_weights,
                        color=color, lw=1.2, label=label, alpha=0.85)
            ax_dos.fill_between(result.dos_frequencies_cm1, 0, result.dos_weights,
                                 alpha=0.15, color=color)

    ax_dos.axvline(0, color="k", lw=0.8, ls="--", alpha=0.5)
    ax_dos.set_xlabel("Frecuencia (cm⁻¹)")
    ax_dos.set_ylabel("DOS")
    ax_dos.legend(fontsize=9)

    fig.suptitle("Dispersión fonónica: comparación Δ", fontsize=13, fontweight="bold")
    fig.tight_layout()

    for ext in ("png", "pdf"):
        fig.savefig(output_dir / f"phonon_comparison_delta.{ext}", dpi=OUTPUT_DPI)

    return fig


# PES scan y NEB ruta plots

def plot_pes_scan(
    result,
    title: str = "Barrido PES - modo blando",
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Grafica E(Q) desde PES."""
    q = result.displacements_Ang
    E = result.energies_eV * 1000  # convert meV para readability

    fig, ax = plt.subplots(figsize=(6, 4))

    ax.plot(q, E, "o-", color="#1f4e79", lw=1.8, ms=5, label="E(Q)")
    ax.axvline(0, color="black", lw=0.8, ls="--", alpha=0.5, label="Equilibrio")

    if result.double_well_detected:
        ax.plot(result.saddle_Q_Ang, result.energies_eV[
            int(np.argmin(np.abs(q - result.saddle_Q_Ang)))
        ] * 1000, "v", color="#d32f2f", ms=10, zorder=5, label="Punto silla")
        ax.plot(result.q_min1_Ang, result.energies_eV[
            int(np.argmin(np.abs(q - result.q_min1_Ang)))
        ] * 1000, "o", color="steelblue", ms=9, zorder=5, label="Mínimos")
        ax.plot(result.q_min2_Ang, result.energies_eV[
            int(np.argmin(np.abs(q - result.q_min2_Ang)))
        ] * 1000, "o", color="steelblue", ms=9, zorder=5)
        ax.annotate(
            f"Barrera: {result.barrier_meV:.1f} meV",
            xy=(result.saddle_Q_Ang, result.energies_eV[
                int(np.argmin(np.abs(q - result.saddle_Q_Ang)))
            ] * 1000),
            xytext=(0.65, 0.88), textcoords="axes fraction",
            fontsize=10, color="#d32f2f",
            arrowprops=dict(arrowstyle="->", color="#d32f2f", lw=1.2),
        )

    ax.set_xlabel(f"Desplazamiento Q modo {result.mode_index} (Å)")
    ax.set_ylabel("ΔE (meV)")
    ax.set_title(
        f"{title}\n"
        f"λ = {result.eigenvalue_eV_Ang2:.4f} eV/Å²  |  "
        f"{'doble pozo' if result.double_well_detected else 'pozo simple'}",
        fontsize=11,
    )
    ax.legend(fontsize=9)
    fig.tight_layout()

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        for ext in ("png", "pdf"):
            fig.savefig(output_path.with_suffix(f".{ext}"), dpi=OUTPUT_DPI)

    return fig


def plot_neb_path(
    result,
    title: str = "Perfil energía CI-NEB",
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Grafica perfil NEB."""
    E_meV = result.energies_eV * 1000
    images_idx = np.arange(result.n_images)

    fig, ax = plt.subplots(figsize=(6, 4))

    ax.plot(images_idx, E_meV, "o-", color="#1f4e79", lw=1.8, ms=6)
    ax.plot(
        result.saddle_image_idx, E_meV[result.saddle_image_idx],
        "v", color="#d32f2f", ms=11, zorder=5, label="Silla (TS)",
    )

    ax.annotate(
        f"Barrera ida: {result.barrier_forward_meV:.1f} meV",
        xy=(result.saddle_image_idx, E_meV[result.saddle_image_idx]),
        xytext=(0.05, 0.88), textcoords="axes fraction",
        fontsize=10, color="#d32f2f",
    )
    ax.annotate(
        f"Barrera vuelta: {result.barrier_reverse_meV:.1f} meV",
        xy=(result.saddle_image_idx, E_meV[result.saddle_image_idx]),
        xytext=(0.05, 0.76), textcoords="axes fraction",
        fontsize=10, color="steelblue",
    )

    converged_str = "convergido" if result.converged else "no convergido"
    ax.set_xlabel("índice imagen NEB")
    ax.set_ylabel("ΔE (meV)")
    ax.set_title(f"{title}\n{converged_str}", fontsize=11)
    ax.set_xticks(images_idx)
    ax.legend(fontsize=9)
    fig.tight_layout()

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        for ext in ("png", "pdf"):
            fig.savefig(output_path.with_suffix(f".{ext}"), dpi=OUTPUT_DPI)

    return fig
