"""Defensive diagnostics for the OghmaNano device handoff.

Writes debug_outputs/ under the Oghma step directory by default.
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
import importlib.util
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
_OGHMA_DEVICE = ROOT / "src" / "dft_cspbi3" / "analysis" / "oghma_device.py"
_spec = importlib.util.spec_from_file_location("_oghma_device_debug_import", _OGHMA_DEVICE)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Could not import {_OGHMA_DEVICE}")
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
parse_oghma_sim_info = _module.parse_oghma_sim_info

EG_EV = 1.5858
URBACH_ENERGY_MEV = 25.0
PIN_MW_CM2 = 100.0
SMOOTH_WINDOW = 11
SMOOTH_POLY = 3
HC_EV_CM = 1.239841984e-4


def _read_oghma_xy(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    meta: dict[str, Any] = {}
    raw = path.read_bytes()
    marker = b"}*"
    if raw.startswith(b"#oghma_csv") and marker in raw:
        header_end = raw.index(marker) + len(marker)
        header = raw[:header_end].decode("utf-8", errors="replace")
        match = re.search(r"\{.*\}", header)
        if match:
            try:
                meta = json.loads(match.group(0))
            except json.JSONDecodeError:
                meta = {}
        if str(meta.get("bin", "0")) == "1":
            payload = raw[header_end:].lstrip(b"\r\n")
            y_len = int(meta.get("y_len") or meta.get("data_len") or 0)
            cols = str(meta.get("cols", "yd"))
            n_cols = max(1, len(cols))
            expected = y_len * n_cols
            arr = np.frombuffer(payload[: expected * 8], dtype="<f8")
            if arr.size < expected:
                arr = np.frombuffer(payload[: expected * 4], dtype="<f4").astype(float)
            if y_len > 0 and arr.size >= expected:
                arr = arr[:expected].reshape(y_len, n_cols)
                return arr[:, 0].astype(float), arr[:, -1].astype(float), meta

    xs: list[float] = []
    ys: list[float] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#oghma_csv"):
            match = re.search(r"\{.*\}", line)
            if match:
                try:
                    meta = json.loads(match.group(0))
                except json.JSONDecodeError:
                    meta = {}
            continue
        if line.startswith("#"):
            continue
        parts = re.split(r"[\s,]+", line)
        if len(parts) >= 2:
            try:
                xs.append(float(parts[0]))
                ys.append(float(parts[1]))
            except ValueError:
                pass
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), meta


def _load_stack(step_dir: Path) -> dict[str, Any]:
    path = step_dir / "device_stack.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _layer_bounds_nm(stack: dict[str, Any]) -> tuple[float, float, float]:
    y = 0.0
    absorber_start = math.nan
    absorber_end = math.nan
    for layer in stack.get("layers", []):
        dy = float(layer.get("thickness_nm") or 0.0)
        if layer.get("role") == "absorber":
            absorber_start = y
            absorber_end = y + dy
        y += dy
    return y, absorber_start, absorber_end


def _load_optical_spectrum(step_dir: Path) -> tuple[dict[str, np.ndarray], list[str]]:
    warnings: list[str] = []
    stack = _load_stack(step_dir)
    source = stack.get("source_files", {})
    freq_path = _resolve_existing_path(source.get("optical_frequencies", ""))
    alpha_path = _resolve_existing_path(source.get("absorption", ""))
    n_path = _resolve_existing_path(source.get("n_omega", ""))
    k_path = _resolve_existing_path(source.get("k_omega", ""))

    if all(p and p.exists() for p in (freq_path, alpha_path, n_path, k_path)):
        energy = np.load(freq_path)
        alpha_cm1 = np.load(alpha_path)
        n = np.load(n_path)
        k = np.load(k_path)
        wavelength_nm = np.divide(1239.84, energy, out=np.full_like(energy, np.nan), where=energy > 0)
        mask = np.isfinite(wavelength_nm) & (wavelength_nm >= 200.0) & (wavelength_nm <= 1200.0)
        spectrum = {
            "energy_eV": energy[mask],
            "wavelength_nm": wavelength_nm[mask],
            "alpha_cm1": alpha_cm1[mask],
            "alpha_m1": alpha_cm1[mask] * 100.0,
            "n": n[mask],
            "k": k[mask],
        }
        dielectric_path = _resolve_existing_path("calculations/alpha/11_optical/dielectric_function.csv")
        if dielectric_path and dielectric_path.exists():
            raw = _load_dielectric_spectrum(dielectric_path)
            spectrum["n_raw"] = np.interp(spectrum["energy_eV"], raw["energy_eV"], raw["n_raw"])
            spectrum["k_raw"] = np.interp(spectrum["energy_eV"], raw["energy_eV"], raw["k_raw"])
        return spectrum, warnings

    dielectric_path = _resolve_existing_path("calculations/alpha/11_optical/dielectric_function.csv")
    if dielectric_path and dielectric_path.exists():
        warnings.append(
            "Expected DFT optical .npy files are missing; deriving n/k/alpha from dielectric_function.csv."
        )
        return _load_dielectric_spectrum(dielectric_path), warnings

    warnings.append("Expected DFT optical files are missing; using Oghma material CSV fallback.")
    mat = step_dir / "sim" / "materials" / "CsPbI3"
    wl_alpha_m, alpha_m1, _ = _read_oghma_xy(mat / "alpha.csv")
    wl_n_m, n, _ = _read_oghma_xy(mat / "n.csv")
    nk_wl_nm, _nk_n, k = _read_plain_columns(mat / "nk.csv", columns=(0, 1, 2))
    wavelength_nm = wl_alpha_m * 1e9
    energy = np.divide(1239.84, wavelength_nm, out=np.full_like(wavelength_nm, np.nan), where=wavelength_nm > 0)
    if len(k) != len(wavelength_nm):
        k = np.interp(wavelength_nm, nk_wl_nm, k) if len(k) else np.full_like(wavelength_nm, np.nan)
        warnings.append("Interpolated k from nk.csv onto alpha.csv wavelengths.")
    if len(n) != len(wavelength_nm):
        n = np.interp(wavelength_nm, wl_n_m * 1e9, n)
    return {
        "energy_eV": energy,
        "wavelength_nm": wavelength_nm,
        "alpha_cm1": alpha_m1 / 100.0,
        "alpha_m1": alpha_m1,
        "n": n,
        "k": k,
    }, warnings


def _resolve_existing_path(raw: str | Path | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    candidates = [path, ROOT / path, ROOT.parent / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return path


def _load_dielectric_spectrum(path: Path) -> dict[str, np.ndarray]:
    """Load GPAW dielectric CSV and derive optical constants.

    Expected columns are energy_eV, eps1_x, eps2_x, eps1_y, eps2_y.  We average
    the available tensor components and derive n/k from sqrt(epsilon).
    """
    data = np.loadtxt(path, delimiter=",")
    energy = data[:, 0]
    eps1 = np.nanmean(data[:, [1, 3]], axis=1)
    eps2 = np.nanmean(data[:, [2, 4]], axis=1)
    eps_abs = np.sqrt(eps1**2 + eps2**2)
    n_raw = np.sqrt(np.clip((eps_abs + eps1) / 2.0, 0.0, None))
    k_raw = np.sqrt(np.clip((eps_abs - eps1) / 2.0, 0.0, None))
    wavelength_nm = np.divide(1239.84, energy, out=np.full_like(energy, np.nan), where=energy > 0)
    n = _smooth_series(n_raw, window=SMOOTH_WINDOW, poly=SMOOTH_POLY)
    k = _smooth_series(k_raw, window=SMOOTH_WINDOW, poly=SMOOTH_POLY)
    k = np.clip(k, 0.0, None)
    k = _apply_urbach_tail(energy, k, EG_EV, URBACH_ENERGY_MEV)
    alpha_cm1 = np.divide(
        4.0 * np.pi * k,
        wavelength_nm * 1e-7,
        out=np.zeros_like(k),
        where=wavelength_nm > 0,
    )
    mask = np.isfinite(wavelength_nm) & (wavelength_nm >= 200.0) & (wavelength_nm <= 1200.0)
    return {
        "energy_eV": energy[mask],
        "wavelength_nm": wavelength_nm[mask],
        "alpha_cm1": alpha_cm1[mask],
        "alpha_m1": alpha_cm1[mask] * 100.0,
        "n": n[mask],
        "k": k[mask],
        "n_raw": n_raw[mask],
        "k_raw": k_raw[mask],
    }


def _smooth_series(values: np.ndarray, *, window: int, poly: int) -> np.ndarray:
    """Savitzky-Golay style smoothing without a SciPy dependency."""
    values = np.asarray(values, dtype=float)
    if len(values) < 5:
        return values.copy()
    window = min(window, len(values) if len(values) % 2 else len(values) - 1)
    window = max(window, poly + 2 + ((poly + 2) % 2 == 0))
    if window % 2 == 0:
        window -= 1
    half = window // 2
    out = np.empty_like(values)
    x_window = np.arange(-half, half + 1, dtype=float)
    for i in range(len(values)):
        left = max(0, i - half)
        right = min(len(values), i + half + 1)
        y = values[left:right]
        x = np.arange(left - i, right - i, dtype=float)
        deg = min(poly, len(y) - 1)
        if len(y) == window:
            coeff = np.polyfit(x_window, y, deg)
        else:
            coeff = np.polyfit(x, y, deg)
        out[i] = np.polyval(coeff, 0.0)
    return out


def _apply_urbach_tail(energy_eV: np.ndarray, k_arr: np.ndarray, eg_eV: float, eu_meV: float) -> np.ndarray:
    energy = np.asarray(energy_eV, dtype=float)
    k = np.clip(np.asarray(k_arr, dtype=float), 0.0, None)
    below = energy < eg_eV
    eu_eV = float(eu_meV) * 1e-3
    if eu_eV <= 0.0:
        out = k.copy()
        out[below] = 0.0
        return out
    alpha = _alpha_cm1_from_k(energy, k)
    above = energy >= eg_eV
    if not np.any(above) or np.nanmax(alpha[above]) <= 0.0:
        out = k.copy()
        out[below] = 0.0
        return out
    order = np.argsort(energy[above])
    edge_energy = energy[above][order]
    edge_alpha = alpha[above][order]
    alpha_edge = float(np.interp(eg_eV, edge_energy, edge_alpha, left=edge_alpha[0], right=edge_alpha[-1]))
    alpha[below] = alpha_edge * np.exp(np.clip((energy[below] - eg_eV) / eu_eV, -700.0, 0.0))
    return _k_from_alpha_cm1(energy, alpha)


def _alpha_cm1_from_k(energy_eV: np.ndarray, k_arr: np.ndarray) -> np.ndarray:
    wavelength_cm = np.divide(
        HC_EV_CM,
        energy_eV,
        out=np.full_like(energy_eV, np.inf, dtype=float),
        where=energy_eV > 0,
    )
    return np.divide(
        4.0 * np.pi * np.clip(k_arr, 0.0, None),
        wavelength_cm,
        out=np.zeros_like(k_arr, dtype=float),
        where=np.isfinite(wavelength_cm) & (wavelength_cm > 0),
    )


def _k_from_alpha_cm1(energy_eV: np.ndarray, alpha_cm1: np.ndarray) -> np.ndarray:
    wavelength_cm = np.divide(
        HC_EV_CM,
        energy_eV,
        out=np.full_like(energy_eV, np.inf, dtype=float),
        where=energy_eV > 0,
    )
    return np.divide(
        np.clip(alpha_cm1, 0.0, None) * wavelength_cm,
        4.0 * np.pi,
        out=np.zeros_like(alpha_cm1, dtype=float),
        where=np.isfinite(wavelength_cm) & (wavelength_cm > 0),
    )


def _read_plain_columns(path: Path, columns: tuple[int, ...]) -> tuple[np.ndarray, ...]:
    arrays = [[] for _ in columns]
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"[\s,]+", line)
        try:
            vals = [float(parts[idx]) for idx in columns]
        except (ValueError, IndexError):
            continue
        for arr, val in zip(arrays, vals):
            arr.append(val)
    return tuple(np.asarray(arr, dtype=float) for arr in arrays)


def _write_optical_outputs(out_dir: Path, spectrum: dict[str, np.ndarray]) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    warnings: list[str] = []
    cols = ["energy_eV", "wavelength_nm", "alpha_cm1", "alpha_m1", "n", "k"]
    if "n_raw" in spectrum and "k_raw" in spectrum:
        cols.extend(["n_raw", "k_raw"])
    with (out_dir / "optical_spectrum_combined.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(cols)
        for row in zip(*(spectrum[c] for c in cols)):
            writer.writerow(row)

    energy = spectrum["energy_eV"]
    alpha_cm1 = spectrum["alpha_cm1"]
    n = spectrum["n"]
    k = spectrum["k"]

    for name, arr in spectrum.items():
        if np.any(~np.isfinite(arr)):
            warnings.append(f"{name} contains NaN or infinite values.")
        if name in {"alpha_cm1", "alpha_m1", "n", "k"} and np.nanmin(arr) < 0:
            warnings.append(f"{name} contains negative values.")
    below = alpha_cm1[energy < EG_EV]
    above = alpha_cm1[energy >= EG_EV]
    if below.size and above.size and np.nanmedian(below) > 0.2 * np.nanmedian(above):
        warnings.append("Sub-gap absorption is high relative to above-gap absorption.")
    if below.size and np.nanmax(below) <= 0.0:
        warnings.append("Sub-gap absorption is hard-clipped to zero; Urbach tail is missing.")
    if above.size and np.nanmax(above) <= 0:
        warnings.append("No above-gap absorption after processing.")
    if np.nanmax(alpha_cm1) > 1e7:
        warnings.append("Absorption exceeds 1e7 cm^-1, likely bad k/alpha scaling.")
    if np.nanmax(np.abs(k)) > 10:
        warnings.append("k exceeds 10, likely bad optical fallback or unit conversion.")

    order = np.argsort(energy)
    source_note = f"source: DFT optical .npy | Urbach tail Eu={URBACH_ENERGY_MEV:.0f} meV"
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.semilogy(energy[order], np.clip(alpha_cm1[order], 1e-30, None), label="alpha cm^-1")
    ax.semilogy(energy[order], np.clip(spectrum["alpha_m1"][order], 1e-30, None), "--", label="alpha m^-1")
    ax.axvline(EG_EV, color="k", linestyle=":", label=f"Eg={EG_EV:.4f} eV")
    ax.set_xlabel("Energy (eV)")
    ax.set_ylabel("Absorption")
    _stamp_axes(ax, source_note)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "optical_spectrum_absorption.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(energy[order], n[order], label="n processed")
    ax.plot(energy[order], k[order], label="k processed")
    ax.axvline(EG_EV, color="k", linestyle=":", label=f"Eg={EG_EV:.4f} eV")
    ax.set_xlabel("Energy (eV)")
    ax.set_ylabel("Optical constants")
    _stamp_axes(ax, source_note)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "optical_spectrum_nk.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    zoom = (energy >= 1.0) & (energy <= 2.0)
    zoom_order = np.argsort(energy[zoom])
    ez = energy[zoom][zoom_order]
    ax.plot(ez, n[zoom][zoom_order], label="n processed")
    ax.plot(ez, k[zoom][zoom_order], label="k processed")
    ax.axvline(EG_EV, color="k", linestyle=":", label=f"Eg={EG_EV:.4f} eV")
    ax.set_xlabel("Energy (eV)")
    ax.set_ylabel("Optical constants")
    ax.set_title("Optical constants near bandgap")
    ax.set_xlim(1.0, 2.0)
    _stamp_axes(ax, source_note)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "optical_spectrum_nk_zoom_1_2eV.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.semilogy(ez, np.clip(alpha_cm1[zoom][zoom_order], 1e-3, None), label="alpha cm^-1")
    ax.axvline(EG_EV, color="k", linestyle=":", label=f"Eg={EG_EV:.4f} eV")
    ax.set_xlabel("Energy (eV)")
    ax.set_ylabel("Absorption (cm^-1)")
    ax.set_title("Absorption onset near bandgap")
    ax.set_xlim(1.0, 2.0)
    _stamp_axes(ax, source_note)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "optical_spectrum_absorption_zoom_1_2eV.png", dpi=160)
    plt.close(fig)

    if "n_raw" in spectrum and "k_raw" in spectrum:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(energy[order], spectrum["n_raw"][order], color="C0", alpha=0.35, linewidth=1, label="n raw")
        ax.plot(energy[order], spectrum["k_raw"][order], color="C1", alpha=0.35, linewidth=1, label="k raw")
        ax.plot(energy[order], n[order], color="C0", linewidth=2, label="n processed")
        ax.plot(energy[order], k[order], color="C1", linewidth=2, label="k processed")
        ax.axvline(EG_EV, color="k", linestyle=":", label=f"Eg={EG_EV:.4f} eV")
        ax.set_xlabel("Energy (eV)")
        ax.set_ylabel("Optical constants")
        _stamp_axes(ax, "source: DFT .npy vs raw dielectric CSV")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "optical_spectrum_nk_raw_vs_processed.png", dpi=160)
        plt.close(fig)
    return warnings


def _stamp_axes(
    ax: Any,
    text: str,
    *,
    x: float = 0.99,
    y: float = 0.01,
    ha: str = "right",
    va: str = "bottom",
) -> None:
    ax.text(
        x,
        y,
        text,
        transform=ax.transAxes,
        ha=ha,
        va=va,
        fontsize=7,
        color="#333333",
        bbox={"facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.85, "pad": 2},
    )


def _interp_jsc_from_curve(step_dir: Path) -> float | None:
    jv = step_dir / "sim" / "jv.csv"
    if not jv.exists():
        return None
    v, j_a_m2, _ = _read_oghma_xy(jv)
    if len(v) < 2:
        return None
    order = np.argsort(v)
    return float(np.interp(0.0, v[order], j_a_m2[order]) * 0.1)


def _generation_sanity(step_dir: Path, stack: dict[str, Any]) -> dict[str, float | None | str]:
    total_nm, absorber_start_nm, absorber_end_nm = _layer_bounds_nm(stack)
    g_path = step_dir / "sim" / "optical_output" / "G_y.csv"
    if not g_path.exists():
        return {
            "total_stack_thickness_nm": total_nm,
            "absorber_start_nm": absorber_start_nm,
            "absorber_end_nm": absorber_end_nm,
            "simulated_generation_depth_max_nm": None,
            "generation_peak_depth_nm": None,
            "generation_warning": "G_y.csv missing",
        }
    y_m, g, _ = _read_oghma_xy(g_path)
    y_nm = y_m * 1e9
    peak_nm = float(y_nm[int(np.nanargmax(g))]) if len(g) else None
    warnings = []
    if len(y_nm) and abs(float(np.nanmax(y_nm)) - total_nm) > max(25.0, 0.05 * total_nm):
        warnings.append("generation depth does not match total stack thickness")
    if peak_nm is not None and not (absorber_start_nm <= peak_nm <= absorber_end_nm):
        warnings.append("main generation peak is outside absorber")
    return {
        "total_stack_thickness_nm": total_nm,
        "absorber_start_nm": absorber_start_nm,
        "absorber_end_nm": absorber_end_nm,
        "simulated_generation_depth_max_nm": float(np.nanmax(y_nm)) if len(y_nm) else None,
        "generation_peak_depth_nm": peak_nm,
        "generation_warning": "; ".join(warnings) or "none",
    }


def _write_time_outputs(step_dir: Path, out_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    snapshots = sorted((step_dir / "sim" / "snapshots").glob("*"), key=lambda p: int(p.name) if p.name.isdigit() else 10**9)
    candidate_count = 0
    for snap in snapshots:
        meta_path = snap / "data.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        time_s = float(meta.get("time", math.nan))
        vext = float(meta.get("Vexternal", meta.get("voltage", math.nan)))
        for csv_path in snap.glob("*.csv"):
            if csv_path.name in {"x.csv", "y.csv"}:
                continue
            candidate_count += 1
            _, values, file_meta = _read_oghma_xy(csv_path)
            if not len(values):
                continue
            rows.append({
                "file": str(csv_path.relative_to(step_dir)),
                "snapshot": snap.name,
                "time_s": time_s,
                "voltage_V": vext,
                "variable": csv_path.stem,
                "units_inferred": file_meta.get("data_units", "unknown"),
                "min": float(np.nanmin(values)),
                "max": float(np.nanmax(values)),
                "mean": float(np.nanmean(values)),
                "negative_count": int(np.sum(values < 0)),
                "jump_ratio": _jump_ratio(values),
            })
    if rows and len({r["time_s"] for r in rows}) <= 1:
        warnings.append("Snapshot files exist but all recorded times are identical; this is JV snapshot output, not a time transient.")
    if candidate_count and not rows:
        warnings.append(
            f"Found {candidate_count} snapshot CSV candidates, but they appear to contain Oghma binary payloads after the header; "
            "text parser skipped them."
        )
    with (out_dir / "time_dependent_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["file", "snapshot", "time_s", "voltage_V", "variable", "units_inferred", "min", "max", "mean", "negative_count", "jump_ratio"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        if rows:
            writer.writerows(rows)
        elif candidate_count:
            writer.writerow({
                "file": "sim/snapshots/*/*.csv",
                "snapshot": "all",
                "time_s": "",
                "voltage_V": "",
                "variable": "binary_snapshot_payloads",
                "units_inferred": "see Oghma headers",
                "min": "",
                "max": "",
                "mean": "",
                "negative_count": "",
                "jump_ratio": "",
            })

    jv = step_dir / "sim" / "jv.csv"
    if jv.exists():
        v, j, _ = _read_oghma_xy(jv)
        _plot_jv_curve(v, j, out_dir / "jv_curve.png")
        _plot_pv_quadrant_power(v, j, out_dir / "jv_power_output.png")
        fig, ax1 = plt.subplots(figsize=(6, 4))
        ax1.plot(v, j * 0.1, "o-", label="J")
        ax1.set_xlabel("Voltage (V)")
        ax1.set_ylabel("Current density (mA cm^-2)")
        ax2 = ax1.twinx()
        ax2.plot(v, _pv_power_mw_cm2(v, j), "r--", label="Signed PV power")
        ax2.axhline(0, color="0.35", linewidth=0.8, linestyle=":")
        ax2.set_ylabel("Signed power density (mW cm^-2)")
        _stamp_axes(ax1, "source: latest Oghma jv.csv")
        fig.tight_layout()
        fig.savefig(out_dir / "time_current_voltage.png", dpi=160)
        plt.close(fig)
    _plot_snapshot_family(rows, out_dir, "Q_", "time_carrier_density.png")
    _plot_snapshot_family(rows, out_dir, ("G_", "R_"), "time_generation_recombination.png")
    return rows, warnings


def _plot_jv_curve(v: np.ndarray, j_a_m2: np.ndarray, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    j_ma_cm2 = j_a_m2 * 0.1
    power_mw_cm2 = _pv_power_mw_cm2(v, j_a_m2)
    fig, ax1 = plt.subplots(figsize=(6, 4))
    ax2 = ax1.twinx()
    ax1.plot(v, j_ma_cm2, "o-", color="C0", label="J-V")
    ax1.axhline(0, color="k", linewidth=0.8, linestyle=":")
    ax1.axvline(0, color="k", linewidth=0.8, linestyle=":")
    ax2.plot(v, power_mw_cm2, "--", color="C3", label="Signed PV power")
    ax2.axhline(0, color="0.35", linewidth=0.8, linestyle=":")
    ax1.set_xlabel("Voltage (V)")
    ax1.set_ylabel("Current density (mA cm^-2)", color="C0")
    ax2.set_ylabel("Signed power density (mW cm^-2)", color="C3")
    ax1.tick_params(axis="y", colors="C0")
    ax2.tick_params(axis="y", colors="C3")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best")
    _stamp_axes(ax1, "source: latest Oghma jv.csv")
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _plot_pv_quadrant_power(v: np.ndarray, j_a_m2: np.ndarray, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pv_v, pv_power = _pv_quadrant_power_mw_cm2(v, j_a_m2)
    if len(pv_v) == 0:
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(pv_v, pv_power, "o-", color="C3", label="P = -V J")
    ax.axhline(0, color="k", linewidth=0.8, linestyle=":")
    ax.axvline(0, color="k", linewidth=0.8, linestyle=":")
    voc = float(pv_v[-1])
    ax.axvline(voc, color="0.35", linewidth=0.8, linestyle=":")
    ax.set_xlabel("Voltage (V)")
    ax.set_ylabel("Output power density (mW cm^-2)")
    ax.legend(loc="best")
    _stamp_axes(ax, "source: latest Oghma jv.csv, PV quadrant", x=0.01, y=0.99, ha="left", va="top")
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _pv_power_mw_cm2(v: np.ndarray, j_a_m2: np.ndarray) -> np.ndarray:
    """Signed PV power density from Oghma current convention.

    Oghma reports photocurrent as negative current density. Power output is
    therefore positive for the photovoltaic quadrant and negative once forward
    injection dominates after Voc. Do not clip by sign; the zero crossing is
    physically meaningful and should remain visible in plots.
    """
    v_arr = np.asarray(v, dtype=float)
    j_arr = np.asarray(j_a_m2, dtype=float)
    return -v_arr * j_arr * 0.1


def _pv_quadrant_power_mw_cm2(v: np.ndarray, j_a_m2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return P=-V*J from V=0 to interpolated Voc for output-power plots."""
    v_arr = np.asarray(v, dtype=float)
    j_arr = np.asarray(j_a_m2, dtype=float)
    order = np.argsort(v_arr)
    v_arr = v_arr[order]
    j_arr = j_arr[order]

    points: list[tuple[float, float]] = []
    if v_arr[0] <= 0.0 <= v_arr[-1]:
        points.append((0.0, 0.0))
    for voltage, current in zip(v_arr, j_arr):
        if voltage > 0.0 and current < 0.0:
            points.append((float(voltage), float(-voltage * current * 0.1)))
    for idx in range(1, len(v_arr)):
        left_j = j_arr[idx - 1]
        right_j = j_arr[idx]
        if v_arr[idx] >= 0.0 and left_j <= 0.0 <= right_j:
            denom = right_j - left_j
            voc = v_arr[idx] if denom == 0 else v_arr[idx - 1] - left_j * (v_arr[idx] - v_arr[idx - 1]) / denom
            if voc >= 0.0:
                points.append((float(voc), 0.0))
            break
    if not points:
        return np.array([], dtype=float), np.array([], dtype=float)
    dedup: dict[float, float] = {}
    for voltage, power in points:
        dedup[round(voltage, 12)] = power
    out_v = np.array(sorted(dedup), dtype=float)
    out_p = np.array([dedup[round(voltage, 12)] for voltage in out_v], dtype=float)
    return out_v, out_p


