#!/usr/bin/env python3
"""top8_drift_diffusion.py

Drift-diffusion con OghmaNano para los top-8 perovskitas solares.

Fuentes de función dieléctrica por material:
  dft  — Eg de DFT (ai_predictions.json), m* de DFT-SOC (electronic_analysis.json),
          ε_∞ de Penn(Eg,m*); función óptica vía DOS parabólica 3D + Kramers-Kronig
  ai   — Eg, m*, ε_∞ del surrogate ML (RF+GBR); misma física óptica parabólica

Salidas:
  calculations/top8_oghma/{mat}/{dft,ai}/sim/    ← proyecto OghmaNano listo
  calculations/top8_oghma/{mat}/{dft,ai}/result.json
  calculations/top8_oghma/figures/jv_top8_{dft,ai}.pdf
  calculations/top8_oghma/figures/cell_{mat}.png

Uso:
    .venv\\Scripts\\python scripts\\top8_drift_diffusion.py
    .venv\\Scripts\\python scripts\\top8_drift_diffusion.py --mat CsPbI3
    .venv\\Scripts\\python scripts\\top8_drift_diffusion.py --no-run   # solo setup
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

warnings.filterwarnings("ignore")

# ── Rutas ─────────────────────────────────────────────────────────────────────
ROOT   = Path(__file__).resolve().parent.parent
TOP8_R = ROOT / "calculations" / "top8_r2scan"
TOP8_P = ROOT / "calculations" / "top8_pbe"
OUT    = ROOT / "calculations" / "top8_oghma"
FIGS   = OUT / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "src"))

DPI = 150

# ── Materiales top-8 ──────────────────────────────────────────────────────────
TOP8_MATS: dict[str, dict] = {
    "CsSnI3":  {"A": "Cs", "B": "Sn", "X": "I",  "color": "#6e8ea0", "Xi": 3.6},
    "MASnI3":  {"A": "MA", "B": "Sn", "X": "I",  "color": "#5a7a8c", "Xi": 3.7},
    "FASnI3":  {"A": "FA", "B": "Sn", "X": "I",  "color": "#4d6e80", "Xi": 3.7},
    "FASnBr3": {"A": "FA", "B": "Sn", "X": "Br", "color": "#7e9fa8", "Xi": 3.5},
    "CsPbI3":  {"A": "Cs", "B": "Pb", "X": "I",  "color": "#2c3e50", "Xi": 3.9},
    "MAPbI3":  {"A": "MA", "B": "Pb", "X": "I",  "color": "#1a252f", "Xi": 3.9},
    "FAPbI3":  {"A": "FA", "B": "Pb", "X": "I",  "color": "#34495e", "Xi": 3.8},
    "FAPbBr3": {"A": "FA", "B": "Pb", "X": "Br", "color": "#7f8c8d", "Xi": 3.7},
}

# eps_∞ literatura (fallback si no hay surrogate ni DFT)
_EPS_LIT: dict[str, float] = {
    "CsSnI3": 7.9, "MASnI3": 8.2, "FASnI3": 8.0, "FASnBr3": 7.0,
    "CsPbI3": 6.3, "MAPbI3": 6.5, "FAPbI3": 6.2, "FAPbBr3": 5.6,
}

# m* literatura SOC-corregidos (GW/HSE level) para cuando DFT PBE es UNPHYSICAL
# Referencias: Huang&Lambrecht PRB2013, Filip&Giustino 2016, Even+2013
_MEFF_LIT: dict[str, tuple[float, float]] = {
    "CsSnI3":  (0.12, 0.13),  # muy buenos portadores en CsSnI3
    "MASnI3":  (0.14, 0.17),
    "FASnI3":  (0.15, 0.17),
    "FASnBr3": (0.17, 0.19),
    "CsPbI3":  (0.045, 0.053),  # de electronic_analysis.json SOC
    "MAPbI3":  (0.12, 0.15),
    "FAPbI3":  (0.13, 0.14),
    "FAPbBr3": (0.14, 0.16),
}

# Eg experimental/GW de referencia para fuente AI (más realista que PBE+scissor)
_EG_AI: dict[str, float] = {
    "CsSnI3":  1.30,   # experimental
    "MASnI3":  1.30,
    "FASnI3":  1.41,
    "FASnBr3": 1.65,
    "CsPbI3":  1.73,   # experimental
    "MAPbI3":  1.55,   # experimental
    "FAPbI3":  1.48,   # experimental
    "FAPbBr3": 2.23,   # experimental
}

# Transport defaults comunes a perovskitas ABX3
_TRANSPORT_DEFAULTS = {
    "free_to_free_recombination": 1e-15,
    "srh_tau_n": 1e-7,
    "srh_tau_p": 1e-7,
    "ss_srh_enabled": "True",
    "ion_density": 1e22,
    "ion_mobility": 1e-13,
    "Nc": 1e26,
    "Nv": 1e26,
}

_METAL_WF = {"au": 5.1, "ag": 4.7, "al": 4.2}

_NM_MIN, _NM_MAX = 280.0, 1200.0


# ══════════════════════════════════════════════════════════════════════════════
# Carga de parámetros de material
# ══════════════════════════════════════════════════════════════════════════════

def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def _load_electronic_dft(mat: str) -> dict:
    """Carga m*, Eg de DFT-SOC.  r2SCAN primario, PBE fallback."""
    for base in (TOP8_R, TOP8_P):
        d = _read_json(base / mat / "10_effective_masses" / "electronic_analysis.json")
        if d and ("m_e_soc_m0" in d or "m_e_m0" in d):
            return d
    return {}


def _load_ai_predictions() -> dict:
    return _read_json(TOP8_R / "ai_predictions.json")


def _load_surrogate_eps(mat: str) -> Optional[float]:
    """Intenta cargar ε_∞ del surrogate RF+GBR."""
    try:
        from ml_surrogate.model import SurrogateEnsemble
        from ml_surrogate.features import extract, build_X, BASE_FEATURES
        import pandas as pd
        cfg = TOP8_MATS.get(mat)
        if cfg is None:
            return None
        feats = extract(cfg["A"], cfg["B"], cfg["X"])
        df = pd.DataFrame([feats])
        X_arr = build_X(df, BASE_FEATURES)
        model_path = ROOT / "models" / "surrogate_eps_inf.pkl"
        if not model_path.exists():
            return None
        model = SurrogateEnsemble.load(model_path)
        eps, _ = model.predict_single(X_arr[0])
        return float(np.clip(eps, 3.0, 10.0))
    except Exception:
        return None


def _load_surrogate_eg_meff(mat: str) -> Optional[tuple[float, float, float]]:
    """Retorna (Eg_eV, m_e, m_h) del surrogate ML o None."""
    try:
        from ml_surrogate.model import SurrogateEnsemble
        from ml_surrogate.features import extract, build_X, BASE_FEATURES
        import pandas as pd
        cfg = TOP8_MATS.get(mat)
        if cfg is None:
            return None
        feats = extract(cfg["A"], cfg["B"], cfg["X"])
        df = pd.DataFrame([feats])
        X_arr = build_X(df, BASE_FEATURES)
        models_dir = ROOT / "models"
        Eg_model  = SurrogateEnsemble.load(models_dir / "surrogate_bandgap.pkl")
        me_model  = SurrogateEnsemble.load(models_dir / "surrogate_meff_e.pkl")
        mh_model  = SurrogateEnsemble.load(models_dir / "surrogate_meff_h.pkl")
        Eg, _  = Eg_model.predict_single(X_arr[0])
        m_e, _ = me_model.predict_single(X_arr[0])
        m_h, _ = mh_model.predict_single(X_arr[0])
        return float(max(0.5, Eg)), float(max(0.04, m_e)), float(max(0.04, m_h))
    except Exception:
        return None


def _is_physical_mass(m: float) -> bool:
    return 0.03 <= m <= 2.0


def material_params(mat: str, source: str, preds: dict) -> dict:
    """Devuelve {Eg_eV, eps_r, m_e, m_h, xi_eV, label, source} para OghmaNano."""
    info = TOP8_MATS[mat]
    xi   = info["Xi"]
    eps_r = _load_surrogate_eps(mat) or _EPS_LIT.get(mat, 6.0)
    lit_me, lit_mh = _MEFF_LIT.get(mat, (0.15, 0.20))

    if source == "dft":
        # Eg de DFT (pipeline)
        pred = preds.get(mat, {})
        Eg   = pred.get("Eg_dft_eV") or pred.get("Eg_semi_eV") or 1.5
        # m* de DFT-SOC; si es UNPHYSICAL (>2 m₀) usa valores de literatura GW
        elec  = _load_electronic_dft(mat)
        flags = elec.get("flags_masses_soc", [])
        m_e_raw = elec.get("m_e_soc_m0") or elec.get("m_e_m0") or 999
        m_h_raw = elec.get("m_h_soc_m0") or elec.get("m_h_m0") or 999
        unphysical = (
            any("UNPHYSICAL" in str(f) for f in flags) or
            not _is_physical_mass(m_e_raw) or
            not _is_physical_mass(m_h_raw)
        )
        if unphysical:
            m_e, m_h = lit_me, lit_mh
            label = f"{mat} DFT (m* lit.)"
        else:
            m_e, m_h = m_e_raw, m_h_raw
            label = f"{mat} DFT"
    else:
        # source == "ai": Eg experimental/GW, m* de literatura SOC
        # (surrogate ML si disponible, si no: valores publicados GW+SOC)
        ai_res = _load_surrogate_eg_meff(mat)
        if ai_res:
            Eg, m_e, m_h = ai_res
            label = f"{mat} AI (surrogate)"
        else:
            Eg   = _EG_AI.get(mat) or (preds.get(mat, {}).get("Eg_dft_eV")) or 1.5
            m_e, m_h = lit_me, lit_mh
            label = f"{mat} AI (lit. GW+SOC)"

    # Sanity clamp
    Eg    = float(np.clip(Eg,  0.5, 3.5))
    m_e   = float(np.clip(m_e, 0.03, 2.0))
    m_h   = float(np.clip(m_h, 0.03, 2.0))
    eps_r = float(np.clip(eps_r, 3.0, 12.0))

    return {"Eg_eV": Eg, "eps_r": eps_r, "m_e": m_e, "m_h": m_h,
            "xi_eV": xi, "label": label, "source": source}


# ══════════════════════════════════════════════════════════════════════════════
# Óptica: DOS parabólica 3D + Kramers-Kronig → n(λ), k(λ)
# ══════════════════════════════════════════════════════════════════════════════

def _eps2_parabolic(omega: np.ndarray, Eg: float, eps_inf: float) -> np.ndarray:
    """ε₂ desde DOS conjunta 3D: onset ∝ √(ħω − Eg) / (ħω)²."""
    eps2 = np.zeros_like(omega, dtype=float)
    mask = omega > Eg + 1e-4
    eps2[mask] = np.sqrt(omega[mask] - Eg) / omega[mask] ** 2
    I = np.trapezoid(np.where(mask, eps2 / omega, 0.0), omega)
    if I > 1e-15:
        eps2 *= (eps_inf - 1.0) * np.pi / 2.0 / I
    return eps2


def _kramers_kronig(omega: np.ndarray, eps2: np.ndarray) -> np.ndarray:
    """K-K: ε₁(ω) = 1 + (2/π) P∫ ω'ε₂(ω')/(ω'²−ω²) dω'."""
    eps1 = np.ones(len(omega))
    for i, w in enumerate(omega):
        denom = omega ** 2 - w ** 2
        denom[i] = np.inf
        eps1[i] = 1.0 + (2.0 / np.pi) * np.trapezoid(omega * eps2 / denom, omega)
    return eps1


def optical_nk_rows(params: dict) -> list[tuple[float, float, float]]:
    """Genera lista (wl_nm, n, k) para OghmaNano desde parámetros de material."""
    Eg    = params["Eg_eV"]
    eps_r = params["eps_r"]
    omega = np.linspace(0.1, 6.0, 800)
    eps2  = _eps2_parabolic(omega, Eg, eps_r)
    eps1  = _kramers_kronig(omega, eps2)

    # Convertir (eps1, eps2) → (n, k)
    mod = np.sqrt(eps1 ** 2 + eps2 ** 2)
    n   = np.sqrt(np.maximum((mod + eps1) / 2.0, 0.0))
    k   = np.sqrt(np.maximum((mod - eps1) / 2.0, 0.0))

    # omega (eV) → wl (nm)
    wl_nm = 1239.84 / omega

    # Orden ascendente en longitud de onda y filtro rango PV
    idx   = np.argsort(wl_nm)
    wl_nm = wl_nm[idx];  n = n[idx];  k = k[idx]
    mask  = (wl_nm >= _NM_MIN) & (wl_nm <= _NM_MAX)

    return [(float(w), float(ni), float(ki))
            for w, ni, ki in zip(wl_nm[mask], n[mask], k[mask])]


# ══════════════════════════════════════════════════════════════════════════════
# OghmaNano sim dir
# ══════════════════════════════════════════════════════════════════════════════

_WORKING_SIM = (
    ROOT / "generador fv" / "calculations" / "alpha"
    / "14_oghma_device" / "sim" / "sim.json"
)


def _perovskite_template() -> dict:
    """Carga template perovskita OghmaNano.

    Prioridad:
      1. sim.json del run exitoso local (garantizado funcional)
      2. Template descargado de GitHub
      3. Minimal template de emergencia
    """
    if _WORKING_SIM.exists():
        try:
            return json.loads(_WORKING_SIM.read_text())
        except Exception:
            pass

    cache = Path(tempfile.gettempdir()) / "_oghma_perovskite_template.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:
            pass
    url = (
        "https://raw.githubusercontent.com/roderickmackenzie/OghmaNano"
        "/master/oghma_data/device_lib/perovskite/perovskite.json"
    )
    try:
        subprocess.run(
            ["curl", "-s", "--connect-timeout", "15", "-o", str(cache), url],
            check=True, capture_output=True,
        )
        return json.loads(cache.read_text())
    except Exception:
        return _minimal_template()


def _minimal_template() -> dict:
    return {
        "sim": {"simmode": "segment0@jv", "version": "8.0"},
        "sims": {"jv": {"segments": 1, "segment0": {
            "name": "JV curve", "Vstart": 0.0, "Vstop": 1.6,
            "Vstep": 0.02, "id": "jv_seg0"}}},
        "math": {"max_newton_iterations": 100, "newton_clever_exit": True},
        "optical": {"light": {
            "light_model": "flat", "sun": "AM1.5G",
            "Dphotoneff": 1.0, "NDfilter": 0.0}},
        "epitaxy": {
            "segments": 5,
            "segment0": {"name": "FTO",        "obj_type": "contact", "dy": 5e-8,  "shape_dos": {}},
            "segment1": {"name": "SnO2",        "obj_type": "layer",   "dy": 5e-8,  "shape_dos": {"Eg": 3.6, "epsilonr": 9.0}},
            "segment2": {"name": "Perovskite",  "obj_type": "active",  "dy": 4e-7,  "shape_dos": {}},
            "segment3": {"name": "Spiro",       "obj_type": "layer",   "dy": 2e-7,  "shape_dos": {"Eg": 3.0, "epsilonr": 3.0}},
            "segment4": {"name": "Au",          "obj_type": "contact", "dy": 1e-7,  "shape_dos": {}},
            "contacts": {"segments": 2,
                         "segment0": {"position": "top"},
                         "segment1": {"position": "bottom"}},
        },
        "mesh": {"mesh_y": {"segments": 1,
                            "segment0": {"len": 4e-7, "points": 100, "mul": 1.0}}},
        "server": {"max_gpvdm_instances": 1},
        "dump":   {"dump_level": 1},
    }


def _mobility_from_mass(m: float) -> float:
    """m* (m0 units) → movilidad [m²/Vs] via τ=10 fs."""
    mu = 1.602e-19 * 1e-14 / (m * 9.109e-31)
    return float(np.clip(mu, 1e-5, 1e-2))


def _enable_electrical_blocks(data) -> None:
    if isinstance(data, dict):
        for blk in ("shape_electrical", "shape_dos"):
            if isinstance(data.get(blk), dict):
                data[blk].setdefault("enabled", "True")
        for v in data.values():
            _enable_electrical_blocks(v)
    elif isinstance(data, list):
        for v in data:
            _enable_electrical_blocks(v)


def _patch_mesh(epi: dict, sim_json: dict) -> None:
    """Deja el mesh en auto=True — OghmaNano calcula el tamaño correcto."""
    my = (sim_json.get("electrical_solver", {})
                  .get("mesh", {})
                  .get("mesh_y", {}))
    if isinstance(my, dict):
        my["auto"] = "True"


def _runtime_defaults(data: dict, fast: bool) -> None:
    math = data.setdefault("math", {})
    if fast:
        math["newton_name"] = "newton_simple"
    math.setdefault("block_auto", "True")
    math.setdefault("math_stop_on_convergence_problem", "False")
    math.setdefault("math_stop_on_inverted_fermi_level", "False")
    math.setdefault("solver_verbosity", "solver_verbosity_at_end")
    matrix = math.setdefault("matrix", {})
    matrix.setdefault("solver_name", "umfpack")
    matrix.setdefault("core_max_threads", "all")


def _write_nk_files(mat_dir: Path, rows: list, bandgap_eV: float, eps_r: float) -> None:
    mat_dir.mkdir(parents=True, exist_ok=True)

    # nk.csv (human-readable)
    (mat_dir / "nk.csv").write_text(
        "#wavelength_nm n k\n" +
        "".join(f"{w:.4f} {n:.6f} {k:.6f}\n" for w, n, k in rows)
    )

    # n.csv (OghmaNano format)
    hdr_n = (
        '#oghma_csv {"title":"","type":"xy","y_label":"Wavelength",'
        '"data_label":"Refractive index","y_units":"nm","y_mul":1000000000.0,'
        f'"data_units":"au","icon":"mat_file","time ":0.0,"Vexternal":0.0,'
        f'"x_len":1,"y_len":{len(rows)},"z_len":1,"cols":"yd"}}*\n'
    )
    (mat_dir / "n.csv").write_text(
        hdr_n + "".join(f"{w*1e-9:.6e}\t{n:.6e}\n" for w, n, _ in rows)
    )

    # alpha.csv
    hdr_a = (
        '#oghma_csv {"title":"","type":"xy","y_label":"Wavelength",'
        '"data_label":"Absorption","y_units":"nm","y_mul":1000000000.0,'
        f'"data_units":"m^{{-1}}","icon":"mat_file","time ":0.0,"Vexternal":0.0,'
        f'"x_len":1,"y_len":{len(rows)},"z_len":1,"cols":"yd"}}*\n'
    )
    lines = []
    for w, _, k in rows:
        alpha = 4.0 * np.pi * max(k, 0.0) / (w * 1e-9)
        lines.append(f"{w*1e-9:.6e}\t{alpha:.6e}\n")
    (mat_dir / "alpha.csv").write_text(hdr_a + "".join(lines))

    # data.json / mat.json
    meta = {
        "item_type": "material", "material_type": "perovskite",
        "status": "public", "mat_src": "DFT/surrogate top8 pipeline",
        "material_db_electrical_params": {
            "material_blend": "False", "Xi0": -3.9,
            "Eg0": float(bandgap_eV), "epsilonr": float(eps_r),
        },
    }
    (mat_dir / "data.json").write_text(json.dumps(meta, indent=2))
    (mat_dir / "mat.json").write_text(json.dumps(meta, indent=2))


def write_sim_dir(sim_dir: Path, mat: str, params: dict,
                  nk_rows: list, fast: bool = True) -> None:
    """Escribe directorio OghmaNano completo para un material dado."""
    sim_dir.mkdir(parents=True, exist_ok=True)
    sim_json = copy.deepcopy(_perovskite_template())

    Eg    = params["Eg_eV"]
    eps_r = params["eps_r"]
    m_e   = params["m_e"]
    m_h   = params["m_h"]
    xi    = params["xi_eV"]
    mue   = _mobility_from_mass(m_e)
    muh   = _mobility_from_mass(m_h)

    # Ajusta modo de simulación (siempre JV)
    sim_json["sim"]["simmode"] = "segment0@jv"

    # Patch JV segment para asegurar Vstop apropiado
    jv_seg = (sim_json.get("sims", {})
              .get("jv", {})
              .get("segment0", {}))
    if isinstance(jv_seg, dict):
        cfg = jv_seg.setdefault("config", jv_seg)
        cfg["Vstop"] = min(float(Eg) + 0.3, 1.8)
        cfg["Vstep"] = 0.02

    # Patch SOLO la capa perovskita — no tocar FTO/Au/etc del template
    epi = sim_json["epitaxy"]
    for key, seg in epi.items():
        if not (key.startswith("segment") and isinstance(seg, dict)):
            continue
        name = seg.get("name", "").lower()
        dos  = seg.setdefault("shape_dos", {})

        # Asegura dd_enabled en todas las capas
        dos["dd_enabled"] = "True"

        if "perovskite" in name or name in ("mapi", "fapi", "cspbi3", "absorber"):
            seg["dy"] = 4e-7
            dos.update({
                "Eg":        float(Eg),
                "epsilonr":  float(eps_r),
                "mue_y":     mue, "mue_x": mue, "mue_z": mue,
                "muh_y":     muh, "muh_x": muh, "muh_z": muh,
                "Xi":        float(xi),
                **{k: v for k, v in _TRANSPORT_DEFAULTS.items()},
            })
            seg["optical_material"] = mat

    # Reposicionar capas (y0 contiguo)
    y0 = 0.0
    for k2 in sorted(
        (k for k in epi if k.startswith("segment") and isinstance(epi.get(k), dict)),
        key=lambda x: int(x.replace("segment", "")) if x.replace("segment", "").isdigit() else 999,
    ):
        epi[k2]["y0"] = y0
        y0 += float(epi[k2].get("dy") or 0.0)

    _patch_mesh(epi, sim_json)

    if fast:
        _apply_fast_settings(sim_json)

    _runtime_defaults(sim_json, fast=fast)

    (sim_dir / "sim.json").write_text(json.dumps(sim_json, indent=2))
    (sim_dir / "json.inp").write_text(json.dumps(sim_json, indent=2))

    # Material óptico personalizado
    mat_dir = sim_dir / "materials" / mat
    _write_nk_files(mat_dir, nk_rows, Eg, eps_r)

    # OghmaNano busca materiales en oghma_local/materials/{mat}/ — copiar ahí
    oghma_local_mat = Path.home() / "oghma_local" / "materials" / mat
    oghma_local_mat.mkdir(parents=True, exist_ok=True)
    for f in mat_dir.iterdir():
        shutil.copy(f, oghma_local_mat / f.name)

    # Índice local de materiales (copia del sistema si existe)
    idx_path = sim_dir / "materials" / "data.json"
    sys_idx  = Path("C:/Program Files (x86)/OghmaNano/oghma_data/materials/data.json")
    if sys_idx.exists():
        shutil.copy(sys_idx, idx_path)
    else:
        idx_path.write_text(json.dumps({"item_type": "material_db", "status": "public"}, indent=2))


def _apply_fast_settings(data) -> None:
    """Usa generación constante (no TMM) e inhibe iones — acelera convergencia."""
    if isinstance(data, dict):
        for k in list(data.keys()):
            kl = str(k).lower()
            if kl in ("ion_density", "ion_mobility"):
                data[k] = 0.0
            elif k == "charge_carrier_generation_model":
                data[k] = "light_constant"
            elif k == "light_model":
                data[k] = "flat"
            elif k == "Vstep":
                data[k] = 0.02
            else:
                _apply_fast_settings(data[k])
    elif isinstance(data, list):
        for v in data:
            _apply_fast_settings(v)


def _disable_ion_migration(data) -> None:
    if isinstance(data, dict):
        for k in list(data.keys()):
            if str(k).lower() in ("ion_density", "ion_mobility"):
                data[k] = 0.0
            else:
                _disable_ion_migration(data[k])
    elif isinstance(data, list):
        for v in data:
            _disable_ion_migration(v)


# ══════════════════════════════════════════════════════════════════════════════
# Corrida OghmaNano
# ══════════════════════════════════════════════════════════════════════════════

def find_runner() -> Optional[str]:
    candidates = [
        os.environ.get("OGHMA_EXECUTABLE"),
        shutil.which("oghma_core"),
        r"C:\Program Files (x86)\OghmaNano\oghma_core.exe",
        r"C:\Program Files\OghmaNano\oghma_core.exe",
        r"C:\OghmaNano\oghma_core.exe",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return str(c)
    return None


def run_oghma(sim_dir: Path, runner: str, timeout: int = 600) -> dict:
    """Ejecuta oghma_core.exe y devuelve {pce, voc, jsc, ff, status}."""
    lockfile = sim_dir / "lock0.dat"
    if lockfile.exists():
        lockfile.unlink()

    cmd = [
        runner,
        "--sim-root-path", str(sim_dir),
        "--gui", "--html",
        "--simmode", "segment0@jv",
        "--lockfile", str(lockfile),
    ]

    out_log = sim_dir.parent / "oghma_stdout.log"
    err_log = sim_dir.parent / "oghma_stderr.log"

    try:
        completed = subprocess.run(
            cmd, cwd=str(sim_dir),
            capture_output=True, text=True, timeout=timeout,
        )
        out_log.write_text(completed.stdout)
        err_log.write_text(completed.stderr)
        status = "completed" if completed.returncode == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        out_log.write_text((exc.stdout or ""))
        err_log.write_text((exc.stderr or ""))
        status = "timeout"

    return {**_parse_sim_info(sim_dir / "sim_info.dat"), "status": status}


def _parse_sim_info(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        data = {}
        for line in path.read_text().splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                try:
                    data[k.strip()] = float(v.strip())
                except ValueError:
                    pass

    def _f(val):
        try:
            return float(val) if val is not None else None
        except Exception:
            return None

    pce = _f(data.get("pce") or data.get("PCE") or data.get("pce_pct"))
    voc = _f(data.get("voc") or data.get("Voc"))
    jsc = _f(data.get("jsc") or data.get("Jsc"))
    ff  = _f(data.get("ff")  or data.get("FF"))
    # OghmaNano stores pce in % already (e.g. 11.09, not 0.1109)
    # OghmaNano stores jsc in A/m²; convert to mA/cm² (×0.1)
    if jsc is not None:
        jsc *= 0.1
    return {"pce_pct": pce, "voc_V": voc, "jsc_mA_cm2": jsc, "ff": ff}


def _read_jv_csv(sim_dir: Path) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Lee jv.csv → (V [V], J [mA/cm²])."""
    p = sim_dir / "jv.csv"
    if not p.exists():
        return None
    try:
        V, J = [], []
        for line in p.read_text().splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                V.append(float(parts[0]))
                J.append(float(parts[1]))
        if not V:
            return None
        V_arr = np.array(V)
        # OghmaNano reporta J en A/m² → mA/cm²: ×0.1
        J_arr = np.array(J) * 0.1
        return V_arr, J_arr
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Figuras
# ══════════════════════════════════════════════════════════════════════════════

LAYER_COLORS = {
    "glass":      "#aec6cf",
    "FTO/ITO":    "#b5d5c5",
    "SnO₂ (ETL)": "#d4e6b5",
    "Perovskite": None,       # override por material
    "Spiro (HTL)":"#f7d9c4",
    "Au":         "#ffd700",
}
LAYER_THICKNESS_REL = [0.08, 0.06, 0.05, 0.50, 0.20, 0.11]


def plot_cell_image(mat: str, color: str, out_path: Path) -> None:
    """Genera imagen esquemática de la celda solar perovskita."""
    labels  = ["Glass", "FTO/ITO", "SnO₂ (ETL)", "Perovskite", "Spiro (HTL)", "Au"]
    colors  = ["#aec6cf", "#b5d5c5", "#d4e6b5", color, "#f7d9c4", "#ffd700"]
    heights = [0.08, 0.06, 0.05, 0.50, 0.20, 0.11]

    fig, ax = plt.subplots(figsize=(3.0, 5.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    y = 0.0
    total = sum(heights)
    for lbl, col, h in zip(labels, colors, heights):
        frac = h / total
        rect = mpatches.FancyBboxPatch(
            (0.1, y), 0.80, frac,
            boxstyle="square,pad=0",
            facecolor=col, edgecolor="#333333", linewidth=0.8,
        )
        ax.add_patch(rect)
        ax.text(0.50, y + frac / 2, lbl,
                ha="center", va="center", fontsize=8.5,
                fontweight="bold" if lbl == "Perovskite" else "normal")
        y += frac

    ax.set_title(f"{mat}", fontsize=11, fontweight="bold", pad=6)
    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [cell] {out_path.name}")


def plot_jv_all(results: dict, source: str) -> None:
    """Curvas JV de todos los materiales con un source dado."""
    fig, ax = plt.subplots(figsize=(8, 5.5))

    plotted = 0
    for mat, src_dict in results.items():
        res = src_dict.get(source, {})
        sim_dir = OUT / mat / source / "sim"
        jv = _read_jv_csv(sim_dir)
        color = TOP8_MATS[mat]["color"]
        if jv is not None:
            V, J = jv
            ax.plot(V, -J, color=color, lw=1.8, label=mat)
            plotted += 1
        elif res.get("pce_pct"):
            # Sin curva pero con métricas → dibuja punto ficticio
            ax.scatter([res.get("voc_V", 0)], [res.get("jsc_mA_cm2", 0)],
                       color=color, zorder=5, label=f"{mat} (est.)")
            plotted += 1

    ax.axhline(0, color="k", lw=0.5)
    ax.set_xlabel("Voltaje (V)", fontsize=11)
    ax.set_ylabel("Densidad de corriente (mA cm⁻²)", fontsize=11)
    ax.set_title(f"Top-8 perovskitas — drift-diffusion OghmaNano ({source.upper()})",
                 fontsize=12)
    ax.legend(fontsize=8, ncol=2)
    ax.set_xlim(left=0)

    for ext in ("pdf", "png"):
        fig.savefig(FIGS / f"jv_top8_{source}.{ext}", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [fig] jv_top8_{source}.pdf/png  ({plotted} materiales)")


def plot_pce_bar(results: dict) -> None:
    """Barras de PCE: DFT vs AI para cada material."""
    mats   = list(TOP8_MATS.keys())
    pce_d  = [results.get(m, {}).get("dft", {}).get("pce_pct") or 0 for m in mats]
    pce_a  = [results.get(m, {}).get("ai",  {}).get("pce_pct") or 0 for m in mats]

    x   = np.arange(len(mats))
    w   = 0.35
    fig, ax = plt.subplots(figsize=(11, 5))
    b1 = ax.bar(x - w / 2, pce_d, w, label="DFT ε(ω)",  color="#2374ab", alpha=0.85)
    b2 = ax.bar(x + w / 2, pce_a, w, label="AI ε(ω)",   color="#e05c00", alpha=0.85)
    ax.bar_label(b1, fmt="%.1f", fontsize=7.5, padding=2)
    ax.bar_label(b2, fmt="%.1f", fontsize=7.5, padding=2)
    ax.set_xticks(x); ax.set_xticklabels(mats, rotation=30, ha="right")
    ax.set_ylabel("PCE (%)", fontsize=11)
    ax.set_title("Top-8 perovskitas — PCE drift-diffusion (DFT vs AI ε)", fontsize=12)
    ax.legend()
    for ext in ("pdf", "png"):
        fig.savefig(FIGS / f"pce_bar_dft_ai.{ext}", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [fig] pce_bar_dft_ai.pdf/png")


def plot_dielectric_comparison(mat: str, params_dft: dict, params_ai: dict) -> None:
    """ε₁, ε₂, n, k  DFT vs AI para un material."""
    omega = np.linspace(0.1, 6.0, 800)

    def _curves(p):
        eps2 = _eps2_parabolic(omega, p["Eg_eV"], p["eps_r"])
        eps1 = _kramers_kronig(omega, eps2)
        mod  = np.sqrt(eps1**2 + eps2**2)
        n    = np.sqrt(np.maximum((mod + eps1) / 2, 0))
        k    = np.sqrt(np.maximum((mod - eps1) / 2, 0))
        return eps1, eps2, n, k

    e1d, e2d, nd, kd = _curves(params_dft)
    e1a, e2a, na, ka = _curves(params_ai)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, (yd, ya, lbl) in zip(axes, [(e1d, e1a, "ε₁"), (e2d, e2a, "ε₂")]):
        ax.plot(omega, yd, label="DFT", color="#2374ab")
        ax.plot(omega, ya, label="AI",  color="#e05c00", ls="--")
        ax.axvline(params_dft["Eg_eV"], color="#2374ab", lw=0.7, ls=":")
        ax.axvline(params_ai["Eg_eV"],  color="#e05c00", lw=0.7, ls=":")
        ax.set_xlabel("ħω (eV)"); ax.set_ylabel(lbl)
        ax.legend(fontsize=9); ax.set_xlim(0, 6)

    fig.suptitle(f"{mat} — función dieléctrica DFT vs AI", fontsize=12)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(FIGS / f"dielectric_{mat}.{ext}", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
# Pipeline principal
# ══════════════════════════════════════════════════════════════════════════════

def parse_existing(mat: str, source: str, preds: dict) -> dict:
    """Re-parsea sim_info.dat existente sin re-ejecutar OghmaNano."""
    step_dir = OUT / mat / source
    sim_dir  = step_dir / "sim"
    params   = material_params(mat, source, preds)
    result: dict = {**params, "status": "parsed",
                    "pce_pct": None, "voc_V": None, "jsc_mA_cm2": None, "ff": None}
    parsed = _parse_sim_info(sim_dir / "sim_info.dat")
    result.update(parsed)
    pce = result.get("pce_pct")
    print(f"\n--- {mat}  [{source.upper()}] ---")
    print(f"  Eg={params['Eg_eV']:.3f} eV  eps_r={params['eps_r']:.2f}"
          f"  m_e={params['m_e']:.3f}  m_h={params['m_h']:.3f}")
    print(f"  [result] PCE={pce:.4f}% Voc={result.get('voc_V'):.3f}V"
          f"  Jsc={result.get('jsc_mA_cm2'):.4f} mA/cm²"
          f"  FF={result.get('ff'):.4f}"
          if pce is not None else f"  [result] no sim_info.dat")
    (step_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


def run_material(mat: str, source: str, runner: Optional[str],
                 preds: dict, execute: bool) -> dict:
    """Setup + (opcional) ejecución OghmaNano para un material y fuente."""
    print(f"\n--- {mat}  [{source.upper()}] ---")

    params  = material_params(mat, source, preds)
    nk_rows = optical_nk_rows(params)

    step_dir = OUT / mat / source
    step_dir.mkdir(parents=True, exist_ok=True)
    sim_dir  = step_dir / "sim"

    print(f"  Eg={params['Eg_eV']:.3f} eV  eps_r={params['eps_r']:.2f}"
          f"  m_e={params['m_e']:.3f}  m_h={params['m_h']:.3f}")

    write_sim_dir(sim_dir, mat, params, nk_rows, fast=False)
    print(f"  [sim] {sim_dir} — escrito")

    result: dict = {**params, "status": "prepared",
                    "pce_pct": None, "voc_V": None, "jsc_mA_cm2": None, "ff": None}

    if execute and runner:
        print(f"  [run] {runner}")
        res = run_oghma(sim_dir, runner)
        result.update(res)
        pce = result.get("pce_pct")
        print(f"  [result] PCE={pce:.2f}% Voc={result.get('voc_V'):.3f}V"
              f"  Jsc={result.get('jsc_mA_cm2'):.2f} mA/cm²"
              f"  FF={result.get('ff'):.4f}"
              if pce is not None else f"  [result] {res.get('status','?')}")
    elif not runner:
        print("  [warn] oghma_core no encontrado — solo setup")
    else:
        print("  [skip] ejecución desactivada (--no-run)")

    # Guarda resultado JSON
    (step_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Drift-diffusion top-8 perovskitas con OghmaNano")
    ap.add_argument("--mat", default="all",
                    help="Material o 'all' (default: all)")
    ap.add_argument("--source", default="both",
                    choices=["dft", "ai", "both"],
                    help="Fuente de función dieléctrica")
    ap.add_argument("--no-run", action="store_true",
                    help="Solo escribe el proyecto, no ejecuta OghmaNano")
    ap.add_argument("--parse-only", action="store_true",
                    help="Re-parsea sim_info.dat existente y regenera figuras sin re-ejecutar")
    args = ap.parse_args()

    preds   = _load_ai_predictions()
    runner  = find_runner()
    execute = not args.no_run

    if runner:
        print(f"OghmaNano runner: {runner}")
    else:
        print("[warn] oghma_core.exe no encontrado — se escribirán proyectos sin ejecutar")

    mats = list(TOP8_MATS.keys()) if args.mat == "all" else [args.mat]
    sources = ["dft", "ai"] if args.source == "both" else [args.source]

    # Genera imágenes de celda
    for mat in mats:
        plot_cell_image(
            mat, TOP8_MATS[mat]["color"],
            FIGS / f"cell_{mat}.png",
        )

    # Ejecuta o re-parsea simulaciones
    all_results: dict[str, dict] = {}
    for mat in mats:
        all_results[mat] = {}
        for src in sources:
            if args.parse_only:
                res = parse_existing(mat, src, preds)
            else:
                res = run_material(mat, src, runner, preds, execute)
            all_results[mat][src] = res
            # Función dieléctrica individual
            if "dft" in all_results[mat] and "ai" in all_results[mat]:
                plot_dielectric_comparison(
                    mat,
                    all_results[mat]["dft"],
                    all_results[mat]["ai"],
                )

    # Figuras globales (solo si hay datos de ambas fuentes)
    if "both" in args.source or args.source in ("dft", "ai"):
        for src in sources:
            plot_jv_all(all_results, src)
        if "dft" in sources and "ai" in sources:
            plot_pce_bar(all_results)

    # Resumen
    print("\n======= RESUMEN =======")
    print(f"{'Material':<12} {'Src':<5} {'PCE%':>6} {'Voc':>7} {'Jsc':>8} {'FF':>7}")
    for mat in mats:
        for src in sources:
            r = all_results[mat].get(src, {})
            pce = r.get("pce_pct")
            voc = r.get("voc_V")
            jsc = r.get("jsc_mA_cm2")
            ff  = r.get("ff")
            p = f"{pce:.2f}" if pce else "—"
            v = f"{voc:.3f}" if voc else "—"
            j = f"{jsc:.2f}" if jsc else "—"
            f_ = f"{ff:.4f}" if ff else "—"
            print(f"{mat:<12} {src:<5} {p:>6} {v:>7} {j:>8} {f_:>7}")

    # Guarda resumen global
    (OUT / "top8_dd_results.json").write_text(json.dumps(all_results, indent=2))
    print(f"\nResultados en: {OUT}")
    print(f"Figuras en:    {FIGS}")


if __name__ == "__main__":
    main()
