#!/usr/bin/env python3
"""Vuelca el esquema OpenAPI del monitor a un archivo.

Los tipos del frontend se generan desde aquí:

    python scripts/dump_openapi.py
    cd frontend && npm run gen:api

Se hace sin levantar el servidor —y sin necesitar sesión— porque `/openapi.json`
está detrás de la autenticación. Además así los modelos Pydantic de
src/monitor_api/models.py son la única fuente de verdad: si cambia un campo, el
build del frontend falla en vez de romper en tiempo de ejecución.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Vuelca el OpenAPI del monitor DFT")
    ap.add_argument(
        "--out",
        default=str(ROOT / "src" / "monitor_api" / "openapi.json"),
        help="Ruta de salida (default: src/monitor_api/openapi.json)",
    )
    args = ap.parse_args()

    try:
        from monitor_api.main import create_app
    except ImportError as exc:
        print(f'ERROR: falta alguna dependencia web ({exc}).\n  pip install -e ".[web]"')
        sys.exit(1)

    schema = create_app().openapi()
    _normalize_for_dart_client(schema)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")

    n_rutas = len(schema.get("paths", {}))
    print(f"OpenAPI escrito en {out}  ({n_rutas} rutas)")


def _normalize_for_dart_client(schema: dict) -> None:
    """Ajustes pequeños para generadores Dart que aún tropiezan con OAS 3.1."""
    _strip_defaults(schema)
    schemas = schema.get("components", {}).get("schemas", {})
    validation = schemas.get("ValidationError")
    if isinstance(validation, dict):
        loc = validation.get("properties", {}).get("loc")
        if isinstance(loc, dict):
            loc["items"] = {"type": "string"}


def _strip_defaults(value) -> None:
    if isinstance(value, dict):
        value.pop("default", None)
        for child in value.values():
            _strip_defaults(child)
    elif isinstance(value, list):
        for child in value:
            _strip_defaults(child)


if __name__ == "__main__":
    main()
