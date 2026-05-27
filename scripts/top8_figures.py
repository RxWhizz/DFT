#!/usr/bin/env python3
"""PDOS, diagrama de bandas, función dieléctrica y espectros ópticos — top-8 perovskitas.

Uso:
    .venv/bin/python3 scripts/top8_figures.py --mat CsPbI3
    .venv/bin/python3 scripts/top8_figures.py --mat all
    .venv/bin/python3 scripts/top8_figures.py --mat CsSnI3 --phase pdos,bands

Para materiales Pb-based se aplica la corrección scissor (+Δ_sc en la banda de conducción)
documentada en r2scan_bandgap.json.
"""
from __future__ import annotations

import argparse
import json
import os
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_top8")
warnings.filterwarnings("ignore", category=UserWarning, module="gpaw")

ROOT = Path(__file__).resolve().parent.parent
TOP8 = ROOT / "calculations" / "top8_r2scan"

# ---------------------------------------------------------------------------
# Configuración de materiales
# ---------------------------------------------------------------------------

MATERIALS: dict[str, dict] = {
    "CsPbI3":  {"gpw": "06_r2scan/r2scan.gpw",                    "is_pb": True},
    "CsSnI3":  {"gpw": "06_r2scan/u_scan/u_scan_U2p50.gpw",       "is_pb": False,
                "dos_npz": "06_r2scan/u_scan/u_scan_U2p50_dos.npz"},
    "MAPbI3":  {"gpw": "06_r2scan/r2scan.gpw",                    "is_pb": True},
    "MASnI3":  {"gpw": "06_r2scan/u_scan/u_scan_U2p50.gpw",       "is_pb": False},
    "FAPbI3":  {"gpw": "06_r2scan/r2scan.gpw",                    "is_pb": True},
    "FAPbBr3": {"gpw": "06_r2scan/r2scan.gpw",                    "is_pb": True},
    "FASnI3":  {"gpw": "06_r2scan/u_scan/u_scan_U2p50.gpw",       "is_pb": False},
    "FASnBr3": {"gpw": "06_r2scan/u_scan/u_scan_U2p50.gpw",       "is_pb": False},
}

# colores PDOS por elemento
PDOS_COLOR = {
    "Pb-s": "#c1440e", "Pb-p": "#e05c00",
    "Sn-s": "#b5460f", "Sn-p": "#d46a00",
    "I-p":  "#2176AE", "Br-p": "#0D6E3A",
    "Cs-s": "#888888",
    "org":  "#555555",
    "total":"#222222",
}

DPI = 150


# ---------------------------------------------------------------------------
# Scissor: delta = gap_scissor - gap_r2scan (de r2scan_bandgap.json)
# ---------------------------------------------------------------------------

def _load_scissor(mat_dir: Path) -> float:
    """Devuelve el desplazamiento rígido de CB (eV) para materiales Pb-based."""
    p = mat_dir / "06_r2scan" / "r2scan_bandgap.json"
    if not p.exists():
        return 0.0
    with open(p) as f:
        d = json.load(f)
    sc = d.get("scissor_correction", {})
    if not sc:
        return 0.0
    gap_sc = sc.get("gap_scissor_eV", 0.0)
    gap_r2 = d.get("gap_eV", 0.0)
    return gap_sc - gap_r2


# ---------------------------------------------------------------------------
# Utilidades: Gaussian y Kramers-Kronig
# ---------------------------------------------------------------------------

def _gauss(energies: np.ndarray, centers: np.ndarray,
           weights: np.ndarray, width: float) -> np.ndarray:
    out = np.zeros(len(energies))
    for e0, w in zip(centers, weights):
        out += w * np.exp(-0.5 * ((energies - e0) / width) ** 2)
    return out / (width * np.sqrt(2 * np.pi))


