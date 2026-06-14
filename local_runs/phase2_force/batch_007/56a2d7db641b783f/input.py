#!/usr/bin/env python3
"""Job Fase 2A: PBE single-point E+F(+stress) sobre K estructuras rattled -> extxyz MACE.

Sin Hubbard U (consistente con MPtrj/MACE-MP-0) y sin FIRE: para datos de fine-tuning de
un MLIP se quieren E+F sobre estructuras DIVERSAS (rattled), no la relajacion al minimo.
"""
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import numpy as np
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import read, write
from gpaw import GPAW, PW
from gpaw.eigensolvers import Davidson
from gpaw.mixer import Mixer
from gpaw.mpi import world


JOB_ROOT = Path(__file__).resolve().parent
STRUCTURE = JOB_ROOT / "structure.cif"
METADATA = json.loads((JOB_ROOT / "metadata.json").read_text())
LABELS = json.loads(r"""[
  {
    "label": "pbe",
    "method": "PBE",
    "u_ev": null,
    "relative_dir": "pbe"
  }
]""")
N_CORES = 8
KPTS_SUPERCELL = [2, 2, 2]
N_RATTLE = 4
RATTLE_STDEV = 0.08
IS_MASTER = world.rank == 0


def _now():
    import datetime
    return datetime.datetime.utcnow().isoformat() + "Z"


def _read_status():
    base = {
        "candidate_id": METADATA.get("candidate_id"),
        "formula": METADATA.get("formula"),
        "phase2_batch_id": METADATA.get("phase2_batch_id"),
        "selection_rank": METADATA.get("selection_rank"),
        "n_labels_expected": len(LABELS),
        "labels_expected": LABELS,
    }
    p = JOB_ROOT / "status.json"
    if not p.exists():
        return base
    try:
        status = json.loads(p.read_text())
    except Exception:
        return base
    if not status.get("candidate_id"):
        base.update(status)
        return base
    return status


def _write_status(update):
    if not IS_MASTER:
        world.barrier()
        return
    status = _read_status()
    status.update(update)
    tmp = JOB_ROOT / "status.json.tmp"
    tmp.write_text(json.dumps(status, indent=2))
    tmp.replace(JOB_ROOT / "status.json")
    world.barrier()


def _kpts_for_atoms(atoms):
    # [2,2,2] para superceldas (test de convergencia 2026-06-09: Γ-only da 0.2 eV/átomo de
    # error en Sn; [2,2,2] converge a 0.015 eV/átomo vs [3,3,3]).
    return KPTS_SUPERCELL if len(atoms) > 10 else [4, 4, 4]


def _calc_kwargs(atoms):
    kpts = _kpts_for_atoms(atoms)
    has_sn = "Sn" in (METADATA.get("formula") or "")
    # SIN Hubbard U (consistente MPtrj). Sn: smearing ancho (0.2) + mixer estandar (0.05)
    # para suavizar la oscilacion SCF — NO Mixer(0.002) que es lentisimo, ni U.
    return {
        "mode": PW(450),
        "xc": "PBE",
        "kpts": {"size": kpts, "gamma": True},
        "occupations": {"name": "fermi-dirac", "width": 0.2 if has_sn else 0.05},
        "eigensolver": Davidson(niter=3),
        # parallel: omitido -> GPAW auto-decide (robusto para cualquier N_CORES; evita el
        # bug de divisibilidad kpt/cores, p.ej. 11 cores con 4 k-points IBZ).
        "convergence": {"density": 1e-4, "eigenstates": 1e-6, "energy": 1e-5},
        "mixer": Mixer(0.05, 8, 50),
        "maxiter": 333,
        # Nombre legacy r2scan.txt: el runner/monitor detectan progreso SCF y stall por este
        # archivo (label_log_paths usa rel_dir/r2scan.txt). Cada config rattled lo reescribe;
        # el mtime fresco evita falsos "no-SCF stall".
        "txt": str(JOB_ROOT / "pbe" / "r2scan.txt"),
    }


def _json_float_list(array):
    if array is None:
        return None
    return np.asarray(array, dtype=float).tolist()


def _single_point(atoms, calc):
    # UN proceso MPI = UN calculo GPAW. Cualquier intento de correr varios GPAW en
    # secuencia dentro del mismo proceso (calc nuevo por config O calc compartido)
    # produce deadlock MPI en GPAW 24.6 + OpenMPI (collectives desfasados, CPU al
    # 100% sin output). job.sh lanza un mpiexec POR config (aislamiento total).
    atoms.calc = calc
    energy = float(atoms.get_potential_energy())
    forces = np.asarray(atoms.get_forces(), dtype=float)
    fmax = float(np.linalg.norm(forces, axis=1).max())
    stress = None
    stress_error = None
    try:
        stress = np.asarray(atoms.get_stress(voigt=True), dtype=float)
    except Exception as exc:
        stress_error = str(exc)
    return energy, forces, fmax, stress, stress_error


