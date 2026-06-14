#!/usr/bin/env python3
"""Ingesta de datasets públicos de perovskitas → extxyz estándar para el MLIP.

Tres fuentes (zips descargados por el usuario en ~/Documents/Data):

  cssni3    (14056015.zip)  CsSn(Cl/Br/I)3   extxyz E+F+stress (FHI-aims all-electron)
                            → cabeza de entrenamiento (breadth, química Sn)
  perovsiap (17363611.zip)  Unified Perovs-IAP CSV pymatgen E+F+stress (VASP PBE)
                            → cabeza de entrenamiento (breadth, química completa + orgánicos)
  cspbclbr  (cspbclbr.zip)  CsPb(Cl/Br)3  xyz pos + etot.dat, SIN fuerzas (FHI-aims)
                            → NO entrena; test de orden energético de fases (eval_mlip.py)

Cada frame se escribe como extxyz estándar (energy/forces/stress vía SinglePointCalculator,
re-leíbles por ASE) con tags en info: head, source, dft_level, config_type (+ phase en
cspbclbr). Se filtra a la química A/B/X del proyecto y se subsamplea para coste CPU.

Las energías ABSOLUTAS difieren entre fuentes (all-electron vs PAW vs nuestro GPAW) → el
entrenamiento usa multi-cabeza (cada fuente su E0s). Fuerzas/stress sí son transferibles.

Uso:
  PYTHONPATH=src .venv/bin/python3 scripts/ingest_public_datasets.py --source cssni3 [--max 4000]
  PYTHONPATH=src .venv/bin/python3 scripts/ingest_public_datasets.py --source perovsiap [--max 4000]
  PYTHONPATH=src .venv/bin/python3 scripts/ingest_public_datasets.py --source cspbclbr
"""
from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import sys
import tempfile
import time
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path.home() / "Documents" / "Data"
OUT_DIR = ROOT / "data" / "mlip_datasets"

# Química del proyecto (cationes orgánicos MA/FA llegan como C/N/H en estructuras explícitas).
A_SET = {"Cs", "Rb", "K", "Na", "Li"}
B_SET = {"Pb", "Sn", "Ge"}
X_SET = {"F", "Cl", "Br", "I"}
ORGANIC = {"C", "N", "H"}              # MA (CH3NH3), FA (CH(NH2)2)
ALLOWED = A_SET | B_SET | X_SET | ORGANIC

# VASP reporta stress en kBar con signo + = compresión; ASE usa eV/Å³ con convención opuesta.
KBAR_TO_EVA3 = -0.1 / 160.21766208

csv.field_size_limit(10**9)


def _passes_chemistry(symbols: list[str]) -> bool:
    """Exige solo elementos permitidos, ≥1 haluro y ≥1 metal (A o B)."""
    eset = set(symbols)
    if not eset <= ALLOWED:
        return False
    if not (eset & X_SET):
        return False
    if not (eset & (A_SET | B_SET)):
        return False
    return True


def _attach(atoms, energy, forces, stress, tags: dict):
    """Adjunta E/F/stress como SinglePointCalculator y mete tags en info."""
    from ase.calculators.singlepoint import SinglePointCalculator
    # Limpiar claves heredadas que rompen el writer extxyz de ASE.
    for k in ("occupancy", "spacegroup", "unit_cell"):
        atoms.info.pop(k, None)
    spc = {"energy": float(energy)}
    if forces is not None:
        spc["forces"] = np.asarray(forces, dtype=float)
    if stress is not None:
        spc["stress"] = np.asarray(stress, dtype=float)
    atoms.calc = SinglePointCalculator(atoms, **spc)
    atoms.info.update(tags)
    return atoms


def _subsample(items: list, n_max: int, seed: int = 42) -> list:
    if n_max <= 0 or len(items) <= n_max:
        return items
    rng = np.random.RandomState(seed)
    idx = rng.permutation(len(items))[:n_max]
    return [items[int(i)] for i in sorted(idx)]


# ─────────────────────────── cssni3 (14056015.zip) ───────────────────────────

