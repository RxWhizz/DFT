#!/usr/bin/env python3
"""Extrae el subconjunto ABX3-haluro de MPtrj (capa 1 del curriculum MACE).

MPtrj = trayectorias de relajación de Materials Project con E+F+stress al nivel
PBE(+U solo óxidos/TM) — el dataset con que se entrenó MACE-MP-0. Filtramos los
sistemas químicos de nuestra química: A∈{Cs,Rb,K,Na,Li}, B∈{Pb,Sn,Ge}, X∈{F,Cl,Br,I}.
Se incluyen binarios (CsI, SnI2, PbBr2…) — enseñan las referencias de descomposición —
y ternarios (perovskitas y polimorfos no-perovskita). Los haluros NO llevan Hubbard U
en MP ⇒ etiquetas consistentes con nuestra capa 2 (PBE puro).

Streaming con ijson (el JSON pesa 12.2 GB; no cabe en RAM).

Uso: .venv/bin/python3 scripts/extract_mptrj_abx3.py
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import ijson
import numpy as np

SRC = Path("/media/luis-ochoa/Nuevo vol/dft/datasets/MPtrj_2022.9_full.json")
OUT_DIR = Path("/media/luis-ochoa/Nuevo vol/dft/datasets")
OUT_XYZ = OUT_DIR / "mptrj_abx3_halides.extxyz"
OUT_STATS = OUT_DIR / "mptrj_abx3_halides_stats.json"

A_SET = {"Cs", "Rb", "K", "Na", "Li"}
B_SET = {"Pb", "Sn", "Ge"}
X_SET = {"F", "Cl", "Br", "I"}
ALLOWED = A_SET | B_SET | X_SET

# 1 kBar = 0.1 GPa; 1 GPa = 1/160.21766 eV/Å³. VASP reporta + = compresión,
# ASE usa la convención opuesta → signo negativo.
KBAR_TO_EVA3 = -0.1 / 160.21766208


def frame_to_extxyz_block(fid: str, fr: dict) -> tuple[str, dict] | None:
    st = fr.get("structure") or {}
    sites = st.get("sites") or []
    if not sites:
        return None
    elems = []
    pos = []
    for s in sites:
        sp = s.get("species", [{}])[0].get("element")
        if sp is None:
            return None
        elems.append(sp)
        pos.append(s.get("xyz"))
    eset = set(elems)
    if not eset <= ALLOWED:
        return None
    if not (eset & X_SET) or not (eset & (A_SET | B_SET)):
        return None   # exigir al menos un haluro y un metal

    energy = fr.get("uncorrected_total_energy")
    forces = fr.get("force")
    if energy is None or forces is None:
        return None
    cell = (st.get("lattice") or {}).get("matrix")
    if cell is None:
        return None

    n = len(elems)
    lat = " ".join(f"{v:.8f}" for row in cell for v in row)
    props = 'Properties=species:S:1:pos:R:3:forces:R:3'
    extra = f'mp_frame_id="{fid}" config_type=mptrj_abx3 layer=1'
    stress = fr.get("stress")
    stress_str = ""
    if stress is not None:
        s = (np.asarray(stress, dtype=float) * KBAR_TO_EVA3).flatten()
        stress_str = ' stress="' + " ".join(f"{v:.8f}" for v in s) + '"'
    header = (f'Lattice="{lat}" {props} energy={float(energy):.8f}'
              f'{stress_str} pbc="T T T" {extra}')
    lines = [str(n), header]
    for el, p, f in zip(elems, pos, forces):
        lines.append(f"{el} {p[0]:.8f} {p[1]:.8f} {p[2]:.8f} "
                     f"{f[0]:.8f} {f[1]:.8f} {f[2]:.8f}")
    key = "".join(sorted(eset))
    return "\n".join(lines) + "\n", {"n_atoms": n, "system": key}


def main() -> None:
    t0 = time.time()
    n_mat = n_mat_kept = n_frames = 0
    sys_counter: Counter = Counter()
    atom_hist: Counter = Counter()
    with SRC.open("rb") as fh, OUT_XYZ.open("w") as out:
        for mp_id, frames in ijson.kvitems(fh, ""):
            n_mat += 1
            kept_here = 0
            for fid, fr in (frames or {}).items():
                block = frame_to_extxyz_block(fid, fr)
                if block is None:
                    continue
                text, meta = block
                out.write(text)
                n_frames += 1
                kept_here += 1
                sys_counter[meta["system"]] += 1
                atom_hist[meta["n_atoms"]] += 1
            if kept_here:
                n_mat_kept += 1
            if n_mat % 10000 == 0:
                print(f"  …{n_mat} materiales, {n_frames} frames extraídos "
                      f"({time.time()-t0:.0f}s)", flush=True)

    stats = {
        "materials_scanned": n_mat,
        "materials_kept": n_mat_kept,
        "frames": n_frames,
        "systems_top": dict(sys_counter.most_common(25)),
        "n_systems": len(sys_counter),
        "atoms_histogram_top": dict(sorted(atom_hist.items())[:20]),
        "elapsed_s": round(time.time() - t0, 1),
        "source": str(SRC),
        "filter": {"A": sorted(A_SET), "B": sorted(B_SET), "X": sorted(X_SET)},
    }
    OUT_STATS.write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
    print(f"\n→ {OUT_XYZ}")


if __name__ == "__main__":
    main()
