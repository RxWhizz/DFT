#!/usr/bin/env python3
"""Prepara el árbol de estructuras que viaja dentro del binario.

`services/files.py` convierte a CIF los `structures/*.json` —el formato de base
de datos de ASE— al vuelo. Son solo cuatro archivos, pero arrastran `ase` (26 MB)
al ejecutable para nada: convirtiéndolos aquí, el binario no necesita ASE y el
visor 3D sigue funcionando igual.

    python scripts/pregenerate_structures.py --out build/structures

El código conserva el camino de conversión para cuando se ejecuta desde el
repositorio, donde ASE sí está disponible.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

ORIGEN = ROOT / "structures"


def convertir(json_path: Path, destino: Path) -> None:
    from monitor_api.services.files import _ase_json_a_cif

    destino.write_text(_ase_json_a_cif(json_path), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Preconvierte structures/ para empaquetar")
    ap.add_argument("--out", default=str(ROOT / "build" / "structures"),
                    help="Directorio de salida (default: build/structures)")
    ap.add_argument("--clean", action="store_true", help="Vaciar la salida antes")
    args = ap.parse_args()

    salida = Path(args.out).resolve()
    if args.clean and salida.exists():
        shutil.rmtree(salida)
    salida.mkdir(parents=True, exist_ok=True)

    if not ORIGEN.is_dir():
        raise SystemExit(f"No existe {ORIGEN}")

    convertidos = copiados = 0
    for path in sorted(ORIGEN.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ORIGEN)
        destino = salida / rel
        destino.parent.mkdir(parents=True, exist_ok=True)

        if path.suffix.lower() == ".json":
            cif = destino.with_suffix(".cif")
            if cif.exists() or (ORIGEN / rel.with_suffix(".cif")).exists():
                continue  # ya hay un CIF de verdad para esta estructura
            try:
                convertir(path, cif)
            except Exception as exc:
                print(f"  aviso: no se pudo convertir {rel}: {exc}")
                continue
            convertidos += 1
        elif path.suffix.lower() in {".cif", ".xyz", ".extxyz"}:
            shutil.copy2(path, destino)
            copiados += 1

    print(f"Estructuras preparadas en {salida}")
    print(f"  convertidas desde JSON de ASE: {convertidos}")
    print(f"  copiadas tal cual:             {copiados}")

    if not convertidos and not copiados:
        raise SystemExit("No se preparó ninguna estructura — revisa structures/")


if __name__ == "__main__":
    main()
