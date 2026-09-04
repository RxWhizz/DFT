# Monitor DFT 0.4.0

**Prerelease.** Construida desde `feature/autonomous-discovery-loop`, pendiente
de fusionar a `main`. No sustituye a v0.3.0 como release estable.

Interfaz gráfica del pipeline de cribado de perovskitas: genera candidatos, los
criba con la cascada HTS, prepara y lanza los cálculos DFT, y sigue el progreso
en vivo.

## Descargar

Abre la pagina del release:

<https://github.com/RxWhizz/PEROVOWL/releases/tag/v0.4.0>

En **Assets**, descarga el paquete que corresponda a tu sistema:

| Sistema | Archivo recomendado | Uso |
|---|---|---|
| Windows 10/11 x64 | `dft-monitor-desktop-0.4.0-windows-x64.zip` | GUI de escritorio nativa con motor local embebido |
| Debian/Ubuntu x64 | `perovowl-dft-monitor-0.4.0-linux-amd64.deb` | GUI de escritorio instalable en el sistema |
| Linux x86_64 portable | `dft-monitor-desktop-0.4.0-linux-x86_64.tar.gz` | GUI portable sin instalador |
| Linux servidor/web | `dft-monitor-web-0.4.0-linux-x86_64.tar.gz` | Servidor local que abre la interfaz en navegador |

Tambien descarga `SHA256SUMS-gui-deliverables.txt` si quieres verificar los
entregables nuevos, o `SHA256SUMS` para los artefactos Linux publicados
originalmente.

## Instalar y abrir

### Windows

Descarga `dft-monitor-desktop-0.4.0-windows-x64.zip`, descomprimelo y ejecuta:

```powershell
Expand-Archive .\dft-monitor-desktop-0.4.0-windows-x64.zip
.\dft-monitor-desktop-0.4.0-windows-x64\dft_monitor_flutter.exe
```

No necesita Python, Node, Flutter ni el repositorio. El motor local viaja dentro
de la carpeta `engine/`.

### Debian/Ubuntu

Descarga `perovowl-dft-monitor-0.4.0-linux-amd64.deb` e instalalo con:

```bash
sudo apt install ./perovowl-dft-monitor-0.4.0-linux-amd64.deb
perovowl-dft-monitor
```

Tambien puedes abrirlo desde el menu de aplicaciones como **PEROVOWL DFT
Monitor**. Por defecto, el lanzador usa `~/PEROVOWL-data` como raiz de datos si
no defines `DFT_DATA_ROOT`.

### Linux portable

Si no quieres instalar el paquete `.deb`, usa el bundle portable:

```bash
tar xzf dft-monitor-desktop-0.4.0-linux-x86_64.tar.gz
./dft-monitor-desktop-0.4.0-linux-x86_64/dft_monitor_flutter
```

### Linux web/servidor

Para abrir la interfaz desde navegador o mirar el pipeline desde otra maquina:

```bash
tar xzf dft-monitor-web-0.4.0-linux-x86_64.tar.gz
./dft-monitor-web/dft-monitor-web --data-root /ruta/a/tus/datos
```

Se abre en `http://127.0.0.1:8000`. Con `--host 0.0.0.0` se expone en la red y
exige un token en `monitor.auth.token`.

## Verificar descargas

En Windows:

```powershell
Get-FileHash .\dft-monitor-desktop-0.4.0-windows-x64.zip -Algorithm SHA256
Get-FileHash .\perovowl-dft-monitor-0.4.0-linux-amd64.deb -Algorithm SHA256
```

En Linux:

```bash
sha256sum -c SHA256SUMS
sha256sum -c SHA256SUMS-gui-deliverables.txt
```

## Qué trae

### Nuevo en 0.4.0

- **Protocolo de descubrimiento autónomo**: un ciclo ML → DFT → reentrenar →
  repetir que encadena rondas solo, sin volver a invocarlo entre medias.
  `buho active-learning discovery run` en consola, pestaña **Protocolo** en la
  app.
- **El aprendizaje activo ahora aprende**: cada reentrenamiento publica el
  modelo (`surrogate_bandgap_current.pkl`) y la siguiente ronda criba con él.
  Antes se reentrenaba y se descartaba — el bucle nunca usaba lo que acababa
  de aprender.
- **El bucle corre como proceso aparte**, no como hilo del servidor: cribar
  decenas de miles de candidatos con pandas ya no deja la API sin responder
  mientras tanto.
