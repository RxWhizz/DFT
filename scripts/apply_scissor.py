#!/usr/bin/env python
"""Aplica scissor operator correction CsPbI3 banda estructura."""

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
    help="Ruta .gpw PBE SCF para cálculos χ.",
)
@click.option(
    "--bands-gpw",
    required=True,
    type=click.Path(exists=True),
    help="Ruta .gpw bandas para aplicar scissor.",
)
@click.option(
    "--soc-gpw",
    default=None,
    type=click.Path(exists=True),
    help="Ruta .gpw PBE+SOC. Si falta, usa χSOC literatura.",
)
@click.option(
    "--hse-gpw",
    default=None,
    type=click.Path(exists=True),
    help="Ruta .gpw HSE06. Si falta, usa χHSE literatura.",
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
    help="Directorio salida bandas corregidas.",
)
@click.option(
    "--report",
    is_flag=True,
    default=False,
    help="Imprime tabla vs valores experimentales.",
)
def main(pbe_gpw, bands_gpw, soc_gpw, hse_gpw, phase, outdir, report):
    """Aplica scissor correction Eg = E_PBE+D3 + χSOC + χHSE banda estructura."""
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

    # Carga bands y aplica scissor
    bs = get_band_structure(bands_gpw)
    cbm_shift = result.chi_soc + result.chi_hse
    corrector.apply_scissor_to_bands(bs, vbm_shift=0.0, cbm_shift=cbm_shift)

    fig = plot_band_structure(
        bs,
        title=f"{phase}-CsPbI3 band structure (scissor corrected)",
        output_prefix=f"bands_scissor_{phase}",
        output_dir=out,
    )
    click.echo(f"\nBandas corregidas en {out}/bands_scissor_{phase}.{{png,pdf}}")


if __name__ == "__main__":
    main()
