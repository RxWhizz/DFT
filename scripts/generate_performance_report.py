#!/usr/bin/env python3
"""Genera tablas y figuras del barrido de rendimiento DFT."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
MODE_ORDER = {"physical": 0, "ht": 1}

SWEEP_RE = re.compile(
    r"^\s*(?P<split>\d+x\d+)\s+"
    r"(?P<total_cores>\d+)\s+"
    r"(?P<ok>\d+/\d+)\s+"
    r"(?P<t_iter_s>[\d.]+)s\s+"
    r"(?P<throughput>[\d.]+)\s+"
    r"(?P<peak_ram_gb>[\d.]+)GB\s+"
    r"(?P<eta_482_h>[\d.]+)h"
)

DOMAIN_RE = re.compile(
    r"^\s*(?P<name>dom_n1|dom\d+)\s+n=(?P<cores>\d+)\s+"
    r"(?P<status>\w+)\s+wall=\s*(?P<wall_s>[\d.]+)s\s+"
    r"iters=(?P<iters>\d+)\s+t/iter=(?P<t_iter_s>[\d.]+)s"
)

SPEEDUP_RE = re.compile(r"^\s*(?P<name>dom_n1|dom\d+)\s+(?P<speedup>[\d.]+)x")


def split_parts(split: str) -> tuple[int, int]:
    slots, cores = split.split("x", 1)
    return int(slots), int(cores)


def parse_sweep(path: Path, mode: str, budget_label: str) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(errors="replace").splitlines():
        match = SWEEP_RE.match(line)
        if not match:
            continue
        row = match.groupdict()
        slots, cores = split_parts(row["split"])
        ok_done, ok_total = row["ok"].split("/", 1)
        rows.append(
            {
                "mode": mode,
                "budget_label": budget_label,
                "split": row["split"],
                "slots": slots,
                "cores_per_slot": cores,
                "total_cores": int(row["total_cores"]),
                "jobs_ok": int(ok_done),
                "jobs_total": int(ok_total),
                "t_iter_s": float(row["t_iter_s"]),
                "throughput_iter_s": float(row["throughput"]),
                "peak_ram_gb": float(row["peak_ram_gb"]),
                "eta_482_h": float(row["eta_482_h"]),
                "source": str(path.relative_to(ROOT)),
            }
        )
    return rows


def parse_domain(path: Path) -> pd.DataFrame:
    rows: dict[str, dict] = {}
    in_speedup = False
    for line in path.read_text(errors="replace").splitlines():
        match = DOMAIN_RE.match(line)
        if match:
            data = match.groupdict()
            rows[data["name"]] = {
                "name": data["name"],
                "domain_cores": int(data["cores"]),
                "status": data["status"],
                "wall_s": float(data["wall_s"]),
                "iters": int(data["iters"]),
                "t_iter_s": float(data["t_iter_s"]),
                "source": str(path.relative_to(ROOT)),
            }
            continue
        if "speedup domain" in line:
            in_speedup = True
            continue
        if in_speedup:
            speed = SPEEDUP_RE.match(line)
            if speed and speed.group("name") in rows:
                rows[speed.group("name")]["speedup_vs_1core"] = float(speed.group("speedup"))
    return pd.DataFrame(rows.values()).sort_values("domain_cores")


def parse_concurrency(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    data = json.loads(path.read_text())
    rows = []
    for row in data:
        rows.append(
            {
                "slots": int(row["n"]),
                "avg_t_iter_s": float(row["avg_t_iter_s"]),
                "throughput_iter_s": float(row["throughput_ji_s"]),
                "source": str(path.relative_to(ROOT)),
            }
        )
    return pd.DataFrame(rows)


def save_fig(fig: plt.Figure, stem: str) -> None:
    for ext in ("png", "pdf"):
        fig.savefig(FIGURES / f"{stem}.{ext}", dpi=180, bbox_inches="tight")
    plt.close(fig)


def ordered_sweep(df: pd.DataFrame) -> pd.DataFrame:
    ordered = df.copy()
    ordered["_mode_order"] = ordered["mode"].map(MODE_ORDER)
    return ordered.sort_values(["_mode_order", "slots", "cores_per_slot"]).drop(columns=["_mode_order"])


def annotate_bars(ax, fmt: str = "{:.3g}", dy: float = 3) -> None:
    for patch in ax.patches:
        value = patch.get_height()
        ax.annotate(
            fmt.format(value),
            (patch.get_x() + patch.get_width() / 2, value),
            ha="center",
            va="bottom",
            xytext=(0, dy),
            textcoords="offset points",
            fontsize=9,
        )


def colors_for(df: pd.DataFrame, value_col: str, best_low: bool = False) -> list[str]:
    physical = "#2F6F73"
    ht = "#B85750"
    best = "#2E8B57"
    values = df[value_col]
    best_value = values.min() if best_low else values.max()
    out = []
    for _, row in df.iterrows():
        if row[value_col] == best_value and row["mode"] == "physical":
            out.append(best)
        elif row["mode"] == "physical":
            out.append(physical)
        else:
            out.append(ht)
    return out


def plot_throughput(df: pd.DataFrame) -> None:
    ordered = ordered_sweep(df)
    xlabels = [f"{r.split}\n{r.mode}" for r in ordered.itertuples()]
    fig, ax = plt.subplots(figsize=(11, 5.8))
    ax.bar(xlabels, ordered["throughput_iter_s"], color=colors_for(ordered, "throughput_iter_s"))
    annotate_bars(ax, "{:.3f}")
    ax.set_ylabel("Throughput agregado (iter/s)")
    ax.set_title("Barrido slots x cores: maximo throughput medido")
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", rotation=0)
    ax.text(
        0.02,
        0.95,
        "Verde = mejor configuracion fisica",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=10,
    )
    save_fig(fig, "performance_throughput")


def plot_tradeoff(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 6.3))
    for mode, group in df.groupby("mode"):
        color = "#2F6F73" if mode == "physical" else "#B85750"
        ax.scatter(
            group["peak_ram_gb"],
            group["throughput_iter_s"],
            s=120,
            color=color,
            alpha=0.9,
            label="44 cores fisicos" if mode == "physical" else "88 cores HT",
        )
        for row in group.itertuples():
            ax.annotate(
                row.split,
                (row.peak_ram_gb, row.throughput_iter_s),
                xytext=(6, 4),
                textcoords="offset points",
                fontsize=9,
            )
    ax.set_xlabel("RAM pico medida (GB)")
    ax.set_ylabel("Throughput agregado (iter/s)")
    ax.set_title("Tradeoff rendimiento vs memoria")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    save_fig(fig, "performance_ram_tradeoff")


def plot_eta(df: pd.DataFrame) -> None:
    ordered = ordered_sweep(df)
    xlabels = [f"{r.split}\n{r.mode}" for r in ordered.itertuples()]
    fig, ax = plt.subplots(figsize=(11, 5.8))
    ax.bar(xlabels, ordered["eta_482_h"], color=colors_for(ordered, "eta_482_h", best_low=True))
    annotate_bars(ax, "{:.1f} h")
    ax.set_ylabel("ETA para 482 superceldas (h)")
    ax.set_title("Tiempo estimado de corrida completa")
    ax.grid(axis="y", alpha=0.25)
    save_fig(fig, "performance_eta_482")


def plot_domain(domain: pd.DataFrame) -> None:
    fig, ax1 = plt.subplots(figsize=(8.5, 5.8))
    color_t = "#2F6F73"
    color_s = "#B85750"
    ax1.plot(domain["domain_cores"], domain["t_iter_s"], marker="o", lw=2.5, color=color_t)
    ax1.set_xlabel("Domain cores por job")
    ax1.set_ylabel("t/iter (s)", color=color_t)
    ax1.tick_params(axis="y", labelcolor=color_t)
    ax1.grid(alpha=0.25)
    ax1.set_title("GPAW 24.6: escalamiento por domain decomposition")

    ax2 = ax1.twinx()
    ax2.plot(domain["domain_cores"], domain["speedup_vs_1core"], marker="s", lw=2.5, color=color_s)
    ax2.set_ylabel("Speedup vs 1 core", color=color_s)
    ax2.tick_params(axis="y", labelcolor=color_s)

    for row in domain.itertuples():
        ax1.annotate(f"{row.t_iter_s:.1f}s", (row.domain_cores, row.t_iter_s), xytext=(0, 8),
                     textcoords="offset points", ha="center", fontsize=9, color=color_t)
        ax2.annotate(f"{row.speedup_vs_1core:.2f}x", (row.domain_cores, row.speedup_vs_1core),
                     xytext=(0, -16), textcoords="offset points", ha="center", fontsize=9, color=color_s)
    save_fig(fig, "performance_domain_scaling")


def plot_concurrency(concurrency: pd.DataFrame) -> None:
    if concurrency.empty:
        return
    fig, ax1 = plt.subplots(figsize=(8, 5.4))
    color_t = "#2F6F73"
    color_p = "#6B5B95"
    ax1.bar(concurrency["slots"].astype(str), concurrency["throughput_iter_s"], color=color_t)
    annotate_bars(ax1, "{:.4f}")
    ax1.set_xlabel("Slots concurrentes a 1 core")
    ax1.set_ylabel("Throughput agregado (iter/s)")
    ax1.set_title("Concurrencia 1-core: evidencia de contencion")
    ax1.grid(axis="y", alpha=0.25)

    ax2 = ax1.twinx()
    ax2.plot(concurrency["slots"].astype(str), concurrency["avg_t_iter_s"], color=color_p, marker="o", lw=2)
    ax2.set_ylabel("t/iter promedio (s)", color=color_p)
    ax2.tick_params(axis="y", labelcolor=color_p)
    save_fig(fig, "performance_concurrency_1core")


def plot_dashboard(df: pd.DataFrame, domain: pd.DataFrame) -> None:
    ordered = ordered_sweep(df)
    xlabels = [r.split for r in ordered.itertuples()]
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))

    axes[0, 0].bar(xlabels, ordered["throughput_iter_s"], color=colors_for(ordered, "throughput_iter_s"))
    axes[0, 0].set_title("Throughput")
    axes[0, 0].set_ylabel("iter/s")
    axes[0, 0].tick_params(axis="x", rotation=35)
    axes[0, 0].grid(axis="y", alpha=0.25)

    axes[0, 1].bar(xlabels, ordered["eta_482_h"], color=colors_for(ordered, "eta_482_h", best_low=True))
    axes[0, 1].set_title("ETA 482")
    axes[0, 1].set_ylabel("horas")
    axes[0, 1].tick_params(axis="x", rotation=35)
    axes[0, 1].grid(axis="y", alpha=0.25)

    for mode, group in ordered.groupby("mode"):
        axes[1, 0].scatter(
            group["peak_ram_gb"],
            group["throughput_iter_s"],
            s=80,
            label=mode,
            color="#2F6F73" if mode == "physical" else "#B85750",
        )
        for row in group.itertuples():
            axes[1, 0].annotate(row.split, (row.peak_ram_gb, row.throughput_iter_s),
                                xytext=(5, 3), textcoords="offset points", fontsize=8)
    axes[1, 0].set_title("RAM vs throughput")
    axes[1, 0].set_xlabel("GB")
    axes[1, 0].set_ylabel("iter/s")
    axes[1, 0].legend(frameon=False)
    axes[1, 0].grid(alpha=0.25)

    axes[1, 1].plot(domain["domain_cores"], domain["t_iter_s"], marker="o", color="#2F6F73", lw=2)
    axes[1, 1].set_title("Domain scaling")
    axes[1, 1].set_xlabel("cores")
    axes[1, 1].set_ylabel("t/iter (s)")
    axes[1, 1].grid(alpha=0.25)

    fig.suptitle("Resumen de rendimiento DFT", fontsize=16, y=0.995)
    fig.tight_layout()
    save_fig(fig, "performance_dashboard")


def markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    pretty = df[columns].copy()
    pretty.columns = [c.replace("_", " ") for c in columns]
    return pretty.to_markdown(index=False)


def write_markdown(df: pd.DataFrame, domain: pd.DataFrame, concurrency: pd.DataFrame) -> None:
    best = df[df["mode"] == "physical"].sort_values("throughput_iter_s", ascending=False).iloc[0]
    best_eta = df[df["mode"] == "physical"].sort_values("eta_482_h").iloc[0]
    ht_best = df[df["mode"] == "ht"].sort_values("throughput_iter_s", ascending=False).iloc[0]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    table_cols = [
        "mode",
        "split",
        "slots",
        "cores_per_slot",
        "total_cores",
        "jobs_ok",
        "jobs_total",
        "t_iter_s",
        "throughput_iter_s",
        "peak_ram_gb",
        "eta_482_h",
    ]

    domain_cols = ["domain_cores", "wall_s", "iters", "t_iter_s", "speedup_vs_1core"]
    lines = [
        "# Resumen de Rendimiento DFT",
        "",
        f"Generado: {now}",
        "",
        "## Resumen Ejecutivo",
        "",
        f"- Configuracion recomendada: **{best.split}** = **{int(best.slots)} slots x {int(best.cores_per_slot)} cores**, GPAW 24.6, domain={int(best.cores_per_slot)}, HT apagado.",
        f"- Mejor throughput con cores fisicos: **{best.throughput_iter_s:.4f} iter/s**, **{best.peak_ram_gb:.2f} GB** RAM pico y **{best.eta_482_h:.1f} h** estimadas para 482 superceldas.",
        f"- Mejor throughput con HT observado: **{ht_best.split}** con **{ht_best.throughput_iter_s:.4f} iter/s**, por debajo del optimo fisico.",
        "- Interpretacion: PW-DFT queda limitado por FFT/ancho de banda de memoria; HT agrega contencion y presion de RAM sin mejorar throughput.",
        "",
        "## Tabla Maestra",
        "",
        markdown_table(df, table_cols),
        "",
        "## Escalamiento Por Domain",
        "",
        markdown_table(domain, domain_cols),
        "",
    ]
    if not concurrency.empty:
        lines += [
            "## Prueba De Concurrencia A 1 Core",
            "",
            markdown_table(concurrency, ["slots", "avg_t_iter_s", "throughput_iter_s"]),
            "",
        ]
    lines += [
        "## Figuras",
        "",
        "- [Throughput bars](figures/performance_throughput.png)",
        "- [RAM vs throughput tradeoff](figures/performance_ram_tradeoff.png)",
        "- [ETA for 482 supercells](figures/performance_eta_482.png)",
        "- [Domain scaling](figures/performance_domain_scaling.png)",
        "- [1-core concurrency](figures/performance_concurrency_1core.png)",
        "- [Dashboard](figures/performance_dashboard.png)",
        "",
        "## Archivos De Datos",
        "",
        "- [Clean benchmark CSV](performance_benchmark.csv)",
        "- [Clean benchmark JSON](performance_benchmark.json)",
        "- [Domain scaling CSV](performance_domain_scaling.csv)",
        "- [1-core concurrency CSV](performance_concurrency_1core.csv)",
        "",
        "## Fuentes Crudas",
        "",
        "- [Physical-core sweep log](sweep_benchmark.log)",
        "- [HT sweep log](sweep_ht_benchmark.log)",
        "- [GPAW 24.6 benchmark log](gpaw246_benchmark.log)",
        "- [Concurrency benchmark JSON](concurrency_benchmark.json)",
        "",
        "## Decision",
        "",
        f"Usar **{best.split}** en produccion. Es la configuracion ganadora en throughput entre splits fisicos y tambien la de menor ETA ({best_eta.eta_482_h:.1f} h). Mantener HT apagado para esta carga.",
        "",
    ]
    (REPORTS / "performance_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    FIGURES.mkdir(exist_ok=True)

    rows = []
    rows.extend(parse_sweep(REPORTS / "sweep_benchmark.log", "physical", "44 physical cores"))
    rows.extend(parse_sweep(REPORTS / "sweep_ht_benchmark.log", "ht", "88 logical cores"))
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("No sweep benchmark rows found.")

    best_mask = df["throughput_iter_s"] == df[df["mode"] == "physical"]["throughput_iter_s"].max()
    df["recommended"] = best_mask & (df["mode"] == "physical")
    df["throughput_rank"] = df["throughput_iter_s"].rank(ascending=False, method="min").astype(int)
    df = ordered_sweep(df).reset_index(drop=True)

    domain = parse_domain(REPORTS / "gpaw246_benchmark.log")
    concurrency = parse_concurrency(REPORTS / "concurrency_benchmark.json")

    df.to_csv(REPORTS / "performance_benchmark.csv", index=False)
    (REPORTS / "performance_benchmark.json").write_text(
        json.dumps(df.to_dict(orient="records"), indent=2), encoding="utf-8"
    )
    domain.to_csv(REPORTS / "performance_domain_scaling.csv", index=False)
    if not concurrency.empty:
        concurrency.to_csv(REPORTS / "performance_concurrency_1core.csv", index=False)

    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 10,
        }
    )

    plot_throughput(df)
    plot_tradeoff(df)
    plot_eta(df)
    plot_domain(domain)
    plot_concurrency(concurrency)
    plot_dashboard(df, domain)
    write_markdown(df, domain, concurrency)

    print("Generated:")
    for path in [
        REPORTS / "performance_summary.md",
        REPORTS / "performance_benchmark.csv",
        REPORTS / "performance_benchmark.json",
        REPORTS / "performance_domain_scaling.csv",
        REPORTS / "performance_concurrency_1core.csv",
    ]:
        if path.exists():
            print(f"  {path.relative_to(ROOT)}")
    for path in sorted(FIGURES.glob("performance_*")):
        print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
