#!/usr/bin/env python3
"""Genera gráficas listas para publicar desde salidas GPAW/NumPy."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from math import ceil
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path("/tmp") / "matplotlib-cspbi3"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

OUTPUT_DPI = 300
PLOT_DATE = datetime.now().strftime("%d/%m/%y")
EV_A2_TO_SI = 1.602176634e-19 / (1e-10) ** 2
AMU_TO_KG = 1.66053906660e-27
C_CM_S = 2.99792458e10
PDOS_COLORS = {
    "I": "#2176AE",
    "Pb": "#D62828",
    "Cs": "#888888",
    "Br": "#0D6E3A",
    "Cl": "#8B0000",
    "Sn": "#B5460F",
    "Ge": "#7A3300",
    "Rb": "#666666",
    "K": "#444444",
}
AUTO_COLORS = [
    "#e41a1c",
    "#377eb8",
    "#4daf4a",
    "#984ea3",
    "#ff7f00",
    "#a65628",
    "#f781bf",
    "#999999",
]
STRUCTURE_COLORS = {
    "Cs": "#c79a24",
    "Pb": "#4c78a8",
    "Sn": "#b85c38",
    "I": "#6f3fa0",
    "Br": "#9a4b22",
    "Cl": "#2ca25f",
    "C": "#2f2f2f",
    "N": "#2b6cb0",
    "H": "#f2f2f2",
}
STRUCTURE_SIZES = {
    "Cs": 190,
    "Pb": 155,
    "Sn": 145,
    "I": 100,
    "Br": 92,
    "Cl": 78,
    "C": 62,
    "N": 66,
    "H": 30,
}
STRUCTURE_RADII = {
    "Cs": 0.55,
    "Pb": 0.45,
    "Sn": 0.42,
    "I": 0.35,
    "Br": 0.32,
    "Cl": 0.28,
    "C": 0.25,
    "N": 0.24,
    "H": 0.16,
}
B_SITE_ELEMENTS = {"Pb", "Sn", "Ge"}
HALIDE_ELEMENTS = {"I", "Br", "Cl"}
A_SITE_ELEMENTS = {"Cs", "Rb", "K"}
ORGANIC_ELEMENTS = {"C", "N", "H"}


@dataclass(frozen=True)
class PhasePaths:
    """Rutas fase cálculo."""

    calc_dir: Path
    out_dir: Path
    initial_cif: Path
    relaxed_cif: Path
    relax_traj: Path
    relax_gpw: Path
    scf_gpw: Path
    bands_gpw: Path
    dos_gpw: Path
    hse_gpw: Path
    soc_eigs: Path
    soc_spin: Path
    hessian: Path
    hessian_eigs: Path
    phonon_freqs: Path
    phonon_freqs_phonopy: Path
    phonon_dos_phonopy: Path
    pes_displacements: Path
    pes_energies: Path
    born_charges: Path
    dielectric_tensor: Path
    loto_born_charges: Path
    loto_dielectric_tensor: Path


def build_paths(calc_dir: Path, out_dir: Path) -> PhasePaths:
    return PhasePaths(
        calc_dir=calc_dir,
        out_dir=out_dir,
        initial_cif=calc_dir / "01_relax" / "initial_structure.cif",
        relaxed_cif=calc_dir / "01_relax" / "relaxed.cif",
        relax_traj=calc_dir / "01_relax" / "relax.traj",
        relax_gpw=calc_dir / "01_relax" / "relax.gpw",
        scf_gpw=calc_dir / "02_scf" / "scf.gpw",
        bands_gpw=calc_dir / "03_bands" / "bands.gpw",
        dos_gpw=calc_dir / "04_dos" / "dos.gpw",
        hse_gpw=calc_dir / "06_hse06" / "hse06_checkpoint.gpw",
        soc_eigs=calc_dir / "05_soc" / "soc_eigenvalues.npy",
        soc_spin=calc_dir / "05_soc" / "soc_spin_projections.npy",
        hessian=calc_dir / "07_vibrational" / "hessian" / "hessian.npy",
        hessian_eigs=calc_dir / "07_vibrational" / "hessian" / "hessian_eigenvalues.npy",
        phonon_freqs=calc_dir / "07_vibrational" / "phonons" / "phonon_frequencies.npy",
        phonon_freqs_phonopy=(
            calc_dir / "07_vibrational" / "phonons" / "phonon_frequencies_phonopy.npy"
        ),
        phonon_dos_phonopy=calc_dir / "07_vibrational" / "phonons" / "phonon_dos_phonopy.npy",
        pes_displacements=calc_dir / "07_vibrational" / "pes" / "pes_displacements.npy",
        pes_energies=calc_dir / "07_vibrational" / "pes" / "pes_energies.npy",
        born_charges=calc_dir / "07_vibrational" / "phonons" / "born_charges.npy",
        dielectric_tensor=calc_dir / "07_vibrational" / "phonons" / "dielectric_tensor.npy",
        loto_born_charges=calc_dir / "08_loto" / "born_charges.npy",
        loto_dielectric_tensor=calc_dir / "08_loto" / "dielectric_tensor.npy",
    )


def note(messages: list[str], message: str) -> None:
    print(message)
    messages.append(message)


def save_figure(fig: plt.Figure, out_dir: Path, stem: str, outputs: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        path = out_dir / f"{stem}.{ext}"
        fig.savefig(path, dpi=OUTPUT_DPI, bbox_inches="tight")
        outputs.append(str(path.relative_to(ROOT)))
    plt.close(fig)


def dated_title(title: str) -> str:
    return f"{title}-{PLOT_DATE}"


def get_pdos_colors(elements: list[str]) -> dict[str, str]:
    colors: dict[str, str] = {}
    fallback = [color for color in AUTO_COLORS if color not in PDOS_COLORS.values()]
    for element in elements:
        if element in PDOS_COLORS:
            colors[element] = PDOS_COLORS[element]
        else:
            colors[element] = fallback.pop(0) if fallback else "#333333"
    return colors


def get_structure_style(symbols: list[str]) -> tuple[dict[str, str], dict[str, int], dict[str, float]]:
    """Devuelve colores, tamaños y radios ASE."""
    unique = list(dict.fromkeys(symbols))
    colors: dict[str, str] = {}
    sizes: dict[str, int] = {}
    radii: dict[str, float] = {}
    fallback = [color for color in AUTO_COLORS if color not in STRUCTURE_COLORS.values()]
    for element in unique:
        colors[element] = STRUCTURE_COLORS.get(element, fallback.pop(0) if fallback else "#888888")
        sizes[element] = STRUCTURE_SIZES.get(element, 84)
        radii[element] = STRUCTURE_RADII.get(element, 0.32)
    return colors, sizes, radii


def ordered_symbols(symbols: list[str] | np.ndarray) -> list[str]:
    priority = ["Cs", "Rb", "K", "C", "N", "H", "Pb", "Sn", "Ge", "I", "Br", "Cl"]
    present = set(str(symbol) for symbol in symbols)
    ordered = [symbol for symbol in priority if symbol in present]
    ordered.extend(sorted(present - set(ordered)))
    return ordered


def draw_cell_wireframe(
    ax: Any,
    cell: np.ndarray,
    repeats: tuple[int, int, int] = (1, 1, 1),
    outer_color: str = "#3d3d3d",
    grid_color: str = "#8a8a8a",
    outer_lw: float = 1.6,
    grid_lw: float = 0.8,
    outer_alpha: float = 0.78,
    grid_alpha: float = 0.38,
) -> np.ndarray:
    """Dibuja rejilla suave + celda externa."""
    repeats_array = np.array(repeats, dtype=float)
    vectors = cell / repeats_array[:, None]
    nx, ny, nz = repeats

    def line(start: np.ndarray, end: np.ndarray, color: str, lw: float, alpha: float) -> None:
        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            [start[2], end[2]],
            color=color,
            lw=lw,
            alpha=alpha,
        )

    if max(repeats) > 1:
        for j in range(ny + 1):
            for k in range(nz + 1):
                start = j * vectors[1] + k * vectors[2]
                line(start, start + nx * vectors[0], grid_color, grid_lw, grid_alpha)
        for i in range(nx + 1):
            for k in range(nz + 1):
                start = i * vectors[0] + k * vectors[2]
                line(start, start + ny * vectors[1], grid_color, grid_lw, grid_alpha)
        for i in range(nx + 1):
            for j in range(ny + 1):
                start = i * vectors[0] + j * vectors[1]
                line(start, start + nz * vectors[2], grid_color, grid_lw, grid_alpha)

    corners = np.array(
        [
            [0, 0, 0],
            cell[0],
            cell[1],
            cell[2],
            cell[0] + cell[1],
            cell[0] + cell[2],
            cell[1] + cell[2],
            cell[0] + cell[1] + cell[2],
        ]
    )
    edges = [(0, 1), (0, 2), (0, 3), (1, 4), (1, 5), (2, 4)]
    edges += [(2, 6), (3, 5), (3, 6), (4, 7), (5, 7), (6, 7)]
    for i, j in edges:
        line(corners[i], corners[j], outer_color, outer_lw, outer_alpha)
    return corners


def style_structure_axis(ax: Any) -> None:
    """Eje 3D limpio para figuras."""
    ax.set_axis_off()
    ax.grid(False)
    ax.set_facecolor("white")
    try:
        ax.set_proj_type("ortho")
    except Exception:
        pass
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        try:
            axis.pane.set_alpha(0.0)
            axis.line.set_alpha(0.0)
        except Exception:
            pass


def set_structure_limits(ax: Any, points: np.ndarray, pad: float = 1.08) -> None:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    spans = np.maximum(maxs - mins, 1.0)
    padding = spans * (pad - 1.0)
    ax.set_xlim(mins[0] - padding[0], maxs[0] + padding[0])
    ax.set_ylim(mins[1] - padding[1], maxs[1] + padding[1])
    ax.set_zlim(mins[2] - padding[2], maxs[2] + padding[2])
    ax.set_box_aspect(tuple(spans))


def draw_pb_i_bonds(
    ax: Any,
    pos: np.ndarray,
    symbols: np.ndarray,
    cutoff: float = 3.75,
    lw: float = 3.0,
    alpha: float = 0.82,
) -> dict[int, list[int]]:
    """Dibuja enlaces B-X; devuelve vecinos B."""
    b_indices = np.array([idx for idx, sym in enumerate(symbols) if sym in B_SITE_ELEMENTS])
    x_indices = np.array([idx for idx, sym in enumerate(symbols) if sym in HALIDE_ELEMENTS])
    neighbor_map: dict[int, list[int]] = {}
    if len(b_indices) == 0 or len(x_indices) == 0:
        return neighbor_map
    for b_idx in b_indices:
        distances = np.linalg.norm(pos[x_indices] - pos[b_idx], axis=1)
        close = x_indices[distances <= cutoff]
        if len(close) == 0:
            continue
        neighbor_map[int(b_idx)] = [int(idx) for idx in close]
        for x_idx in close:
            ax.plot(
                [pos[b_idx, 0], pos[x_idx, 0]],
                [pos[b_idx, 1], pos[x_idx, 1]],
                [pos[b_idx, 2], pos[x_idx, 2]],
                color="#7a7a7a",
                lw=lw,
                alpha=alpha,
                solid_capstyle="round",
            )
    return neighbor_map


def draw_molecular_bonds(
    ax: Any,
    pos: np.ndarray,
    symbols: np.ndarray,
    lw: float = 1.5,
    alpha: float = 0.65,
) -> None:
    """Dibuja enlaces internos MA/FA."""
    covalent_cutoffs = {
        frozenset(("C", "N")): 1.55,
        frozenset(("C", "H")): 1.25,
        frozenset(("N", "H")): 1.20,
    }
    organic_indices = [idx for idx, sym in enumerate(symbols) if sym in ORGANIC_ELEMENTS]
    for left, right in combinations(organic_indices, 2):
        pair = frozenset((str(symbols[left]), str(symbols[right])))
        cutoff = covalent_cutoffs.get(pair)
        if cutoff is None:
            continue
        if np.linalg.norm(pos[left] - pos[right]) > cutoff:
            continue
        ax.plot(
            [pos[left, 0], pos[right, 0]],
            [pos[left, 1], pos[right, 1]],
            [pos[left, 2], pos[right, 2]],
            color="#5f6368",
            lw=lw,
            alpha=alpha,
            solid_capstyle="round",
        )


def plot_ball_stick_structure(
    ax: Any,
    atoms: Any,
    colors: dict[str, str],
    scatter_sizes: dict[str, int],
    repeats: tuple[int, int, int] = (1, 1, 1),
    panel_label: str | None = None,
    cutoff: float = 3.75,
) -> None:
    pos = atoms.get_positions()
    symbols = np.array(atoms.get_chemical_symbols())
    max_repeat = max(repeats)
    size_scale = 1.0 if max_repeat == 1 else max(0.28, 1.0 / (max_repeat**0.45))
    edge_lw = 0.55 if max_repeat == 1 else 0.28

    draw_pb_i_bonds(
        ax,
        pos,
        symbols,
        cutoff=cutoff,
        lw=3.8 if max_repeat == 1 else 2.2,
        alpha=0.84,
    )
    draw_molecular_bonds(
        ax,
        pos,
        symbols,
        lw=1.6 if max_repeat == 1 else 0.9,
        alpha=0.70,
    )
    corners = draw_cell_wireframe(
        ax,
        atoms.cell.array,
        repeats=repeats,
        outer_color="#4b4b4b",
        grid_color="#9a9a9a",
        outer_lw=1.9 if max_repeat == 1 else 1.45,
        grid_lw=0.8 if max_repeat == 1 else 0.62,
        outer_alpha=0.76,
        grid_alpha=0.34,
    )

    for sym in ordered_symbols(symbols):
        mask = symbols == sym
        if not mask.any():
            continue
        ax.scatter(
            pos[mask, 0],
            pos[mask, 1],
            pos[mask, 2],
            s=scatter_sizes.get(sym, 110) * size_scale,
            c=colors.get(sym, "#999999"),
            edgecolor="#303030",
            linewidth=edge_lw,
            alpha=0.96,
            depthshade=True,
        )

    style_structure_axis(ax)
    set_structure_limits(ax, np.vstack([pos, corners]))
    ax.view_init(elev=18, azim=36)
    if panel_label:
        ax.text2D(0.00, 0.98, panel_label, transform=ax.transAxes, fontsize=16, color="black")


def add_species_legend(ax: Any, colors: dict[str, str], symbols: list[str]) -> None:
    """Agrega leyenda especies."""
    from matplotlib.lines import Line2D

    present = dict.fromkeys(s for s in symbols if s in colors)
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=colors[s],
               markeredgecolor="#303030", markeredgewidth=0.6, markersize=8, label=s)
        for s in present
    ]
    if handles:
        ax.legend(handles=handles, loc="upper right", fontsize=9, framealpha=0.85)


def plot_cell_3d(
    atoms: Any,
    paths: PhasePaths,
    label: str,
    outputs: list[str],
    colors: dict[str, str],
    scatter_sizes: dict[str, int],
    repeats: tuple[int, int, int] = (1, 1, 1),
) -> None:
    fig = plt.figure(figsize=(7.2, 6.0), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")
    fig.subplots_adjust(left=0.0, right=1.0, top=0.95, bottom=0.0)
    plot_ball_stick_structure(ax, atoms, colors, scatter_sizes, repeats=repeats, panel_label="(a)")
    add_species_legend(ax, colors, list(atoms.get_chemical_symbols()))
    cell = atoms.cell.lengths()
    fig.suptitle(
        dated_title(f"Celda 3D {label}") + f"\na={cell[0]:.2f}, b={cell[1]:.2f}, c={cell[2]:.2f} Å",
        fontsize=9, y=0.99,
    )
    save_figure(fig, paths.out_dir, f"cell_3d_{label}", outputs)


def plot_octahedra_3d(
    base_atoms: Any,
    paths: PhasePaths,
    repeat: int,
    outputs: list[str],
    colors: dict[str, str],
    label: str = "relaxed",
    cutoff: float = 3.75,
) -> None:
    """Grafica celda repetida; muestra BX6."""
    atoms = base_atoms.repeat((repeat, repeat, repeat))
    pos = atoms.get_positions()
    symbols = np.array(atoms.get_chemical_symbols())

    fig = plt.figure(figsize=(7.2, 6.0), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")
    fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0)

    neighbor_map = draw_pb_i_bonds(
        ax,
        pos,
        symbols,
        cutoff=cutoff,
        lw=2.2 if repeat == 2 else 1.35,
        alpha=0.86,
    )
    draw_molecular_bonds(
        ax,
        pos,
        symbols,
        lw=0.85 if repeat == 2 else 0.48,
        alpha=0.52,
    )
    corners = draw_cell_wireframe(
        ax,
        atoms.cell.array,
        repeats=(repeat, repeat, repeat),
        outer_color="#4b4b4b",
        grid_color="#9a9a9a",
        outer_lw=1.45,
        grid_lw=0.62,
        outer_alpha=0.76,
        grid_alpha=0.34,
    )
    guide_lw = 0.55 if repeat == 2 else 0.34
    for pb_idx, neighbors in neighbor_map.items():
        if len(neighbors) >= 6:
            for i_a, i_b in combinations(neighbors, 2):
                d_ii = np.linalg.norm(pos[i_a] - pos[i_b])
                if d_ii <= 5.0:
                    ax.plot(
                        [pos[i_a, 0], pos[i_b, 0]],
                        [pos[i_a, 1], pos[i_b, 1]],
                        [pos[i_a, 2], pos[i_b, 2]],
                        color="#5f6368",
                        lw=guide_lw,
                        alpha=0.28,
                    )

    for sym in ordered_symbols(symbols):
        mask = symbols == sym
        if not mask.any():
            continue
        base_size = STRUCTURE_SIZES.get(sym, 84)
        alpha = 0.82 if sym in A_SITE_ELEMENTS | ORGANIC_ELEMENTS else 0.96
        ax.scatter(
            pos[mask, 0],
            pos[mask, 1],
            pos[mask, 2],
            s=base_size * (0.42 if repeat == 2 else 0.24),
            c=colors.get(sym, "#999999"),
            edgecolor="#303030",
            linewidth=0.25 if repeat == 2 else 0.12,
            alpha=alpha,
            depthshade=True,
        )

    style_structure_axis(ax)
    set_structure_limits(ax, np.vstack([pos, corners]), pad=1.06)
    ax.view_init(elev=18, azim=36)
    ax.text2D(0.00, 0.98, "(a)", transform=ax.transAxes, fontsize=16, color="black")
    ax.text2D(0.01, 0.03, f"B-X <= {cutoff} A, N={len(pos)}", transform=ax.transAxes, fontsize=8,
              color="#444444")
    add_species_legend(ax, colors, list(symbols))
    fig.suptitle(dated_title(f"Octaedros BX6 {label} {repeat}x{repeat}x{repeat}"), fontsize=9, y=0.99)
    save_figure(fig, paths.out_dir, f"octahedra_{label}_{repeat}x{repeat}x{repeat}", outputs)


def plot_structure_panels(
    structures: list[tuple[str, Any]],
    paths: PhasePaths,
    outputs: list[str],
    colors: dict[str, str],
    scatter_sizes: dict[str, int],
    repeat: int = 2,
) -> None:
    """Grafica estructuras como paneles."""
    if len(structures) < 2:
        return
    panel_letters = "abcdefghijklmnopqrstuvwxyz"
    ncols = min(4, len(structures))
    nrows = ceil(len(structures) / ncols)
    fig = plt.figure(figsize=(5.0 * ncols, 4.4 * nrows), facecolor="white")
    for index, (label, atoms) in enumerate(structures):
        ax = fig.add_subplot(nrows, ncols, index + 1, projection="3d")
        repeated = atoms.repeat((repeat, repeat, repeat))
        plot_ball_stick_structure(
            ax,
            repeated,
            colors,
            scatter_sizes,
            repeats=(repeat, repeat, repeat),
            panel_label=f"({panel_letters[index]})",
        )
        ax.set_title(label, fontsize=11, pad=0)
    fig.subplots_adjust(left=0.0, right=1.0, top=0.98, bottom=0.0, wspace=0.0, hspace=0.02)
    labels = "_".join(label for label, _atoms in structures)
    save_figure(fig, paths.out_dir, f"structure_panels_{labels}_{repeat}x{repeat}x{repeat}", outputs)


def load_atoms(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix in {".gpw", ".gpaw"}:
        from gpaw import GPAW

        return GPAW(str(path), txt=None).get_atoms()

    from ase.io import read

    return read(str(path), index=-1)


def safe_label(label: str) -> str:
    label = label.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "estructura"


def parse_int_list(value: str) -> tuple[int, ...]:
    if not value:
        return ()
    repeats = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if any(repeat < 1 for repeat in repeats):
        raise argparse.ArgumentTypeError("repeticiones deben ser enteros positivos")
    return repeats


def load_structure_builder_phase(phase: str) -> Any:
    module_path = SRC / "dft_cspbi3" / "structure_builder.py"
    spec = importlib.util.spec_from_file_location("_visualizer_structure_builder", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No pude cargar StructureBuilder desde {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    builder = module.StructureBuilder
    build_method = getattr(builder, f"build_{phase}", None)
    if build_method is not None:
        return build_method()
    return builder.load_phase(phase)


def load_structure_spec(spec: str) -> tuple[str, Any]:
    """Carga estructura desde LABEL=PATH, PATH, builder:FASE o fase."""
    if "=" in spec:
        raw_label, raw_source = spec.split("=", 1)
        label = safe_label(raw_label)
        source = raw_source.strip()
    else:
        source = spec.strip()
        label_source = source.removeprefix("builder:")
        label = safe_label(
            Path(label_source).stem if any(sep in label_source for sep in ("/", "\\")) else label_source
        )

    if source.startswith("builder:"):
        phase = source.split(":", 1)[1].strip()
        return label, load_structure_builder_phase(phase)

    path = Path(source).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if path.exists():
        return label, load_atoms(path)

    phase_files = {
        "alpha": ROOT / "structures" / "alpha_cubic.json",
        "beta": ROOT / "structures" / "beta_tetra.json",
        "gamma": ROOT / "structures" / "gamma_ortho.json",
        "delta": ROOT / "structures" / "delta_ortho.json",
    }
    if source in phase_files and phase_files[source].exists():
        return label, load_atoms(phase_files[source])

    return label, load_structure_builder_phase(source)


def load_structure_inputs(
    specs: list[str] | None,
    phases: list[str] | None,
    messages: list[str],
) -> list[tuple[str, Any]]:
    loaded: list[tuple[str, Any]] = []
    for spec in [*(phases or []), *(specs or [])]:
        try:
            loaded.append(load_structure_spec(spec))
        except Exception as exc:
            note(messages, f"Estructura omitida {spec}: {exc}")
    return loaded


def plot_cell_views(
    paths: PhasePaths,
    outputs: list[str],
    messages: list[str],
    skip_gpaw: bool = False,
    structure_inputs: list[tuple[str, Any]] | None = None,
    supercell_repeats: tuple[int, ...] = (3, 6),
    octahedra_repeats: tuple[int, ...] = (2, 3),
) -> None:
    if structure_inputs:
        loaded = structure_inputs
    else:
        candidates = [
            ("initial", paths.initial_cif),
            ("relaxed", paths.relaxed_cif),
            ("relax_checkpoint", paths.relax_gpw),
            ("scf_checkpoint", paths.scf_gpw),
        ]

        loaded = []
        for label, path in candidates:
            if skip_gpaw and path.suffix in {".gpw", ".gpaw"}:
                continue
            if path.exists():
                try:
                    loaded.append((label, load_atoms(path)))
                except Exception as exc:
                    note(messages, f"Estructura omitida {path}: {exc}")

    if not loaded:
        note(messages, "Sin archivos estructura para gráficas celda.")
        return

    from ase.visualize.plot import plot_atoms

    all_symbols = [
        symbol
        for _label, atoms in loaded
        for symbol in atoms.get_chemical_symbols()
    ]
    colors, scatter_sizes, radii = get_structure_style(all_symbols)

    view_labels = ("ab", "ac", "bc")
    rotations = ("0x,0y,0z", "90x,0y,0z", "0x,90y,0z")

    for label, atoms in loaded:
        fig, axes = plt.subplots(1, 3, figsize=(10, 4.0), facecolor="white")
        atom_radii = [radii.get(sym, 0.4) for sym in atoms.symbols]
        atom_colors = [colors.get(sym, "#999999") for sym in atoms.symbols]
        for index, (ax, rotation) in enumerate(zip(axes, rotations)):
            plot_atoms(
                atoms,
                ax,
                rotation=rotation,
                radii=atom_radii,
                colors=atom_colors,
                show_unit_cell=2,
            )
            ax.set_title(f"vista {view_labels[index]}", fontsize=11)
            ax.text(0.01, 0.97, f"({chr(ord('a') + index)})", transform=ax.transAxes,
                    fontsize=13, va="top")
            ax.set_axis_off()

        # species legend en right axes
        from matplotlib.patches import Patch
        present = dict.fromkeys(s for s in ordered_symbols(atoms.get_chemical_symbols()) if s in colors)
        handles = [Patch(facecolor=colors[s], edgecolor="#303030", linewidth=0.6, label=s)
                   for s in present]
        axes[-1].legend(handles=handles, loc="lower right", fontsize=9, framealpha=0.85)

        cell = atoms.cell.lengths()
        fig.suptitle(
            dated_title(f"Celda estructura - {label}") +
            f"\na={cell[0]:.2f}, b={cell[1]:.2f}, c={cell[2]:.2f} Å",
            fontsize=10, y=1.01,
        )
        fig.subplots_adjust(left=0.0, right=1.0, top=0.92, bottom=0.0, wspace=0.02)
        save_figure(fig, paths.out_dir, f"cell_views_{label}", outputs)

        plot_cell_3d(atoms, paths, label, outputs, colors, scatter_sizes)

    if structure_inputs:
        panel_repeat = (
            octahedra_repeats[0]
            if octahedra_repeats
            else supercell_repeats[0]
            if supercell_repeats
            else 1
        )
        plot_structure_panels(loaded, paths, outputs, colors, scatter_sizes, repeat=panel_repeat)

    if structure_inputs:
        base_structures = loaded
    else:
        base_structures = [
            next(
                ((label, atoms) for label, atoms in loaded if label == "relaxed"),
                loaded[0],
            )
        ]

    for base_label, base_atoms in base_structures:
        for repeat in supercell_repeats:
            supercell = base_atoms.repeat((repeat, repeat, repeat))
            plot_cell_3d(
                supercell,
                paths,
                f"{base_label}_{repeat}x{repeat}x{repeat}",
                outputs,
                colors,
                scatter_sizes,
                repeats=(repeat, repeat, repeat),
            )
        for repeat in octahedra_repeats:
            plot_octahedra_3d(base_atoms, paths, repeat, outputs, colors, label=base_label)


def plot_dos_from_gpw(paths: PhasePaths, outputs: list[str], messages: list[str]) -> None:
    if not paths.dos_gpw.exists():
        note(messages, "Sin checkpoint DOS.")
        return

    try:
        from gpaw import GPAW
        from gpaw.dos import DOSCalculator

        calc = GPAW(str(paths.dos_gpw), txt=None)
        atoms = calc.get_atoms()
        symbols = atoms.get_chemical_symbols()

        calc_dos = DOSCalculator.from_calculator(calc, shift_fermi_level=True)
        energies = np.linspace(-6, 4, 2000)
        total = calc_dos.raw_dos(energies, width=0.05)

        pdos: dict[str, np.ndarray] = {}
        for atom_index, sym in enumerate(symbols):
            contrib = np.zeros(len(energies))
            for l in range(4):
                try:
                    contrib += calc_dos.raw_pdos(energies, a=atom_index, l=l, width=0.05)
                except Exception:
                    continue
            if sym not in pdos:
                pdos[sym] = np.zeros_like(contrib)
            pdos[sym] += contrib
    except Exception as exc:
        note(messages, f"DOS omitido desde {paths.dos_gpw}: {exc}")
        return

    colors = get_pdos_colors(list(pdos))

    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.plot(energies, total, color="black", lw=1.5, label="DOS total")
    for sym, values in pdos.items():
        color = colors.get(sym, "#777777")
        ax.fill_between(energies, 0, values, color=color, alpha=0.32)
        ax.plot(energies, values, color=color, lw=1.0, label=f"{sym} PDOS")
    ax.axvline(0, color="black", lw=1.0, ls="--", alpha=0.6, label="$E_F$")
    ax.set_xlim(-6, 4)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Energía - $E_F$ (eV)")
    ax.set_ylabel("DOS (estados/eV/celda)")
    ax.set_title(dated_title("DOS"))
    ax.legend(framealpha=0.85)
    save_figure(fig, paths.out_dir, "dos_pdos_from_gpw", outputs)


def plot_band_structure_from_gpw(paths: PhasePaths, outputs: list[str], messages: list[str]) -> None:
    if not paths.bands_gpw.exists():
        note(messages, "Sin checkpoint bandas.")
        return

    try:
        from gpaw import GPAW

        calc = GPAW(str(paths.bands_gpw), txt=None)
        bs = calc.band_structure()
    except Exception as exc:
        note(messages, f"Bandas omitidas desde {paths.bands_gpw}: {exc}")
        return

    energies = np.array(bs.energies, dtype=float)
    reference = float(bs.reference)
    rel = energies - reference
    kx = np.linspace(0, 1, rel.shape[1])

    fig, ax = plt.subplots(figsize=(7, 5))
    for spin in range(rel.shape[0]):
        color = "#1f4e79" if spin == 0 else "#c00000"
        for band in range(rel.shape[2]):
            ax.plot(kx, rel[spin, :, band], color=color, lw=1.0, alpha=0.75)

    if paths.soc_eigs.exists():
        try:
            soc = np.load(paths.soc_eigs)
            n_el = int(round(calc.get_number_of_electrons()))
            # SOC spinors hold 1 electron each (no 2) → HOMO en index n_el-1
            n_occ = max(n_el, 1)
            near = soc[:, max(n_occ - 5, 0) : n_occ + 5] - calc.get_fermi_level()
            kx_soc = np.linspace(0, 1, near.shape[0])
            for band in range(near.shape[1]):
                ax.plot(
                    kx_soc,
                    near[:, band],
                    color="#e85d04",
                    lw=0.6,
                    alpha=0.45,
                    ls="--",
                    label="eigs SOC guardados" if band == 0 else "",
                )
        except Exception as exc:
            note(messages, f"No pude superponer eigs SOC: {exc}")

    try:
        _, xcoords, labels = bs.path.get_linear_kpoint_axis()
        xcoords = np.array(xcoords, dtype=float)
        if xcoords[-1] != 0:
            xcoords = xcoords / xcoords[-1]
        ax.set_xticks(xcoords)
        ax.set_xticklabels([r"$\Gamma$" if lab in {"G", "Gamma"} else lab for lab in labels])
        for xc in xcoords:
            ax.axvline(xc, color="black", lw=0.5, alpha=0.35)
    except Exception:
        ax.set_xlabel("ruta k")

    ax.axhline(0, color="black", lw=0.8, ls="--", alpha=0.5)
    ax.set_xlim(0, 1)
    ax.set_ylim(-4, 4)
    ax.set_ylabel("Energía - referencia (eV)")
    ax.set_title(dated_title("Bandas CsPbI3 desde checkpoint GPAW"))
    if paths.soc_eigs.exists():
        ax.legend(loc="upper right")
    save_figure(fig, paths.out_dir, "band_structure_from_gpw", outputs)


def plot_phonons(paths: PhasePaths, outputs: list[str], messages: list[str]) -> None:
    source = paths.phonon_freqs_phonopy if paths.phonon_freqs_phonopy.exists() else paths.phonon_freqs
    if not source.exists():
        note(messages, "Sin .npy frecuencias fonón.")
        return

    try:
        freqs = np.load(source)
    except Exception as exc:
        note(messages, f"Fonones omitidos desde {source}: {exc}")
        return

    if freqs.ndim != 2:
        note(messages, f"Fonones omitidos: esperaba arreglo 2D, llegó {freqs.shape}.")
        return

    fig, ax = plt.subplots(figsize=(7, 5))
    x = np.arange(freqs.shape[0])
    for band in range(freqs.shape[1]):
        values = freqs[:, band]
        color = "#d62828" if values.min() < -10 else "#1f77b4"
        ax.plot(x, values, color=color, lw=0.9, alpha=0.75)
    ax.axhline(0, color="black", lw=0.8, ls="--", alpha=0.5)
    ax.set_xlabel("índice punto q")
    ax.set_ylabel("Frecuencia (cm$^{-1}$)")
    ax.set_title(dated_title(f"Dispersión fonónica desde {source.name}"))
    save_figure(fig, paths.out_dir, "phonon_dispersion_from_npy", outputs)

    if paths.phonon_dos_phonopy.exists():
        try:
            phonon_dos = np.load(paths.phonon_dos_phonopy)
            fig, ax = plt.subplots(figsize=(6, 4.5))
            if phonon_dos.ndim == 2 and phonon_dos.shape[1] >= 2:
                ax.plot(phonon_dos[:, 0], phonon_dos[:, 1], color="#1f77b4", lw=1.4)
                ax.set_xlabel("Frecuencia (cm$^{-1}$)")
                ax.set_ylabel("DOS fonónica")
            else:
                ax.hist(freqs.ravel(), bins=60, color="#1f77b4", alpha=0.8)
                ax.set_xlabel("Frecuencia (cm$^{-1}$)")
                ax.set_ylabel("Conteo")
            ax.set_title(dated_title("Densidad estados fonónica"))
            save_figure(fig, paths.out_dir, "phonon_dos_from_npy", outputs)
        except Exception as exc:
            note(messages, f"No pude graficar DOS fonónica: {exc}")


def plot_hessian(
    paths: PhasePaths,
    outputs: list[str],
    messages: list[str],
    skip_gpaw: bool = False,
) -> None:
    if not paths.hessian.exists():
        note(messages, "Sin .npy Hessiano.")
        return

    try:
        hessian = np.load(paths.hessian)
    except Exception as exc:
        note(messages, f"Hessiano omitido desde {paths.hessian}: {exc}")
        return

    fig, ax = plt.subplots(figsize=(6, 5))
    vmax = np.nanpercentile(np.abs(hessian), 98)
    im = ax.imshow(hessian, cmap="coolwarm", vmin=-vmax, vmax=vmax)
    ax.set_title(dated_title("Hessiano sin ponderar por masa"))
    ax.set_xlabel("GDL cartesiano")
    ax.set_ylabel("GDL cartesiano")
    fig.colorbar(im, ax=ax, label="eV/A$^2$")
    save_figure(fig, paths.out_dir, "hessian_matrix", outputs)

    eigs = np.load(paths.hessian_eigs) if paths.hessian_eigs.exists() else np.linalg.eigvalsh(hessian)
    fig, ax = plt.subplots(figsize=(6, 4.5))
    idx = np.arange(len(eigs))
    colors = np.where(eigs < 0, "#d62828", "#1f77b4")
    ax.bar(idx, eigs, color=colors, alpha=0.85)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("índice modo")
    ax.set_ylabel("Autovalor (eV/A$^2$)")
    ax.set_title(dated_title("Espectro autovalores Hessiano"))
    save_figure(fig, paths.out_dir, "hessian_eigenvalues", outputs)

    try:
        atoms_path = paths.relaxed_cif
        if not skip_gpaw and paths.relax_gpw.exists():
            atoms_path = paths.relax_gpw
        atoms = load_atoms(atoms_path)
        masses = np.repeat(atoms.get_masses(), 3) * AMU_TO_KG
        dyn = hessian * EV_A2_TO_SI / np.sqrt(np.outer(masses, masses))
        dyn_eigs = np.linalg.eigvalsh(dyn)
        freqs = np.sign(dyn_eigs) * np.sqrt(np.abs(dyn_eigs)) / (2 * np.pi * C_CM_S)
        fig, ax = plt.subplots(figsize=(6, 4.5))
        ax.bar(np.arange(len(freqs)), freqs, color=np.where(freqs < 0, "#d62828", "#1f77b4"))
        ax.axhline(0, color="black", lw=0.8)
        ax.set_xlabel("índice modo")
        ax.set_ylabel("Frecuencia (cm$^{-1}$)")
        ax.set_title(dated_title("Frecuencias Gamma desde Hessiano ponderado"))
        save_figure(fig, paths.out_dir, "hessian_gamma_frequencies", outputs)
    except Exception as exc:
        note(messages, f"No pude calcular frecuencias Hessiano ponderado: {exc}")


def plot_pes(paths: PhasePaths, outputs: list[str], messages: list[str]) -> None:
    if not (paths.pes_displacements.exists() and paths.pes_energies.exists()):
        note(messages, "Sin par desplazamiento/energía PES.")
        return

    try:
        x = np.load(paths.pes_displacements)
        y = np.load(paths.pes_energies)
    except Exception as exc:
        note(messages, f"PES omitido: {exc}")
        return

    x = np.ravel(x)
    y = np.ravel(y)
    if len(x) != len(y):
        note(messages, f"PES omitido: longitudes x/y difieren ({len(x)} vs {len(y)}).")
        return

    fig, ax = plt.subplots(figsize=(6, 4.5))
    order = np.argsort(x)
    y_mev = (y[order] - np.nanmin(y)) * 1000
    ax.plot(x[order], y_mev, "o-", color="#1f77b4", lw=1.4, ms=4)
    ax.set_xlabel("Desplazamiento modo (A)")
    ax.set_ylabel("ΔE (meV)")
    ax.set_title(dated_title("Barrido energía potencial desde NPY"))
    save_figure(fig, paths.out_dir, "pes_scan_from_npy", outputs)


def plot_soc_arrays(paths: PhasePaths, outputs: list[str], messages: list[str]) -> None:
    if paths.soc_eigs.exists():
        try:
            eigs = np.load(paths.soc_eigs)
            fig, ax = plt.subplots(figsize=(6.5, 4.5))
            im = ax.imshow(eigs.T, aspect="auto", origin="lower", cmap="viridis")
            ax.set_xlabel("índice punto k")
            ax.set_ylabel("índice banda")
            ax.set_title(dated_title("Autovalores SOC guardados"))
            fig.colorbar(im, ax=ax, label="Energía (eV)")
            save_figure(fig, paths.out_dir, "soc_eigenvalues_map", outputs)
        except Exception as exc:
            note(messages, f"No pude graficar autovalores SOC: {exc}")

    if paths.soc_spin.exists():
        try:
            spins = np.load(paths.soc_spin)
            squeezed = np.squeeze(spins)
            spin_components = None
            if squeezed.ndim == 2:
                fig, ax = plt.subplots(figsize=(6.5, 4.5))
                im = ax.imshow(squeezed.T, aspect="auto", origin="lower", cmap="coolwarm")
                ax.set_xlabel("índice punto k")
                ax.set_ylabel("índice banda/espín")
                ax.set_title(dated_title("Proyecciones espín SOC guardadas"))
                fig.colorbar(im, ax=ax)
            elif squeezed.ndim == 3 and squeezed.shape[0] == 3:
                spin_components = squeezed
            elif squeezed.ndim == 3 and squeezed.shape[-1] == 3:
                spin_components = np.moveaxis(squeezed, -1, 0)
            else:
                spin_components = None

            if spin_components is not None:
                fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
                vmax = np.nanpercentile(np.abs(spin_components), 98)
                labels = ("Sx", "Sy", "Sz")
                for comp, ax in enumerate(axes):
                    im = ax.imshow(
                        spin_components[comp].T,
                        aspect="auto",
                        origin="lower",
                        cmap="coolwarm",
                        vmin=-vmax,
                        vmax=vmax,
                    )
                    ax.set_title(labels[comp])
                    ax.set_xlabel("índice punto k")
                axes[0].set_ylabel("índice banda")
                fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.85)
                fig.suptitle(dated_title("Proyecciones espín SOC guardadas"))
            elif squeezed.ndim != 2:
                raise ValueError(f"shape no soportado {spins.shape}")
            save_figure(fig, paths.out_dir, "soc_spin_projection_map", outputs)
        except Exception as exc:
            note(messages, f"No pude graficar proyecciones espín SOC: {exc}")


def plot_tensor_arrays(paths: PhasePaths, outputs: list[str], messages: list[str]) -> None:
    tensor_files = [
        ("born_charges", paths.born_charges),
        ("dielectric_tensor", paths.dielectric_tensor),
        ("loto_born_charges", paths.loto_born_charges),
        ("loto_dielectric_tensor", paths.loto_dielectric_tensor),
    ]

    for stem, path in tensor_files:
        if not path.exists():
            continue
        try:
            array = np.load(path)
        except Exception as exc:
            note(messages, f"No pude leer {path}: {exc}")
            continue

        if array.ndim == 2:
            fig, ax = plt.subplots(figsize=(5.5, 4.8))
            im = ax.imshow(array, cmap="coolwarm")
            ax.set_title(dated_title(stem.replace("_", " ")))
            fig.colorbar(im, ax=ax)
            save_figure(fig, paths.out_dir, stem, outputs)
        elif array.ndim == 3:
            fig, axes = plt.subplots(1, 3, figsize=(10, 3.4))
            vmax = np.nanpercentile(np.abs(array), 98)
            for axis, ax in enumerate(axes):
                im = ax.imshow(array[:, axis, :], cmap="coolwarm", vmin=-vmax, vmax=vmax)
                ax.set_title(f"fila cartesiana {axis}")
                ax.set_xlabel("col cartesiana")
                ax.set_ylabel("átomo")
            fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.85)
            fig.suptitle(dated_title(stem.replace("_", " ")))
            save_figure(fig, paths.out_dir, stem, outputs)
        else:
            note(messages, f"Omitido {path}: shape no soportado {array.shape}.")


def write_manifest(paths: PhasePaths, outputs: list[str], messages: list[str]) -> None:
    manifest = {
        "calculation_dir": str(paths.calc_dir.relative_to(ROOT)),
        "output_dir": str(paths.out_dir.relative_to(ROOT)),
        "generated_files": outputs,
        "messages": messages,
    }
    manifest_path = paths.out_dir / "visualization_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    outputs.append(str(manifest_path.relative_to(ROOT)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera visualizaciones CsPbI3 desde .npy y checkpoints GPAW."
    )
    parser.add_argument("--phase", default="alpha", help="Carpeta fase bajo calculations/.")
    parser.add_argument(
        "--calc-dir",
        type=Path,
        default=None,
        help="Directorio cálculo. Sobrescribe --phase si existe.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directorio salida. Default: ./imagenes.",
    )
    parser.add_argument(
        "--skip-gpaw",
        action="store_true",
        help="Omite gráficas con import GPAW o lectura .gpw/.gpaw.",
    )
    parser.add_argument(
        "--structure",
        action="append",
        default=[],
        help=(
            "Estructura extra. Acepta PATH, LABEL=PATH o fase conocida. "
            "Usa builder:FASE para regenerar con StructureBuilder. Repetible."
        ),
    )
    parser.add_argument(
        "--structure-phase",
        action="append",
        default=[],
        help="Fase StructureBuilder a visualizar, ej. gamma o beta. Repetible.",
    )
    parser.add_argument(
        "--structures-only",
        action="store_true",
        help="Solo gráficas estructura/celda/octaedros.",
    )
    parser.add_argument(
        "--supercell-repeats",
        type=parse_int_list,
        default=(3, 6),
        help="Repeticiones separadas por coma para superceldas 3D. Usa '' para desactivar.",
    )
    parser.add_argument(
        "--octahedra-repeats",
        type=parse_int_list,
        default=(2, 3),
        help="Repeticiones separadas por coma para octaedros BX6. Usa '' para desactivar.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    calc_dir = args.calc_dir or ROOT / "calculations" / args.phase
    out_dir = args.out_dir or ROOT / "imagenes"
    paths = build_paths(calc_dir.resolve(), out_dir.resolve())
    outputs: list[str] = []
    messages: list[str] = []
    structure_inputs = load_structure_inputs(args.structure, args.structure_phase, messages)

    paths.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Datos cálculo: {paths.calc_dir}")
    print(f"Escribiendo gráficas en: {paths.out_dir}")

    plot_cell_views(
        paths,
        outputs,
        messages,
        skip_gpaw=args.skip_gpaw,
        structure_inputs=structure_inputs,
        supercell_repeats=args.supercell_repeats,
        octahedra_repeats=args.octahedra_repeats,
    )
    if args.structures_only:
        note(messages, "Gráficas no estructurales omitidas.")
    else:
        if args.skip_gpaw:
            note(messages, "DOS/bandas dependientes de GPAW omitidas.")
        else:
            plot_dos_from_gpw(paths, outputs, messages)
            plot_band_structure_from_gpw(paths, outputs, messages)
        plot_phonons(paths, outputs, messages)
        plot_hessian(paths, outputs, messages, skip_gpaw=args.skip_gpaw)
        plot_pes(paths, outputs, messages)
        plot_soc_arrays(paths, outputs, messages)
        plot_tensor_arrays(paths, outputs, messages)
    write_manifest(paths, outputs, messages)

    print("\nArchivos generados:")
    for path in outputs:
        print(f"  {path}")
    if messages:
        print("\nNotas:")
        for message in messages:
            print(f"  - {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
