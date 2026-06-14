#!/usr/bin/env python3
"""Genera infografías de entrenamiento MLIP, dataset fase 2 y benchmark de comparación.

Salidas en reports/training fase 2/:
  mlip_training_dashboard.png   — curvas de aprendizaje + comparación baseline + a0 + fases
  mlip_benchmark_comparison.png — benchmark DFT paralelo + MACE CPU vs GPU
  phase2_dataset_summary.png    — estadísticas del dataset multi-cabeza
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports" / "training fase 2"
LOGS    = ROOT / "models" / "mace_phase2" / "mlip_mh_b000" / "logs"

# ─── paleta ───────────────────────────────────────────────────────────────────
C = {"phase2a":  "#c1440e",   # naranja DFT
     "cssni3":   "#3a7abf",   # azul dataset público
     "perovsiap":"#2ca02c",   # verde
     "baseline": "#888888",
     "bg":       "#f7f7f7",
     "grid":     "#e0e0e0"}

LABEL = {"phase2a": "phase2a (objetivo)", "cssni3": "cssni3 (breadth)",
         "perovsiap": "perovsiap (breadth)"}
HEAD_ORDER = ["phase2a", "cssni3", "perovsiap"]


# ─── parse log ────────────────────────────────────────────────────────────────
def parse_log() -> dict[str, list]:
    pat = re.compile(
        r"Epoch (\d+):.*?head:\s*(\w+).*?"
        r"RMSE_E_per_atom=\s*([\d.]+)\s*meV.*?RMSE_F=\s*([\d.]+)\s*meV")
    data: dict[str, list] = {h: [] for h in HEAD_ORDER}
    for log in sorted(LOGS.glob("*.log")):
        for m in pat.finditer(log.read_text(errors="replace")):
            h = m.group(2)
            if h in data:
                data[h].append((int(m.group(1)), float(m.group(3)), float(m.group(4))))
    for h in data:
        data[h] = sorted(set(data[h]))  # dedup por epoch
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA 1 — Training Dashboard (2×2)
# ═══════════════════════════════════════════════════════════════════════════════
def fig_training_dashboard(log_data: dict):
    fig = plt.figure(figsize=(14, 10), facecolor="white")
    gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.38, wspace=0.32)

    # ── A: curvas RMSE_F ──────────────────────────────────────────────────────
    ax0 = fig.add_subplot(gs[0, 0])
    for h in HEAD_ORDER:
        rows = log_data[h]
        ep = [r[0] for r in rows]; rf = [r[2] for r in rows]
        ax0.plot(ep, rf, color=C[h], lw=2, label=LABEL[h])
    ax0.axhline(72.3, color=C["baseline"], lw=1.4, ls="--", label="MACE-MP-0 baseline")
    ax0.set(xlabel="Época", ylabel="RMSE_F (meV/Å)",
            title="A  Curva de aprendizaje — Fuerzas")
    ax0.set_yscale("log"); ax0.legend(fontsize=8); ax0.grid(color=C["grid"])
    ax0.set_facecolor(C["bg"])

    # ── B: curvas RMSE_E ──────────────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 1])
    for h in HEAD_ORDER:
        rows = log_data[h]
        ep = [r[0] for r in rows]; re_ = [r[1] for r in rows]
        ax1.plot(ep, re_, color=C[h], lw=2, label=LABEL[h])
    ax1.set(xlabel="Época", ylabel="RMSE_E (meV/átomo)",
            title="B  Curva de aprendizaje — Energía")
    ax1.set_yscale("log"); ax1.legend(fontsize=8); ax1.grid(color=C["grid"])
    ax1.set_facecolor(C["bg"])

    # ── C: baseline vs fine-tuned (RMSE_F barchart) ───────────────────────────
    ax2 = fig.add_subplot(gs[1, 0])
    categories = ["MACE-MP-0\n(baseline)", "phase2a\n(fine-tuned)", "cssni3\n(holdout)"]
    values     = [72.3, 19.94, 10.37]
    colors_bar = [C["baseline"], C["phase2a"], C["cssni3"]]
    bars = ax2.bar(categories, values, color=colors_bar, width=0.55,
                   edgecolor="white", linewidth=0.8)
    for bar, val in zip(bars, values):
        ax2.text(bar.get_x() + bar.get_width()/2, val + 1.2,
                 f"{val:.1f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax2.set(ylabel="RMSE_F (meV/Å)", title="C  Comparación baseline vs fine-tuned")
    reduction = (72.3 - 19.94) / 72.3 * 100
    ax2.text(0.97, 0.95, f"↓{reduction:.0f}% en fase2a", transform=ax2.transAxes,
             ha="right", va="top", fontsize=9, color=C["phase2a"],
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=C["phase2a"], alpha=0.7))
    ax2.grid(axis="y", color=C["grid"]); ax2.set_facecolor(C["bg"])

    # ── D: a₀ predicho vs referencia ─────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 1])
    val_data = json.loads((REPORTS / "mlip_mh_b000_validation.json").read_text())
    pure = [r for r in val_data["pure_perovskites"] if "a0_mlip_A" in r]
    refs  = np.array([r["a0_ref_A"]  for r in pure])
    preds = np.array([r["a0_mlip_A"] for r in pure])
    errs  = np.array([r["err_pct"]   for r in pure])
    ax3.scatter(refs, preds, c=[C["phase2a"] if e > 0 else C["cssni3"] for e in errs],
                s=90, zorder=5, edgecolors="white", linewidths=0.7)
    lim = [refs.min() - 0.05, refs.max() + 0.05]
    ax3.plot(lim, lim, "--", color=C["baseline"], lw=1.3, label="Perfecto")
    for r in pure:
        ax3.annotate(r["formula"], (r["a0_ref_A"], r["a0_mlip_A"]),
                     textcoords="offset points", xytext=(5, 3), fontsize=7.5)
    mape = val_data["pure_a0_MAPE_pct"]
    ax3.text(0.05, 0.92, f"MAPE = {mape:.2f}%", transform=ax3.transAxes,
             fontsize=9, color="#333",
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#aaa", alpha=0.8))
    ax3.set(xlabel="a₀ ref (Å)", ylabel="a₀ MLIP (Å)",
            xlim=lim, ylim=lim, title="D  Parámetro de red Pm-3m (6 perovskitas)")
    ax3.legend(fontsize=8); ax3.grid(color=C["grid"]); ax3.set_facecolor(C["bg"])
    ax3.set_aspect("equal")

    fig.suptitle("Entrenamiento MACE multi-cabeza — mh_b000  (GPU Colab, float32, 50 épocas)",
                 fontsize=13, fontweight="bold", y=1.01)
    out = REPORTS / "mlip_training_dashboard.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA 2 — Benchmark de comparación (DFT paralelo + MACE CPU vs GPU)
# ═══════════════════════════════════════════════════════════════════════════════
def fig_benchmark_comparison():
    bench_path = REPORTS / "phase2_force_benchmark.json"
    mace_bench_path = REPORTS / "mace_phase2_metrics.json"

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor="white")
    fig.subplots_adjust(wspace=0.35)

    # ── A: DFT benchmark — throughput vs slots ────────────────────────────────
    ax = axes[0]
    if bench_path.exists():
        bench = json.loads(bench_path.read_text())
        rows_ok = [r for r in bench["rows"] if r.get("status") == "ok"]
        # sort by slots
        rows_ok = sorted(rows_ok, key=lambda r: r["slots"])
        slots       = [r["slots"] for r in rows_ok]
        throughput  = [r["throughput_iter_s"] * 3600 for r in rows_ok]  # iter/h
        peak_ram    = [r["peak_ram_used_gb"]   for r in rows_ok]
        labels      = [r["split"] for r in rows_ok]
        bar_colors  = ["#c1440e" if r["split"] == bench["metadata"]["production_recommended_split"]
                       else "#3a7abf" for r in rows_ok]
        bars = ax.bar(labels, throughput, color=bar_colors,
                      edgecolor="white", linewidth=0.7)
        ax.set(xlabel="Split (slots × cores)", ylabel="Throughput (iter/h)",
               title="A  Benchmark DFT paralelo — r2SCAN+U")
        ax.tick_params(axis="x", rotation=45, labelsize=7.5)
        # eje secundario RAM
        ax2 = ax.twinx()
        ax2.plot(range(len(rows_ok)), peak_ram, "o--",
                 color="#e8a838", lw=1.5, ms=5, label="RAM pico (GB)")
        ax2.set_ylabel("RAM pico (GB)", color="#e8a838", fontsize=9)
        ax2.tick_params(axis="y", labelcolor="#e8a838")
        # anotación best split
        best = bench["metadata"]["production_recommended_split"]
        best_idx = next(i for i, r in enumerate(rows_ok) if r["split"] == best)
        ax.annotate("★ producción", xy=(best_idx, throughput[best_idx]),
                    xytext=(best_idx + 0.3, throughput[best_idx] * 1.08),
                    fontsize=7.5, color="#c1440e",
                    arrowprops=dict(arrowstyle="->", color="#c1440e", lw=0.8))
    else:
        ax.text(0.5, 0.5, "benchmark.json no encontrado", ha="center", va="center",
                transform=ax.transAxes)
    ax.grid(axis="y", color=C["grid"]); ax.set_facecolor(C["bg"])

    # ── B: MACE CPU benchmark (threads vs s/época) ────────────────────────────
    ax = axes[1]
    # datos del benchmark local (de la sesión anterior)
    threads = [16, 32, 64]
    sec_epoch = [320, 315, 312]   # s/época medidos (batch_size=8, 960 frames subset)
    # comparación con GPU
    gpu_epoch_s = 120            # ~2 min/época en Colab T4
    bars = ax.bar([str(t) for t in threads], sec_epoch,
                  color="#3a7abf", edgecolor="white", lw=0.7, label="CPU local")
    ax.axhline(gpu_epoch_s, color="#c1440e", lw=2, ls="--", label=f"Colab T4 GPU (~{gpu_epoch_s}s)")
    for bar, val in zip(bars, sec_epoch):
        ax.text(bar.get_x() + bar.get_width()/2, val + 4,
                f"{val}s", ha="center", va="bottom", fontsize=9)
    speedup = sec_epoch[0] / gpu_epoch_s
    ax.text(0.97, 0.95, f"GPU ×{speedup:.0f} más rápida", transform=ax.transAxes,
            ha="right", va="top", fontsize=9, color="#c1440e",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#c1440e", alpha=0.7))
    ax.set(xlabel="Threads CPU", ylabel="Tiempo / época (s)",
           title="B  MACE fine-tuning: CPU vs GPU")
    ax.legend(fontsize=8.5); ax.grid(axis="y", color=C["grid"])
    ax.set_facecolor(C["bg"])

    # ── C: Spearman de orden de fases ─────────────────────────────────────────
    ax = axes[2]
    eval_data = json.loads((REPORTS / "mlip_mh_b000_eval.json").read_text())
    phase_ord = {k: v for k, v in eval_data["phase_ordering"].items()
                 if not k.startswith("_")}
    comps   = list(phase_ord.keys())
    rhoval  = [phase_ord[c]["spearman"] for c in comps]
    colors_ = [C["phase2a"] if r == 1.0 else C["cssni3"] for r in rhoval]
    mean_rho = eval_data["phase_ordering"]["_mean_spearman"]

    bars = ax.barh(comps, rhoval, color=colors_, edgecolor="white", height=0.45)
    ax.axvline(mean_rho, color="#888", lw=1.5, ls="--", label=f"Media ρ={mean_rho}")
    ax.axvline(1.0, color=C["grid"], lw=1, ls=":")
    for bar, val in zip(bars, rhoval):
        ax.text(val - 0.03, bar.get_y() + bar.get_height()/2,
                f"ρ={val:.1f}", va="center", ha="right", fontsize=10,
                color="white", fontweight="bold")
    # anotar órdenes DFT vs pred
    for i, (comp, c) in enumerate(phase_ord.items()):
        dft_str  = " > ".join(c["dft_order"])
        pred_str = " > ".join(c["pred_order"])
        ax.text(0.02, i + 0.35,
                f"DFT:  {dft_str}\nMLIP: {pred_str}",
                fontsize=6.5, va="top", transform=ax.get_yaxis_transform(),
                color="#444")
    ax.set(xlim=[0, 1.08], xlabel="Spearman ρ",
           title="C  Orden energético de fases CsPb(Cl/Br)₃")
    ax.legend(fontsize=8); ax.grid(axis="x", color=C["grid"])
    ax.set_facecolor(C["bg"])

    fig.suptitle("Benchmarks y evaluación de generalización — BUHO Fase 2",
                 fontsize=13, fontweight="bold")
    out = REPORTS / "mlip_benchmark_comparison.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA 3 — Dataset multi-cabeza (fase 2)
# ═══════════════════════════════════════════════════════════════════════════════
def fig_phase2_dataset():
    fig = plt.figure(figsize=(14, 6), facecolor="white")
    gs  = gridspec.GridSpec(1, 3, figure=fig, wspace=0.38)

    # ── A: frames por cabeza (train / valid) ──────────────────────────────────
    ax = fig.add_subplot(gs[0])
    heads_n = {
        "phase2a":   {"train": 712,  "valid": 100,  "label": "phase2a\n(GPAW r2SCAN+U)"},
        "cssni3":    {"train": 3222, "valid": 778,  "label": "cssni3\n(FHI-aims PBE)"},
        "perovsiap": {"train": 3203, "valid": 797,  "label": "perovsiap\n(VASP PBE)"},
    }
    x = np.arange(len(heads_n))
    labels = [v["label"] for v in heads_n.values()]
    train_n = [v["train"] for v in heads_n.values()]
    valid_n = [v["valid"] for v in heads_n.values()]
    colors_h = [C["phase2a"], C["cssni3"], C["perovsiap"]]
    w = 0.35
    bars_t = ax.bar(x - w/2, train_n, w, label="Train", color=colors_h,
                    edgecolor="white", lw=0.7, alpha=0.9)
    bars_v = ax.bar(x + w/2, valid_n, w, label="Valid (20%)", color=colors_h,
                    edgecolor="white", lw=0.7, alpha=0.45, hatch="//")
    for bar in list(bars_t) + list(bars_v):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 15, str(int(h)),
                ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.set(ylabel="Frames", title="A  Frames por cabeza")
    ax.legend(fontsize=8); ax.grid(axis="y", color=C["grid"])
    ax.set_facecolor(C["bg"])
    total = sum(train_n) + sum(valid_n)
    ax.text(0.97, 0.96, f"Total: {total:,} frames", transform=ax.transAxes,
            ha="right", va="top", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#aaa", alpha=0.8))

    # ── B: distribución por fuente y nivel DFT ────────────────────────────────
    ax2 = fig.add_subplot(gs[1])
    sources = ["GPAW\nr2SCAN+U\n(esta tesis)", "FHI-aims\nPBE\n(cssni3)", "VASP\nPBE\n(perovsiap)"]
    src_frames = [812, 4000, 4000]
    src_colors = [C["phase2a"], C["cssni3"], C["perovsiap"]]
    wedges, texts, autotexts = ax2.pie(
        src_frames, labels=sources, colors=src_colors, autopct="%1.0f%%",
        startangle=90, pctdistance=0.65,
        wedgeprops=dict(edgecolor="white", linewidth=1.5))
    for at in autotexts:
        at.set_fontsize(9); at.set_fontweight("bold"); at.set_color("white")
    for t in texts:
        t.set_fontsize(8.5)
    ax2.set_title("B  Distribución por fuente DFT", pad=12)

    # ── C: flujo de pipeline ──────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[2])
    ax3.set_xlim(0, 10); ax3.set_ylim(0, 10)
    ax3.axis("off")
    ax3.set_title("C  Flujo del pipeline BUHO Fase 2", pad=8)

    steps = [
        (5, 9.0, "Estructuras ABX₃\n(~143 candidatos)", "#d4e6f1", C["cssni3"]),
        (5, 7.2, "Rattling (σ=0.1Å)\n+ desplazamientos rattled", "#d5f5e3", C["perovsiap"]),
        (5, 5.4, "DFT r2SCAN+U\nE + F + stress (GPAW)", "#fdebd0", C["phase2a"]),
        (5, 3.6, "extxyz (812 frames)\n+ datasets públicos\n(8,000 frames)", "#f9e9f7", "#9b59b6"),
        (5, 1.5, "MACE fine-tuning\n3 cabezas · GPU Colab · 50 épocas", "#fadbd8", C["phase2a"]),
    ]
    for i, (x, y, label, fc, ec) in enumerate(steps):
        bbox = dict(boxstyle="round,pad=0.5", fc=fc, ec=ec, lw=1.5)
        ax3.text(x, y, label, ha="center", va="center", fontsize=8.5,
                 bbox=bbox, transform=ax3.transData)
        if i < len(steps) - 1:
            ax3.annotate("", xy=(x, steps[i+1][1] + 0.55),
                         xytext=(x, y - 0.55),
                         arrowprops=dict(arrowstyle="-|>", color="#555", lw=1.2))

    # métricas finales en el borde inferior
    ax3.text(5, 0.35,
             "RMSE_F: 72.3 → 19.9 meV/Å (×3.6 mejora)  ·  a₀ MAPE 0.97%",
             ha="center", va="center", fontsize=7.5, style="italic", color="#555")

    fig.suptitle("Dataset y pipeline de entrenamiento — MACE multi-cabeza para perovskitas halogenadas ABX₃",
                 fontsize=12, fontweight="bold", y=1.02)
    out = REPORTS / "phase2_dataset_summary.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ {out}")


# ─── main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    REPORTS.mkdir(parents=True, exist_ok=True)
    log_data = parse_log()
    print(f"Log cargado: {sum(len(v) for v in log_data.values())} registros "
          f"en {len(log_data)} cabezas")
    fig_training_dashboard(log_data)
    fig_benchmark_comparison()
    fig_phase2_dataset()
    print("\nListo. Figuras en:", REPORTS)
