# OghmaNano device step

OghmaNano is not ML; it is a device-physics drift-diffusion/optics solver.

This step prepares DFT-derived device inputs in `device_stack.json`.
Use the GUI to create or validate the Oghma project, then map the absorber
band gap, thickness, dielectric constant, and optical data from this folder.

Detected runner:

```bash
<install OghmaNano first: bash scripts/install_oghma_ubuntu.sh>
```

If a validated Oghma project writes `sim_info.dat` in this directory,
rerun the workflow step to parse PCE, Voc, Jsc, and FF into
`oghma_device_result.json`.
