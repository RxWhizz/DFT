#!/usr/bin/env python3
"""Recalcula `tolerance_t` tras corregir el radio del sitio A a coordinacion 12.

Hasta 2026-09 `ml_surrogate.features.IONIC_RADII` usaba los radios de Shannon a
coordinacion **6** para Cs/Rb/K, etiquetados como coordinacion 12. El sitio A de
una perovskita ABX3 esta rodeado por 12 aniones X, asi que el radio correcto es
el de CN12 -- y con el, el factor de tolerancia de todo el espacio de busqueda
cambia.

`tolerance_t` es la unica de las cinco features del surrogate que depende de
r_A: `oct_factor` (r_B/r_X) y `vol_est_A3` (de r_B, r_X) no cambian, y
`band_gap_gga_eV` / `Eform_eV_atom` son datos medidos.

Este script reescribe los ficheros que llevan el valor ya calculado:

  * `data/discovery/candidates.jsonl`  -- registro del espacio de busqueda
  * `data/discovery/surrogate_training_dft.csv` -- conjunto de entrenamiento

No toca las etiquetas DFT (`Eg_target_eV`, `energy_per_atom_eV`): esas son
medidas, no derivadas, y la correccion no las invalida. Tampoco toca las
estructuras ya calculadas -- la constante de red sale de `lattice_est(r_B, r_X)`
y no depende del sitio A.

Uso:
    python scripts/migrate_tolerance_factor_cn12.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ml_surrogate.features import IONIC_RADII, goldschmidt  # noqa: E402

CANDIDATES = ROOT / "data" / "discovery" / "candidates.jsonl"
TRAINING = ROOT / "data" / "discovery" / "surrogate_training_dft.csv"


def _radio_efectivo(fracciones: dict[str, float]) -> float:
    """Radio del sitio, promediado por fraccion de ocupacion."""
    return sum(f * IONIC_RADII[sp] for sp, f in fracciones.items())


def _t_de_fracciones(fracciones: dict[str, dict[str, float]]) -> float:
    return goldschmidt(
        _radio_efectivo(fracciones["A"]),
        _radio_efectivo(fracciones["B"]),
        _radio_efectivo(fracciones["X"]),
    )


def migrar_candidatos(dry_run: bool) -> dict[str, float]:
    """Reescribe candidates.jsonl y devuelve {candidate_id: t_nuevo}."""
    if not CANDIDATES.is_file():
        print(f"  (no existe {CANDIDATES}, se omite)")
        return {}

    nuevos: dict[str, float] = {}
    salida: list[str] = []
    cambiados = 0

    with CANDIDATES.open(encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            row = json.loads(linea)
            t_nuevo = round(_t_de_fracciones(row["fractions"]), 5)
            if abs(t_nuevo - float(row.get("tolerance_t", 0.0))) > 1e-9:
                cambiados += 1
            row["tolerance_t"] = t_nuevo
            nuevos[row["candidate_id"]] = t_nuevo
            salida.append(json.dumps(row, ensure_ascii=False))

    print(f"  candidatos: {len(nuevos)} leidos, {cambiados} con t distinto")
    if not dry_run and salida:
        shutil.copy2(CANDIDATES, CANDIDATES.with_suffix(".jsonl.pre-cn12"))
        CANDIDATES.write_text("\n".join(salida) + "\n", encoding="utf-8")
        print(f"  escrito (respaldo en {CANDIDATES.name}.pre-cn12)")
    return nuevos


def migrar_entrenamiento(t_por_id: dict[str, float], dry_run: bool) -> None:
    if not TRAINING.is_file():
        print(f"  (no existe {TRAINING}, se omite)")
        return

    import pandas as pd

    df = pd.read_csv(TRAINING)
    if "tolerance_t" not in df.columns:
        print("  (sin columna tolerance_t, se omite)")
        return

    antes = df["tolerance_t"].copy()
    sin_match = 0
    for i, cid in enumerate(df["candidate_id"].astype(str)):
        if cid in t_por_id:
            df.at[i, "tolerance_t"] = t_por_id[cid]
        else:
            sin_match += 1

    cambiados = int((antes != df["tolerance_t"]).sum())
    print(f"  entrenamiento: {len(df)} filas, {cambiados} actualizadas, "
          f"{sin_match} sin candidato en el registro")
    if sin_match:
        print("  AVISO: las filas sin match conservan el t viejo; revisa el registro.")

    if not dry_run:
        shutil.copy2(TRAINING, TRAINING.with_suffix(".csv.pre-cn12"))
        df.to_csv(TRAINING, index=False)
        print(f"  escrito (respaldo en {TRAINING.name}.pre-cn12)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Calcula y reporta sin escribir nada.")
    args = ap.parse_args()

    print(f"r_A en uso: Cs={IONIC_RADII['Cs']} Rb={IONIC_RADII['Rb']} K={IONIC_RADII['K']}")
    if IONIC_RADII["Cs"] != 1.88:
        print("ERROR: features.py no tiene el radio CN12; corrige eso primero.",
              file=sys.stderr)
        return 1

    print("\n1. Registro de candidatos")
    t_por_id = migrar_candidatos(args.dry_run)
    print("\n2. Conjunto de entrenamiento")
    migrar_entrenamiento(t_por_id, args.dry_run)

    if args.dry_run:
        print("\n(dry-run: no se escribio nada)")
    else:
        print("\nListo. Reentrena el surrogate para que use los valores nuevos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