def ingest_cssni3(n_max: int, include_al: bool) -> tuple[list, dict]:
    from ase.io import read
    zip_path = DATA_DIR / "14056015.zip"
    members = ["sp_train_set.xyz"]
    if include_al:
        members.append("al_data.xyz")
    out, sysc, athist = [], Counter(), Counter()
    n_seen = n_drop = 0
    with zipfile.ZipFile(zip_path) as zf:
        for member in members:
            with zf.open(member) as fh, tempfile.NamedTemporaryFile(
                    "wb", suffix=".xyz", delete=True) as tmp:
                tmp.write(fh.read())
                tmp.flush()
                frames = read(tmp.name, index=":")
            for at in frames:
                n_seen += 1
                syms = at.get_chemical_symbols()
                if not _passes_chemistry(syms):
                    n_drop += 1
                    continue
                res = at.calc.results if at.calc is not None else {}
                e = res.get("energy", at.info.get("energy"))
                f = res.get("forces")
                s = res.get("stress", at.info.get("stress"))   # ya en eV/Å³
                if e is None or f is None:
                    n_drop += 1
                    continue
                tags = {"head": "cssni3", "source": "14056015.zip",
                        "dft_level": "FHI-aims_allelectron_PBE",
                        "config_type": member.replace(".xyz", "")}
                out.append(_attach(at, e, f, s, tags))
                sysc["".join(sorted(set(syms)))] += 1
                athist[len(at)] += 1
    out = _subsample(out, n_max)
    stats = {"source": "14056015.zip", "head": "cssni3", "members": members,
             "frames_seen": n_seen, "frames_dropped": n_drop,
             "frames_written": len(out), "n_max": n_max,
             "systems_top": dict(sysc.most_common(20)),
             "atoms_histogram": dict(sorted(athist.items()))}
    return out, stats


# ─────────────────────────── perovsiap (17363611.zip) ───────────────────────────

def ingest_perovsiap(n_max: int, stress_unit: str) -> tuple[list, dict]:
    from pymatgen.core import Structure
    from pymatgen.io.ase import AseAtomsAdaptor
    zip_path = DATA_DIR / "17363611.zip"
    member = "Perovs-IAP_train_set.csv"
    out, sysc, athist = [], Counter(), Counter()
    n_seen = n_drop = 0
    sfac = KBAR_TO_EVA3 if stress_unit == "kbar" else (
        -1.0 / 160.21766208 if stress_unit == "gpa" else 1.0)
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(member) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))
            for rowi, row in enumerate(reader):
                n_seen += 1
                try:
                    struct = Structure.from_dict(ast.literal_eval(row["Structure"]))
                    atoms = AseAtomsAdaptor.get_atoms(struct)
                except Exception:
                    n_drop += 1
                    continue
                syms = atoms.get_chemical_symbols()
                if not _passes_chemistry(syms):
                    n_drop += 1
                    continue
                try:
                    e = float(row["Actual Energy"])
                    f = np.asarray(ast.literal_eval(row["Actual Forces"]), dtype=float)
                except Exception:
                    n_drop += 1
                    continue
                s = None
                try:
                    smat = np.asarray(ast.literal_eval(row["Actual Stress"]), dtype=float)
                    # 3x3 → Voigt (xx,yy,zz,yz,xz,xy) con conversión de unidad/signo
                    s = np.array([smat[0, 0], smat[1, 1], smat[2, 2],
                                  smat[1, 2], smat[0, 2], smat[0, 1]]) * sfac
                except Exception:
                    s = None
                if len(f) != len(atoms):
                    n_drop += 1
                    continue
                tags = {"head": "perovsiap", "source": "17363611.zip",
                        "dft_level": "VASP_PBE", "config_type": "sp",
                        "struct_name": row.get("Structure Name", f"row{rowi}")}
                eform = row.get("Actual Formation Energy")
                if eform:
                    try:
                        tags["eform_eV_atom"] = round(float(eform), 6)
                    except ValueError:
                        pass
                out.append(_attach(atoms, e, f, s, tags))
                sysc["".join(sorted(set(syms)))] += 1
                athist[len(atoms)] += 1
    out = _subsample(out, n_max)
    stats = {"source": "17363611.zip", "head": "perovsiap", "member": member,
             "frames_seen": n_seen, "frames_dropped": n_drop,
             "frames_written": len(out), "n_max": n_max,
             "stress_unit_assumed": stress_unit,
             "systems_top": dict(sysc.most_common(20)),
             "atoms_histogram": dict(sorted(athist.items()))}
    return out, stats


# ─────────────────────────── cspbclbr (cspbclbr.zip) ───────────────────────────

def _read_xyz_frames_from_text(text: str) -> list:
    """Lee extxyz/xyz multi-frame desde un string (posiciones, sin calc)."""
    from ase.io import read
    with tempfile.NamedTemporaryFile("w", suffix=".xyz", delete=True) as tmp:
        tmp.write(text)
        tmp.flush()
        return read(tmp.name, index=":")


