# OghmaNano Debug Context — Estado al 2026-05-07

## El problema original
`prepare_oghma_device_step()` en `oghma_device.py` llama a `subprocess.run([runner])` **sin argumentos** → oghma_core arranca en **modo servidor** (espera conexiones GUI por IPC y sale con código 1 tras timeout). Nunca corría simulaciones.

## Arquitectura que hay que entender
OghmaNano v8.x tiene dos modos de ejecución:

| Modo | Cómo invocar | Qué hace |

|------|-------------|---------|
| **Servidor** | `oghma_core.exe` (sin args) | Espera conexiones IPC de la GUI. Sale con código 1 tras `server_stall_time=2000 ms`. |
| **Worker** | `oghma_core.exe --simmode <modo> --lockfile <ruta>` | Corre la simulación, crea/borra lock file, escribe `sim_info.dat`. |

La GUI usa `server_base.py → server_add_cmd_line_job()` para lanzar workers con el formato:
```
oghma_core.exe <sim_path> --simmode segment0@jv --lockfile lock0.dat
```

## Cómo invocar correctamente (worker mode)
```bash
# Necesita Xvfb obligatoriamente (aunque sea headless)
Xvfb :96 -screen 0 1024x768x24 &
cd /path/to/sim_dir
DISPLAY=:96 WINEPREFIX=~/.wine64 WINEARCH=win64 WINEDEBUG=-all \
    wine /usr/lib/oghma_core/oghma_core.exe \
    --simmode segment0@jv \
    --lockfile 'S:\lock0.dat'
```

**Fix pendiente en `oghma_device.py` líneas 162-172**: cambiar llamada a `subprocess.run` para:
1. Usar `xvfb-run -a` como prefijo
2. Pasar `--simmode segment0@jv --lockfile lock0.dat` como args
3. Asegurarse DISPLAY está seteado (no vacío)

```python
# en _wine_env(), cambiar DISPLAY="" a...
# ...no setear DISPLAY aquí, usar xvfb-run -a que lo setea solo
cmd = ["xvfb-run", "-a", "--", "/usr/lib/oghma_core/oghma_core.exe",
       "--simmode", "segment0@jv", "--lockfile", r"S:\lock0.dat"]
```

## Problema del directorio de datos (oghma_local)
oghma_core busca `html/info0.html` como marcador para encontrar su directorio de datos.
Orden de búsqueda (visible en wine trace con `WINEDEBUG=+file,warn`):

