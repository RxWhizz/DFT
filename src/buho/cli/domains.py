"""Grupos de dominio del ejecutable `buho`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from ._common import (
    HELP_OPTS,
    PASSTHROUGH,
    data_path,
    data_root,
    echo_json,
    echo_result,
    import_available,
    json_option,
    module_command,
    run_module,
    script_command,
    simple_status,
)


def _add_scripts(group: click.Group, scripts: list[tuple[str, str, str]]) -> None:
    for name, script, help_text in scripts:
        group.add_command(script_command(script, name=name, help_text=help_text))


def _module_subcommand(module: str, subcommand: str, *, name: str, help_text: str) -> click.Command:
    @click.command(name, context_settings=PASSTHROUGH, help=help_text, short_help=help_text)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def _cmd(args: tuple[str, ...]) -> None:
        run_module(module, (subcommand, *args))

    return _cmd


# ── Generacion y DFT basico ──────────────────────────────────────────────────


@click.group("generate", context_settings=HELP_OPTS)
def generate() -> None:
    """Generacion, filtrado y estructuras ABX3."""


@generate.command("status", context_settings=HELP_OPTS)
@json_option
def generate_status(as_json: bool) -> None:
    """Resume archivos de entrada/salida del generador."""
    files = {
        "config": data_path("config/generator.yaml"),
        "raw_candidates": data_path("data/raw/generated_candidates.jsonl"),
        "filtered_candidates": data_path("data/processed/filtered_candidates.csv"),
        "top_candidates": data_path("data/processed/top500_candidates.csv"),
    }
    data = {
        "group": "generate",
        "files": {k: {"path": str(v), "exists": v.exists()} for k, v in files.items()},
    }
    echo_result(data, as_json=as_json, human=lambda d: "\n".join(
        f"{k}: {v['path']} ({'existe' if v['exists'] else 'no existe'})"
        for k, v in d["files"].items()
    ))


generate.add_command(
    _module_subcommand("buho.generator", "generate", name="generate", help_text="Genera candidatos ABX3.")
)
generate.add_command(
    _module_subcommand("buho.generator", "filter", name="filter", help_text="Filtra y puntua candidatos.")
)
generate.add_command(
    _module_subcommand(
        "buho.generator",
        "build-structures",
        name="build-structures",
        help_text="Construye CIF/POSCAR/traj para candidatos.",
    )
)


@click.group("dft-jobs", context_settings=HELP_OPTS)
def dft_jobs() -> None:
    """Preparacion, recoleccion y runners de jobs DFT."""


@dft_jobs.command("status", context_settings=HELP_OPTS)
@click.option("--runs-dir", default="runs/relax_basic", show_default=True, help="Directorio de jobs.")
@json_option
def dft_jobs_status(runs_dir: str, as_json: bool) -> None:
    root = data_path(runs_dir)
    counts: dict[str, int] = {}
    if root.is_dir():
        for status in root.glob("*/status.json"):
            try:
                state = json.loads(status.read_text(encoding="utf-8")).get("status", "unknown")
            except (OSError, json.JSONDecodeError):
                state = "unknown"
            counts[state] = counts.get(state, 0) + 1
    data = {"runs_dir": str(root), "counts": counts, "total": sum(counts.values())}
    echo_result(data, as_json=as_json, human=lambda d: f"{d['total']} jobs en {d['runs_dir']}: {d['counts']}")


dft_jobs.add_command(
    _module_subcommand(
        "buho.dft_jobs",
        "prepare-relax",
        name="prepare-relax",
        help_text="Prepara directorios de relajacion DFT.",
    )
)
dft_jobs.add_command(
    _module_subcommand(
        "buho.dft_jobs",
        "collect-results",
        name="collect-results",
        help_text="Recolecta resultados DFT.",
    )
)
dft_jobs.add_command(
    script_command(
        "scripts/buho_relax_runner.py",
        name="run-relax",
        help_text="Lanza el scheduler historico de relajaciones.",
    )
)


# ── Active learning y Fase 2 ────────────────────────────────────────────────


@click.group("active-learning", context_settings=HELP_OPTS)
def active_learning() -> None:
    """Loop de active learning por batches."""


@active_learning.command("status", context_settings=HELP_OPTS)
@click.option("--batches-dir", default="data/batches", show_default=True, help="Directorio de batches.")
@json_option
def active_learning_status(batches_dir: str, as_json: bool) -> None:
    root = data_path(batches_dir)
    items = []
    if root.is_dir():
        for manifest in sorted(root.glob("batch_*/batch_manifest.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items.append(data)
    payload = {"batches_dir": str(root), "items": items, "total": len(items)}
    echo_result(payload, as_json=as_json, human=lambda d: f"{d['total']} batch(es) en {d['batches_dir']}")


for _name in ("run-batch", "finalize-batch", "status"):
    if _name != "status":
        active_learning.add_command(
            _module_subcommand(
                "buho.active_learning",
                _name,
                name=_name,
                help_text=f"Ejecuta buho.active_learning {_name}.",
            )
        )
active_learning.add_command(
    script_command(
        "scripts/active_learning_orchestrator.py",
        name="orchestrator",
        help_text="Orquesta batches con criterio de paro.",
    )
)
active_learning.add_command(
    module_command(
        "buho.discovery",
        name="discovery",
        help_text="Loop autonomo ML discovery -> DFT -> reentrenar.",
    )
)


@click.group("phase2-force", context_settings=HELP_OPTS)
def phase2_force() -> None:
    """Fase 2A: etiquetado DFT de energia y fuerzas."""


@phase2_force.command("status", context_settings=HELP_OPTS)
@click.option("--runs-dir", default="local_runs/phase2_force", show_default=True, help="Raiz de batches.")
@json_option
def phase2_status(runs_dir: str, as_json: bool) -> None:
    root = data_path(runs_dir)
    batches = []
    if root.is_dir():
        for batch in sorted(root.glob("batch_*")):
            if not batch.is_dir():
                continue
            counts: dict[str, int] = {}
            for st in batch.glob("*/status.json"):
                try:
                    state = json.loads(st.read_text(encoding="utf-8")).get("status", "unknown")
                except (OSError, json.JSONDecodeError):
                    state = "unknown"
                counts[state] = counts.get(state, 0) + 1
            batches.append({"name": batch.name, "path": str(batch), "counts": counts})
    data = {"runs_dir": str(root), "batches": batches, "total": len(batches)}
    echo_result(data, as_json=as_json, human=lambda d: f"{d['total']} batch(es) Fase 2A")


for _sub in ("select", "prepare", "run", "collect"):
    phase2_force.add_command(
        _module_subcommand(
            "buho.phase2_force",
            _sub,
            name=_sub,
            help_text=f"Fase 2A: {_sub}.",
        )
    )

_add_scripts(
    phase2_force,
    [
        ("runner", "scripts/phase2_force_runner.py", "Wrapper historico del runner Fase 2A."),
        ("live-eta", "scripts/phase2_force_live_eta.py", "Actualiza ETA vivo de Fase 2A."),
        ("mace-cycle", "scripts/phase2_mace_cycle.py", "Entrena MACE al completar batches."),
        ("mace-train", "scripts/phase2_mace_train.py", "Fine-tuning MACE Fase 2A."),
        ("prepare-organic-batch", "scripts/phase2_prepare_organic_batch.py", "Prepara batch organico explicito."),
    ],
)


# ── Monitor, servicios y actividad ──────────────────────────────────────────


@click.group("monitor", context_settings=HELP_OPTS)
def monitor() -> None:
    """Servidor, rutas y utilidades del monitor."""


@monitor.command("paths", context_settings=HELP_OPTS)
@json_option
def monitor_paths(as_json: bool) -> None:
    from monitor_api import paths

    data = paths.describe()
    echo_result(data, as_json=as_json, human=lambda d: "\n".join(f"{k}: {v}" for k, v in d.items()))


monitor.add_command(module_command("monitor_api.launcher", name="serve", help_text="Arranca el monitor."))
monitor.add_command(script_command("scripts/dump_openapi.py", name="openapi", help_text="Vuelca OpenAPI."))
monitor.add_command(script_command("scripts/buho_monitor.py", name="jobs", help_text="Dashboard textual de jobs."))
monitor.add_command(script_command("scripts/gpaw_monitor.py", name="gpaw", help_text="Monitor de un PID GPAW."))


@click.group("activity", context_settings=HELP_OPTS)
def activity() -> None:
    """Actividad real de runners y procesos."""


@activity.command("runners", context_settings=HELP_OPTS)
@json_option
def activity_runners(as_json: bool) -> None:
    if not import_available("psutil"):
        data = {
            "available": False,
            "reason": "falta psutil",
            "runners": [],
            "n_calculos_vivos": 0,
        }
        echo_result(data, as_json=as_json, human=lambda d: d["reason"])
        return

    from monitor_api.services import activity as service

    data = {
        "available": True,
        "runners": service.runners_activos(),
        "n_calculos_vivos": service.n_calculos_vivos(),
    }
    echo_result(data, as_json=as_json, human=lambda d: f"runners={len(d['runners'])}, gpaw={d['n_calculos_vivos']}")


@activity.command("batch-count", context_settings=HELP_OPTS)
@click.argument("batch_dir", required=False)
@json_option
def activity_batch_count(batch_dir: str | None, as_json: bool) -> None:
    from monitor_api.services.activity import contar_lote

    root = data_path(batch_dir or "local_runs/phase2_force")
    data = {"batch_dir": str(root), "counts": contar_lote(root)}
    echo_result(data, as_json=as_json, human=lambda d: f"{d['batch_dir']}: {d['counts']}")


@click.group("screening", context_settings=HELP_OPTS)
def screening() -> None:
    """Cascada de cribado HTS."""


@screening.command("tiers", context_settings=HELP_OPTS)
@json_option
def screening_tiers(as_json: bool) -> None:
    from monitor_api.services.screening import gates, tier_availability

    data = {"tiers": tier_availability({}), "gates": gates({})}
    echo_result(data, as_json=as_json, human=lambda d: "\n".join(
        f"Tier {t['tier']} {t['name']}: {'OK' if t['available'] else t['reason']}"
        for t in d["tiers"]
    ))


@screening.command("runs", context_settings=HELP_OPTS)
@json_option
def screening_runs(as_json: bool) -> None:
    from monitor_api.services.screening import list_runs

    data = {"items": list_runs()}
    echo_result(data, as_json=as_json, human=lambda d: f"{len(d['items'])} ejecucion(es) recordadas")


@screening.command("run", context_settings=HELP_OPTS)
@click.option("--batch-id", type=int, default=None, help="ID de batch.")
@click.option("--n-candidates", type=int, default=100, show_default=True, help="Candidatos.")
@click.option("--n-batches", type=int, default=1, show_default=True, help="Numero de lotes.")
@click.option("--random-seed", type=int, default=None, help="Semilla.")
@click.option("--use-mlff/--no-mlff", default=None, help="Usa Tier 2 si esta disponible.")
@json_option
def screening_run(
    batch_id: int | None,
    n_candidates: int,
    n_batches: int,
    random_seed: int | None,
    use_mlff: bool | None,
    as_json: bool,
) -> None:
    from monitor_api.services.screening import start_run

    run = start_run(
        batch_id=batch_id,
        n_candidates=n_candidates,
        n_batches=n_batches,
        random_seed=random_seed,
        use_mlff=use_mlff,
    )
    data = run.as_dict()
    echo_result(data, as_json=as_json, human=lambda d: f"Cribado lanzado: {d['run_id']}")


@click.group("candidates", context_settings=HELP_OPTS)
def candidates() -> None:
    """Consulta candidatos generados o verificados."""


@candidates.command("list", context_settings=HELP_OPTS)
@click.option("--runs-dir", default="local_runs/phase2_force", show_default=True)
@click.option("--limit", type=int, default=20, show_default=True)
@click.option("--offset", type=int, default=0, show_default=True)
@click.option("--all", "show_all", is_flag=True, help="Incluye no verificados.")
@json_option
def candidates_list(runs_dir: str, limit: int, offset: int, show_all: bool, as_json: bool) -> None:
    from monitor_api.services.candidates import query_candidates

    data = query_candidates(
        data_path(runs_dir),
        solo_verificados=not show_all,
        limit=limit,
        offset=offset,
    )
    echo_result(data, as_json=as_json, human=lambda d: f"{d['total']} candidato(s), fuente: {d['source']}")


@click.group("batches", context_settings=HELP_OPTS)
def batches() -> None:
    """Inspeccion y control de batches."""


@batches.command("list", context_settings=HELP_OPTS)
@click.option("--root", "root_dir", default="local_runs/phase2_force", show_default=True)
@json_option
def batches_list(root_dir: str, as_json: bool) -> None:
    root = data_path(root_dir)
    items = []
    if root.is_dir():
        for batch in sorted(root.glob("batch_*")):
            if batch.is_dir():
                items.append({"name": batch.name, "path": str(batch)})
    data = {"root": str(root), "items": items}
    echo_result(data, as_json=as_json, human=lambda d: f"{len(d['items'])} batch(es) en {d['root']}")


# ── ML, MLIP y analisis ─────────────────────────────────────────────────────


@click.group("ml", context_settings=HELP_OPTS)
def ml() -> None:
    """Surrogates composicionales y prediccion."""


@ml.command("status", context_settings=HELP_OPTS)
@json_option
def ml_status(as_json: bool) -> None:
    models = data_path("models")
    data = {
        "models_dir": str(models),
        "models_exists": models.is_dir(),
        "sklearn_importable": import_available("sklearn"),
        "pandas_importable": import_available("pandas"),
        "model_files": sorted(p.name for p in models.glob("*.pkl")) if models.is_dir() else [],
    }
    echo_result(data, as_json=as_json, human=lambda d: f"{len(d['model_files'])} modelo(s) en {d['models_dir']}")


@ml.command("metrics", context_settings=HELP_OPTS)
@json_option
def ml_metrics(as_json: bool) -> None:
    from monitor_api.services.ml import model_metrics

    data = model_metrics()
    echo_result(data, as_json=as_json, human=lambda d: f"surrogate_status={d['surrogate_status']}")


@ml.command("predict", context_settings=HELP_OPTS)
@click.option("--A", "site_a", required=True, help="Sitio A.")
@click.option("--B", "site_b", required=True, help="Sitio B.")
@click.option("--X", "site_x", required=True, help="Sitio X.")
@json_option
def ml_predict(site_a: str, site_b: str, site_x: str, as_json: bool) -> None:
    from monitor_api.services.ml import predict

    data = predict(site_a, site_b, site_x)
    echo_result(data, as_json=as_json)


_add_scripts(
    ml,
    [
        ("train-from-dft", "scripts/train_surrogate_from_dft.py", "Entrena surrogate desde resultados DFT."),
        ("train-meff-dielectric", "scripts/train_meff_dielectric.py", "Entrena surrogates m* y epsilon."),
        ("plot-training", "scripts/plot_surrogate_training.py", "Grafica entrenamiento surrogate."),
    ],
)
ml.add_command(module_command("ml_surrogate.predict", name="predict-legacy", help_text="CLI legacy de prediccion."))
ml.add_command(module_command("ml_surrogate.train", name="train-surrogate", help_text="Entrena surrogate legacy."))
ml.add_command(module_command("ml_surrogate.inference", name="inference", help_text="Inferencia GNN legacy."))


@click.group("mlip", context_settings=HELP_OPTS)
def mlip() -> None:
    """Entrenamiento, validacion y empaquetado MLIP/MACE."""


@mlip.command("status", context_settings=HELP_OPTS)
@json_option
def mlip_status(as_json: bool) -> None:
    root = data_path("models/mace_phase2")
    data = {
        "models_dir": str(root),
        "exists": root.is_dir(),
        "models": sorted(p.name for p in root.glob("*.model")) if root.is_dir() else [],
        "torch_importable": import_available("torch"),
        "mace_importable": import_available("mace"),
    }
    echo_result(data, as_json=as_json, human=lambda d: f"{len(d['models'])} modelo(s) MLIP")


_add_scripts(
    mlip,
    [
        ("build-training", "scripts/build_mlip_training.py", "Construye dataset multi-cabeza."),
        ("train", "scripts/train_mlip.py", "Entrena MLIP multi-cabeza."),
        ("eval", "scripts/eval_mlip.py", "Evalua MLIP."),
        ("validate", "scripts/validate_mlip.py", "Valida MLIP en sistemas de interes."),
        ("fetch-colab-model", "scripts/fetch_colab_model.py", "Trae modelo entrenado en Colab."),
        ("pack-colab-bundle", "scripts/pack_colab_bundle.py", "Empaqueta bundle Colab."),
        ("infographics", "scripts/plot_mlip_infographics.py", "Genera infografias MLIP."),
        ("train-phase2", "scripts/phase2_mace_train.py", "Fine-tuning MACE Fase 2A."),
        ("cycle", "scripts/phase2_mace_cycle.py", "Watcher de entrenamiento entre batches."),
    ],
)


@click.group("analysis", context_settings=HELP_OPTS)
def analysis() -> None:
    """Analisis cientifico de salidas DFT."""


@analysis.command("list", context_settings=HELP_OPTS)
@json_option
def analysis_list(as_json: bool) -> None:
    root = data_path("src/dft_cspbi3/analysis")
    modules = sorted(p.stem for p in root.glob("*.py") if p.name != "__init__.py") if root.is_dir() else []
    data = {"modules": modules}
    echo_result(data, as_json=as_json, human=lambda d: "\n".join(d["modules"]))


for _name in (
    "electronic",
    "structural",
    "optical",
    "device",
    "sq-limit",
    "defects",
    "neb",
    "pes",
    "kmc",
    "thermal",
    "phonopy",
    "aimd-mlip",
):
    analysis.add_command(
        click.Command(
            _name,
            help="Capacidad disponible como paso de workflow o modulo de analisis.",
            callback=lambda name=_name: click.echo(
                f"Usa `buho calc run --steps {name}` si el paso existe, o el modulo dft_cspbi3.analysis correspondiente."
            ),
        )
    )


@click.group("validate", context_settings=HELP_OPTS)
def validate() -> None:
    """Validaciones cientificas."""


@validate.command("status", context_settings=HELP_OPTS)
@json_option
def validate_status(as_json: bool) -> None:
    modules = ["scf", "soc", "hessian", "phonons", "stability"]
    data = {"modules": modules, "command_hint": "buho calc report / buho calc run --validate"}
    echo_result(data, as_json=as_json, human=lambda d: "\n".join(d["modules"]))


# ── Benchmarks, reportes, top8, datos auxiliares ────────────────────────────


@click.group("bench", context_settings=HELP_OPTS)
def bench() -> None:
    """Benchmarks, calibracion y rendimiento."""


@bench.command("status", context_settings=HELP_OPTS)
@json_option
def bench_status(as_json: bool) -> None:
    from monitor_api.services.bench import status

    data = status()
    echo_result(data, as_json=as_json, human=lambda d: f"benchmark={d['status']}, running={d['running']}")


@bench.command("plan", context_settings=HELP_OPTS)
@click.option("--max-splits", type=int, default=5, show_default=True)
@json_option
def bench_plan(max_splits: int, as_json: bool) -> None:
    try:
        from buho.bench.machine import budgets_for, detect, splits_for
    except ImportError as exc:
        data = {"available": False, "reason": str(exc)}
        echo_result(data, as_json=as_json, human=lambda d: d["reason"])
        return

    machine = detect()
    budgets = budgets_for(machine)
    data = {
        "machine": machine.as_dict(),
        "budgets": budgets,
        "splits": {
            str(b): [
                {"slots": s.slots, "cores": s.cores, "total_cores": s.total_cores}
                for s in splits_for(b, max_splits=max_splits)
            ]
            for b in budgets
        },
    }
    echo_result(data, as_json=as_json, human=lambda d: f"{d['machine']['physical_cores']} cores fisicos")


_add_scripts(
    bench,
    [
        ("machine", "scripts/bench_machine.py", "Calibra maquina con barrido real."),
        ("concurrency", "scripts/bench_concurrency.py", "Benchmark de concurrencia."),
        ("gpaw246", "scripts/bench_gpaw246.py", "Benchmark GPAW 24.6."),
        ("mixer", "scripts/bench_mixer.py", "Benchmark de mixers."),
        ("mlip-train", "scripts/bench_mlip_train.py", "Benchmark entrenamiento MLIP."),
        ("ram-domain", "scripts/bench_ram_domain.py", "Sonda RAM por domain."),
        ("scf-mpi", "scripts/bench_scf_mpi.py", "Benchmark SCF MPI."),
        ("sweep", "scripts/bench_sweep.py", "Barrido slots x cores."),
        ("mpi", "scripts/buho_mpi_benchmark.py", "Benchmark MPI BUHO."),
        ("report", "scripts/generate_performance_report.py", "Genera reporte de rendimiento."),
        ("phase2-crash-watch", "scripts/phase2_benchmark_crash_watch.py", "Flight recorder Fase 2A."),
        ("phase2-force", "scripts/phase2_force_benchmark.py", "Benchmark Fase 2A."),
        ("phase2-force-smoke", "scripts/phase2_force_smoke_benchmark.py", "Smoke benchmark Fase 2A."),
        ("phase2-kpoint-convergence", "scripts/phase2_kpoint_convergence.py", "Gate k-points Fase 2A."),
    ],
)


@click.group("report", context_settings=HELP_OPTS, invoke_without_command=True)
@click.option("--phase", default="alpha", show_default=True, help="Fase.")
@click.option("--workdir", default="./calculations", show_default=True, help="Directorio raiz.")
@click.option("--config", default="configs/default_params.yaml", show_default=True, help="YAML.")
@click.option("--soc", is_flag=True, help="Incluye validacion SOC si hay datos.")
@click.option("--with-vibrational", is_flag=True, help="Incluye reporte vibracional si hay datos.")
@click.pass_context
def report(
    ctx: click.Context,
    phase: str,
    workdir: str,
    config: str,
    soc: bool,
    with_vibrational: bool,
) -> None:
    """Reportes, figuras y visualizaciones."""
    if ctx.invoked_subcommand is not None:
        return
    from .calc import report_cmd

    report_cmd.callback(phase, workdir, config, soc, with_vibrational)


@report.command("list", context_settings=HELP_OPTS)
@json_option
def report_list(as_json: bool) -> None:
    from monitor_api.services.files import list_reports

    data = list_reports()
    echo_result(data, as_json=as_json, human=lambda d: f"{len(d['documents'])} documento(s), {len(d['galleries'])} galeria(s)")


_add_scripts(
    report,
    [
        ("visualizations", "scripts/generate_visualizations.py", "Genera visualizaciones."),
        ("legacy", "scripts/generate_report.py", "Genera results_report.md legacy."),
        ("phase2-training", "scripts/generate_phase2_training_report.py", "Reporte inicial Fase 2."),
        ("figures-from-batch", "scripts/figures_from_batch.py", "Figuras desde batch."),
        ("regen-phase2", "scripts/regen_phase2_figures.py", "Regenera figuras Fase 2."),
    ],
)


@click.group("top8", context_settings=HELP_OPTS)
def top8() -> None:
    """Flujos comparativos de las top-8 perovskitas."""


@top8.command("status", context_settings=HELP_OPTS)
@json_option
def top8_status(as_json: bool) -> None:
    root = data_path("structures/top8")
    data = {
        "structures_dir": str(root),
        "exists": root.is_dir(),
        "structures": sorted(p.name for p in root.glob("*") if p.is_file()) if root.is_dir() else [],
    }
    echo_result(data, as_json=as_json, human=lambda d: f"{len(d['structures'])} estructura(s) top8")


_add_scripts(
    top8,
    [
        ("setup-pbe", "scripts/setup_top8_pbe.py", "Prepara workspace PBE top8."),
        ("setup-r2scan", "scripts/setup_top8_r2scan.py", "Prepara workspace r2SCAN top8."),
        ("figures", "scripts/top8_figures.py", "Figuras top8."),
        ("spectra", "scripts/ai_spectra_top8.py", "Espectros top8."),
        ("ai-pipeline", "scripts/ai_pipeline_top8.py", "Pipeline AI top8."),
        ("drift-diffusion", "scripts/top8_drift_diffusion.py", "Drift-diffusion OghmaNano."),
    ],
)


@click.group("structures", context_settings=HELP_OPTS)
def structures() -> None:
    """Estructuras de referencia y pre-generadas."""


@structures.command("list", context_settings=HELP_OPTS)
@click.option("--runs-dir", default="local_runs/phase2_force", show_default=True)
@json_option
def structures_list(runs_dir: str, as_json: bool) -> None:
    from monitor_api.services.files import list_structures

    data = {"items": list_structures(data_path(runs_dir))}
    echo_result(data, as_json=as_json, human=lambda d: f"{len(d['items'])} estructura(s)")


structures.add_command(script_command("scripts/pregenerate_structures.py", name="pregenerate", help_text="Preconvierte estructuras para empaquetar."))


@click.group("data", context_settings=HELP_OPTS)
def data() -> None:
    """Ingesta y extraccion de datasets."""


@data.command("status", context_settings=HELP_OPTS)
@json_option
def data_status(as_json: bool) -> None:
    root = data_path("data")
    data_payload = {"data_dir": str(root), "exists": root.is_dir()}
    echo_result(data_payload, as_json=as_json, human=lambda d: f"{d['data_dir']} ({'existe' if d['exists'] else 'no existe'})")


_add_scripts(
    data,
    [
        ("extract-mptrj", "scripts/extract_mptrj_abx3.py", "Extrae subconjunto ABX3 de MPtrj."),
        ("ingest-public", "scripts/ingest_public_datasets.py", "Ingiere datasets publicos."),
    ],
)


@click.group("g0w0", context_settings=HELP_OPTS)
def g0w0() -> None:
    """Correcciones G0W0."""


@g0w0.command("status", context_settings=HELP_OPTS)
@json_option
def g0w0_status(as_json: bool) -> None:
    payload = simple_status("g0w0", commands=["groundstate", "run", "soc"])
    echo_result(payload, as_json=as_json, human=lambda d: ", ".join(d["commands"]))


_add_scripts(
    g0w0,
    [
        ("groundstate", "scripts/g0w0_groundstate.py", "Prepara groundstate PBE para G0W0."),
        ("run", "scripts/g0w0_run.py", "Ejecuta correccion G0W0."),
        ("soc", "scripts/g0w0_soc.py", "Aplica correccion SOC a G0W0."),
    ],
)


@click.group("u-scan", context_settings=HELP_OPTS)
def u_scan() -> None:
    """Barridos Hubbard U con r2SCAN/SOC/DOS."""


@u_scan.command("status", context_settings=HELP_OPTS)
@json_option
def u_scan_status(as_json: bool) -> None:
    payload = simple_status("u-scan", commands=["preconv-pbe-u", "u-ramp-r2scan", "u-scan-r2scan", "u-scan-pdos", "u-scan-soc-dos"])
    echo_result(payload, as_json=as_json, human=lambda d: ", ".join(d["commands"]))


_add_scripts(
    u_scan,
    [
        ("preconv-pbe-u", "scripts/preconv_pbe_u.py", "Preconverge PBEsol+U."),
        ("u-ramp-r2scan", "scripts/u_ramp_r2scan.py", "Rampa U r2SCAN."),
        ("u-scan-r2scan", "scripts/u_scan_r2scan.py", "Barrido fino U r2SCAN."),
        ("u-scan-pdos", "scripts/u_scan_pdos.py", "PDOS por U."),
        ("u-scan-soc-dos", "scripts/u_scan_soc_dos.py", "SOC + DOS por U."),
    ],
)


# ── Archivos, jobs, agente, notificaciones y watchdog ───────────────────────


@click.group("files", context_settings=HELP_OPTS)
def files() -> None:
    """Acceso controlado a archivos de resultados."""


files.add_command(report_list, name="reports")
files.add_command(structures_list, name="structures")


@click.group("jobs", context_settings=HELP_OPTS)
def jobs() -> None:
    """Artefactos y logs de jobs."""


@jobs.command("list", context_settings=HELP_OPTS)
@click.option("--runs-dir", default="local_runs/phase2_force", show_default=True)
@click.option("--limit", type=int, default=20, show_default=True)
@json_option
def jobs_list(runs_dir: str, limit: int, as_json: bool) -> None:
    root = data_path(runs_dir)
    items = []
    if root.is_dir():
        for status in sorted(root.glob("**/status.json"))[:limit]:
            items.append({"job": status.parent.name, "path": str(status.parent)})
    payload = {"runs_dir": str(root), "items": items}
    echo_result(payload, as_json=as_json, human=lambda d: f"{len(d['items'])} job(s)")


@jobs.command("logs", context_settings=HELP_OPTS)
@click.argument("job_dir")
@click.option("--label", default=None, help="Etiqueta de log.")
@click.option("--tail", type=int, default=80, show_default=True)
@json_option
def jobs_logs(job_dir: str, label: str | None, tail: int, as_json: bool) -> None:
    from monitor_api.services.jobs import read_log_tail

    data = read_log_tail(data_path(job_dir), label, tail)
    echo_result(data, as_json=as_json, human=lambda d: "\n".join(d["lines"]))


@click.group("agent", context_settings=HELP_OPTS)
def agent() -> None:
    """Agente local del monitor."""


@agent.command("status", context_settings=HELP_OPTS)
@json_option
def agent_status(as_json: bool) -> None:
    data = {"ollama_importable": import_available("httpx"), "config": str(data_path("configs/monitor.yaml"))}
    echo_result(data, as_json=as_json, human=lambda d: f"config: {d['config']}")


for _cmd in ("health", "tools", "propose", "run"):
    agent.add_command(
        click.Command(
            _cmd,
            help="Disponible via API REST del monitor; usa `buho monitor serve`.",
            callback=lambda name=_cmd: click.echo(f"`agent {name}` se expone en la API del monitor."),
        )
    )


@click.group("notify", context_settings=HELP_OPTS)
def notify() -> None:
    """Notificaciones Telegram de entrenamientos y benchmarks."""


@notify.command("status", context_settings=HELP_OPTS)
@json_option
def notify_status(as_json: bool) -> None:
    payload = simple_status("notify", commands=["bench-done", "train-done"])
    echo_result(payload, as_json=as_json, human=lambda d: ", ".join(d["commands"]))


_add_scripts(
    notify,
    [
        ("bench-done", "scripts/notify_bench_done.py", "Notifica fin de benchmark."),
        ("train-done", "scripts/notify_train_done.py", "Notifica fin de entrenamiento."),
    ],
)


@click.group("watchdog", context_settings=HELP_OPTS)
def watchdog() -> None:
    """Guardas de recursos."""


@watchdog.command("status", context_settings=HELP_OPTS)
@json_option
def watchdog_status(as_json: bool) -> None:
    payload = simple_status("watchdog", commands=["ram"])
    echo_result(payload, as_json=as_json, human=lambda d: ", ".join(d["commands"]))


watchdog.add_command(script_command("scripts/ram_watchdog.py", name="ram", help_text="Mata jobs si RAM/swap superan limites."))


ALL_GROUPS = [
    generate,
    dft_jobs,
    active_learning,
    phase2_force,
    monitor,
    activity,
    screening,
    candidates,
    batches,
    ml,
    mlip,
    analysis,
    validate,
    bench,
    report,
    top8,
    structures,
    data,
    g0w0,
    u_scan,
    files,
    jobs,
    agent,
    notify,
    watchdog,
]