def _jump_ratio(values: np.ndarray) -> float:
    denom = max(float(np.nanmedian(np.abs(values))), 1e-300)
    return float(np.nanmax(np.abs(np.diff(values))) / denom) if len(values) > 1 else 0.0


def _plot_snapshot_family(rows: list[dict[str, Any]], out_dir: Path, prefix: str | tuple[str, ...], name: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    prefixes = (prefix,) if isinstance(prefix, str) else prefix
    selected = [r for r in rows if str(r["variable"]).startswith(prefixes)]
    if not selected:
        return
    by_var: dict[str, list[dict[str, Any]]] = {}
    for row in selected:
        by_var.setdefault(str(row["variable"]), []).append(row)
    fig, ax = plt.subplots(figsize=(6, 4))
    for var, vals in list(by_var.items())[:8]:
        vals = sorted(vals, key=lambda r: int(r["snapshot"]) if str(r["snapshot"]).isdigit() else 10**9)
        ax.plot([int(v["snapshot"]) for v in vals], [v["mean"] for v in vals], "o-", label=var)
    ax.set_xlabel("Snapshot index")
    ax.set_ylabel("Spatial mean")
    ax.legend(fontsize=8)
    _stamp_axes(ax, "source: latest Oghma snapshots")
    fig.tight_layout()
    fig.savefig(out_dir / name, dpi=160)
    plt.close(fig)


def run(step_dir: Path) -> None:
    out_dir = step_dir / "debug_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stack = _load_stack(step_dir)
    spectrum, optical_source_warnings = _load_optical_spectrum(step_dir)
    optical_warnings = _write_optical_outputs(out_dir, spectrum)
    time_rows, time_warnings = _write_time_outputs(step_dir, out_dir)

    parsed = parse_oghma_sim_info(step_dir / "sim" / "sim_info.dat") or {}
    jsc_curve = _interp_jsc_from_curve(step_dir)
    pce = parsed.get("pce_pct")
    voc = parsed.get("voc_V")
    ff = parsed.get("ff")
    jsc_reported = parsed.get("jsc_mA_cm2")
    pce_recomputed = abs(jsc_reported) * voc * ff if all(v is not None for v in (jsc_reported, voc, ff)) else None
    rel_err = abs(pce_recomputed - pce) / max(abs(pce), 1e-30) * 100.0 if pce and pce_recomputed is not None else None
    gen = _generation_sanity(step_dir, stack)

    sanity = {
        **gen,
        "Jsc_from_curve_mA_cm2": jsc_curve,
        "Jsc_reported_mA_cm2": jsc_reported,
        "Voc_V": voc,
        "FF": ff,
        "PCE_reported_pct": pce,
        "PCE_recomputed_pct": pce_recomputed,
        "relative_error_pct": rel_err,
    }
    report = _render_report(step_dir, spectrum, sanity, optical_source_warnings + optical_warnings, time_rows, time_warnings)
    (out_dir / "DEBUG_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(sanity, indent=2))


def _render_report(
    step_dir: Path,
    spectrum: dict[str, np.ndarray],
    sanity: dict[str, Any],
    optical_warnings: list[str],
    time_rows: list[dict[str, Any]],
    time_warnings: list[str],
) -> str:
    energy = spectrum["energy_eV"]
    wavelength = spectrum["wavelength_nm"]
    alpha = spectrum["alpha_cm1"]
    n = spectrum["n"]
    k = spectrum["k"]
    temporal_files = sorted({r["file"] for r in time_rows})
    units = sorted({str(r["units_inferred"]) for r in time_rows})
    lines = [
        "# OghmaNano Debug Report",
        "",
        "## Sanity check",
    ]
    for key, value in sanity.items():
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Optical spectrum",
        f"- Energy range: {np.nanmin(energy):.6g} to {np.nanmax(energy):.6g} eV",
        f"- Wavelength range: {np.nanmin(wavelength):.6g} to {np.nanmax(wavelength):.6g} nm",
        f"- alpha range: {np.nanmin(alpha):.6g} to {np.nanmax(alpha):.6g} cm^-1",
        f"- n range: {np.nanmin(n):.6g} to {np.nanmax(n):.6g}",
        f"- k range: {np.nanmin(k):.6g} to {np.nanmax(k):.6g}",
        f"- Eg marker: {EG_EV:.4f} eV",
        "- Warnings: " + ("; ".join(optical_warnings) if optical_warnings else "none"),
        "",
        "## Time dependent outputs",
        f"- Files found: {len(temporal_files)}",
        f"- Variables detected: {', '.join(sorted({Path(f).stem for f in temporal_files})[:40])}",
        f"- Units inferred: {', '.join(units) if units else 'none'}",
        "- Warnings: " + ("; ".join(time_warnings) if time_warnings else "none"),
        "",
        "## Files reviewed",
        f"- {step_dir / 'sim' / 'sim_info.dat'}",
        f"- {step_dir / 'sim' / 'jv.csv'}",
        f"- {step_dir / 'sim' / 'optical_output' / 'G_y.csv'}",
        f"- {step_dir / 'sim' / 'materials' / 'CsPbI3'}",
        f"- {step_dir / 'device_stack.json'}",
        "",
        "## Recommendations",
        "- Treat Oghma JV current columns and sim_info jsc as A/m^2 unless proven otherwise.",
        "- If optical warnings mention missing .npy files, regenerate them from the RPA dielectric CSV before rerunning Oghma.",
        "- If material CSV files are older than the optical .npy files, rerun Oghma preparation so CsPbI3/n.csv and alpha.csv are refreshed.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("calculations/alpha/14_oghma_device")
    run(arg)
