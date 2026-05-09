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

```powershell
& "C:\Program Files (x86)\OghmaNano\oghma_core.exe" --sim-root-path "C:\Users\LUIS\Documents\GitHub\DFT\.tmp_pytest\pytest-of-LUIS\pytest-16\test_oghma_device_step_prepare0\alpha\14_oghma_device\sim" --gui --html --simmode segment0@jv --lockfile "C:\Users\LUIS\Documents\GitHub\DFT\.tmp_pytest\pytest-of-LUIS\pytest-16\test_oghma_device_step_prepare0\alpha\14_oghma_device\sim\lock0.dat"
```

Linux/Wine runs use the same worker arguments, with `xvfb-run -a --` and the Wine S: drive mapping.

Output `sim_info.dat` is parsed for PCE, Voc, Jsc, FF on next workflow run.