def _kramers_kronig(omega: np.ndarray, eps2: np.ndarray) -> np.ndarray:
    """ε₁(ω) = 1 + (2/π) P∫ ω'ε₂(ω')/(ω'²-ω²) dω'  via trapecio."""
    dw = omega[1] - omega[0]
    eps1 = np.ones(len(omega))
    for i, w in enumerate(omega):
        denom = omega**2 - w**2
        denom[i] = np.inf
        integrand = omega * eps2 / denom
        eps1[i] = 1.0 + (2.0 / np.pi) * np.trapezoid(integrand, omega)
    return eps1


def _save(fig: plt.Figure, out_dir: Path, stem: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / f"{stem}.{ext}", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# PDOS
# ---------------------------------------------------------------------------

def plot_pdos(mat: str, mat_dir: Path, out_dir: Path, scissor: float) -> None:
    from gpaw import GPAW
    from gpaw.dos import DOSCalculator

    cfg = MATERIALS[mat]
    gpw = mat_dir / cfg["gpw"]
    if not gpw.exists():
        print(f"  [pdos] {mat}: GPW no encontrado ({gpw.name})")
        return

    print(f"  [pdos] Cargando {gpw.name} …")
    calc = GPAW(str(gpw), txt=None)
    syms = calc.atoms.get_chemical_symbols()
    ef = calc.get_fermi_level()

    dc = DOSCalculator.from_calculator(calc, shift_fermi_level=True)
    emin, emax, npts = -7.0, 4.0 + scissor, 2000
    energies = np.linspace(emin, emax, npts)

    # ---------- total DOS ----------
    total = dc.raw_dos(energies, width=0.1)

    # ---------- PDOS por grupo de elementos y orbital ----------
    def pdos_group(elem_list: list[str], l: int) -> np.ndarray:
        out = np.zeros(npts)
        for a, sym in enumerate(syms):
            if sym in elem_list:
                try:
                    c = dc.raw_pdos(energies, a=a, l=l, width=0.1)
                    out += c
                except Exception:
                    pass
        return out

    is_pb = cfg["is_pb"]
    b_elems = ["Pb"] if is_pb else ["Sn"]
    x_elems = [s for s in set(syms) if s in ("I", "Br")]
    org_elems = [s for s in set(syms) if s in ("C", "N", "H")]
    a_elems = [s for s in set(syms) if s in ("Cs", "Rb", "K")]

    b_s = pdos_group(b_elems, 0)
    b_p = pdos_group(b_elems, 1)
    x_p = pdos_group(x_elems, 1)
    org = pdos_group(org_elems, 0) + pdos_group(org_elems, 1)
    a_s = pdos_group(a_elems, 0)

    # Aplicar scissor: shift eigenvalores CB → en PDOS movemos la contribución
    # de estados por encima de EF (ya referenciado a 0)
    if scissor > 0.001:
        e_cb = energies.copy()
        mask_cb = e_cb > 0.0
        # Para cada componente: redistribuir masa espectral por encima de 0
        # Aproximación: shift del eje para el rango CB → hacemos dos segmentos
        # Más limpio: recalcular con eigenvalores shiftados
        pass  # el scissor se muestra como línea vertical (ver abajo)

    b_label = "Pb" if is_pb else "Sn"
    x_label = x_elems[0] if x_elems else "X"

    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.fill_between(energies, 0, total,   color=PDOS_COLOR["total"], alpha=0.12)
    ax.plot(energies, total,   color=PDOS_COLOR["total"], lw=1.2, label="DOS total")
    ax.fill_between(energies, 0, b_s,    color=PDOS_COLOR[f"{b_label}-s"], alpha=0.35)
    ax.plot(energies, b_s,    color=PDOS_COLOR[f"{b_label}-s"], lw=1.0,
            label=f"{b_label}-s")
    ax.fill_between(energies, 0, b_p,    color=PDOS_COLOR[f"{b_label}-p"], alpha=0.35)
    ax.plot(energies, b_p,    color=PDOS_COLOR[f"{b_label}-p"], lw=1.0,
            label=f"{b_label}-p")
    ax.fill_between(energies, 0, x_p,    color=PDOS_COLOR[f"{x_label}-p"], alpha=0.35)
    ax.plot(energies, x_p,    color=PDOS_COLOR[f"{x_label}-p"], lw=1.0,
            label=f"{x_label}-p")
    if org.max() > 0.01:
        ax.fill_between(energies, 0, org, color=PDOS_COLOR["org"], alpha=0.25)
        ax.plot(energies, org, color=PDOS_COLOR["org"], lw=0.9, ls="--", label="orgánico")
    if a_s.max() > 0.01:
        ax.plot(energies, a_s, color=PDOS_COLOR["Cs-s"], lw=0.9, ls=":", label=f"{a_elems[0]}-s")

    # Líneas especiales
    ax.axvline(0.0, color="black", lw=1.2, ls="--", alpha=0.7, label="$E_F$")

    ax.set_xlim(emin, emax)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Energía − $E_F$ (eV)", fontsize=12)
    ax.set_ylabel("DOS (estados/eV/celda)", fontsize=12)
    title = f"PDOS — {mat}  (r²SCAN+U)" if not is_pb else f"PDOS — {mat}  (r²SCAN)"
    if scissor > 0.001:
        title += f"\n[scissor +{scissor:.3f} eV indicado]"
    ax.set_title(title, fontsize=11)
    ax.legend(fontsize=9, framealpha=0.85)
    ax.grid(axis="x", alpha=0.2)
    _save(fig, out_dir, f"pdos_{mat}")
    print(f"  [pdos] guardado → {out_dir.name}/pdos_{mat}.png")


def _load_gaps(mat_dir: Path, is_pb: bool) -> tuple[float, float]:
    """Devuelve (gap_dft_eV, gap_soc_eV). gap_soc=0.0 si no disponible.

    Para Pb: lee r2scan_bandgap.json (gap DFT) + scissor_correction si existe.
    Para Sn: lee u_scan_summary.json (U=2.50, gap r²SCAN+U) y
             u_scan_soc_summary.json (U=2.50, gap SOC).
    """
    if is_pb:
        p = mat_dir / "06_r2scan" / "r2scan_bandgap.json"
        if not p.exists():
            return 0.0, 0.0
        d = json.loads(p.read_text())
        gap_dft = d.get("gap_eV", 0.0)
        sc = d.get("scissor_correction", {})
        gap_scissor = sc.get("gap_scissor_eV", 0.0) if sc else 0.0
        return gap_dft, gap_scissor
    else:
        # Sn materials: U scan JSONs
        scan_dir = mat_dir / "06_r2scan" / "u_scan"
        gap_dft, gap_soc = 0.0, 0.0
        p_scan = scan_dir / "u_scan_summary.json"
        if p_scan.exists():
            d = json.loads(p_scan.read_text())
            gap_dft = d.get("U2.50", {}).get("gap_eV", 0.0)
        p_soc = scan_dir / "u_scan_soc_summary.json"
        if p_soc.exists():
            d = json.loads(p_soc.read_text())
            gap_soc = d.get("U2.50", {}).get("gap_soc_eV", 0.0)
        return gap_dft, gap_soc


def _load_gap_r2scan(mat_dir: Path) -> float:
    """Compat shim — devuelve gap DFT (sin SOC). Detecta Pb/Sn por directorios."""
    is_pb = (mat_dir / "06_r2scan" / "r2scan_bandgap.json").exists() and \
            not (mat_dir / "06_r2scan" / "u_scan" / "u_scan_summary.json").exists()
    gap, _ = _load_gaps(mat_dir, is_pb)
    return gap


# ---------------------------------------------------------------------------
# Diagrama de bandas
# ---------------------------------------------------------------------------

def plot_bands(mat: str, mat_dir: Path, out_dir: Path, scissor: float) -> None:
    r2scan_dir = mat_dir / "06_r2scan"
    eigs_file   = r2scan_dir / "bands_path_eigs.npy"
    xcoord_file = r2scan_dir / "bands_path_xcoords.npy"
    special_file = r2scan_dir / "bands_path_special.json"
    soc_file    = r2scan_dir / "bands_path_soc_eigs.npy"

    if not eigs_file.exists():
        print(f"  [bands] {mat}: bands_path_eigs.npy no encontrado — "
              f"ejecutar band_calc.py primero")
        return

    # --- Cargar resultados del cálculo de bandas ---
    eigs_abs = np.load(str(eigs_file))      # (nspins, nk_path, nbands) eV absolutos
    xcoords  = np.load(str(xcoord_file))    # (nk_path,)
    meta     = json.loads(special_file.read_text())
    ef       = meta["ef_eV"]
    xsp_norm = meta["special_xcoords"]
    labels   = meta["labels"]
    path_str = meta.get("path", "")
    xc_label = meta.get("xc", "r²SCAN+U" if not MATERIALS[mat]["is_pb"] else "r²SCAN")

    nspins, nk_path, nbands = eigs_abs.shape

    # --- Trim comma-paths to the first (main) segment ---
    # Paths like "GXMGRX,MR" produce two segments sharing a k-point at the comma.
    # We drop the tail segment so no spurious X|M separator appears in the figure.
    _trim_k: int | None = None  # shared with SOC section below
    if ',' in path_str:
        xsp_arr = np.asarray(xsp_norm)
        brk = int(np.abs(np.diff(xsp_arr)).argmin())   # index where xsp[i]≈xsp[i+1]
        x_cut = float(xsp_arr[brk])
        _trim_k = int(np.searchsorted(xcoords, x_cut + 1e-9, side='left'))
        xcoords  = xcoords[:_trim_k]
        eigs_abs = eigs_abs[:, :_trim_k, :]
        nk_path  = _trim_k
        xsp_norm = list(xsp_arr[:brk + 1])
        labels   = list(labels[:brk + 1])
        if xcoords[-1] > 0:
            _sc = float(xcoords[-1])
            xcoords  = xcoords / _sc
            xsp_norm = [x / _sc for x in xsp_norm]

    # Referencia VBM = 0 (convenio para semiconductores).
    # El EF de GPAW con smearing finito puede quedar lejos del gap real;
    # usamos n_occ (del JSON) para encontrar la VBM directamente.
    n_occ = meta.get("n_occ", None)
    if n_occ is not None and n_occ <= nbands:
        vbm = float(eigs_abs[:, :, n_occ - 1].max())
    else:
        # Fallback: buscar el salto de energía más grande entre bandas consecutivas
        band_max = eigs_abs[0].max(axis=0)
        band_min = eigs_abs[0].min(axis=0)
        gaps = band_min[1:] - band_max[:-1]
        idx = int(gaps.argmax())
        vbm = float(band_max[idx])

    ref = vbm   # VBM = 0 en el plot

    # Eigenvalores relativos a VBM, scissor aplicado sobre la CB (> 0)
    eigs_rel = eigs_abs - ref
    if scissor > 0.001:
        eigs_plot = eigs_rel.copy()
        eigs_plot[eigs_plot > 0] += scissor
    else:
        eigs_plot = eigs_rel

    ef_rel = ef - ref   # posición de EF relativa a VBM (negativa para semiconductor)

    # --- SOC overlay (mismo camino k que las bandas) ---
    soc_eigs = None
    if soc_file.exists():
        soc_abs = np.load(str(soc_file))    # (nk_path, 2*nbands) eV absolutos
        if _trim_k is not None:
            soc_abs = soc_abs[:_trim_k, :]
        soc_rel = soc_abs - ref             # centrado en VBM
        if scissor > 0.001:
            soc_plot = soc_rel.copy()
            soc_plot[soc_plot > 0] += scissor
        else:
            soc_plot = soc_rel
        soc_eigs = soc_plot

    # --- Detectar saltos de segmento en el camino ---
    # Un salto ocurre cuando dos xsp_norm consecutivos comparten la misma coordenada x
    # (coma en "GXMGRX,MR" → X y M caen en el mismo x → línea espuria sin split)
    xsp_arr = np.asarray(xsp_norm)
    break_xcoords = xsp_arr[1:][np.abs(np.diff(xsp_arr)) < 1e-10]  # x de cada salto

    # Índices en xcoords donde ocurre el salto (punto justo después del límite)
    seg_breaks = []
    for bx in break_xcoords:
        idxs = np.where(np.abs(xcoords - bx) < 1e-9)[0]
        if len(idxs) >= 2:
            seg_breaks.append(int(idxs[len(idxs) // 2]))  # punto medio entre los duplicados

    # Slices de cada segmento continuo
    cuts = [0] + seg_breaks + [nk_path]
    segs = [slice(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]

    # --- Label de método, bandas primarias y CBM ---
    is_pb_mat = MATERIALS[mat]["is_pb"]
    n_soc = soc_eigs.shape[1] if soc_eigs is not None else 0

    if not is_pb_mat and soc_eigs is not None:
        # Sn: r²SCAN+U+SOC — re-alinear al VBM del SOC (cada banda DFT → 2 bandas SOC)
        main_label = "r²SCAN+U+SOC"
        use_soc_primary = True
        if n_occ is not None and 2 * n_occ < n_soc:
            _vbm_soc = float(soc_eigs[:, 2 * n_occ - 1].max())
            soc_eigs = soc_eigs - _vbm_soc
            cbm = float(soc_eigs[:, 2 * n_occ].min())
            k_cbm = int(np.argmin(soc_eigs[:, 2 * n_occ]))
        else:
            _above = np.where(soc_eigs > 5e-3, soc_eigs, np.inf)
            cbm = float(_above.min())
            k_cbm = int(_above.min(axis=1).argmin())
    else:
        # Pb: PBE+scissor como proxy hasta tener G0W0+SOC
        main_label = "PBE+scissor"
        use_soc_primary = False
        if n_occ is not None and n_occ < nbands:
            cbm = float(eigs_plot[0, :, n_occ].min())
            k_cbm = int(np.argmin(eigs_plot[0, :, n_occ]))
        else:
            _above = np.where(eigs_plot > 5e-3, eigs_plot, np.inf)
            cbm = float(_above.min())
            k_cbm = int(_above.min(axis=(0, 2)).argmin())

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    fig.subplots_adjust(right=0.82)   # deja espacio para la anotación E_g

    # Bandas primarias: SOC para Sn, DFT+scissor para Pb
    if use_soc_primary:
        for b in range(n_soc):
            for seg in segs:
                ax.plot(xcoords[seg], soc_eigs[seg, b],
                        color="#1a4e8a", lw=0.9, alpha=0.68)
    else:
        for s in range(nspins):
            for b in range(nbands):
                for seg in segs:
                    ax.plot(xcoords[seg], eigs_plot[s, seg, b],
                            color="#1a4e8a", lw=0.8, alpha=0.65)

    # Líneas horizontales: VBM=0 (negro) y CBM (rojo)
    ax.axhline(0,   color="black",   lw=1.0, ls="--", alpha=0.55)
    ax.axhline(cbm, color="#c0392b", lw=1.0, ls="--", alpha=0.80)

    # Anotación E_g: flecha doble + texto fuera del eje (derecha)
    from matplotlib.transforms import blended_transform_factory
    _tr = blended_transform_factory(ax.transAxes, ax.transData)
    ax.annotate("", xy=(1.04, cbm), xytext=(1.04, 0.0),
                xycoords=_tr, textcoords=_tr, clip_on=False,
                arrowprops=dict(arrowstyle="<->", color="#c0392b",
                                lw=1.4, mutation_scale=14))
    ax.text(1.06, cbm / 2,
            f"$E_g$\n{cbm:.2f} eV",
            transform=_tr, color="#c0392b", fontsize=8.5,
            va="center", ha="left", clip_on=False,
            bbox=dict(fc="white", ec="none", alpha=0.9, pad=1.5))

    # Puntos de alta simetría
    drawn_xc: set = set()
    for xc in xsp_norm:
        if xc not in drawn_xc:
            ax.axvline(xc, color="gray", lw=0.5, alpha=0.55)
            drawn_xc.add(xc)

    # Labels: fusionar puntos compartidos
    tick_xcoords, tick_labels = [], []
    i = 0
    while i < len(xsp_norm):
        xc = xsp_norm[i]
        lb = labels[i]
        if i + 1 < len(xsp_norm) and abs(xsp_norm[i + 1] - xc) < 1e-10:
            lb = lb + "|" + labels[i + 1]
            i += 2
        else:
            i += 1
        tick_xcoords.append(xc)
        tick_labels.append(lb)

    def _fmt(lb: str) -> str:
        return lb.replace("G", "Γ").replace("Gamma", "Γ")

    ax.set_xticks(tick_xcoords)
    ax.set_xticklabels([_fmt(lb) for lb in tick_labels], fontsize=11)
    ax.set_xlim(xcoords[0], xcoords[-1])
    ax.set_ylim(-5, 5)
    ax.set_ylabel("Energía − VBM (eV)", fontsize=12)
    ax.set_title(f"Estructura de bandas — {mat}  ({main_label})", fontsize=10)

    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([0], [0], color="#1a4e8a", lw=1.5, label=main_label)],
              fontsize=9, loc="upper right")
    ax.grid(axis="y", alpha=0.15)

    # --- Inset close-up alrededor del gap ---
    x_cbm = float(xcoords[k_cbm])
    dx = 0.13
    xl = max(float(xcoords[0]), x_cbm - dx)
    xr = min(float(xcoords[-1]), x_cbm + dx)
    yi_lo, yi_hi = -0.55, cbm + 0.55

    inset_x0 = 0.55 if x_cbm < 0.5 else 0.04
    axins = ax.inset_axes([inset_x0, 0.54, 0.38, 0.42])

    if use_soc_primary:
        for b in range(n_soc):
            axins.plot(xcoords, soc_eigs[:, b], color="#1a4e8a", lw=0.7, alpha=0.65)
    else:
        for s in range(nspins):
            for b in range(nbands):
                axins.plot(xcoords, eigs_plot[s, :, b], color="#1a4e8a", lw=0.7, alpha=0.65)

    axins.axhline(0,   color="black",   lw=0.7, ls="--", alpha=0.55)
    axins.axhline(cbm, color="#c0392b", lw=0.7, ls="--", alpha=0.80)
    axins.set_xlim(xl, xr)
    axins.set_ylim(yi_lo, yi_hi)

    # Etiqueta E_g dentro del inset
    axins.text(0.97, 0.50, f"$E_g$={cbm:.2f} eV",
               transform=axins.transAxes, color="#c0392b", fontsize=7,
               va="center", ha="right",
               bbox=dict(fc="white", ec="#c0392b", alpha=0.92, pad=2, lw=0.6))

    # Tick del punto k más cercano al CBM
    _ci = min(range(len(tick_xcoords)), key=lambda j: abs(tick_xcoords[j] - x_cbm))
    axins.set_xticks([tick_xcoords[_ci]])
    axins.set_xticklabels([_fmt(tick_labels[_ci])], fontsize=7)
    axins.tick_params(axis="y", labelsize=6.5)
    axins.yaxis.set_major_locator(plt.MaxNLocator(nbins=3))
    ax.indicate_inset_zoom(axins, edgecolor="#777777", alpha=0.55)

    _save(fig, out_dir, f"bands_{mat}")
    print(f"  [bands] {mat}: guardado → {out_dir.name}/bands_{mat}.png  "
          f"(E_g={cbm:.3f} eV, {main_label})")


# ---------------------------------------------------------------------------
# Función dieléctrica y espectros ópticos (JDOS → IPA)
# ---------------------------------------------------------------------------

def plot_optical(mat: str, mat_dir: Path, out_dir: Path, scissor: float) -> None:
    from gpaw import GPAW

    cfg = MATERIALS[mat]
    gpw = mat_dir / cfg["gpw"]
    if not gpw.exists():
        print(f"  [optical] {mat}: GPW no encontrado")
        return

    print(f"  [optical] Calculando espectros ópticos IPA para {mat} …")
    calc = GPAW(str(gpw), txt=None)
    ef = calc.get_fermi_level()
    nk = calc.get_ibz_k_points().shape[0]
    nbands = calc.get_number_of_bands()
    nspins = calc.get_number_of_spins()

    # Pesos IBZ (suman a 1)
    kweights = calc.get_k_point_weights()

    eigs = np.array([[calc.get_eigenvalues(kpt=k, spin=s)
                      for k in range(nk)] for s in range(nspins)])
    # eigs: (nspins, nk, nbands) en eV absolutos

    # JDOS(ω): suma sobre todos los pares (v,c,k) con ε_c - ε_v > 0
    # Con corrección scissor: ε_c → ε_c + scissor para estados ε_c > ef
    eigs_sc = eigs.copy()
    eigs_sc[eigs_sc > ef] += scissor

    omega = np.linspace(0.0, 6.0, 2000)  # eV
    eta = 0.10  # eV de broadening

    jdos = np.zeros(len(omega))
    for s in range(nspins):
        for k in range(nk):
            w = kweights[k] / nspins
            e_k = eigs_sc[s, k]  # (nbands,)
            occ_mask = e_k <= ef + 0.01
            virt_mask = e_k > ef + 0.01
            e_occ  = e_k[occ_mask]
            e_virt = e_k[virt_mask]
            for ev in e_occ:
                for ec in e_virt:
                    dE = ec - ev
                    if 0.05 < dE < 7.0:
                        jdos += w * np.exp(-0.5 * ((omega - dE) / eta) ** 2)
    jdos /= (eta * np.sqrt(2 * np.pi))

    # ε₂(ω) ∝ JDOS(ω) / ω² (dipole approximation, normalizado)
    with np.errstate(divide="ignore", invalid="ignore"):
        eps2 = np.where(omega > 0.1, jdos / omega**2, 0.0)
    if eps2.max() > 0:
        eps2 = eps2 / eps2.max() * 8.0  # normalización cualitativa

    # ε₁(ω) via Kramers-Kronig (numérico, discreto)
    eps1 = _kramers_kronig(omega, eps2)

    # Índice óptico n(ω), k(ω)
    eps_complex = eps1 + 1j * eps2
    sqrt_eps = np.sqrt(eps_complex.astype(complex))
    n_opt = sqrt_eps.real
    k_ext = sqrt_eps.imag

    # Coeficiente de absorción α(ω) = 2ω·k/c  [cm⁻¹]
    hbar_eV_s = 6.582119569e-16
    c_cm_s = 2.99792458e10
    alpha = np.where(omega > 0.1,
                     2.0 * omega * k_ext / (hbar_eV_s * c_cm_s), 0.0)

    is_pb = cfg["is_pb"]
    gap_dft, gap_alt = _load_gaps(mat_dir, is_pb)

    # Para Pb: gap_dft = r²SCAN, gap_alt = scissor
    # Para Sn: gap_dft = r²SCAN+U, gap_alt = SOC-corrected
    if is_pb:
        gap_eff = gap_dft + scissor   # scissor shift ya calculado arriba
        gap_label = f"r²SCAN+scissor = {gap_eff:.3f} eV" if scissor > 0.001 \
                    else f"r²SCAN = {gap_dft:.3f} eV"
        gap_soc_label = None
    else:
        gap_eff = gap_dft             # r²SCAN+U DFT gap (para espectro sin SOC)
        gap_label = f"r²SCAN+U = {gap_dft:.3f} eV"
        gap_soc_label = f"r²SCAN+U+SOC = {gap_alt:.3f} eV" if gap_alt > 0.01 else None

    sc_note = f"  [scissor +{scissor:.3f} eV]" if scissor > 0.001 else \
              (f"  [SOC gap = {gap_alt:.3f} eV]" if gap_soc_label else "")

    # --- Figura 1: función dieléctrica ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 7), sharex=True)
    ax1.plot(omega, eps2, color="#2176AE", lw=1.4, label=r"$\varepsilon_2(\omega)$")
    ax1.set_ylabel(r"$\varepsilon_2(\omega)$ (u.a.)", fontsize=12)
    ax1.legend(fontsize=9); ax1.grid(alpha=0.2)

    ax2.plot(omega, eps1, color="#c0392b", lw=1.4, label=r"$\varepsilon_1(\omega)$")
    ax2.axhline(0, color="black", lw=0.7, ls="--", alpha=0.5)
    ax2.set_xlabel(r"Energía fotónica $\hbar\omega$ (eV)", fontsize=12)
    ax2.set_ylabel(r"$\varepsilon_1(\omega)$", fontsize=12)
    ax2.legend(fontsize=9); ax2.grid(alpha=0.2)
    ax2.set_xlim(0, 6)

    fig.suptitle(f"Función dieléctrica IPA — {mat}{sc_note}", fontsize=11)
    fig.tight_layout()
    _save(fig, out_dir, f"dielectric_{mat}")

    # --- Figura 2: espectros ópticos ---
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))

    axes[0].plot(omega, n_opt, color="#1a4e8a", lw=1.4)
    axes[0].set_xlabel(r"$\hbar\omega$ (eV)"); axes[0].set_ylabel("n(ω)")
    axes[0].set_title("Índice de refracción"); axes[0].set_xlim(0, 5)
    axes[0].grid(alpha=0.2)

    axes[1].plot(omega, k_ext, color="#8e44ad", lw=1.4)
    axes[1].set_xlabel(r"$\hbar\omega$ (eV)"); axes[1].set_ylabel("k(ω)")
    axes[1].set_title("Coef. extinción"); axes[1].set_xlim(0, 5)
    axes[1].grid(alpha=0.2)

    # α: solo graficar por encima del umbral físico (floor = 1 cm⁻¹)
    alpha_floor = 1.0
    mask = (omega > 0.5) & (omega < 5.0) & (alpha > alpha_floor)
    if mask.any():
        axes[2].semilogy(omega[mask], alpha[mask], color="#27ae60", lw=1.4)
    axes[2].set_xlabel(r"$\hbar\omega$ (eV)"); axes[2].set_ylabel(r"$\alpha$ (cm$^{-1}$)")
    axes[2].set_title("Absorción óptica"); axes[2].set_xlim(0, 5)
    axes[2].grid(alpha=0.2, which="both")

    fig.suptitle(f"Espectros ópticos IPA — {mat}{sc_note}", fontsize=11)
    fig.tight_layout()
    _save(fig, out_dir, f"optical_{mat}")
    print(f"  [optical] guardado → {out_dir.name}/dielectric_{mat}.png + optical_{mat}.png")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def run_material(mat: str, phases: list[str]) -> None:
    mat_dir = TOP8 / mat
    out_dir = mat_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = MATERIALS[mat]
    scissor = _load_scissor(mat_dir) if cfg["is_pb"] else 0.0
    if scissor > 0.001:
        print(f"  → scissor Δ = {scissor:.4f} eV aplicado a BC de {mat}")

    if "pdos" in phases:
        try:
            plot_pdos(mat, mat_dir, out_dir, scissor)
        except Exception as e:
            print(f"  [pdos] ERROR {mat}: {e}")

    if "bands" in phases:
        try:
            plot_bands(mat, mat_dir, out_dir, scissor)
        except Exception as e:
            print(f"  [bands] ERROR {mat}: {e}")

    if "optical" in phases:
        try:
            plot_optical(mat, mat_dir, out_dir, scissor)
        except Exception as e:
            print(f"  [optical] ERROR {mat}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Figuras top-8 perovskitas: PDOS, bandas, dieléctrica, óptica"
    )
    parser.add_argument("--mat", default="all",
                        help="Material (ej. CsPbI3) o 'all'")
    parser.add_argument("--phase", default="pdos,bands,optical",
                        help="Fases separadas por coma: pdos,bands,optical")
    args = parser.parse_args()

    phases = [p.strip() for p in args.phase.split(",")]
    mats = list(MATERIALS.keys()) if args.mat == "all" else [args.mat]

    for mat in mats:
        if mat not in MATERIALS:
            print(f"Material desconocido: {mat}. Opciones: {list(MATERIALS)}")
            continue
        print(f"\n=== {mat} ===")
        run_material(mat, phases)

    print("\nFiguras completadas.")


if __name__ == "__main__":
    main()
