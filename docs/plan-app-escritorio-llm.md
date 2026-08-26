# Plan — app de escritorio con LLM embebido

> Escrito al final de la sesión del 2026-08-24, para que no se pierda el contexto.
> Todo lo que aparece aquí está verificado contra el repo, no recordado.

## Contexto

El monitor ya es un binario. `scripts/build_web.sh` produce
`dist/dft-monitor-<versión>-<plataforma>.tar.gz` — **94 MB**, arranca sin Python,
sin Node y sin el repositorio, y lleva dentro el SPA, el surrogate y las
estructuras. El workflow de GitHub Actions lo publica en cada tag para Linux y
Windows.

Lo que molesta no es el empaquetado: es que **abre el navegador**. Se siente
como una web app porque lo es en la última milla — un servidor local y una
pestaña. El cambio pedido es el envoltorio, no la arquitectura.

Y encima de eso: **un LLM embebido** que haga los ajustes que hoy se hacen a mano.

---

## Lo que NO hay que reconstruir

Inventario para que la siguiente sesión no redescubra nada.

| Pieza | Dónde | Estado |
|---|---|---|
| API REST + WebSocket | `src/monitor_api/` | 37 rutas, OpenAPI generado |
| SPA React | `frontend/` | 7 vistas, 229 KB inicial, chunks perezosos |
| Separación de raíces | `src/monitor_api/paths.py` | bundle / data / config |
| Capacidades de plataforma | `src/monitor_api/platform_caps.py` | comprobadas, no supuestas |
| Autenticación | `src/monitor_api/security.py` | cookie firmada, auditoría JSONL |
| Cascada HTS | `src/monitor_api/services/screening.py` | 3 tiers, torre real |
| Empaquetado | `packaging/dft-monitor-web.spec` | PyInstaller onedir |
| Lanzador | `bin/dft-monitor-web`, `src/monitor_api/launcher.py` | resuelve venv, config, navegador |
| CI de release | `.github/workflows/release.yml` | tag → Linux + Windows + SHA256 |
| Tests | `tests/test_monitor_api.py`, `tests/test_packaging.py` | 169 |

**La superficie de herramientas del agente ya existe**: 37 endpoints con esquema
OpenAPI, log de auditoría, y el patrón de confirmación en dos pasos
(`ConfirmButton`). Es exactamente lo que un agente necesita. Falta el agente.

---

## Decisión 1 — el envoltorio de escritorio

El SPA no se tira. Sigue siendo React; lo que cambia es dónde se pinta.

Estado de la máquina, comprobado: **no hay `webkit2gtk`, ni PyQt6, ni tkinter**.
Eso descarta dar por hecho cualquier webview del sistema.

| Opción | Peso | Dependencia de sistema | Aspecto |
|---|---|---|---|
| **`--app=` del navegador** | 0 | ninguna | ventana sin cromo, sin pestañas ni barra |
| **pywebview** | ~1 MB | `libwebkit2gtk-4.1` en Linux; en Windows usa el Edge WebView2 ya presente | nativo |
| **PyQt6-WebEngine** | ~150 MB | ninguna (empaqueta Chromium) | nativo, autocontenido |

**Recomendación: una escalera, no una elección.** El lanzador prueba en orden y
cae con gracia, que es la pauta que ya sigue todo el proyecto:

```
1. pywebview        si el módulo importa y hay webview del sistema
2. --app=<url>      si hay chrome/chromium/edge/brave en el PATH
3. navegador normal el comportamiento de hoy
```

Con eso, en Windows es nativo desde el primer día (Edge WebView2 viene con el
sistema) y en Linux es nativo para quien tenga webkit2gtk e indistinguible de
una app para el resto. `--host 0.0.0.0` sigue existiendo para el acceso remoto:
no se pierde nada.

PyQt6-WebEngine queda como plan B si `--app=` no convence: +150 MB sobre 94 es
un artefacto de ~250 MB, todavía razonable.

**Detalle que hay que resolver**: hoy el puerto es fijo (8000). Una app de
escritorio debe pedir un puerto libre al sistema (`socket.bind(('127.0.0.1', 0))`)
y pasárselo al shell, para poder abrir dos instancias sin colisión.

---

## Decisión 2 — el LLM

### Lo que la máquina permite