def ingest_cspbclbr() -> tuple[list, dict]:
    """Test de fases: energías por fase (sin fuerzas). Tags phase + es_endpoint."""
    zip_path = DATA_DIR / "cspbclbr.zip"
    phases = ["pnma", "i4mcm", "pm3m", "p4mbm"]
    out, n_seen, n_drop = [], 0, 0
    phase_counts: Counter = Counter()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        # 1) single_point_tails: structures.xyz + etot.dat por fase
        for phase in phases:
            sx = f"cspbclbr/cspbclbr_single_point_tails/{phase}/structures.xyz"
            et = f"cspbclbr/cspbclbr_single_point_tails/{phase}/etot.dat"
            if sx not in names or et not in names:
                continue
            frames = _read_xyz_frames_from_text(zf.read(sx).decode())
            energies = [float(x) for x in zf.read(et).decode().split() if x.strip()]
            if len(frames) != len(energies):
                print(f"  WARN {phase}: {len(frames)} frames vs {len(energies)} etot "
                      "— se trunca al mínimo", flush=True)
            for at, e in zip(frames, energies):
                n_seen += 1
                if not _passes_chemistry(at.get_chemical_symbols()):
                    n_drop += 1
                    continue
                tags = {"head": "cspbclbr", "source": "cspbclbr.zip",
                        "dft_level": "FHI-aims_allelectron", "config_type": "tail",
                        "phase": phase, "is_endpoint": False}
                out.append(_attach(at, e, None, None, tags))
                phase_counts[phase] += 1
        # 2) end_points: estructuras puras por fase (las más limpias para el test)
        for name in names:
            if "/cspbclbr_end_points/" not in name or not name.endswith("structure.xyz"):
                continue
            base = name.rsplit("/", 1)[0]
            tag = base.rsplit("/", 1)[1]            # p.ej. cspbbr3_pnma
            et_name = base + "/etot.dat"
            if et_name not in names:
                continue
            phase = next((p for p in phases if tag.endswith(p)), "unknown")
            try:
                at = _read_xyz_frames_from_text(zf.read(name).decode())[0]
                e = float(zf.read(et_name).decode().split()[0])
            except Exception:
                continue
            n_seen += 1
            if not _passes_chemistry(at.get_chemical_symbols()):
                n_drop += 1
                continue
            tags = {"head": "cspbclbr", "source": "cspbclbr.zip",
                    "dft_level": "FHI-aims_allelectron", "config_type": "endpoint",
                    "phase": phase, "is_endpoint": True, "endpoint_name": tag}
            out.append(_attach(at, e, None, None, tags))
            phase_counts[f"{phase}_endpoint"] += 1
    stats = {"source": "cspbclbr.zip", "head": "cspbclbr",
             "role": "phase_ordering_test (NO entrena)",
             "frames_seen": n_seen, "frames_dropped": n_drop,
             "frames_written": len(out), "by_phase": dict(phase_counts)}
    return out, stats


# ─────────────────────────── main ───────────────────────────

INGESTORS = {"cssni3": "ingest_cssni3", "perovsiap": "ingest_perovsiap",
             "cspbclbr": "ingest_cspbclbr"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, choices=list(INGESTORS))
    ap.add_argument("--max", type=int, default=4000,
                    help="máx frames a escribir tras filtrar (subsample; 0 = todos)")
    ap.add_argument("--include-al", action="store_true",
                    help="cssni3: incluir también al_data.xyz (relajación)")
    ap.add_argument("--stress-unit", default="kbar", choices=["kbar", "gpa", "eva3"],
                    help="perovsiap: unidad del stress en el CSV (def. kbar)")
    args = ap.parse_args()

    from ase.io import write
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    if args.source == "cssni3":
        frames, stats = ingest_cssni3(args.max, args.include_al)
        out_name = "cssni3.extxyz"
    elif args.source == "perovsiap":
        frames, stats = ingest_perovsiap(args.max, args.stress_unit)
        out_name = "perovsiap.extxyz"
    else:
        frames, stats = ingest_cspbclbr()
        out_name = "cspbclbr_phase_test.extxyz"

    if not frames:
        raise SystemExit(f"{args.source}: 0 frames tras filtrar — revisa rutas/filtros.")

    # Rangos físicos para detectar unidades/referencias mal puestas.
    epa = [at.calc.results["energy"] / len(at) for at in frames]
    fmaxs = [float(np.abs(at.calc.results["forces"]).max())
             for at in frames if "forces" in at.calc.results]
    stats["energy_per_atom_eV"] = {"min": round(min(epa), 3), "max": round(max(epa), 3),
                                   "median": round(float(np.median(epa)), 3)}
    if fmaxs:
        stats["fmax_eV_A"] = {"min": round(min(fmaxs), 3), "max": round(max(fmaxs), 3),
                              "median": round(float(np.median(fmaxs)), 3)}
    stats["elapsed_s"] = round(time.time() - t0, 1)

    out_path = OUT_DIR / out_name
    write(str(out_path), frames, format="extxyz")
    (OUT_DIR / out_name.replace(".extxyz", "_stats.json")).write_text(
        json.dumps(stats, indent=2, ensure_ascii=False))
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"\n→ {out_path}  ({len(frames)} frames)")


if __name__ == "__main__":
    main()
