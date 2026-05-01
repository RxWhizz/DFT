#!/usr/bin/env python
"""Apply the scissor operator correction to a CsPbI3 band structure."""

import logging
import sys
from pathlib import Path

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("apply_scissor")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dft_cspbi3.bandgap_correction import ScissorCorrection
from dft_cspbi3.plotting import plot_band_structure
from dft_cspbi3.postprocessing import get_band_structure, get_bandgap


@click.command()
@click.option(
    "--pbe-gpw",
    required=True,
    type=click.Path(exists=True),
    help="Path to PBE SCF .gpw file (for χ calculations).",
)
@click.option(
    "--bands-gpw",
    required=True,
    type=click.Path(exists=True),
    help="Path to bands .gpw file to apply scissor to.",
)
@click.option(
    "--soc-gpw",
    default=None,
    type=click.Path(exists=True),
    help="Path to PBE+SOC .gpw file. If not given, uses literature χSOC.",
)
@click.option(
    "--hse-gpw",
    default=None,
    type=click.Path(exists=True),
    help="Path to HSE06 .gpw file. If not given, uses literature χHSE.",
)
@click.option(
    "--phase",
    type=click.Choice(["alpha", "gamma", "delta"]),
    default="alpha",
    show_default=True,
)
@click.option(
    "--outdir",
    default="./scissor_results",
    show_default=True,
    type=click.Path(),
    help="Output directory for corrected band structure plots.",
)
@click.option(
    "--report",
    is_flag=True,
    default=False,
    help="Print comparison table vs. experimental values.",
)
def main(pbe_gpw, bands_gpw, soc_gpw, hse_gpw, phase, outdir, report):
    """Apply scissor correction Eg = E_PBE+D3 + χSOC + χHSE to a band structure.

    Example:

        python apply_scissor.py \\
            --pbe-gpw calculations/alpha/02_scf/scf.gpw \\
            --bands-gpw calculations/alpha/03_bands/bands.gpw \\
            --phase alpha --report
    """
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    corrector = ScissorCorrection()
    result = corrector.run_full_correction(
        gpw_pbe=pbe_gpw,
        gpw_pbe_soc=soc_gpw,
        gpw_hse=hse_gpw,
        phase=phase,
    )

    click.echo(f"\nScissor correction results — {phase}-CsPbI3")
    click.echo(f"  E_PBE+D3  : {result.e_pbe_d3:.4f} eV")
    click.echo(f"  χSOC      : {result.chi_soc:+.4f} eV")
    click.echo(f"  χHSE      : {result.chi_hse:+.4f} eV")
    click.echo(f"  Eg_corr   : {result.e_corrected:.4f} eV")
    if result.e_experimental:
        click.echo(f"  Eg_exp    : {result.e_experimental:.4f} eV")
        click.echo(f"  MAE       : {result.mae_vs_experiment:.4f} eV")

    if report:
        corrector.report(phase=phase)

    # Load bands and apply scissor
    bs = get_band_structure(bands_gpw)
    cbm_shift = result.chi_soc + result.chi_hse
    corrector.apply_scissor_to_bands(bs, vbm_shift=0.0, cbm_shift=cbm_shift)

    fig = plot_band_structure(
        bs,
        title=f"{phase}-CsPbI3 band structure (scissor corrected)",
        output_prefix=f"bands_scissor_{phase}",
        output_dir=out,
    )
    click.echo(f"\nCorrected band structure saved to {out}/bands_scissor_{phase}.{{png,pdf}}")


if __name__ == "__main__":
    main()
