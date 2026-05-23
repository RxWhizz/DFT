#!/usr/bin/env python3
"""DFT-CsPbI3 pipeline CLI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

# Logging setup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dft_cspbi3.main")


# CLI root


@click.group()
@click.option("--debug", is_flag=True, help="Activa logs DEBUG.")
def cli(debug: bool) -> None:
    """Pipeline DFT CsPbI3 con GPAW."""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)


# ejecuta command


@cli.command()
@click.option(
    "--phase",
    default="alpha",
    type=str,
    show_default=True,
    help="Fase cristalina (alpha/gamma/delta) o nombre con --composition-config.",
)
@click.option(
    "--config",
    default="configs/default_params.yaml",
    show_default=True,
    type=click.Path(),
    help="Ruta YAML parámetros.",
)
@click.option(
    "--composition-config",
    default=None,
    type=click.Path(),
    help="YAML por composición: estructuras, refs gap. Default desde default_params.yaml.",
)
@click.option(
    "--workdir",
    default="./calculations",
    show_default=True,
    type=click.Path(),
    help="Directorio raíz cálculos.",
)
@click.option(
    "--steps",
    default="relax,scf,bands,dos",
    show_default=True,
    help="Pasos DFT separados por coma.",
)
@click.option("--soc", is_flag=True, help="Aplica SOC perturbativo tras SCF.")
@click.option("--hse06", is_flag=True, help="Ejecuta funcional híbrido HSE06.")
@click.option(
    "--convergence-test",
    is_flag=True,
    help="Corre convergencia Ecut y malla k antes del workflow.",
)
@click.option(
    "--phonons",
    is_flag=True,
    help="Calcula dispersión fonónica por supercelda.",
)
@click.option(
    "--validate",
    is_flag=True,
    help="Ejecuta validación científica tras DFT.",
)
@click.option(
    "--report",
    is_flag=True,
    help="Genera reportes Markdown en <workdir>/<phase>/reports/.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Prepara entradas sin ejecutar GPAW.",
)
@click.option(
    "--phonon-supercell",
    default="2,2,2",
    show_default=True,
    help="Supercelda fonones, ej. '2,2,2'.",
)
@click.option(
    "--force-threshold",
    default=0.05,
    show_default=True,
    type=float,
    help="Fuerza max (eV/Å) antes de Hessiano/fonones.",
)
def run(
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
    """Ejecuta pipeline DFT completo por fase."""
    from dft_cspbi3 import DFTWorkflow, GPAWCalculatorFactory, StructureBuilder

    config_path = Path(config)
    work_root = Path(workdir)
    report_dir = work_root / phase / "reports"

    click.echo(f"\n{'='*60}")
    click.echo(f"  DFT pipeline  |  phase={phase}  |  dry_run={dry_run}")
    click.echo(f"{'='*60}\n")

    if convergence_test:
        _run_convergence_tests(phase, config_path, work_root, report_dir)

    # Construye step list
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
    wf.get_status()

    if dry_run:
        click.echo("\nDry-run completo. GPAW no ejecutado.")
        return

    # Phonons / Hessiano (opcional)
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

    # Scientific validación
    validation_results: dict = {}
    if validate:
        validation_results = _run_validation(
            phase=phase,
            work_root=work_root,
            soc_enabled=soc,
            hessian_result=hessian_result,
            phonon_result=phonon_result,
        )
        _print_validation_summary(validation_results)

    # Report generación
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


# estado command


@cli.command()
@click.option("--phase", default="alpha", type=str)
@click.option("--workdir", default="./calculations", type=click.Path())
@click.option("--config", default="configs/default_params.yaml", type=click.Path())
def status(phase: str, workdir: str, config: str) -> None:
    """Nota técnica."""
    from dft_cspbi3 import DFTWorkflow

    wf = DFTWorkflow(phase=phase, config_path=Path(config) if Path(config).exists() else None,
                     work_dir=Path(workdir))
    wf.get_status()


# reporte command (standalone, en existente.gpw archivos)


@cli.command("report")
@click.option("--phase", default="alpha", type=str)
@click.option("--workdir", default="./calculations", type=click.Path())
@click.option("--config", default="configs/default_params.yaml", type=click.Path())
@click.option("--soc", is_flag=True)
@click.option("--with-vibrational", is_flag=True, help="Incluye reporte vibracional si hay .npy.")
def report_cmd(phase: str, workdir: str, config: str, soc: bool, with_vibrational: bool) -> None:
    """Genera all Markdown reportes desde existente cálculo salidas."""
    work_root = Path(workdir)
    report_dir = work_root / phase / "reports"
    config_path = Path(config)

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


# Internal helpers


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

    plot_convergence(df_ecut, "ecut_eV", "ΔE (meV/atom)", 1.0, "Ecut convergence",
                     "ecut_conv", output_dir=report_dir)
    plot_convergence(df_kpts, "nkpts_total", "ΔE (meV/atom)", 1.0, "k-mesh convergence",
                     "kpts_conv", output_dir=report_dir)
    click.echo("[convergencia] Listo.")


def _run_vibrational(
    phase: str,
    work_root: Path,
    config_path: Path,
    supercell_str: str,
    force_threshold: float,
) -> tuple:
    from dft_cspbi3 import GPAWCalculatorFactory, StructureBuilder
    from dft_cspbi3.validation import compute_hessian, compute_phonons

    sc_ints = tuple(int(x) for x in supercell_str.split(","))
    assert len(sc_ints) == 3, f"Supercell must be 'a,b,c' format, got: {supercell_str}"

    click.echo(f"\n[vibracional] Cargando estructura relajada fase={phase}...")
    factory = GPAWCalculatorFactory(config_path if config_path.exists() else None)

    relax_gpw = work_root / phase / "01_relax" / "relax.gpw"
    if not relax_gpw.exists():
        click.echo(f"  ERROR: relax.gpw no existe en {relax_gpw}. Ejecuta paso 'relax' primero.")
        return None, None

    from gpaw import GPAW
    ref_calc = GPAW(str(relax_gpw))
    atoms = ref_calc.get_atoms()

    vib_dir = work_root / phase / "07_vibrational"
    hess_dir = vib_dir / "hessian"
    phon_dir = vib_dir / "phonons"

    # Hessiano
    click.echo("[vibracional] Calculando Hessiano (diferencias finitas)...")
    hess_calc = factory.create("scf", txt=str(hess_dir / "hess.txt"))
    hessian_result = compute_hessian(
        atoms=atoms,
        calc=hess_calc,
        delta=0.01,
        work_dir=hess_dir,
        force_threshold_eV_Ang=force_threshold,
    )
    click.echo(f"  {hessian_result.summary}")

    # Phonons
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
    hessian_result,
    phonon_result,
) -> dict:
    from dft_cspbi3.validation import (
        validate_scf,
        validate_physical_checks,
        classify_electronic_structure,
        validate_soc,
        soc_was_applied,
    )

    phase_dir = work_root / phase
    results: dict = {}

    # SCF validación
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

    # SOC validación
    soc_dir = phase_dir / "05_soc"
    if soc_enabled or soc_was_applied(soc_dir):
        eig_npy = soc_dir / "soc_eigenvalues.npy"
        spin_npy = soc_dir / "soc_spin_projections.npy"
        if scf_gpw.exists() and eig_npy.exists():
            results["soc_report"] = validate_soc(scf_gpw, eig_npy, spin_npy)
            soc = results["soc_report"]
            click.echo(
                f"[validate] SOC χSOC={soc.chi_soc_eV:+.3f} eV | "
                f"plausible={soc.chi_soc_plausible}"
            )

    # Hessiano / fonón
    if hessian_result is not None:
        results["hessian_result"] = hessian_result
    if phonon_result is not None:
        results["phonon_result"] = phonon_result

    return results


def _print_validation_summary(results: dict) -> None:
    click.echo("\n--- Resumen Validación ---")
    all_flags: list[str] = []
    for key in ("scf_report", "physical_checks", "soc_report"):
        obj = results.get(key)
        if obj and hasattr(obj, "flags"):
            all_flags.extend(obj.flags)

    if not all_flags:
        click.echo("  ✅ Todo OK. Sin flags críticos.")
    else:
        click.echo(f"  ⚠ flags: {len(all_flags)}")
        for f in all_flags:
            click.echo(f"    • {f}")
    click.echo("-" * 26)


def _generate_all_reports(
    phase: str,
    work_root: Path,
    config_path: Path,
    validation_results: dict,
    hessian_result,
    phonon_result,
    report_dir: Path,
) -> None:
    from dft_cspbi3 import GPAWCalculatorFactory
    from dft_cspbi3.reporting import (
        ValidationData,
        generate_validation_report,
        generate_vibrational_report,
        generate_methodology,
        generate_assumptions,
    )
    from dft_cspbi3.validation.stability import classify_combined, classify_from_hessian, classify_from_phonons

    report_dir.mkdir(parents=True, exist_ok=True)

    # Carga params desde config
    factory = GPAWCalculatorFactory(config_path if config_path.exists() else None)
    cfg = factory.config
    xc = cfg.get("scf", {}).get("xc", "PBEsol")
    ecut = cfg.get("scf", {}).get("ecut", 450)
    kpts = cfg.get("scf", {}).get("kpts", [6, 6, 6])

    params_dict = {
        "phase": f"{phase}-CsPbI₃",
        "xc": xc,
        "ecut_eV": ecut,
        "kpts": kpts,
        "soc_mode": "perturbative (spinorbit_eigenvalues)",
        "fmax": 0.01,
    }

    # Collect electronic estructura info
    es = validation_results.get("electronic_structure", {})
    pc = validation_results.get("physical_checks")

    vdata = ValidationData(
        phase=phase,
        formula="CsPbI3",
        n_atoms=es.get("n_atoms", 0) if isinstance(es, dict) and "n_atoms" in es else _guess_natoms(phase),
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

    p1 = generate_validation_report(vdata, output_dir=report_dir)
    click.echo(f"  • {p1}")

    if hessian_result is not None or phonon_result is not None:
        stability = None
        if hessian_result is not None and phonon_result is not None:
            stability = classify_combined(hessian_result, phonon_result)
        elif hessian_result is not None:
            stability = classify_from_hessian(hessian_result)
        elif phonon_result is not None:
            stability = classify_from_phonons(phonon_result)

        p2 = generate_vibrational_report(
            hessian_result=hessian_result,
            phonon_result=phonon_result,
            stability_report=stability,
            phase=phase,
            output_dir=report_dir,
        )
        click.echo(f"  • {p2}")

    p3 = generate_methodology(params=params_dict, output_dir=report_dir)
    click.echo(f"  • {p3}")

    p4 = generate_assumptions(params=params_dict, output_dir=report_dir)
    click.echo(f"  • {p4}")


def _guess_natoms(phase: str) -> int:
    return {"alpha": 5, "gamma": 20, "delta": 20}.get(phase, 5)


# Entry point

if __name__ == "__main__":
    cli()
