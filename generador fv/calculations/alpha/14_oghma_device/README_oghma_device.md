# Paso dispositivo OghmaNano

OghmaNano = solver drift-diffusion + optica. No ML.

## Archivos

- `device_stack.json` — parametros dispositivo desde DFT
- `sim/sim.json` — proyecto OghmaNano
- `sim/materials/CsPbI3/nk.csv` — datos opticos n(ω)/k(ω)
- `sim/materials/CsPbI3/mat.json` — metadatos material

## Ejecutar

Activa `execute: true` en `configs/default_params.yaml` bajo `oghma_device:`
y reejecuta workflow, o manual:

```bash
cd sim && /usr/bin/oghma_core
```

`sim_info.dat` se parsea en siguiente corrida para PCE, Voc, Jsc, FF.
