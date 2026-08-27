# -*- mode: python ; coding: utf-8 -*-
"""Empaquetado del monitor DFT con PyInstaller.

Se construye en modo `--onedir` y se comprime después: con ~200 MB dentro, el
modo `--onefile` descomprimiría todo a un temporal en CADA arranque, entre 10 y
30 segundos por vez. Con onedir se extrae una vez al instalar y arranca al
instante; sigue siendo un único archivo que descargar.

Los recursos van a la raíz del paquete, que es lo que `monitor_api.paths`
resuelve como `bundle_root()` (`sys._MEIPASS`).

    python -m PyInstaller packaging/dft-monitor.spec --noconfirm
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

# ── Recursos empaquetados ────────────────────────────────────────────────────
# Rutas relativas a bundle_root(); paths.py las busca exactamente ahí.
datas = [
    (str(ROOT / "src" / "monitor_api" / "static"), "static"),
    (str(ROOT / "configs" / "monitor.example.yaml"), "configs"),
]

# Estructuras preconvertidas por scripts/pregenerate_structures.py: sin los
# JSON de ASE, el binario no necesita `ase` (26 MB) para el visor 3D.
estructuras = ROOT / "build" / "structures"
if estructuras.is_dir():
    datas.append((str(estructuras), "structures"))
else:
    raise SystemExit(
        "Faltan las estructuras preconvertidas. Ejecuta antes:\n"
        "  python scripts/pregenerate_structures.py"
    )

# Modelos del surrogate (~21 MB). Sin ellos la vista ML degrada con un aviso,
# pero el binario completo los lleva.
for pkl in sorted((ROOT / "models").glob("surrogate_*.pkl")):
    datas.append((str(pkl), "models"))
for met in sorted((ROOT / "models").glob("surrogate_*.metrics.json")):
    datas.append((str(met), "models"))

# ── Imports que PyInstaller no ve ────────────────────────────────────────────
hiddenimports = [
    # Los secretos se leen de .env. El import es perezoso, así que sin
    # declararlo aquí el binario podría quedarse sin él y no cargar
    # ninguna clave, en silencio.
    "dotenv",
    # uvicorn carga sus implementaciones por nombre en tiempo de ejecución.
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    # La cookie de sesión firmada.
    "itsdangerous",
    # El surrogate se despickliza y necesita las clases concretas presentes.
    "sklearn.ensemble._forest",
    "sklearn.ensemble._gb",
    "sklearn.tree._tree",
    "sklearn.pipeline",
    "sklearn.preprocessing._data",
    "sklearn.impute._base",
]
if sys.platform != "win32":
    hiddenimports += ["uvicorn.loops.uvloop", "uvicorn.protocols.http.httptools_impl"]

# ── Lo que no debe entrar ────────────────────────────────────────────────────
excludes = [
    "matplotlib",      # el monitor no dibuja nada en el servidor
    "ase",             # ya no hace falta: las estructuras van preconvertidas
    "gpaw", "phonopy", "spglib",
    "tkinter", "IPython", "jupyter", "notebook",
    "pytest", "_pytest", "sphinx",
    "torch", "matgl", "dgl",
    # Qt WebEngine entraba por los backends opcionales de pywebview y pesaba
    # 344 MB —195 de libQt6WebEngineCore, 118 de PyQt6, 31 de ICU—, el 72 % del
    # artefacto. Solo servía para `--shell webview/app`, que abre una ventana
    # nativa: eso es exactamente lo que hace la app de escritorio, y mucho
    # mejor. Este binario se abre en el navegador; el lanzador ya degrada a
    # navegador cuando falta pywebview.
    "PyQt6", "PyQt5", "PySide6", "PySide2", "webview",
    # Dependencia transitiva que nada del monitor usa.
    "boto3", "botocore", "s3transfer",
    "numpy.tests", "scipy.tests", "sklearn.tests", "pandas.tests",
    "pandas.plotting._matplotlib",
]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dft-monitor-web",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX rompe algunas .so de numpy/scipy
    console=True,       # es un servidor: la salida importa
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="dft-monitor-web",
)
