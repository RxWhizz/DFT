# OghmaNano device step

OghmaNano is a drift-diffusion + optics device physics solver (not ML).

## Files generated

- `device_stack.json` — DFT-derived device parameters
- `sim/sim.json` — OghmaNano project (perovskite template + DFT params)
- `sim/materials/CsPbI3/nk.csv` — DFT n(ω)/k(ω) optical data
- `sim/materials/CsPbI3/mat.json` — material metadata

## To run

Either set `execute: true` in `configs/default_params.yaml` under `oghma_device:`
and rerun the workflow, or run manually:

```bash
cd sim && /usr/bin/oghma_core
```

Output `sim_info.dat` is parsed for PCE, Voc, Jsc, FF on next workflow run.
