#!/usr/bin/env python3
"""Crea el tablero visual inicial para Fase 2 / MACE fine-tune.

La carpeta de salida es documental mientras no existan datos DFT con fuerzas/stress.
Las graficas que requieren entrenamiento MACE se generan como placeholders explicitos
para evitar reportar metricas inventadas.
"""
from __future__ import annotations

import json
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "training fase 2"
CURVE = ROOT / "models" / "surrogate_energy_learning_curve.csv"
STATE = ROOT / "data" / "batches" / "orchestrator_state.json"
DPI = 180

COLOR_MAIN = "#2F6F73"
COLOR_ACCENT = "#B85750"
COLOR_OK = "#2E8B57"
COLOR_PENDING = "#8A8F98"
COLOR_WARN = "#C58B19"
COLOR_BG = "#F7F7F5"

EXPECTED_ARTIFACTS = {
    "dataset_mace": "data/mace_finetune/phase2_seed.extxyz",
    "splits": "data/mace_finetune/splits.json",
    "metrics": "reports/training fase 2/mace_phase2_metrics.json",
    "model": "models/mace_phase2_finetuned.model",
    "phase_outputs": "runs/phase2_mace/{candidate_id}/{phase}/relaxed.cif, relax.log, metrics.json",
}

FIGURES = [
    ("mace_phase2_dashboard", "Resumen operativo Fase 2", "phase1_context"),
    ("dataset_coverage", "Cobertura de dataset", "phase1_context"),
    ("phase_candidate_funnel", "Embudo candidatos a estructuras", "planned_placeholder"),
    ("mace_baseline_benchmark", "Baseline MACE-MP-0", "pending_mace_data"),
    ("training_loss", "Loss train/validation MACE", "pending_mace_data"),
    ("energy_parity", "Paridad energia DFT vs MACE", "pending_mace_data"),
    ("force_parity", "Paridad fuerzas DFT vs MACE", "pending_mace_data"),
    ("force_residuals", "Residuales de fuerza", "pending_mace_data"),
    ("stress_parity", "Paridad stress DFT vs MACE", "pending_mace_data"),
    ("phase_ranking_accuracy", "Acierto de ranking de fases", "pending_mace_data"),
    ("relaxation_stability", "Estabilidad de relajaciones", "pending_mace_data"),
    ("learning_curve", "MAE vs estructuras etiquetadas", "pending_mace_data"),
    ("benchmark_runtime", "Benchmark runtime MACE vs DFT", "pending_mace_data"),
]


def ensure_out() -> None:
    OUT.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _coerce_curve_value(key: str, value: str) -> Any:
    if key in {"batch", "n_total", "n_train", "n_test", "new_candidates"}:
        return int(float(value))
    if key in {"train_mae", "test_mae", "train_rmse", "test_rmse", "overfit_ratio"}:
        return float(value)
    return value


