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


def main():
    ap = argparse.ArgumentParser(description="DFT Monitor API")
    ap.add_argument("--host",   default="0.0.0.0",             help="Host (default 0.0.0.0)")
    ap.add_argument("--port",   type=int, default=8000,        help="Puerto (default 8000)")
    ap.add_argument("--reload", action="store_true",           help="Hot-reload (dev)")
    ap.add_argument("--workers", type=int, default=1,          help="Workers uvicorn")
    ap.add_argument("--log-level", default="info",
                    choices=["debug", "info", "warning", "error"],
                    help="Nivel de logging uvicorn")
    args = ap.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn no instalado. Ejecuta:\n  pip install fastapi uvicorn[standard] httpx")
        sys.exit(1)

    print(f"Iniciando DFT Monitor en http://{args.host}:{args.port}")
    print(f"Docs: http://localhost:{args.port}/docs")

    uvicorn.run(
        "monitor_api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