Medido, no supuesto: **62 GB de RAM, 88 núcleos, 2× Radeon RX 580**.

`PROJECT_CONTEXT.md` dice «Intel Xeon 8 cores, ~16 GB RAM» — **está obsoleto** y
lleva a descartar el modelo local por razones falsas. Conviene corregirlo.

Con 88 núcleos, inferencia en CPU de un modelo de 7B–14B cuantizado es viable
incluso con GPAW corriendo. Las RX 580 son Polaris: ROCm las abandonó, pero el
backend Vulkan de llama.cpp funciona. La vía pragmática es CPU.

### La restricción que decide

**GitHub Releases limita cada archivo a 2 GB.** Un modelo local útil pesa entre
4 y 20 GB. Por tanto:

> El modelo **no puede viajar dentro del artefacto**. O se descarga en el primer
> uso, o se apunta a una ruta local.

Eso vale para cualquier backend local y hay que diseñarlo desde el principio.

### Los dos backends

| | Local (llama.cpp / GGUF) | Claude API |
|---|---|---|
| Tamaño del artefacto | 94 MB + descarga de 4–20 GB | 94 MB |
| Red | no hace falta | obligatoria + clave |
| Coste | electricidad | por token |
| Uso de herramientas multi-paso | flojo con 37 endpoints | es su fuerte |
| Leer un log y proponer un arreglo | plausible con 7B–14B | holgado |
| Datos fuera de la máquina | nunca | van a la API |

**Recomendación: capa agnóstica del proveedor, dos backends.** Lo difícil no es
el modelo — es la superficie de herramientas, la puerta de aprobación y la
traza. Eso se diseña una vez y el modelo se vuelve intercambiable.

Reparto sensato por tarea:

- **Diagnóstico** (leer un `r2scan.txt` que no converge y proponer mixer/ecut/kpts):
  local basta. Es una tarea, un contexto, una respuesta.
- **Orquestación** (decidir el siguiente paso mirando el estado de varios
  endpoints): API. Encadenar llamadas a herramientas con JSON correcto es donde
  los modelos pequeños se caen.

Para el backend de API: **`claude-opus-5`** con pensamiento adaptativo
(`thinking: {"type": "adaptive"}`) y el **Tool Runner** del SDK
(`client.beta.messages.tool_runner`), que lleva el bucle de herramientas sin
escribirlo a mano y deja ganchos por turno para la puerta de aprobación.
Dependencia: `anthropic` (Python). Sin `budget_tokens` — está retirado en esa
familia de modelos.

### La línea que no se cruza

**El LLM va en la capa de control, nunca en la numérica.**

El surrogate no produce un bandgap: produce **un bandgap con un σ calibrado**, y
ese σ alimenta `ucb_bonus = β·σ`, que es lo que hace que el ciclo explore en vez
de repetirse. Un LLM no tiene incertidumbre calibrada. Sustituir el surrogate
por un LLM mata el active learning en silencio — seguiría dando números, pero el
término de exploración dejaría de significar nada.

Lo mismo con MACE: 10.4 meV/Å en fuerzas no lo produce un modelo de lenguaje.

BUHO sigue siendo generador + cascada + surrogate + MACE. El LLM es su
**operador**, que es lo que hoy haces tú a mano.

---

## Arquitectura del agente

