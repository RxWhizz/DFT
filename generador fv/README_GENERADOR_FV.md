# Generador FV

Espacio separado para el trabajo OghmaNano/fotovoltaico movido desde el pipeline DFT principal.

## Entorno virtual

Activar en PowerShell:

```powershell
& "generador fv\.venv\Scripts\Activate.ps1"
```

La venv dedicada ya permite correr los diagnosticos en Windows nativo. Si se
quieren ejecutar tests, instalar el extra de desarrollo dentro de esa venv
(`pytest` no viene instalado por defecto en el snapshot actual).

```powershell
& "generador fv\.venv\Scripts\python.exe" -m pip install pytest
```

## Contenido

- `calculations/alpha/14_oghma_device/`: proyecto OghmaNano, resultados JV, optica, snapshots y `debug_outputs/`.
- `src/dft_cspbi3/analysis/oghma_device.py`: modulo Python de preparacion/parsing/debug OghmaNano.
- `scripts/debug_oghma_outputs.py`: diagnostico defensivo para resultados OghmaNano.
- `scripts/install_oghma_ubuntu.sh`: instalador Linux previo.
- `vendor/oghma/`: paquete OghmaNano guardado.
- `OGHMA_DEBUG_CONTEXT.md`: bitacora tecnica del debugging.

## Diagnostico rapido

```powershell
& "generador fv\.venv\Scripts\python.exe" "generador fv\scripts\debug_oghma_outputs.py" "generador fv\calculations\alpha\14_oghma_device"
```

## Estado actual

- OghmaNano ya corre en Windows nativo con `oghma_core.exe` en modo worker.
- La corrida alpha produce `sim_info.dat`, `jv.csv`, salida optica y snapshots.
- Resultado actual con `.npy` opticos: PCE 16.37708 %, Voc 0.9188036 V, Jsc -24.985913 mA/cm2, FF 0.7133761.
- Jsc de Oghma se interpreta defensivamente como A/m2 y se reporta en mA/cm2.
- La geometria optica ya es coherente con el template: stack total 1050 nm, absorbedor 250-750 nm, pico de generacion dentro del absorbedor.
- Los `.npy` opticos requeridos ya existen en `calculations/alpha/11_optical/`; se derivaron de `dielectric_function.csv` con onset impuesto en Eg.

Comando manual equivalente en Windows:

```powershell
& "C:\Program Files (x86)\OghmaNano\oghma_core.exe" --sim-root-path "C:\Users\LUIS\Documents\GitHub\DFT\generador fv\calculations\alpha\14_oghma_device\sim" --gui --html --simmode segment0@jv --lockfile "C:\Users\LUIS\Documents\GitHub\DFT\generador fv\calculations\alpha\14_oghma_device\sim\lock0.dat"
```
