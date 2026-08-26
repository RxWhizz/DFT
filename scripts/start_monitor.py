#!/usr/bin/env python3
"""Arranca el servidor FastAPI del monitor DFT.

Uso:
    python scripts/start_monitor.py
    python scripts/start_monitor.py --host 127.0.0.1 --port 8000 --reload
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Asegurar que src/ esté en el path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


NON_LOCAL_HOSTS = ("0.0.0.0", "::", "")


def _check_exposure(host: str) -> None:
    """Impide exponer el monitor en la red sin autenticación.

    El monitor puede matar procesos y lanzar runners; abierto en la LAN sin
    token, cualquiera de la red puede hacerlo.
    """
    if host not in NON_LOCAL_HOSTS and not host.startswith("127."):
        return  # una IP concreta: decisión deliberada del usuario
    if host.startswith("127."):
        return

    from monitor_api.main import ROOT, load_config
    from monitor_api.security import load_auth_config

    try:
        auth = load_auth_config(load_config(ROOT / "configs" / "monitor.yaml"))
    except ValueError as exc:
        print(f"ERROR de configuración: {exc}")
        sys.exit(1)

    if not auth.enabled:
        print(
            f"ERROR: --host {host} expone el monitor en la red sin autenticación.\n"
            "       El monitor puede matar procesos y lanzar runners.\n\n"
            "       Configura un token antes de exponerlo:\n"
            "         cp configs/monitor.example.yaml configs/monitor.yaml\n"
            "         # y define monitor.auth.token\n"
            "       o bien:  export DFT_MONITOR_TOKEN='...'\n\n"
            "       Para uso local basta con el default:  --host 127.0.0.1"
        )
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="DFT Monitor API")
    ap.add_argument("--host",   default="127.0.0.1",
                    help="Host de escucha (default 127.0.0.1). Usa 0.0.0.0 para exponer "
                         "en la red; requiere token de auth configurado.")
    ap.add_argument("--port",   type=int, default=8000,        help="Puerto (default 8000)")
    ap.add_argument("--reload", action="store_true",           help="Hot-reload (dev)")
    ap.add_argument("--log-level", default="info",
                    choices=["debug", "info", "warning", "error"],
                    help="Nivel de logging uvicorn")
    args = ap.parse_args()

    try:
        import uvicorn
    except ImportError:
        print('ERROR: uvicorn no instalado. Ejecuta:\n  pip install -e ".[web]"')
        sys.exit(1)

    _check_exposure(args.host)

    print(f"Iniciando DFT Monitor en http://{args.host}:{args.port}")
    print(f"Docs: http://localhost:{args.port}/docs")

    uvicorn.run(
        "monitor_api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        # workers=1 fijo, no configurable: el estado del monitor (los snapshots
        # del poller) vive en memoria del proceso y el listener de Telegram
        # arranca en el lifespan. Con N workers habría N pollers divergentes y
        # N bots respondiendo el mismo comando.
        workers=1,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