```
┌── Ventana de escritorio (pywebview / --app=) ─────────────┐
│  El SPA de siempre + un panel de agente                    │
└────────────────────────────────────────────────────────────┘
                          │  mismo origen, puerto efímero
┌── FastAPI (el de ahora) ───────────────────────────────────┐
│  37 endpoints  ·  WebSocket  ·  auditoría                  │
│                                                             │
│  ┌── services/agent/ ──────────────────────────────────┐   │
│  │  backend.py   protocolo común (chat + herramientas) │   │
│  │  claude.py    Tool Runner sobre el SDK              │   │
│  │  local.py     llama.cpp / GGUF                      │   │
│  │  tools.py     generadas desde el OpenAPI            │   │
│  │  gate.py      lectura libre · escritura aprobada    │   │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

**Las herramientas salen del OpenAPI que ya se genera.** `scripts/dump_openapi.py`
produce el esquema; un generador lo convierte en definiciones de herramienta. Los
modelos Pydantic siguen siendo la única fuente de verdad, igual que para el
frontend.

**Dos anillos de permiso**, no uno:

- **Lectura** — `/api/health`, `/api/jobs`, `/api/screening/runs/{id}`,
  `/api/jobs/{id}/log`: el agente las llama solo. No pueden hacer daño.
- **Escritura** — `kill`, `retry`, `start`, `screening/run`, y cualquier cambio
  de configuración: el agente **propone**, la interfaz muestra el comando o el
  diff, y la persona aprueba con el `ConfirmButton` que ya existe.

Todo, aprobado o rechazado, a `logs/monitor_audit.jsonl` con el motivo que dio
el modelo. La regla que lo hace confiable es la misma que ya sigue la GUI: **el
agente propone un comando visible, no ejecuta una caja negra.**

### Por dónde empezar

**El diagnóstico de fallos SCF.** `src/buho/phase2_force/self_heal.py` ya tiene
reglas escritas a mano para oscilación de U y estancamiento sin iteraciones. El
agente cubre los casos que las reglas no contemplan: lee el log, propone el
cambio, deja su razonamiento en la auditoría. Alto valor, riesgo bajo, y el
hueco ya está hecho.

---

## Fases

**Fase A — Ventana.** Escalera de shells en `launcher.py`, puerto efímero,
`--shell {auto,webview,app,browser}`. Verificable sin tocar nada del agente.

**Fase B — Superficie de herramientas.** `services/agent/tools.py` generando
definiciones desde el OpenAPI, con el anillo de lectura/escritura. Sin modelo
todavía: se prueba con llamadas fabricadas a mano.

**Fase C — Backend de API.** `claude.py` con el Tool Runner, `claude-opus-5`,
pensamiento adaptativo. Panel de chat en el SPA. Solo herramientas de lectura.

**Fase D — Puerta de escritura.** Las propuestas del agente pasan por
`ConfirmButton`; el comando o el diff se muestran antes de aprobar; todo a la
auditoría.

**Fase E — Backend local.** `local.py` con llama.cpp, descarga del modelo al
primer uso con barra de progreso y verificación de hash, ruta configurable.
Selector de backend por tarea.

**Fase F — Diagnóstico SCF.** El primer uso real: leer el log de un job estancado
y proponer el arreglo. Comparar contra lo que decide `self_heal.py` hoy.

Cada fase deja algo comprobable. Cortando después de la C ya hay una app de
escritorio con un asistente que sabe leer el estado del pipeline.

---

## Trampas conocidas

Todas mordieron en esta sesión. Están arregladas; la lista existe para que no
vuelvan por otra puerta.

**Rutas.** `Path(__file__).parents[N]` se rompe congelado. `tests/test_packaging.py`
**falla si reaparece** en `src/monitor_api/`; `paths.py` es la única excepción.
Cualquier módulo nuevo del agente debe usar `paths.py`.

**`sys.executable` congelado ES el binario.** Lanzar scripts con él arranca otro
monitor, en bucle. Usar `platform_caps.runner_python()`.

**Pydantic descarta en silencio lo que el modelo no declara.** `auto_advance` se
añadió a `describe()` y no a `PlatformInfo`: nunca llegó al frontend. Hay un test
que compara ambos conjuntos — mantenerlo al añadir campos.

**Un default en Pydantic hace el campo opcional en el OpenAPI.** Los tipos de TS
tienen que reflejarlo (`campo?: tipo`) o las comprobaciones de contrato fallan.

**Nombres de módulo de terceros cambian entre versiones.** El parche de MEGNet
apuntaba a `matgl.layers._graph_convolution_pyg`; en matgl 4.x es
`_graph_convolution`. Un `except ImportError: pass` lo convirtió en un fallo mudo
durante toda una tarde. Si se parchea algo de terceros, **avisar cuando no se
pueda aplicar**.

**Los `.pkl` van atados a la versión de scikit-learn.** Los de `models/` se
serializaron con **1.8.0**; con 1.9 no cargan. Pinado en el extra `[screening]`.

**`auto_advance` muta el pipeline.** Al detectar un lote terminado, el monitor
lanza el runner del siguiente o dispara el orquestador. Por defecto está activo
—sostiene la operación desatendida— y la cabecera lo avisa. Un agente con
permiso de escritura y `auto_advance` activo son **dos** cosas que pueden mover
el pipeline: hay que pensar la interacción antes de la Fase D.

**Los tests no deben depender del entorno.** Dependían de que no existiera
`configs/monitor.yaml` ni `DFT_MONITOR_TOKEN`. `create_app(config=...)` y un
fixture autouse lo aíslan.

**El fallback del SPA enmascaraba errores de la API.** Cualquier `/api/` mal
escrito devolvía HTML con 200. `_API_PREFIXES` en `main.py` lo excluye.

**`Path("")` es `Path(".")`**, que es verdadero. Comprobar la cadena de config,
no el `Path`.

**Estados que el pipeline escribe y los modelos no declaran.** `skipped_duplicate`
existía en el 37 % de los jobs y no estaba en `JobStatusLiteral`: `snapshot_job()`
lanzaba `ValidationError` y `poll_once` se lo tragaba en DEBUG. Ese log es ahora
WARNING.

**El Tier 1 de la cascada puntúa y criba, pero con holgura de σ.** No es un
descuido: el surrogate tiene MAE 0.31 eV y la ventana PV mide 0.7 eV. Cribar por
la estimación puntual tira materiales cuyo Eg real sí cae dentro — se midieron 10
de 100 en una prueba. `sigma_k: 0` da la malla dura si alguna vez hace falta.

**Una bandera de «ocupado» sin proceso detrás se queda encendida.** El poller
marcaba `_orchestrator_running = True` al lanzar el orquestador de active
learning y solo la limpiaba cuando aparecía un batch preparado. Si el
orquestador moría —volumen desmontado, disco lleno— la bandera quedaba fija: el
monitor se creía ocupado para siempre, ni reintentaba ni avisaba. Ahora se
guarda el `Popen` y se cosecha con `poll()`.

**Pero cosechar el fallo sin enfriamiento convierte el bloqueo en un bucle.**
Liberar la bandera hace que el ciclo siguiente relance el mismo orquestador
contra la misma causa, indefinidamente. De ahí el backoff exponencial
(5 min → 1 h) y la rendición tras 5 fallos seguidos: una causa transitoria se
resuelve sola, una permanente no inunda el log.

**La config de primer arranque se escribe una vez y manda para siempre.** Si el
primer lanzamiento ocurre con la raíz de datos equivocada, `_elegir_runs_dir()`
elige el fallback y `preparar_config()` no vuelve a tocar el archivo: queda un
`runs_dir` inservible que parece un bug del monitor. El `.desktop` debe fijar
`DFT_DATA_ROOT` **antes** del primer arranque, y ante un «0 jobs» inexplicable lo
primero es mirar `~/.config/dft-monitor/monitor.yaml`.

**`auto_advance` por defecto muta el pipeline al abrir.** Es lo correcto para la
operación desatendida y lo contrario de lo que espera un doble clic en el
escritorio. La config generada en modo congelado lo pone a `false`; desde el
repositorio se conserva `true`.

**`pkill -f <patrón>` se mata a sí mismo** si el patrón aparece en la línea de
comandos del propio shell. Con `[d]ft-monitor-engine` deja de coincidir consigo
mismo.

---

## Verificación

**Que nada se rompa.** Los 169 tests actuales tienen que seguir pasando, y
`./bin/dft-monitor-web --no-browser` comportarse igual:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

**La ventana.** Con cada shell forzado, comprobar que abre y que cerrarla para el
servidor:

```bash
./bin/dft-monitor-web --shell webview
./bin/dft-monitor-web --shell app
./bin/dft-monitor-web --shell browser
```

Y dos instancias a la vez, para validar el puerto efímero.

**El binario.** La prueba de fuego de siempre: extraer en un directorio limpio y
ejecutar sin `.venv`, sin Node y sin `PYTHONPATH`.

```bash
bash scripts/build_web.sh
cd /tmp && tar xzf .../dft-monitor-*-linux-x86_64.tar.gz
./dft-monitor/dft-monitor --data-root ~/DFT
```

**El agente.** Antes de darle escritura, comprobar sobre el anillo de lectura que
diagnostica sin actuar: preguntarle por qué falló un job concreto de
`local_runs/phase2_force/batch_000` y contrastar su respuesta con el log. Y que
cada propuesta de escritura aparece en la auditoría **aunque se rechace**.
