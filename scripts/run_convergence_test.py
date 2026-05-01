#!/usr/bin/env python
"""CLI script to run Ecut and k-point convergence tests for CsPbI3."""

import logging
import sys
from pathlib import Path

import click
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_convergence_test")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dft_cspbi3.convergence import find_converged_value, run_both, test_encut, test_kpoints
from dft_cspbi3.plotting import plot_convergence
from dft_cspbi3.structure_builder import StructureBuilder


@click.command()
@click.option(
    "--test",
    type=click.Choice(["encut", "kpoints", "both"]),
    default="both",
    show_default=True,
    help="Which convergence parameter to sweep.",
)
@click.option(
    "--phase",
    type=click.Choice(["alpha", "gamma", "delta"]),
    default="alpha",
    show_default=True,
    help="CsPbI3 phase to use as test structure.",
)
@click.option(
    "--workdir",
    default="./convergence",
    show_default=True,
    type=click.Path(),
    help="Root directory for convergence subdirectories.",
)
@click.option(
    "--threshold",
    default=1.0,
    show_default=True,
    type=float,
    help="Convergence threshold in meV/atom.",
)
@click.option(
    "--ecut-values",
    default="300,350,400,450,500,550",
    show_default=True,
    help="Comma-separated list of cutoff energies (eV) for --test encut.",
)
@click.option(
    "--kpt-meshes",
    default="4,6,8,10",
    show_default=True,
    help="Comma-separated list of NxNxN k-mesh sizes for --test kpoints.",
)
@click.option(
    "--plot",
    is_flag=True,
    default=True,
    help="Generate convergence plots (PNG + PDF).",
)
def main(test, phase, workdir, threshold, ecut_values, kpt_meshes, plot):
    """Run DFT convergence tests for CsPbI3.

    Example:

        python run_convergence_test.py --test both --phase alpha

        python run_convergence_test.py --test encut --ecut-values 300,400,500,600
    """
    work_dir = Path(workdir)
    atoms = StructureBuilder.load_phase(phase)
    click.echo(f"Loaded {phase}-CsPbI3: {len(atoms)} atoms")

    ecut_list = [float(v) for v in ecut_values.split(",")]
    k_list = [[n, n, n] for n in [int(v) for v in kpt_meshes.split(",")]]

    if test in ("encut", "both"):
        click.echo(f"\nRunning Ecut convergence: {ecut_list} eV")
        df_ecut = test_encut(ecut_list, atoms, work_dir=work_dir / "encut")
        click.echo(df_ecut.to_string(index=False, float_format="%.4f"))

        converged = find_converged_value(df_ecut, "ecut_eV", threshold)
        if converged:
            click.echo(f"\nConverged Ecut ({threshold} meV/atom): {converged:.0f} eV")
        else:
            click.echo(f"\nWARNING: Convergence not reached within {threshold} meV/atom")

        df_ecut.to_csv(work_dir / "encut_results.csv", index=False)

        if plot:
            plot_convergence(
                df_ecut,
                param="ecut_eV",
                ylabel="ΔE (meV/atom)",
                threshold_meV=threshold,
                title=f"Ecut convergence — {phase}-CsPbI3",
                output_prefix="convergence_encut",
                output_dir=work_dir,
            )
            click.echo(f"Plots saved to {work_dir}/convergence_encut.{{png,pdf}}")

    if test in ("kpoints", "both"):
        click.echo(f"\nRunning k-mesh convergence: {k_list}")
        df_kpts = test_kpoints(k_list, atoms, work_dir=work_dir / "kpoints")
        click.echo(df_kpts.to_string(index=False, float_format="%.4f"))

        converged_k = find_converged_value(df_kpts, "nkpts_total", threshold)
        if converged_k:
            click.echo(f"\nConverged k-mesh ({threshold} meV/atom): {int(converged_k)} total k-points")

        df_kpts.to_csv(work_dir / "kpoints_results.csv", index=False)

        if plot:
            plot_convergence(
                df_kpts,
                param="nkpts_total",
                ylabel="ΔE (meV/atom)",
                threshold_meV=threshold,
                title=f"k-mesh convergence — {phase}-CsPbI3",
                output_prefix="convergence_kpoints",
                output_dir=work_dir,
            )
            click.echo(f"Plots saved to {work_dir}/convergence_kpoints.{{png,pdf}}")

    click.echo(f"\nConvergence test complete. Results in: {work_dir}")


if __name__ == "__main__":
    main()