def load_curve() -> list[dict[str, Any]]:
    if not CURVE.exists():
        return []
    with CURVE.open(newline="", encoding="utf-8") as handle:
        return [
            {key: _coerce_curve_value(key, value) for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def load_state() -> dict[str, Any]:
    if not STATE.exists():
        return {}
    return json.loads(STATE.read_text(encoding="utf-8"))


def load_phase2_metrics() -> dict[str, Any]:
    path = OUT / "mace_phase2_metrics.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_phase2_selection() -> dict[str, Any]:
    path = ROOT / "data" / "mace_finetune" / "phase2_batches.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def phase1_context() -> dict[str, Any]:
    curve = load_curve()
    state = load_state()
    batches = state.get("batches_finalized", [0, 1, 2, 3, 4])
    context: dict[str, Any] = {
        "batches_finalized": batches,
        "dft_continuous_converged": 2508,
        "dft_continuous_failed": 0,
        "surrogate_dataset_points": 3008,
        "stop_reason": state.get("reason", "convergencia (test_mae estancado 2 batches)"),
        "final_test_mae_eV_atom": 0.01604,
        "final_overfit_ratio": 1.021,
        "real_mace_metrics_available": False,
        "mace_training_status": "not_started",
    }
    phase2 = load_phase2_metrics().get("phase2_dft_labels", {})
    if phase2:
        context["phase2_dft_labels"] = phase2
    selection = load_phase2_selection()
    if selection:
        context["phase2_selection"] = selection
    if curve:
        final = curve[-1]
        continuous = sum(row["new_candidates"] for row in curve if row["batch"] >= 0)
        context.update(
            {
                "batches_finalized": [int(v) for v in batches],
                "dft_continuous_converged": int(continuous),
                "surrogate_dataset_points": int(final["n_total"]),
                "final_test_mae_eV_atom": float(final["test_mae"]),
                "final_overfit_ratio": float(final["overfit_ratio"]),
                "learning_curve_source": rel(CURVE),
                "last_surrogate_update": str(final.get("ts", "")),
            }
        )
    return context


def save_fig(fig: plt.Figure, stem: str) -> None:
    ensure_out()
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"{stem}.{ext}", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def style_axes(ax: plt.Axes) -> None:
    ax.grid(alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def add_pending_box(ax: plt.Axes, title: str, message: str, subtitle: str | None = None) -> None:
    ax.set_facecolor(COLOR_BG)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(0.5, 0.64, title, ha="center", va="center", fontsize=16, weight="bold")
    ax.text(0.5, 0.48, message, ha="center", va="center", fontsize=11, wrap=True)
    if subtitle:
        ax.text(0.5, 0.34, subtitle, ha="center", va="center", fontsize=9, color="#555555", wrap=True)


def plot_dashboard(context: dict[str, Any]) -> None:
    fig = plt.figure(figsize=(12, 7.2), facecolor="white")
    gs = fig.add_gridspec(2, 2, hspace=0.35, wspace=0.25)

    ax = fig.add_subplot(gs[0, 0])
    ax.axis("off")
    ax.set_title("Cierre Fase 1 -> arranque Fase 2", loc="left", weight="bold")
    stop_reason = context["stop_reason"].replace(" (", "\n(")
    rows = [
        ("Batches finalizados", ", ".join(map(str, context["batches_finalized"]))),
        ("DFT continuo", f"{context['dft_continuous_converged']}/{context['dft_continuous_converged']} conv., 0 fallidos"),
        ("Dataset surrogate", f"{context['surrogate_dataset_points']} puntos"),
        ("Stop", stop_reason),
        ("test_mae final", f"{context['final_test_mae_eV_atom']:.5f} eV/atomo"),
        ("overfit_ratio", f"{context['final_overfit_ratio']:.3f}"),
    ]
    y = 0.9
    for key, value in rows:
        ax.text(0.02, y, key, fontsize=10, color="#555555", va="top")
        ax.text(0.42, y, value, fontsize=10.5, weight="bold", va="top")
        y -= 0.16 if "\n" in value else 0.13
    ax.text(
        0.02,
        0.08,
        "Nota: Fase 1 son single-points cubicos sin fuerzas/stress; no entrenan MACE directamente.",
        fontsize=9.5,
        color=COLOR_ACCENT,
        wrap=True,
    )

    ax = fig.add_subplot(gs[0, 1])
    steps = [
        "MACE-MP-0\nbaseline",
        "shortlist\ndiversa",
        "fases y\npolimorfos",
        "DFT\nE+F+stress",
        "fine-tune\nMACE",
        "validacion\nestructural",
        "fase estable\nantes DFT caro",
    ]
    x = list(range(len(steps)))
    yline = [1] * len(steps)
    ax.plot(x, yline, color=COLOR_MAIN, lw=2, alpha=0.7)
    ax.scatter(x, yline, s=260, color=[COLOR_OK] + [COLOR_PENDING] * (len(steps) - 1), zorder=3)
    for i, label in enumerate(steps):
        ax.text(i, 1.12 if i % 2 == 0 else 0.82, label, ha="center", va="center", fontsize=8.5)
    ax.set_ylim(0.65, 1.35)
    ax.set_xlim(-0.4, len(steps) - 0.6)
    ax.axis("off")
    ax.set_title("Plan operativo", loc="left", weight="bold")

    ax = fig.add_subplot(gs[1, 0])
    artifact_names = ["seed.extxyz", "splits.json", "metrics.json", "model", "phase outputs"]
    ready = [
        (ROOT / "data" / "mace_finetune" / "phase2_seed.extxyz").exists(),
        (ROOT / "data" / "mace_finetune" / "splits.json").exists(),
        (OUT / "mace_phase2_metrics.json").exists(),
        (ROOT / "models" / "mace_phase2_finetuned.model").exists(),
        (ROOT / "runs" / "phase2_mace").exists(),
    ]
    colors = [COLOR_OK if item else COLOR_PENDING for item in ready]
    ax.barh(artifact_names, [1] * len(artifact_names), color=colors)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("Contrato de artefactos", loc="left", weight="bold")
    for i, item in enumerate(ready):
        ax.text(0.5, i, "listo" if item else "pendiente", ha="center", va="center", color="white", weight="bold")
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax = fig.add_subplot(gs[1, 1])
    metrics = ["energia", "fuerzas", "stress", "ranking fases", "runtime"]
    values = [0, 0, 0, 0, 0]
    ax.bar(metrics, values, color=COLOR_PENDING)
    ax.set_ylim(0, 1)
    ax.set_ylabel("metricas reales MACE")
    ax.set_title("Estado de metricas Fase 2", loc="left", weight="bold")
    ax.text(0.5, 0.55, "Sin datos reales de MACE aun", transform=ax.transAxes, ha="center", weight="bold")
    ax.text(
        0.5,
        0.40,
        "Se llenara despues de etiquetar estructuras DFT\ncon energia, fuerzas y stress.",
        transform=ax.transAxes,
        ha="center",
        fontsize=9,
        color="#555555",
    )
    style_axes(ax)
    fig.suptitle("Fase 2 - MACE fine-tune estructura-consciente", fontsize=15, weight="bold")
    save_fig(fig, "mace_phase2_dashboard")


def plot_dataset_coverage(context: dict[str, Any]) -> None:
    phase2 = context.get("phase2_dft_labels", {})
    n_phase = int(phase2.get("n_unique_candidates", 0) or 0)
    n_forces = int(phase2.get("n_with_forces", 0) or 0)
    n_stress = int(phase2.get("n_with_stress", 0) or 0)
    splits_ready = 1 if (ROOT / "data" / "mace_finetune" / "splits.json").exists() else 0
    labels = [
        "Fase 1\ncomposicion",
        "fase etiquetada",
        "DFT con fuerzas",
        "DFT con stress",
        "splits MACE",
    ]
    values = [context["surrogate_dataset_points"], n_phase, n_forces, n_stress, splits_ready]
    fig, ax = plt.subplots(figsize=(8.5, 5.1))
    bars = ax.bar(labels, values, color=[COLOR_MAIN] + [COLOR_PENDING] * 4)
    ax.set_ylabel("estructuras / puntos disponibles")
    ax.set_title("Cobertura de datos para Fase 2")
    style_axes(ax)
    for bar, value in zip(bars, values):
        text = f"{int(value)}" if value else "pendiente"
        ax.text(bar.get_x() + bar.get_width() / 2, max(value, 1) * 1.01, text, ha="center", va="bottom", fontsize=9)
    ax.text(
        0.02,
        0.92,
        "Solo la primera barra es dato real actual; las demas requieren etiquetas E+F+stress.",
        transform=ax.transAxes,
        fontsize=9,
        color=COLOR_ACCENT,
    )
    save_fig(fig, "dataset_coverage")


def plot_phase_candidate_funnel(context: dict[str, Any]) -> None:
    phase2 = context.get("phase2_dft_labels", {})
    selected = ROOT / "data" / "mace_finetune" / "phase2_candidates_1000.csv"
    n_selected = 1000 if selected.exists() else 0
    n_labeled = int(phase2.get("n_unique_candidates", 0) or 0)
    n_labels = int(phase2.get("n_labels", 0) or 0)
    stages = [
        ("dataset surrogate", context["surrogate_dataset_points"], COLOR_MAIN),
        ("shortlist diversa", n_selected, COLOR_OK if n_selected else COLOR_PENDING),
        ("fases/polimorfos", 0, COLOR_PENDING),
        ("DFT E+F+stress", n_labels, COLOR_OK if n_labels else COLOR_PENDING),
        ("train/test MACE", n_labeled, COLOR_OK if n_labeled else COLOR_PENDING),
    ]
    widths = [1.0, 0.78, 0.58, 0.38, 0.22]
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(stages))
    ax.axis("off")
    for i, ((label, value, color), width) in enumerate(zip(stages, widths)):
        y = len(stages) - i - 0.8
        x0 = (1 - width) / 2
        rect = plt.Rectangle((x0, y), width, 0.55, color=color, alpha=0.92)
        ax.add_patch(rect)
        value_txt = str(value) if value else "pendiente"
        ax.text(0.5, y + 0.28, f"{label}: {value_txt}", ha="center", va="center", color="white", weight="bold")
    ax.set_title("Embudo de Fase 2: candidatos -> fases -> etiquetas -> splits", weight="bold")
    ax.text(0.5, 0.25, "Los conteos pendientes se llenaran con el generador de fases y DFT E+F+stress.", ha="center", fontsize=9)
    save_fig(fig, "phase_candidate_funnel")


def plot_placeholder(stem: str, title: str, message: str, subtitle: str | None = None) -> None:
    fig, ax = plt.subplots(figsize=(7.8, 4.8))
    add_pending_box(ax, title, message, subtitle)
    save_fig(fig, stem)


def plot_baseline_benchmark() -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    metrics = ["E MAE", "F MAE", "stress MAE", "relax fmax", "ranking"]
    ax.bar(metrics, [0, 0, 0, 0, 0], color=COLOR_PENDING)
    ax.set_ylim(0, 1)
    ax.set_ylabel("metricas reales")
    ax.set_title("Baseline MACE-MP-0 antes del fine-tune")
    ax.text(0.5, 0.55, "Pendiente de baseline sobre estructuras etiquetadas", transform=ax.transAxes, ha="center", weight="bold")
    ax.text(
        0.5,
        0.40,
        "No se reporta speedup ni error hasta tener DFT con energia, fuerzas y stress.",
        transform=ax.transAxes,
        ha="center",
        fontsize=9,
        color="#555555",
    )
    style_axes(ax)
    save_fig(fig, "mace_baseline_benchmark")


def plot_training_loss() -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_xlabel("epoch")
    ax.set_ylabel("loss MACE")
    ax.set_title("Fine-tune MACE: loss train/validation")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 1)
    style_axes(ax)
    ax.text(0.5, 0.55, "Pendiente: no hay corrida de fine-tune", transform=ax.transAxes, ha="center", weight="bold")
    ax.text(0.5, 0.43, "Se graficara train/valid cuando exista el log de entrenamiento.", transform=ax.transAxes, ha="center", fontsize=9)
    save_fig(fig, "training_loss")


def plot_parity(stem: str, title: str, xlabel: str, ylabel: str, subtitle: str) -> None:
    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    ax.plot([0, 1], [0, 1], ls="--", color="#333333", lw=1.5, label="paridad")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(frameon=False)
    style_axes(ax)
    ax.text(0.5, 0.52, "Sin datos reales aun", transform=ax.transAxes, ha="center", weight="bold")
    ax.text(0.5, 0.42, subtitle, transform=ax.transAxes, ha="center", fontsize=9, color="#555555")
    save_fig(fig, stem)


def plot_force_residuals() -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_xlabel("residuo fuerza: MACE - DFT (eV/A)")
    ax.set_ylabel("frecuencia")
    ax.set_title("Distribucion de errores de fuerza")
    ax.set_xlim(-1, 1)
    ax.set_ylim(0, 1)
    style_axes(ax)
    ax.text(0.5, 0.55, "Pendiente de etiquetas de fuerzas DFT", transform=ax.transAxes, ha="center", weight="bold")
    ax.text(0.5, 0.43, "No se simula ninguna distribucion hasta tener datos reales.", transform=ax.transAxes, ha="center", fontsize=9)
    save_fig(fig, "force_residuals")


def plot_phase_ranking_accuracy() -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["top-1 fase", "top-2 dentro", "Kendall tau", "DeltaE estable"]
    ax.bar(labels, [0, 0, 0, 0], color=COLOR_PENDING)
    ax.set_ylim(0, 1)
    ax.set_ylabel("score / exactitud")
    ax.set_title("Acierto del orden relativo de fases")
    style_axes(ax)
    ax.text(0.5, 0.55, "Pendiente: se requiere conjunto con multiples fases por candidato", transform=ax.transAxes, ha="center", weight="bold")
    ax.text(0.5, 0.43, "El objetivo es elegir fase estable antes del DFT caro.", transform=ax.transAxes, ha="center", fontsize=9)
    save_fig(fig, "phase_ranking_accuracy")


def plot_relaxation_stability() -> None:
    fig, ax = plt.subplots(figsize=(8.2, 5))
    phases = ["Pm-3m", "tetragonal", "ortorrombica", "delta", "Glazer"]
    ax.bar(phases, [0, 0, 0, 0, 0], color=COLOR_PENDING)
    ax.axhline(0.05, color=COLOR_WARN, ls="--", lw=1.8, label="target fmax < 0.05 eV/A")
    ax.set_ylim(0, 0.12)
    ax.set_ylabel("fmax final (eV/A)")
    ax.set_title("Convergencia y estabilidad de relajaciones")
    ax.legend(frameon=False)
    style_axes(ax)
    ax.text(0.5, 0.60, "Pendiente de relajaciones por fase", transform=ax.transAxes, ha="center", weight="bold")
    ax.text(0.5, 0.48, "La linea punteada es criterio objetivo, no resultado medido.", transform=ax.transAxes, ha="center", fontsize=9)
    save_fig(fig, "relaxation_stability")


def plot_learning_curve(context: dict[str, Any]) -> None:
    curve = load_curve()
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.set_xlabel("estructuras etiquetadas E+F+stress")
    ax.set_ylabel("MAE MACE")
    ax.set_title("Curva de aprendizaje Fase 2")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    style_axes(ax)
    ax.text(0.5, 0.63, "Pendiente de dataset MACE", transform=ax.transAxes, ha="center", weight="bold")
    ax.text(0.5, 0.51, "Se reportara MAE vs numero de estructuras etiquetadas.", transform=ax.transAxes, ha="center", fontsize=9)
    if curve:
        final = curve[-1]
        ax.text(
            0.5,
            0.33,
            f"Contexto Fase 1: surrogate composicional cerro en test_mae={float(final['test_mae']):.5f} eV/atomo con n={int(final['n_total'])}.",
            transform=ax.transAxes,
            ha="center",
            fontsize=9,
            color=COLOR_ACCENT,
        )
    save_fig(fig, "learning_curve")


def plot_benchmark_runtime() -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["DFT 5x8\nmedido", "MACE relax\npendiente", "speedup\npendiente"]
    values = [0.749, 0, 0]
    bars = ax.bar(labels, values, color=[COLOR_MAIN, COLOR_PENDING, COLOR_PENDING])
    ax.set_ylabel("throughput / speedup reportado")
    ax.set_title("Costo MACE vs DFT")
    style_axes(ax)
    ax.text(bars[0].get_x() + bars[0].get_width() / 2, values[0] + 0.02, "0.749 iter/s", ha="center", va="bottom", fontsize=9)
    ax.text(0.58, 0.62, "Solo el throughput DFT es dato real actual.", transform=ax.transAxes, ha="center", weight="bold")
    ax.text(0.58, 0.50, "El speedup MACE se llenara tras baseline/relax benchmark.", transform=ax.transAxes, ha="center", fontsize=9)
    save_fig(fig, "benchmark_runtime")


def write_metrics(context: dict[str, Any]) -> None:
    existing = load_phase2_metrics()
    metrics = {
        "status": "not_trained",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "MACE-MP-0 foundation; phase2 fine-tune pending",
        "real_mace_metrics_available": False,
        "reason": "Fase 1 single-points do not include forces/stress and cannot directly train MACE.",
        "phase1_context": context,
        "expected_artifacts": EXPECTED_ARTIFACTS,
        "acceptance_targets": {
            "energy_mae_eV_atom": "TBD after baseline",
            "force_mae_eV_A": "TBD after baseline",
            "stress_mae": "TBD if stress labels are available",
            "relaxation_fmax_eV_A": "< 0.05 target for relaxed structures",
            "phase_ranking": "stable phase selected before expensive DFT",
        },
        "phase2_dft_labels": existing.get("phase2_dft_labels", context.get("phase2_dft_labels", {})),
        "reported_mace_metrics": existing.get("reported_mace_metrics", {}),
    }
    (OUT / "mace_phase2_metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_manifest(context: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    figure_entries = []
    for stem, title, status in FIGURES:
        figure_entries.append(
            {
                "stem": stem,
                "title": title,
                "status": status,
                "png": f"{stem}.png",
                "pdf": f"{stem}.pdf",
                "real_mace_data": False if status != "phase1_context" else None,
            }
        )
    manifest = {
        "report": "Fase 2 - MACE fine-tune estructura-consciente",
        "generated_at": now,
        "output_dir": rel(OUT),
        "data_policy": "No se inventan metricas MACE; placeholders hasta tener DFT con energia, fuerzas y stress.",
        "phase1_context": context,
        "phase2_dft_labels": context.get("phase2_dft_labels", {}),
        "phase2_selection": context.get("phase2_selection", {}),
        "sources": {
            "phase1_learning_curve": rel(CURVE) if CURVE.exists() else None,
            "orchestrator_state": rel(STATE) if STATE.exists() else None,
            "phase2_metrics": "reports/training fase 2/mace_phase2_metrics.json",
        },
        "expected_artifacts": EXPECTED_ARTIFACTS,
        "figures": figure_entries,
    }
    (OUT / "training_phase2_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_readme(context: dict[str, Any]) -> None:
    figure_rows = "\n".join(
        f"| `{stem}` | [{stem}.png]({stem}.png) / [{stem}.pdf]({stem}.pdf) | {status} |"
        for stem, _, status in FIGURES
    )
    readme = f"""# Training Fase 2 — MACE Fine-Tune

Esta carpeta es el tablero visual de Fase 2. Su objetivo es seguir el paso de la Fase 1
composicional a un modelado estructura-consciente con baseline **MACE-MP-0**, generación
de fases/polimorfos, etiquetado DFT con energía + fuerzas + stress y fine-tune MACE.

## Estado Actual

- Fase 1 cerrada: batches `{", ".join(map(str, context["batches_finalized"]))}`.
- DFT continuo: `{context["dft_continuous_converged"]}/{context["dft_continuous_converged"]}` convergidos, `0` fallidos.
- Dataset surrogate: `{context["surrogate_dataset_points"]}` puntos.
- Motivo de paro: `{context["stop_reason"]}`.
- Métrica final Fase 1: `test_mae={context["final_test_mae_eV_atom"]:.5f} eV/átomo`, `overfit_ratio={context["final_overfit_ratio"]:.3f}`.
- Métricas reales MACE: **no disponibles todavía**.
- Etiquetas DFT Fase 2A: `{int(context.get("phase2_dft_labels", {}).get("n_labels", 0) or 0)}` labels,
  `{int(context.get("phase2_dft_labels", {}).get("n_unique_candidates", 0) or 0)}` candidatos únicos.
- Shortlist Fase 2A: `{int(context.get("phase2_selection", {}).get("n_candidates", 0) or 0)}` candidatos,
  `{int(context.get("phase2_selection", {}).get("n_batches", 0) or 0)}` lotes,
  `{int(context.get("phase2_selection", {}).get("n_expected_dft_labels", 0) or 0)}` etiquetas DFT esperadas.

Nota crítica: los single-points de Fase 1 son cúbicos idealizados y no contienen
fuerzas/stress. Sirven para el surrogate composicional, pero no entrenan MACE directamente.

## Artefactos Contrato

- Dataset MACE: `{EXPECTED_ARTIFACTS["dataset_mace"]}`.
- Splits: `{EXPECTED_ARTIFACTS["splits"]}`.
- Métricas: `{EXPECTED_ARTIFACTS["metrics"]}`.
- Modelo: `{EXPECTED_ARTIFACTS["model"]}`.
- Salidas por fase: `{EXPECTED_ARTIFACTS["phase_outputs"]}`.

## Regeneración

El tablero se regenera con `scripts/generate_phase2_training_report.py`. En esta máquina se
usó el entorno `gpaw246` porque el Python del sistema no tiene matplotlib:

```bash
MPLCONFIGDIR=/tmp/mpl-phase2 /home/luis-ochoa/miniforge3/envs/gpaw246/bin/python3 scripts/generate_phase2_training_report.py
```

## Figuras

| Figura | Archivos | Estado |
|--------|----------|--------|
{figure_rows}

Estados:

- `phase1_context`: usa datos reales ya existentes para cerrar Fase 1.
- `planned_placeholder`: define el embudo/contrato operativo sin métricas reales.
- `pending_mace_data`: figura reservada hasta tener baseline, fine-tune o validación MACE.

## Política De Datos

No se reportan valores de energía, fuerzas, stress, ranking de fases, estabilidad de
relajación ni speedup MACE como reales hasta que existan estructuras etiquetadas con DFT
compatible. Las plantillas se reemplazarán con curvas y tablas reales conforme aparezcan
`phase2_seed.extxyz`, `splits.json`, logs de entrenamiento y métricas por fase.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")


def generate() -> None:
    ensure_out()
    context = phase1_context()
    write_metrics(context)
    plot_dashboard(context)
    plot_dataset_coverage(context)
    plot_phase_candidate_funnel(context)
    plot_baseline_benchmark()
    plot_training_loss()
    plot_parity(
        "energy_parity",
        "Paridad energia DFT vs MACE",
        "energia DFT (eV/atomo)",
        "energia MACE (eV/atomo)",
        "Pendiente de dataset con energias consistentes.",
    )
    plot_parity(
        "force_parity",
        "Paridad fuerzas DFT vs MACE",
        "fuerzas DFT (eV/A)",
        "fuerzas MACE (eV/A)",
        "Pendiente de etiquetas de fuerzas atomicas.",
    )
    plot_force_residuals()
    plot_parity(
        "stress_parity",
        "Paridad stress DFT vs MACE",
        "stress DFT",
        "stress MACE",
        "Pendiente y opcional si stress esta disponible.",
    )
    plot_phase_ranking_accuracy()
    plot_relaxation_stability()
    plot_learning_curve(context)
    plot_benchmark_runtime()
    write_manifest(context)
    write_readme(context)
    print(f"Fase 2 training report generado en {OUT}")
    print(f"Figuras PNG: {len(list(OUT.glob('*.png')))}")
    print(f"Figuras PDF: {len(list(OUT.glob('*.pdf')))}")


if __name__ == "__main__":
    generate()
