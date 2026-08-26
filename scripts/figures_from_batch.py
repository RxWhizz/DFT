#!/usr/bin/env python3
"""Genera figuras de las estructuras que salieron del cribado.

`generate_visualizations.py` está pensado para las fases de referencia
(alpha, beta, gamma) que viven en `calculations/`. Los candidatos del cribado
son otra cosa: cientos de CIF repartidos por `local_runs/<fase>/batch_*/<job>/`,
sin fase asociada. Este script los localiza, los etiqueta con su fórmula y se
los pasa al generador en una sola corrida.

Uso:
    python scripts/figures_from_batch.py                    # último lote, 8 estructuras
    python scripts/figures_from_batch.py --batch batch_765153 --limit 20
    python scripts/figures_from_batch.py --all              # todas las del lote
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Seis figuras por estructura: con un lote entero son cientos de archivos y
# varios minutos, así que por defecto se toman solo unas pocas.
LIMITE_POR_DEFECTO = 8


def lotes_disponibles() -> list[Path]:
    """Lotes con estructuras, del más reciente al más antiguo."""
    encontrados = []
    for base in sorted(ROOT.glob("local_runs/*")):
        if not base.is_dir():
            continue
        for lote in base.glob("batch_*"):
            if lote.is_dir() and any(lote.glob("*/structure.cif")):
                encontrados.append(lote)
    return sorted(encontrados, key=lambda d: d.stat().st_mtime, reverse=True)


def estructuras_de(lote: Path, limite: int | None) -> list[tuple[str, Path]]:
    """(etiqueta, ruta) de las estructuras del lote.

    Se prefieren los jobs convergidos: son los que interesan mirar, y su
    geometría es la que de verdad se calculó.
    """
    convergidas, otras = [], []
    for cif in sorted(lote.glob("*/structure.cif")):
        meta_f = cif.parent / "metadata.json"
        st_f = cif.parent / "status.json"
        try:
            formula = json.loads(meta_f.read_text(encoding="utf-8")).get("formula")
        except (OSError, json.JSONDecodeError):
            formula = None
        etiqueta = formula or cif.parent.name
        try:
            estado = json.loads(st_f.read_text(encoding="utf-8")).get("status")
        except (OSError, json.JSONDecodeError):
            estado = None
        (convergidas if estado == "converged" else otras).append((etiqueta, cif))

    elegidas = convergidas + otras
    # Etiquetas únicas: dos candidatos pueden compartir fórmula redondeada y el
    # generador sobreescribiría los archivos del primero.
    vistas: dict[str, int] = {}
    salida = []
    for etiqueta, cif in elegidas:
        n = vistas.get(etiqueta, 0)
        vistas[etiqueta] = n + 1
        salida.append((etiqueta if n == 0 else f"{etiqueta}_{n + 1}", cif))
    return salida if limite is None else salida[:limite]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", help="Nombre del lote (default: el más reciente).")
    ap.add_argument("--limit", type=int, default=LIMITE_POR_DEFECTO,
                    help=f"Estructuras a dibujar (default {LIMITE_POR_DEFECTO}).")
    ap.add_argument("--all", action="store_true", help="Todas las del lote.")
    ap.add_argument("--out-dir", help="Destino (default: imagenes/<lote>).")
    ap.add_argument("--list", action="store_true", help="Solo enumerar los lotes.")
    args = ap.parse_args()

    lotes = lotes_disponibles()
    if not lotes:
        print("No hay ningún lote con structure.cif.", file=sys.stderr)
        return 1

    if args.list:
        for lote in lotes:
            n = len(list(lote.glob("*/structure.cif")))
            print(f"  {lote.relative_to(ROOT)}  ({n} estructuras)")
        return 0

    if args.batch:
        lote = next((d for d in lotes if d.name == args.batch), None)
        if lote is None:
            print(f"No encuentro el lote '{args.batch}'. Usa --list.", file=sys.stderr)
            return 1
    else:
        lote = lotes[0]

    estructuras = estructuras_de(lote, None if args.all else args.limit)
    if not estructuras:
        print(f"{lote.name} no tiene estructuras.", file=sys.stderr)
        return 1

    destino = Path(args.out_dir) if args.out_dir else ROOT / "imagenes" / lote.name
    print(f"  {lote.name}: {len(estructuras)} estructuras -> {destino}")

    cmd = [sys.executable, str(ROOT / "scripts" / "generate_visualizations.py"),
           "--structures-only", "--skip-gpaw", "--out-dir", str(destino)]
    for etiqueta, cif in estructuras:
        cmd += ["--structure", f"{etiqueta}={cif}"]

    entorno = {**dict(__import__("os").environ), "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.run(cmd, cwd=str(ROOT), env=entorno)
    if proc.returncode != 0:
        return proc.returncode

    pngs = sorted(destino.glob("*.png"))
    print(f"  {len(pngs)} figuras en {destino.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
