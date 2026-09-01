# Monitor: referencia completa

Puesta en marcha, endpoints, acceso remoto, seguridad y desarrollo del
frontend. El [README](../README.md) resume qué es la aplicación; el detalle
está aquí.

Hay **dos formas de usar la interfaz**, con el mismo backend detrás. No son
alternativas rivales: resuelven situaciones distintas.

| | **Monitor DFT** (escritorio) | **Monitor DFT (servidor web)** |
|---|---|---|
| Cómo se ve | Ventana nativa | Pestaña del navegador |
| Motor | Embebido, congelado dentro | El del repositorio o el binario |
| Necesita Python | No | Sí (o el binario congelado) |
| Necesita el repositorio | No | Sí, salvo con el binario |
| Acceso desde otra máquina | No | Sí, con `--host 0.0.0.0` y token |
| Se lanza con | Icono del escritorio o del menú | `dft-monitor-web` |
| Artefacto | `dft-monitor-desktop-<v>-<plataforma>.tar.gz` | `dft-monitor-web-<v>-<plataforma>.tar.gz` |
| Se compila con | `scripts/build_desktop.sh` | `scripts/build_web.sh` |
| Peso | ~137 MB | ~94 MB |

**Usa la de escritorio** para trabajar a diario en tu máquina: se abre de un
doble clic y no depende de nada instalado. **Usa la web** cuando quieras mirar
el pipeline desde otro equipo, o cuando ya estés en el repositorio y prefieras
el navegador.

Ambas comparten backend: FastAPI sirve la API y el SPA de React en un solo
proceso y un solo origen. La de escritorio lo arranca por dentro en un puerto
efímero; la web lo expone donde le digas.

## La app de escritorio

```bash
bash scripts/build_desktop.sh     # → dist/dft-monitor-desktop-<versión>-<plataforma>.tar.gz
bash scripts/install_launcher.sh  # instala icono, menú y acceso directo
```

Congela el motor con PyInstaller, compila la app Flutter, mete el motor dentro
del bundle y comprueba el contrato de arranque antes de comprimir. El resultado
no necesita Python, Node ni el repositorio: el `.desktop` fija `DFT_DATA_ROOT`
para que encuentre tus datos.

## El servidor web: instalación desde el binario