- **Sobrevive a un runner DFT que muere a media ronda**: lo detecta por falta
  de progreso (no solo por si el runner nunca llegó a arrancar), reintenta, y
  se rinde con un estado de error legible tras varios intentos en vez de
  colgarse indefinidamente.
- **Métrica honesta del reentrenamiento**: junto al `train_mae_eV` (que solo
  mide ajuste y baja artificialmente al crecer los datos) se registran
  `cv_mae_eV` (validación cruzada 5-fold) y `baseline_mae_eV` (predecir la
  media), para saber si el surrogate generaliza de verdad.
- **Pantalla Entorno**: una tarjeta por runtime (núcleo, API, GPAW, datasets
  PAW, MLFF) con lo que hay instalado, lo que falta y un botón para instalarlo,
  con el log en vivo. El equivalente en consola es `buho setup check` /
  `buho setup install`.
- **Tier 2 (MLFF/GNN) fuera del proceso del monitor**: `torch` + `matgl` +
  `pymatgen` pesan ~2 GB y en Windows son la parte más frágil de la pila. Ahora
  corren en su propio entorno —en Windows, dentro de WSL— y el monitor habla
  con él por un worker. `buho setup install mlff` lo crea.
- El entorno MLFF se crea **separado del de GPAW** a propósito: GPAW está fijado
  a numpy 1.26 y `matgl` exige numpy ≥ 2. Compartirlo rompería los cálculos.

### De antes

- **Vista en vivo** del pipeline: qué se está haciendo y tiempo estimado,
  calculado con la mediana real de los trabajos ya terminados.
- **Cribado HTS** en cascada de tres tiers, con malla de σ en el Tier 1.
- **Predictor** de bandgap con su incertidumbre y comparación contra DFT.
- **Candidatos** viables, verificados por DFT y ordenados por score
  fotovoltaico, exportables a CSV.
- **Visor de estructuras** 3D con bolas y palos, exportable a PNG.
- **Log de GPAW en vivo** mientras corren los cálculos.
- **Calibración de rendimiento**: mide cuántos trabajos concurrentes y cuántos
  núcleos por trabajo aguanta la máquina.

## Correcciones importantes

### Nuevo en 0.4.0

- **Una ronda ya no muere por una dependencia opcional**: si falta el entorno
  MLFF, el cribado sigue con los tiers 0 y 1 y lo dice en pantalla, en vez de
  reventar a mitad. Se descarta menos material, pero el DFT —que es lo caro— no
  se bloquea.
- **El estado dejaba de poder rearrancarse**: al fallar durante el cribado, el
  estado persistido se quedaba en «cribando» para siempre. Parecía que seguía
  trabajando cuando el hilo ya había muerto, y el botón de ejecutar salía
  deshabilitado. Ahora cualquier fallo deja el estado diagnosticable.
- **Barra de navegación**: con once secciones ya no cabían en la ventana por
  defecto y las últimas quedaban inalcanzables. Ahora la barra se desplaza.

### De antes

- **Datasets PAW**: la ruta estaba escrita a mano en siete archivos y dejó de
  existir; todos los cálculos fallaban al arrancar. Ahora se resuelve
  verificando que el dataset esté de verdad, y se aborta con instrucciones si
  falta, en vez de consumir el lote entero trabajo a trabajo.
- **Geometría ABX3**: la red cúbica se fijaba con `2√2·(r_B+r_X)`, que es la
  relación A–X; la correcta es `2·(r_B+r_X)`, que fija el enlace B–X. Las
  estructuras salían √2 veces dilatadas.
- **Runners y app**: cerrar la ventana mataba los cálculos en marcha. Los
  procesos largos ya no heredan los descriptores del motor.
- **Seguimiento de lotes**: el monitor se quedaba mirando el lote configurado al
  arrancar y no veía los lanzados después.

## Limitación conocida

El protocolo autónomo puede declararse `done` tras pocas rondas aunque queden
miles de candidatos sin verificar: la ventana fotovoltaica del Tier 1 asume
bandgap experimental, y el surrogate aprende el bandgap PBE de la criba, que es
sistemáticamente más bajo. No es un fallo del código — es una calibración
pendiente. Detalle y opciones de arreglo en
[#7](https://github.com/RxWhizz/PEROVOWL/issues/7).

## Licencias

Incluye ASE (LGPL-2.1-or-later) dentro del binario. El resto de dependencias
empaquetadas —scikit-learn, numpy, scipy, pandas, FastAPI, uvicorn, psutil— es
BSD/MIT.