1. `Z:\home\luis-ochoa\oghma_local\html\info0.html` ← **primer candidato**
2. `S:\html\info0.html` (sim dir)
3. Varios relativos al sim dir (`S:\oghma_gui\`, `S:\oghma_data\`, etc.)
4. `C:\Program Files\OghmaNano\`, `D:\Program Files\OghmaNano\`
5. `/usr/share/\html\info0.html` (path malformado → falla siempre)

`Z:` mapea a `/` en wine, así que `Z:\home\luis-ochoa\oghma_local` = `/home/luis-ochoa/oghma_local`.

### Solución aplicada
Se creó `/home/luis-ochoa/oghma_local/` con symlinks al sistema:
```
/home/luis-ochoa/oghma_local/
├── html       -> /usr/share/oghma_gui/html          ← contiene info0.html (el marcador)
├── atmosphere -> /usr/share/oghma_data/atmosphere
├── cie_color  -> /usr/share/oghma_data/cie_color
├── components -> /usr/share/oghma_data/components
├── device_lib -> /usr/share/oghma_data/device_lib
├── filters    -> /usr/share/oghma_data/filters
├── materials  -> /usr/share/oghma_data/materials
├── morphology -> /usr/share/oghma_data/morphology
├── plugins    -> /usr/lib/oghma_core/plugins
├── shape      -> /usr/share/oghma_data/shape
└── spectra    -> /usr/share/oghma_data/spectra
```

Después de estos symlinks, oghma_core ENCUENTRA:
- ✅ `html/info0.html`
- ✅ `atmosphere`
- ✅ `device_lib`
- ✅ `plugins`

## Estado actual del error (al interrumpir)
Después de encontrar plugins, oghma_core busca `images/image.jpg`:
```
Z:\home\luis-ochoa\oghma_local\images\image.jpg → not found
```
`images/image.jpg` está en `/usr/share/oghma_gui/images/image.jpg`.
**El siguiente paso** era:
```bash
ln -sfn /usr/share/oghma_gui/images /home/luis-ochoa/oghma_local/images
```
El patrón es que oghma_core busca un directorio, lo agrega, y aparece el siguiente. Esto sugiere que hay un número finito de dirs faltantes. Probablemente después de `images` hay: `lang/`, `css/`, y quizás `inp_templates/`.

## Directorios en /usr/share/oghma_gui/ (candidatos a agregar)
```
/usr/share/oghma_gui/
├── html/      ← ya linkado
├── images/    ← PENDIENTE (images/image.jpg falta)
├── (probablemente más: lang/, css/, etc.)
```

## Rutas clave del sistema
- **Ejecutable**: `/usr/lib/oghma_core/oghma_core.exe` (vía wine)
- **Wrapper shell**: `/usr/bin/oghma_core` → `wine /usr/lib/oghma_core/oghma_core.exe "$@"`
- **Datos sistema**: `/usr/share/oghma_data/` (atmosphere, device_lib, materials, etc.)
- **GUI/HTML**: `/usr/share/oghma_gui/` (html/, images/, etc.)
- **Plugins DLLs**: `/usr/lib/oghma_core/plugins/` (jv.dll, equilibrium.dll, etc.)
- **Wine prefix**: `~/.wine64/` (win64)
- **Drive S:**: symlink → sim dir activo
- **Drive O:**: symlink → `/usr/lib/oghma_core/`
- **Drive Z:**: symlink → `/` (raíz del sistema)

## Archivo de simulación
- **Sim dir**: `calculations/alpha/14_oghma_device/sim/`
- **Proyecto OghmaNano**: `sim/json.inp` (150 963 bytes, v8.1)
- **Material DFT**: `sim/materials/CsPbI3/nk.csv` (200 puntos, 206–1000 nm)
- **sim.json**: idéntico a json.inp

### Parámetros actuales (lentos / problemáticos)
```
JV: Vstart=0.0, Vstop=1.1, Vstep=0.02  → 56 puntos de voltaje
optical model: transfer_matrix           → lento
ion_density (perovskite): 1e25 m⁻³      → migración iónica, muy lento
```
Para una prueba rápida, simplificar a:
- `Vstep=0.1` (11 puntos)
- `ion_density=0`
- Modo `equilibrium@equilibrium` primero para verificar estabilidad

## Fix pendiente en oghma_device.py
1. **Líneas 162-172**: cambiar `subprocess.run([runner])` a worker mode con xvfb-run + args
2. **Método `_wine_env()`**: eliminar `DISPLAY: ""` (xvfb-run lo seteará automáticamente)
3. **Método `write_oghma_sim_dir()`**: aplicar simplificaciones opcionales al JSON (ion_density=0, Vstep=0.05 para modo fast)

## Contexto del proyecto DFT más amplio
- Hay un plan activo en `.claude/plans/zazzy-orbiting-garden.md` (TMM + SQ limit) pendiente
- El paso oghma_device es el 14 del workflow (después del 13_sq_limit)
- Una vez que `sim_info.dat` se genere, el parser `parse_oghma_sim_info()` ya está implementado correctamente

## Actualizacion Codex — 2026-05-07 23:45

No parece ser un problema de login. El binario reporta licencia MIT en stdout y no hay flujo de autenticacion activo; el campo `password` del proyecto esta vacio y no bloquea. El problema actual esta en la validacion runtime del template/mesh bajo Wine.

### Cambios ya aplicados en `src/dft_cspbi3/analysis/oghma_device.py`
1. El worker ya se lanza en modo correcto:
   `xvfb-run -a -- /usr/bin/oghma_core --sim-root-path S:\ --gui --html --simmode segment0@jv --lockfile S:\lock0.dat`
2. `_wine_env()` ya no pisa `DISPLAY`; lo gestiona `xvfb-run`.
3. `ensure_oghma_local_links()` ahora crea overlay de materiales para exponer `CsPbI3/n.csv` y `CsPbI3/alpha.csv`.
4. Se escriben `n.csv`, `alpha.csv`, `nk.csv`, `data.json` y `mat.json` para `CsPbI3`.
5. Se agregaron defaults runtime faltantes de Oghma v8:
   - `math.matrix_threshold_enabled`
   - `math.matrix_threshold`
   - `math.matrix.solver_name`
   - `math.matrix_block_normalization`
   - parametros `block_*`
6. Se corrige la ruta real de la malla electrica:
   `electrical_solver.mesh.mesh_y.segment0.len`
7. El resultado ahora captura la linea `error:` real en `oghma_device_result.json`.

### Estado actual
La corrida limpia llega hasta construir DoS, cargar cache y construir el device pointer array, pero falla con:
```
error:There is a shape (Au) covering the electrical mesh with no electrical parameters enabled
```

Tambien se verifico que el template stock instalado `/usr/share/oghma_data/device_lib/perovskite/perovskite.json` falla con el mismo error bajo el core instalado. Eso apunta a incompatibilidad template/core o a un requisito de preprocesado de la GUI antes de correr el worker, no a login.

### Pruebas realizadas
- `pytest tests/test_oghma_device.py -q` pasa: 7 tests.
- `equilibrium@equilibrium` no es simmode valido para este template.
- `equilibrium` arranca pero queda colgado hasta timeout.
- Pasar el sim path como argumento posicional (`S:\`) se queda colgado; `--sim-root-path S:\` es la forma mas estable.
- Desactivar `Au` cambia el error a `big_box`.
- Convertir `Au` en capa activa generica evita el error de `Au`, pero aparece validacion de borde `No object at ...`, por la caja global/margen de mundo.

### Actualizacion — 2026-05-08: Decision de migrar a Windows

**El error "Au covering the electrical mesh" persiste sin importar:**
- `obj_type` de Au (contact / other / active)
- `dd_enabled`, `shape_electrical.enabled`, `electrical_component` en Au
- `mesh_y.auto` (True/False) en malla electrica u optica
- `mesh_y.len` (9e-7, 8.9e-7, activa completa, total dispositivo)
- `light_model` (full / flat)
- `solve_optical_problem` (True / False) en Au

**Causa raiz confirmada:** OghmaNano v8.1 requiere que la GUI de Windows
preprocese el proyecto JSON antes de lanzar el worker headless. Bajo Wine en
Linux este preprocesado nunca ocurre correctamente. El stock perovskite.json
falla identico.

**Decision:** Instalar OghmaNano en Windows nativo y ejecutar desde ahi.

### Para ejecutar en Windows

En Windows `oghma_core.exe` corre sin Wine. El codigo en `oghma_device.py` ya
detecta el runner correctamente (busca `oghma_core.exe` o `oghma_core`).
Cambios necesarios:

1. **`_build_worker_cmd()`** — eliminar `xvfb-run -a --` del prefijo; en
   Windows no hay Xvfb.  El condicional ya existe (busca `xvfb-run` en PATH).
2. **`_wine_env()`** — en Windows las variables WINEPREFIX/WINEARCH no aplican;
   el metodo ya retorna el env del proceso si no encuentra wine.
3. **Drive S:** — en Windows no existe `~/.wine64/dosdevices/s:`. Hay que
   pasar el sim_dir como ruta absoluta Windows directamente al `--sim-root-path`.
4. El `--lockfile` debe ser una ruta Windows absoluta, e.g. `C:\...\lock0.dat`.

El parser `parse_oghma_sim_info()` y todo lo demas ya esta correcto.

### Flujo en Windows (pseudocodigo)
```
oghma_core.exe --sim-root-path "C:\path\to\sim" ^
               --simmode segment0@jv ^
               --lockfile "C:\path\to\sim\lock0.dat"
```