def run_config(k: int) -> None:
    """Computa SOLO la config k (proceso MPI fresco). Idempotente via frame_k.json."""
    label = LABELS[0]   # unico label PBE (sin U-scan)
    work = JOB_ROOT / label["relative_dir"]
    work.mkdir(parents=True, exist_ok=True)
    frame_path = work / f"frame_{k}.json"
    if frame_path.exists():
        try:
            if json.loads(frame_path.read_text()).get("status") == "ok":
                return   # ya computada (resume)
        except Exception:
            pass

    if k == 0:
        _write_status({"status": "running", "started_at": _now()})
        if IS_MASTER:
            for old in (work / "label.extxyz", work / "metrics.json"):
                if old.exists():
                    old.unlink()
    world.barrier()

    t0 = time.time()
    atoms = read(str(STRUCTURE))
    if k > 0:
        atoms.rattle(stdev=RATTLE_STDEV, seed=1000 + k)

    try:
        calc = GPAW(**_calc_kwargs(atoms))
        energy, forces, fmax, stress, stress_error = _single_point(atoms, calc)
        # SinglePointCalculator: forma canonica de guardar E+F+stress en extxyz para
        # MLIP (no poner energy/stress en info: colisiona al escribir).
        at_out = atoms.copy()
        spc = {"energy": energy, "forces": forces}
        if stress is not None:
            spc["stress"] = stress
        at_out.calc = SinglePointCalculator(at_out, **spc)
        at_out.info.update({
            "candidate_id": METADATA["candidate_id"],
            "formula": METADATA.get("formula"),
            "config_index": k,
            "rattle_stdev": (0.0 if k == 0 else RATTLE_STDEV),
            "method": "PBE",
            "fidelity": "phase2_force",
        })
        frame = {
            "config_index": k, "status": "ok",
            "energy_eV": energy, "energy_per_atom_eV": energy / len(atoms),
            "forces_max_eVA": fmax, "stress": _json_float_list(stress),
            "stress_available": stress is not None, "stress_error": stress_error,
            "n_atoms": len(atoms), "kpts": _kpts_for_atoms(atoms),
            "elapsed_s": round(time.time() - t0, 1), "finished_at": _now(),
        }
        if IS_MASTER:
            write(str(work / "label.extxyz"), at_out, format="extxyz", append=True)
            frame_path.write_text(json.dumps(frame, indent=2))
    except Exception as exc:
        if IS_MASTER:
            frame_path.write_text(json.dumps({
                "config_index": k, "status": "failed", "error_message": str(exc),
                "elapsed_s": round(time.time() - t0, 1), "finished_at": _now(),
            }, indent=2))
            (work / f"error_config{k}.txt").write_text(traceback.format_exc())
    world.barrier()


def finalize() -> None:
    """Agrega frame_*.json -> metrics.json + status final. Correr SIN mpiexec."""
    label = LABELS[0]
    work = JOB_ROOT / label["relative_dir"]
    frames = []
    for k in range(N_RATTLE):
        p = work / f"frame_{k}.json"
        if p.exists():
            try:
                frames.append(json.loads(p.read_text()))
                continue
            except Exception:
                pass
        frames.append({"config_index": k, "status": "failed",
                       "error_message": "frame_json_missing (proceso murio sin escribir)"})
    n_ok = sum(1 for m in frames if m.get("status") == "ok")
    status = "converged" if n_ok == N_RATTLE else ("partial" if n_ok > 0 else "failed")
    metrics = {
        "status": status,
        "candidate_id": METADATA["candidate_id"],
        "formula": METADATA.get("formula"),
        "method": "PBE",
        "n_frames": n_ok,
        "n_frames_requested": N_RATTLE,
        "rattle_stdev": RATTLE_STDEV,
        "xc": "PBE",
        "frames": frames,
        "finished_at": _now(),
    }
    (work / "metrics.json").write_text(json.dumps(metrics, indent=2))
    _write_status({"status": status, "n_frames": n_ok,
                   "n_frames_requested": N_RATTLE, "finished_at": _now()})
    if status == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-index", type=int, default=None)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        finalize()
    elif args.config_index is not None:
        run_config(args.config_index)
    else:
        raise SystemExit("Usa --config-index K (bajo mpiexec) o --finalize (sin mpiexec).")
