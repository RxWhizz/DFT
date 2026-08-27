"""Carga de secretos desde `.env`."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from monitor_api import entorno


_VARIABLES = (
    "DFT_MONITOR_TOKEN",
    "DFT_MONITOR_SESSION_SECRET",
    "DFT_MONITOR_TELEGRAM_BOT_TOKEN",
    "DFT_MONITOR_TELEGRAM_CHAT_ID",
    entorno.VARIABLE_RUTA,
)


@pytest.fixture(autouse=True)
def _entorno_limpio():
    """Aísla las variables que tocan estos tests, antes y después.

    Hay que restaurarlas a mano: `load_dotenv` escribe directamente en
    `os.environ`, así que `monkeypatch` no se entera y no puede deshacerlo. Sin
    esto, el primer test dejaba un DFT_MONITOR_TOKEN puesto para el resto de la
    sesión y `test_packaging` empezaba a recibir 401 en endpoints que espera
    abiertos.
    """
    previos = {v: os.environ.get(v) for v in _VARIABLES}
    for var in _VARIABLES:
        os.environ.pop(var, None)

    yield

    for var, valor in previos.items():
        if valor is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = valor


def test_carga_desde_el_directorio_actual(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DFT_MONITOR_TOKEN=abc123\n")
    monkeypatch.chdir(tmp_path)

    ruta = entorno.cargar()

    assert ruta == tmp_path / ".env"
    assert os.environ["DFT_MONITOR_TOKEN"] == "abc123"


def test_el_entorno_gana_al_fichero(tmp_path, monkeypatch):
    """Un valor puesto a mano no puede ser pisado por un `.env` viejo.

    Es la diferencia entre `DFT_MONITOR_TOKEN=x buho monitor serve` haciendo lo
    que dice y haciendo otra cosa sin avisar.
    """
    (tmp_path / ".env").write_text("DFT_MONITOR_TOKEN=del-fichero\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DFT_MONITOR_TOKEN", "del-entorno")

    entorno.cargar()

    assert os.environ["DFT_MONITOR_TOKEN"] == "del-entorno"


def test_variable_de_ruta_tiene_prioridad(tmp_path, monkeypatch):
    explicito = tmp_path / "otro.env"
    explicito.write_text("DFT_MONITOR_TOKEN=explicito\n")
    (tmp_path / ".env").write_text("DFT_MONITOR_TOKEN=implicito\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(entorno.VARIABLE_RUTA, str(explicito))

    assert entorno.cargar() == explicito
    assert os.environ["DFT_MONITOR_TOKEN"] == "explicito"


def test_sin_fichero_no_falla(tmp_path, monkeypatch):
    """Sin `.env` el monitor tiene que arrancar igual."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(entorno, "rutas_candidatas", lambda data_root=None: [tmp_path / ".env"])

    assert entorno.cargar() is None


def test_telegram_prefiere_el_entorno(monkeypatch):
    from monitor_api.poller import _telegram_bot_token, _telegram_chat_id

    cfg = {"bot_token": "del-yaml", "chat_id": "111"}
    assert _telegram_bot_token(cfg) == "del-yaml"

    monkeypatch.setenv("DFT_MONITOR_TELEGRAM_BOT_TOKEN", "del-entorno")
    monkeypatch.setenv("DFT_MONITOR_TELEGRAM_CHAT_ID", "222")
    assert _telegram_bot_token(cfg) == "del-entorno"
    assert _telegram_chat_id(cfg) == "222"


def test_telegram_vacio_no_revienta():
    from monitor_api.poller import _telegram_bot_token, _telegram_chat_id

    assert _telegram_bot_token({}) == ""
    assert _telegram_chat_id({"chat_id": None}) == ""


def test_el_ejemplo_no_trae_valores():
    """`.env.example` se comitea, así que ninguna variable puede traer valor."""
    ejemplo = Path(__file__).parent.parent / ".env.example"
    con_valor = [
        linea for linea in ejemplo.read_text(encoding="utf-8").splitlines()
        if "=" in linea and not linea.lstrip().startswith("#")
        and linea.split("=", 1)[1].strip()
    ]
    assert not con_valor, f"la plantilla trae valores: {con_valor}"


# Guardas contra comitear secretos

_PATRONES = (
    ("clave OpenAI",        r"sk-[A-Za-z0-9_-]{20,}"),
    ("token GitHub",        r"gh[pousr]_[A-Za-z0-9]{30,}"),
    ("PAT de GitHub",       r"github_pat_[A-Za-z0-9_]{20,}"),
    ("clave AWS",           r"AKIA[0-9A-Z]{16}"),
    ("token Slack",         r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("clave Google",        r"AIza[0-9A-Za-z_-]{30,}"),
    ("token de Telegram",   r"[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}"),
    ("clave privada",       r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _ficheros_trackeados() -> list[Path]:
    import subprocess

    raiz = Path(__file__).parent.parent
    try:
        salida = subprocess.run(
            ["git", "ls-files", "-z"], cwd=raiz,
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pytest.skip("no se puede consultar git")
    return [raiz / n for n in salida.split("\0") if n]


def test_ningun_fichero_trackeado_trae_credenciales():
    """Nada de lo que git sigue puede contener una credencial.

    El repositorio es público: una clave comiteada sigue en el historial
    aunque se borre después, así que el momento de pararla es antes del commit.
    """
    import re

    hallazgos: list[str] = []
    for fichero in _ficheros_trackeados():
        if not fichero.is_file() or fichero.stat().st_size > 2_000_000:
            continue
        try:
            texto = fichero.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for etiqueta, patron in _PATRONES:
            if re.search(patron, texto):
                hallazgos.append(f"{fichero}: {etiqueta}")

    assert not hallazgos, "credenciales en ficheros trackeados: " + "; ".join(hallazgos)


def test_el_env_no_esta_trackeado():
    """El `.env` real nunca debe entrar en git; la plantilla sí."""
    nombres = {f.name for f in _ficheros_trackeados()}
    assert ".env" not in nombres
    assert ".env.example" in nombres, "falta la plantilla .env.example"


def test_no_hay_configuracion_de_asistentes_trackeada():
    """`.claude/`, `.codex`, `.idea/` y compañía no pertenecen al repositorio."""
    import subprocess

    raiz = Path(__file__).parent.parent
    try:
        salida = subprocess.run(
            ["git", "ls-files"], cwd=raiz,
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pytest.skip("no se puede consultar git")

    prohibidos = (".claude/", ".codex", ".cursor/", ".aider", ".idea/", ".vscode/")
    colados = [
        linea for linea in salida.splitlines()
        if any(p in f"/{linea}" for p in prohibidos)
    ]
    assert not colados, f"configuración de asistente trackeada: {colados}"