Cada tag publica en [Releases](https://github.com/RxWhizz/PEROVOWL/releases) un
artefacto autocontenido: **no necesita Python, ni Node, ni el repositorio**.
Lleva dentro el SPA compilado, el surrogate ML y las estructuras de referencia.

```bash
# Linux
tar xzf dft-monitor-web-0.3.0-linux-x86_64.tar.gz
./dft-monitor-web/dft-monitor-web --data-root /ruta/a/tus/datos
```

En Windows, descomprime el `.zip` y ejecuta `dft-monitor.exe`.

`--data-root` es el directorio que contiene `runs/`, `local_runs/`,
`calculations/`, `reports/`… Si se omite, se busca hacia arriba desde el
directorio actual. La configuración va a `~/.config/dft-monitor/monitor.yaml`
(`%APPDATA%` en Windows), no al repositorio.

`GET /api/health` dice exactamente dónde busca cada cosa:

```json
"paths":    { "frozen": true, "bundle_root": "…/_internal",
              "data_root": "…/mis-datos", "config_dir": "~/.config/dft-monitor" },
"platform": { "os": "linux", "hardware_temps": true, "runner_launch": true }
```

`platform` refleja lo que de verdad se puede hacer en esa máquina, comprobado y
no supuesto: sin sensores de temperatura (Windows) la GUI oculta esas fichas, y
sin un intérprete de Python o sin los `scripts/` del pipeline, los endpoints de
lanzar runners responden **501** en vez de fallar.

Verifica la descarga con `sha256sum -c SHA256SUMS`.

#### Compilar el binario en local

```bash
bash scripts/build_web.sh      # → dist/dft-monitor-web-<versión>-<plataforma>.tar.gz
```

Compila el SPA, preconvierte las estructuras (con eso `ase` no entra en el
artefacto), congela con PyInstaller y **prueba el resultado** (salud, SPA,
estructuras y una predicción ML) antes de comprimir. Se distribuye como
directorio comprimido y no como ejecutable único porque `--onefile` con este
tamaño descomprimiría todo a un temporal en cada arranque.

La versión sale de `src/monitor_api/__init__.py` y es la única: la usan
`pyproject.toml`, la app, `/api/health`, la cabecera del SPA, y la CI aborta si
un tag no coincide.

## Puesta en marcha desde el repositorio

Un solo comando, desde cualquier directorio:

```bash
./bin/dft-monitor-web
```

La primera vez crea el entorno virtual, instala las dependencias, genera
`configs/monitor.yaml` apuntando a un `runs_dir` que exista, compila el frontend
y abre el navegador. Las siguientes arranca directo.

```bash
./bin/dft-monitor-web --port 9000        # otro puerto
./bin/dft-monitor-web --host 0.0.0.0     # accesible en la LAN (exige token)
./bin/dft-monitor-web --no-browser       # sin abrir el navegador
./bin/dft-monitor-web --reload           # hot-reload para desarrollar
```

Para tenerlo como comando del sistema y en el menú de aplicaciones:

```bash
bash scripts/install_launcher.sh     # symlink en ~/.local/bin + entrada .desktop
dft-monitor
```

Todo va a `~/.local`, sin `sudo`. Se revierte con `--uninstall`.

## Puesta en marcha manual

```bash
pip install -e ".[web]"
cp configs/monitor.example.yaml configs/monitor.yaml   # ajusta runs_dir y auth.token
cd frontend && npm install && npm run build && cd ..
python3 scripts/start_monitor.py
```

Sin frontend compilado el servidor arranca igual y sirve solo la API.

## Desarrollo del frontend

```bash
python scripts/start_monitor.py --reload         # backend en :8000
cd frontend && npm run dev                       # SPA en :5173 con proxy a :8000
```

Los tipos de TypeScript se derivan de los modelos Pydantic, así que un cambio en
el backend rompe el build del frontend en vez de fallar en tiempo de ejecución:

```bash
python scripts/dump_openapi.py     # vuelca src/monitor_api/openapi.json
cd frontend && npm run gen:api     # regenera src/lib/api.d.ts
```

## Secretos

Las claves no van en `monitor.yaml`: ese fichero se comparte, se copia al
directorio de configuración al instalar y se edita a mano, así que es el
candidato natural a colarse en un commit. Van en un `.env`, que está
gitignorado y no viaja dentro de los binarios publicados.

```bash
cp .env.example .env
```

| Variable | Para qué |
|---|---|
| `DFT_MONITOR_TOKEN` | Token compartido de la interfaz web. Ponerlo activa la autenticación |
| `DFT_MONITOR_SESSION_SECRET` | Firma de las cookies. Vacío genera uno nuevo en cada arranque y cierra las sesiones abiertas |
| `DFT_MONITOR_TELEGRAM_BOT_TOKEN` | Token de @BotFather. Vacío desactiva el bot |
| `DFT_MONITOR_TELEGRAM_CHAT_ID` | Chat autorizado; los mensajes de cualquier otro se ignoran |

El `.env` se busca en la ruta que indique `DFT_ENV_FILE`, luego junto a
`monitor.yaml`, luego en la raíz de datos y por último en el directorio actual.
**Lo que ya esté en el entorno gana siempre**, así que un
`DFT_MONITOR_TOKEN=xxx buho monitor serve` puntual no lo pisa un fichero viejo.

## Acceso remoto y seguridad

El monitor puede matar procesos y lanzar runners, así que:

- Escucha en `127.0.0.1` por defecto.
- `--host 0.0.0.0` **se niega a arrancar** si no hay token configurado.
- El token se canjea por una cookie de sesión firmada, `HttpOnly` y `SameSite`,
  que protege por igual el REST y el WebSocket (el navegador no admite cabeceras
  propias en el handshake de un WebSocket).
- Los intentos de login se limitan por IP y quedan en `logs/monitor_audit.jsonl`.

Para llegar desde fuera de la LAN, usa **Tailscale o WireGuard** en vez de abrir
el puerto. Un token sobre HTTP plano en internet abierto no es protección
suficiente; si aun así se expone, debe ir tras un proxy con TLS y
`monitor.auth.https_only: true`.

## Vistas

| Vista | Contenido |
|---|---|
| **Live** | Recuento por estado, hardware con sparklines, heatmap por núcleo, progreso de batches, jobs activos y consola de eventos |
| **Jobs** | Tabla virtualizada con filtros y panel de detalle: trazas SCF, frames, log y ficha del candidato |
| **Candidatos** | Scatter de tolerancia Goldschmidt vs factor octaédrico con las zonas de aceptación, embudo de cribado y tabla |
| **ML** | Predicción de bandgap con incertidumbre, parity plot frente a DFT y experimento, métricas de los modelos |
| **Estructuras** | Visor 3D (3Dmol.js) de fases, top-8 y estructuras de cada job, con supercelda y celda unidad |
| **Resultados** | Reportes Markdown renderizados y galerías desde los `visualization_manifest.json` |

## Endpoints

| Endpoint | Descripción |
|---|---|
| `GET /api/health` | Montaje de `runs_dir`, frescura del poller, clientes WS |
| `GET /api/jobs` | Jobs paginados, con filtro por estado, búsqueda y orden |
| `GET /api/jobs/converged` | Convergidos ordenados por fórmula |
| `GET /api/jobs/{id}` · `/ping` · `/stats` | Detalle, lectura instantánea, re-parseo |
| `GET /api/jobs/{id}/traces` · `/log` · `/metadata` | Series SCF y frames · cola del log · ficha del candidato |
| `GET /api/summary` · `/api/batches` | Recuento global · por batch, con throughput y ETA |
| `GET /api/system` · `/api/system/history` | Hardware ahora · ventana de 1 hora |
| `GET /api/candidates` | Candidatos del generador, con facetas y cotas de filtro |
| `GET /api/models` · `POST /api/ml/predict` · `GET /api/ml/top8` | Métricas · predicción · comparativa ML/DFT/exp |
| `GET /api/structures` · `/api/structures/content` | Inventario · CIF (convierte los JSON de ASE al vuelo) |
| `GET /api/reports` · `/document` · `/figure` | Documentos y galerías · Markdown · figuras |
| `GET /api/statusfull` · `/api/status/report` | Reportes en texto (los de Telegram) |
| `POST /api/notify/*` | Envío manual a Telegram |
| `WS /ws/events` | Cambios de estado en vivo, con `seq` y aviso de huecos |

**Acciones de control**, destructivas, confirmadas en la UI y registradas en `logs/monitor_audit.jsonl`:

| Endpoint | Descripción |
|---|---|
| `POST /api/jobs/{id}/kill` | Termina los procesos del job |
| `POST /api/jobs/{id}/retry` | Devuelve un job fallido a la cola |
| `POST /api/batches/{id}/start` | Lanza el runner de un batch |

> El PID que guarda `status.json` se verifica contra `/proc/<pid>/cwd` antes de
> usarlo: puede llevar meses escrito y haberse reciclado, y el matador termina
> el grupo de procesos completo del PID que reciba.

> `runs/` y `calculations/` son symlinks a un volumen externo. Si no está
> montado, `GET /api/health` devuelve `runs_mounted: false` y la GUI muestra un
> aviso, en lugar de un panel vacío indistinguible de "no hay trabajo".
