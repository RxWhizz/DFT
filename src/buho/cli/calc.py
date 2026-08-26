"""Comandos de calculo DFT del CLI BUHO."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import click

from ._common import HELP_OPTS, bundle_file, data_path, echo_result, json_option, script_command


def _workflow_constants() -> dict[str, Any]:
    source = bundle_file("src", "dft_cspbi3", "workflow_manager.py")
    if not source.is_file():
        raise click.ClickException(f"No se encuentra workflow_manager.py en {source}")

    tree = ast.parse(source.read_text(encoding="utf-8"))
    wanted = {"STEP_ORDER", "STEP_DIRS", "STEP_DONE_FILES"}
    found: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in wanted:
                found[target.id] = ast.literal_eval(node.value)
    missing = wanted - set(found)
    if missing:
        raise click.ClickException(
            "No se pudieron leer constantes de workflow: " + ", ".join(sorted(missing))
        )
    return found


def _step_rows(workdir: str, phase: str) -> list[dict[str, Any]]:
    const = _workflow_constants()
    phase_dir = data_path(workdir) / phase
    rows = []
    for step in const["STEP_ORDER"]:
        rel_dir = const["STEP_DIRS"].get(step, step)
        done_name = const["STEP_DONE_FILES"].get(step, f"{step}.gpw")
        step_dir = phase_dir / rel_dir
        done = step_dir / done_name
        rows.append(
            {
                "step": step,
                "dir": str(step_dir),
                "done_file": done_name,
                "exists": done.exists(),
                "status": "done" if done.exists() else "pending",
            }
        )
    return rows


def _steps_human(rows: list[dict[str, Any]]) -> str:
    lines = [f"{'step':<20} {'status':<10} dir", "-" * 72]
    for row in rows:
        lines.append(f"{row['step']:<20} {row['status']:<10} {row['dir']}")
    return "\n".join(lines)


@click.group("calc", context_settings=HELP_OPTS)
def calc() -> None:
    """Calculos DFT, pasos del workflow y postproceso."""


@click.command("steps", context_settings=HELP_OPTS)
@click.option("--phase", default="alpha", show_default=True, help="Fase o composicion.")
@click.option("--workdir", default="./calculations", show_default=True, help="Directorio raiz.")
@json_option
def steps_cmd(phase: str, workdir: str, as_json: bool) -> None:
    """Lista los 26 pasos del workflow y sus artefactos de finalizacion."""
    rows = _step_rows(workdir, phase)
    data = {"phase": phase, "workdir": str(data_path(workdir)), "steps": rows}
    echo_result(data, as_json=as_json, human=lambda d: _steps_human(d["steps"]))


@click.command("status", context_settings=HELP_OPTS)
@click.option("--phase", default="alpha", show_default=True, help="Fase o composicion.")
@click.option("--workdir", default="./calculations", show_default=True, help="Directorio raiz.")
@click.option("--config", default="configs/default_params.yaml", show_default=True, help="YAML.")
@json_option
def status_cmd(phase: str, workdir: str, config: str, as_json: bool) -> None:
    """Muestra estado del workflow sin cargar GPAW."""
    rows = _step_rows(workdir, phase)
    done = sum(1 for r in rows if r["exists"])
    data = {
        "phase": phase,
        "workdir": str(data_path(workdir)),
        "config": str(data_path(config)),
        "done": done,
        "total": len(rows),
        "steps": rows,
    }
    echo_result(
        data,
        as_json=as_json,
        human=lambda d: f"{d['done']}/{d['total']} pasos completos\n" + _steps_human(d["steps"]),
    )


def _run_workflow(
    *,
    phase: str,
    config: str,
    composition_config: str | None,
    workdir: str,
    steps: str,
    soc: bool,
    hse06: bool,
    convergence_test: bool,
    phonons: bool,
    validate: bool,
    report: bool,
    dry_run: bool,
    phonon_supercell: str,
    force_threshold: float,
) -> None:
    from dft_cspbi3 import DFTWorkflow

    config_path = data_path(config)
    work_root = data_path(workdir)
    report_dir = work_root / phase / "reports"

    click.echo("")
    click.echo("=" * 60)
    click.echo(f"  Pipeline DFT BUHO | phase={phase} | dry_run={dry_run}")
    click.echo("=" * 60)
    click.echo("")

    if convergence_test:
        _run_convergence_tests(phase, config_path, work_root, report_dir)

    step_list = [s.strip() for s in steps.split(",") if s.strip()]
    if soc and "soc" not in step_list:
        step_list.append("soc")
    if hse06 and "hse06" not in step_list:
        step_list.append("hse06")

    wf = DFTWorkflow(
        phase=phase,
        config_path=config_path if config_path.exists() else None,
        composition_config=composition_config,
        work_dir=work_root,
        dry_run=dry_run,
    )

    click.echo(f"Pasos: {step_list}")
    wf.run(steps=step_list)

    for line in _steps_human(_step_rows(str(work_root), phase)).splitlines():
        click.echo(line)

    if dry_run:
        click.echo("\nDry-run completo. GPAW no ejecutado.")
        return

    hessian_result = None
    phonon_result = None
    if phonons:
        hessian_result, phonon_result = _run_vibrational(
            phase=phase,
            work_root=work_root,
            config_path=config_path,
            supercell_str=phonon_supercell,
            force_threshold=force_threshold,
        )

    validation_results: dict[str, Any] = {}
    if validate:
        validation_results = _run_validation(
            phase=phase,
            work_root=work_root,
            soc_enabled=soc,
            hessian_result=hessian_result,
            phonon_result=phonon_result,
        )
        _print_validation_summary(validation_results)

    if report:
        _generate_all_reports(
            phase=phase,
            work_root=work_root,
            config_path=config_path,
            validation_results=validation_results,
            hessian_result=hessian_result,
            phonon_result=phonon_result,
            report_dir=report_dir,
        )
        click.echo(f"\nReportes escritos en: {report_dir}")

    click.echo("\nPipeline completo.\n")


@click.command("run", context_settings=HELP_OPTS)
@click.option("--phase", default="alpha", show_default=True, help="Fase cristalina o nombre.")
@click.option("--config", default="configs/default_params.yaml", show_default=True, help="YAML.")
@click.option("--composition-config", default=None, help="YAML por composicion.")
@click.option("--workdir", default="./calculations", show_default=True, help="Directorio raiz.")
@click.option("--steps", default="relax,scf,bands,dos", show_default=True, help="Pasos separados por coma.")
@click.option("--soc", is_flag=True, help="Agrega SOC perturbativo.")
@click.option("--hse06", is_flag=True, help="Agrega HSE06.")
@click.option("--convergence-test", is_flag=True, help="Corre convergencia antes del workflow.")
@click.option("--phonons", is_flag=True, help="Calcula Hessiano/fonones.")
@click.option("--validate", is_flag=True, help="Ejecuta validacion cientifica.")
@click.option("--report", is_flag=True, help="Genera reportes Markdown.")
@click.option("--dry-run", is_flag=True, help="Prepara entradas sin ejecutar GPAW.")
@click.option("--phonon-supercell", default="2,2,2", show_default=True, help="Supercelda fonones.")
@click.option("--force-threshold", default=0.05, show_default=True, type=float, help="Fuerza max eV/A.")
def run_cmd(
    phase: str,
    config: str,
    composition_config: str | None,
    workdir: str,
    steps: str,
    soc: bool,
    hse06: bool,
    convergence_test: bool,
    phonons: bool,
    validate: bool,
    report: bool,
    dry_run: bool,
    phonon_supercell: str,
    force_threshold: float,
) -> None:
    """Ejecuta el workflow DFT."""
    _run_workflow(
        phase=phase,
        config=config,
        composition_config=composition_config,
        workdir=workdir,
        steps=steps,
        soc=soc,
        hse06=hse06,
        convergence_test=convergence_test,
        phonons=phonons,
        validate=validate,
        report=report,
        dry_run=dry_run,
        phonon_supercell=phonon_supercell,
        force_threshold=force_threshold,
    )


@click.command("step", context_settings=HELP_OPTS)
@click.argument("step_name")
@click.option("--phase", default="alpha", show_default=True, help="Fase cristalina o nombre.")
@click.option("--config", default="configs/default_params.yaml", show_default=True, help="YAML.")
@click.option("--composition-config", default=None, help="YAML por composicion.")
@click.option("--workdir", default="./calculations", show_default=True, help="Directorio raiz.")
@click.option("--dry-run", is_flag=True, help="Prepara entradas sin ejecutar GPAW.")
def step_cmd(
    step_name: str,
    phase: str,
    config: str,
    composition_config: str | None,
    workdir: str,
    dry_run: bool,
) -> None:
    """Ejecuta un solo paso definido en workflow_manager.STEP_ORDER."""
    valid = set(_workflow_constants()["STEP_ORDER"])
    if step_name not in valid:
        raise click.UsageError(
            f"Paso desconocido '{step_name}'. Usa `buho calc steps` para ver la lista."
        )
    _run_workflow(
        phase=phase,
        config=config,
        composition_config=composition_config,
        workdir=workdir,
        steps=step_name,
        soc=False,
        hse06=False,
        convergence_test=False,
        phonons=False,
        validate=False,
        report=False,
        dry_run=dry_run,
        phonon_supercell="2,2,2",
        force_threshold=0.05,
    )


@click.command("report", context_settings=HELP_OPTS)
@click.option("--phase", default="alpha", show_default=True, help="Fase.")
@click.option("--workdir", default="./calculations", show_default=True, help="Directorio raiz.")
@click.option("--config", default="configs/default_params.yaml", show_default=True, help="YAML.")
@click.option("--soc", is_flag=True, help="Incluye validacion SOC si hay datos.")
@click.option("--with-vibrational", is_flag=True, help="Incluye reporte vibracional si hay datos.")
def report_cmd(phase: str, workdir: str, config: str, soc: bool, with_vibrational: bool) -> None:
    """Genera reportes desde salidas existentes."""
    work_root = data_path(workdir)
    report_dir = work_root / phase / "reports"
    config_path = data_path(config)

    validation_results = _run_validation(
        phase=phase,
        work_root=work_root,
        soc_enabled=soc,
        hessian_result=None,
        phonon_result=None,
    )
    _generate_all_reports(
        phase=phase,
        work_root=work_root,
        config_path=config_path,
        validation_results=validation_results,
        hessian_result=None,
        phonon_result=None,
        report_dir=report_dir,
    )
    click.echo(f"Reportes escritos en: {report_dir}")


def _run_convergence_tests(
    phase: str,
    config_path: Path,
    work_root: Path,
    report_dir: Path,
) -> None:
    from dft_cspbi3 import StructureBuilder
    from dft_cspbi3.convergence import run_both
    from dft_cspbi3.plotting import plot_convergence

    click.echo("\n[convergencia] Corriendo Ecut y malla k...")
    atoms = StructureBuilder.load_phase(phase)
    conv_dir = work_root / phase / "convergence"

    df_ecut, df_kpts = run_both(
        atoms,
        config_path=config_path if config_path.exists() else None,
        work_dir=conv_dir,
    )

    df_ecut.to_csv(conv_dir / "encut" / "convergence_ecut.csv", index=False)
    df_kpts.to_csv(conv_dir / "kpoints" / "convergence_kpts.csv", index=False)

    plot_convergence(
        df_ecut,
        "ecut_eV",
        "delta E (meV/atom)",
        1.0,
        "Ecut convergence",
        "ecut_conv",
        output_dir=report_dir,
    )
    plot_convergence(
        df_kpts,
        "nkpts_total",
        "delta E (meV/atom)",
        1.0,
        "k-mesh convergence",
        "kpts_conv",
        output_dir=report_dir,
    )
    click.echo("[convergencia] Listo.")


def _run_vibrational(
    phase: str,
    work_root: Path,
    config_path: Path,
    supercell_str: str,
    force_threshold: float,
) -> tuple[Any, Any]:
    from dft_cspbi3 import GPAWCalculatorFactory
    from dft_cspbi3.validation import compute_hessian, compute_phonons

    sc_ints = tuple(int(x) for x in supercell_str.split(","))
    if len(sc_ints) != 3:
        raise click.UsageError(f"--phonon-supercell debe tener formato a,b,c: {supercell_str}")

    click.echo(f"\n[vibracional] Cargando estructura relajada fase={phase}...")
    factory = GPAWCalculatorFactory(config_path if config_path.exists() else None)

    relax_gpw = work_root / phase / "01_relax" / "relax.gpw"
    if not relax_gpw.exists():
        raise click.ClickException(
            f"relax.gpw no existe en {relax_gpw}. Ejecuta el paso 'relax' primero."
        )

    from gpaw import GPAW

    ref_calc = GPAW(str(relax_gpw))
    atoms = ref_calc.get_atoms()

    vib_dir = work_root / phase / "07_vibrational"
    hess_dir = vib_dir / "hessian"
    phon_dir = vib_dir / "phonons"

    click.echo("[vibracional] Calculando Hessiano...")
    hess_calc = factory.create("scf", txt=str(hess_dir / "hess.txt"))
    hessian_result = compute_hessian(
        atoms=atoms,
        calc=hess_calc,
        delta=0.01,
        work_dir=hess_dir,
        force_threshold_eV_Ang=force_threshold,
    )
    click.echo(f"  {hessian_result.summary}")

    click.echo(f"[vibracional] Calculando fonones (supercelda {sc_ints})...")
    phon_calc = factory.create("scf", txt=str(phon_dir / "phon.txt"))
    phonon_result = compute_phonons(
        atoms=atoms,
        calc=phon_calc,
        supercell=sc_ints,
        delta=0.05,
        work_dir=phon_dir,
    )
    click.echo(f"  {phonon_result.summary}")

    return hessian_result, phonon_result


def _run_validation(
    phase: str,
    work_root: Path,
    soc_enabled: bool,
    hessian_result: Any,
    phonon_result: Any,
) -> dict[str, Any]:
    from dft_cspbi3.validation import (
        classify_electronic_structure,
        soc_was_applied,
        validate_physical_checks,
        validate_scf,
        validate_soc,
    )

    phase_dir = work_root / phase
    results: dict[str, Any] = {}

    scf_txt = phase_dir / "02_scf" / "scf.txt"
    scf_gpw = phase_dir / "02_scf" / "scf.gpw"

    if scf_txt.exists():
        results["scf_report"] = validate_scf(scf_txt)
        click.echo(
            f"[validate] SCF converged={results['scf_report'].converged} | "
            f"iters={results['scf_report'].iterations}"
        )
    if scf_gpw.exists():
        results["physical_checks"] = validate_physical_checks(scf_gpw)
        results["electronic_structure"] = classify_electronic_structure(scf_gpw)
        click.echo(
            f"[validate] E_tot={results['physical_checks'].energy_eV:.4f} eV | "
            f"type={results['electronic_structure'].get('type', '?')}"
        )

    soc_dir = phase_dir / "05_soc"
    if soc_enabled or soc_was_applied(soc_dir):
        eig_npy = soc_dir / "soc_eigenvalues.npy"
        spin_npy = soc_dir / "soc_spin_projections.npy"
        if scf_gpw.exists() and eig_npy.exists():
            results["soc_report"] = validate_soc(scf_gpw, eig_npy, spin_npy)
            soc = results["soc_report"]
            click.echo(
                f"[validate] SOC chi_SOC={soc.chi_soc_eV:+.3f} eV | "
                f"plausible={soc.chi_soc_plausible}"
            )

    if hessian_result is not None:
        results["hessian_result"] = hessian_result
    if phonon_result is not None:
        results["phonon_result"] = phonon_result

    return results


def _print_validation_summary(results: dict[str, Any]) -> None:
    click.echo("\n--- Resumen validacion ---")
    flags: list[str] = []
    for key in ("scf_report", "physical_checks", "soc_report"):
        obj = results.get(key)
        if obj and hasattr(obj, "flags"):
            flags.extend(obj.flags)

    if not flags:
        click.echo("  Todo OK. Sin flags criticos.")
    else:
        click.echo(f"  Flags: {len(flags)}")
        for flag in flags:
            click.echo(f"    - {flag}")
    click.echo("-" * 26)


def _generate_all_reports(
    phase: str,
    work_root: Path,
    config_path: Path,
    validation_results: dict[str, Any],
    hessian_result: Any,
    phonon_result: Any,
    report_dir: Path,
) -> None:
    from dft_cspbi3 import GPAWCalculatorFactory
    from dft_cspbi3.reporting import (
        ValidationData,
        generate_assumptions,
        generate_methodology,
        generate_validation_report,
        generate_vibrational_report,
    )
    from dft_cspbi3.validation.stability import (
        classify_combined,
        classify_from_hessian,
        classify_from_phonons,
    )

    report_dir.mkdir(parents=True, exist_ok=True)

    factory = GPAWCalculatorFactory(config_path if config_path.exists() else None)
    cfg = factory.config
    xc = cfg.get("scf", {}).get("xc", "PBEsol")
    ecut = cfg.get("scf", {}).get("ecut", 450)
    kpts = cfg.get("scf", {}).get("kpts", [6, 6, 6])

    params_dict = {
        "phase": f"{phase}-CsPbI3",
        "xc": xc,
        "ecut_eV": ecut,
        "kpts": kpts,
        "soc_mode": "perturbative",
        "fmax": 0.01,
    }

    es = validation_results.get("electronic_structure", {})
    pc = validation_results.get("physical_checks")

    vdata = ValidationData(
        phase=phase,
        formula="CsPbI3",
        n_atoms=es.get("n_atoms", 0) if isinstance(es, dict) else _guess_natoms(phase),
        volume_ang3=es.get("volume_ang3", float("nan")) if isinstance(es, dict) else float("nan"),
        xc=xc,
        ecut_eV=ecut,
        kpts=kpts,
        total_energy_eV=pc.energy_eV if pc else float("nan"),
        fermi_level_eV=pc.fermi_level_eV if pc else float("nan"),
        bandgap_eV=es.get("bandgap_eV") if isinstance(es, dict) else None,
        electronic_type=es.get("type", "unknown") if isinstance(es, dict) else "unknown",
        scf_report=validation_results.get("scf_report"),
        physical_checks=pc,
        soc_report=validation_results.get("soc_report"),
    )

    click.echo(f"  - {generate_validation_report(vdata, output_dir=report_dir)}")

    if hessian_result is not None or phonon_result is not None:
        stability = None
        if hessian_result is not None and phonon_result is not None:
            stability = classify_combined(hessian_result, phonon_result)
        elif hessian_result is not None:
            stability = classify_from_hessian(hessian_result)
        elif phonon_result is not None:
            stability = classify_from_phonons(phonon_result)
        click.echo(
            f"  - {generate_vibrational_report(hessian_result, phonon_result, stability, phase, report_dir)}"
        )

    click.echo(f"  - {generate_methodology(params=params_dict, output_dir=report_dir)}")
    click.echo(f"  - {generate_assumptions(params=params_dict, output_dir=report_dir)}")


def _guess_natoms(phase: str) -> int:
    return {"alpha": 5, "gamma": 20, "delta": 20}.get(phase, 5)


calc.add_command(run_cmd)
calc.add_command(status_cmd)
calc.add_command(report_cmd)
calc.add_command(steps_cmd)
calc.add_command(step_cmd)
calc.add_command(
    script_command(
        "scripts/run_convergence_test.py",
        name="convergence",
        help_text="Ejecuta pruebas de convergencia heredadas.",
    )
)
calc.add_command(
    script_command("scripts/apply_scissor.py", name="scissor", help_text="Aplica correccion scissor.")
)
calc.add_command(
    script_command("scripts/band_calc.py", name="bands", help_text="Calcula bandas non-SCF.")
)
calc.add_command(
    script_command("scripts/analyze_existing.py", name="analyze", help_text="Analiza salidas existentes.")
)
calc.add_command(
    script_command(
        "run_hse06_nsc_dos.py",
        name="hse06-nsc-dos",
        help_text="Calcula DOS HSE06 corregida en malla densa.",
    )
)
