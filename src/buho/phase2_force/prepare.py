"""Preparacion de jobs Fase 2A para DFT E+F(+stress)."""

from __future__ import annotations

import argparse
import json
import shutil
import string
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from buho.phase2_force import ROOT
from buho.phase2_force.common import RUNS_DIR, display_path, label_plan_for_formula, read_csv, write_json
from buho.phase2_force.selection import load_candidate_index


INPUT_TEMPLATE = string.Template(r'''#!/usr/bin/env python3
"""Job Fase 2A: r2SCAN/r2SCAN+U + FIRE(2) + etiqueta MACE extxyz."""
from __future__ import annotations

import json
import math
import time
import traceback
from pathlib import Path

import numpy as np
from ase.io import read, write
from ase.optimize import FIRE
from gpaw import GPAW, PW
from gpaw.eigensolvers import Davidson
from gpaw.mixer import Mixer


JOB_ROOT = Path(__file__).resolve().parent
STRUCTURE = JOB_ROOT / "structure.cif"
METADATA = json.loads((JOB_ROOT / "metadata.json").read_text())
LABELS = json.loads(r"""$labels_json""")
N_CORES = $n_cores


def _now():
    import datetime
    return datetime.datetime.utcnow().isoformat() + "Z"


def _read_status():
    p = JOB_ROOT / "status.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _write_status(update):
    status = _read_status()
    status.update(update)
    (JOB_ROOT / "status.json").write_text(json.dumps(status, indent=2))


def _kpts_for_atoms(atoms):
    # Fase 2A usa r2SCAN con malla 2x2x2 para superceldas grandes.
    # El reparto MPI debe respetar N_CORES: por ejemplo 8 -> kpt=8/domain=1,
    # pero 11 -> kpt=1/domain=11.
    return [2, 2, 2] if len(atoms) > 10 else [6, 6, 6]


def _parallel_layout(kpts):
    nk = int(kpts[0] * kpts[1] * kpts[2])
    for k in range(min(N_CORES, nk), 0, -1):
        if nk % k == 0 and N_CORES % k == 0:
            return {"kpt": k, "domain": max(1, N_CORES // k), "band": 1}
    return {"kpt": 1, "domain": max(1, N_CORES), "band": 1}


def _calc_kwargs(atoms, label):
    kpts = _kpts_for_atoms(atoms)
    has_sn = bool(label.get("u_ev") is not None)
    mixer = Mixer(0.002, 15, 100) if has_sn else Mixer(0.05, 8, 50)
    setups = {"Sn": f":s,{label['u_ev']}"} if has_sn else {}
    return {
        "mode": PW(450),
        "xc": "MGGA_X_R2SCAN+MGGA_C_R2SCAN",
        "kpts": {"size": kpts, "gamma": True},
        "occupations": {"name": "fermi-dirac", "width": 0.2 if has_sn else 0.05},
        "eigensolver": Davidson(niter=3),
        "parallel": _parallel_layout(kpts),
        "convergence": {"density": 1e-4, "eigenstates": 1e-6, "energy": 1e-5},
        "mixer": mixer,
        "maxiter": 2000,
        "setups": setups,
        "txt": str(JOB_ROOT / label["relative_dir"] / "r2scan.txt"),
    }


def _json_float_list(array):
    if array is None:
        return None
    return np.asarray(array, dtype=float).tolist()


def _run_label(label):
    work = JOB_ROOT / label["relative_dir"]
    work.mkdir(parents=True, exist_ok=True)
    metrics_path = work / "metrics.json"
    if metrics_path.exists():
        try:
            old = json.loads(metrics_path.read_text())
            if old.get("status") == "converged":
                return old
        except Exception:
            pass

    t0 = time.time()
    atoms = read(str(STRUCTURE))
    kwargs = _calc_kwargs(atoms, label)
    calc = GPAW(**kwargs)
    atoms.calc = calc

    try:
        opt = FIRE(atoms, trajectory=str(work / "relax.traj"), logfile=str(work / "relax.log"))
        opt.run(fmax=0.0, steps=2)

        energy = float(atoms.get_potential_energy())
        forces = np.asarray(atoms.get_forces(), dtype=float)
        fmax = float(np.linalg.norm(forces, axis=1).max())
        stress = None
        stress_error = None
        try:
            stress = np.asarray(atoms.get_stress(voigt=True), dtype=float)
        except Exception as exc:
            stress_error = str(exc)

        atoms.arrays["forces"] = forces
        atoms.info.update({
            "energy": energy,
            "candidate_id": METADATA["candidate_id"],
            "formula": METADATA.get("formula"),
            "phase": "cubic_pm3m_seed_fire2",
            "method": label["method"],
            "u_ev": label.get("u_ev"),
            "fidelity": "phase2_force",
            "fire_steps_requested": 2,
            "forces_max_eVA": fmax,
            "stress_available": stress is not None,
        })
        if stress is not None:
            atoms.info["stress"] = stress.tolist()

        write(str(work / "relaxed.cif"), atoms)
        write(str(work / "label.extxyz"), atoms, format="extxyz")
        try:
            calc.write(str(work / "label.gpw"))
        except Exception as exc:
            (work / "gpw_write_error.txt").write_text(str(exc))

        metrics = {
            "status": "converged",
            "candidate_id": METADATA["candidate_id"],
            "formula": METADATA.get("formula"),
            "method": label["method"],
            "u_ev": label.get("u_ev"),
            "label": label["label"],
            "relative_dir": label["relative_dir"],
            "energy_eV": energy,
            "energy_per_atom_eV": energy / len(atoms),
            "n_atoms": len(atoms),
            "forces_max_eVA": fmax,
            "forces_shape": list(forces.shape),
            "stress": _json_float_list(stress),
            "stress_available": stress is not None,
            "stress_error": stress_error,
            "cell_A": _json_float_list(atoms.cell.array),
            "volume_A3": float(atoms.get_volume()),
            "kpts": kwargs["kpts"]["size"],
            "parallel": kwargs["parallel"],
            "xc_method": "r2SCAN+U" if label.get("u_ev") is not None else "r2SCAN",
            "fire_steps_requested": 2,
            "elapsed_s": round(time.time() - t0, 1),
            "finished_at": _now(),
        }
    except Exception as exc:
        metrics = {
            "status": "failed",
            "candidate_id": METADATA["candidate_id"],
            "formula": METADATA.get("formula"),
            "method": label["method"],
            "u_ev": label.get("u_ev"),
            "label": label["label"],
            "relative_dir": label["relative_dir"],
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
            "elapsed_s": round(time.time() - t0, 1),
            "finished_at": _now(),
        }
        (work / "error.txt").write_text(metrics["traceback"])

    metrics_path.write_text(json.dumps(metrics, indent=2))
    return metrics


def main():
    _write_status({"status": "running", "started_at": _now()})
    results = []
    for label in LABELS:
        results.append(_run_label(label))

    n_ok = sum(1 for item in results if item.get("status") == "converged")
    n_fail = sum(1 for item in results if item.get("status") == "failed")
    if n_ok == len(results):
        status = "converged"
    elif n_ok > 0:
        status = "partial"
    else:
        status = "failed"
    _write_status({
        "status": status,
        "n_labels_converged": n_ok,
        "n_labels_failed": n_fail,
        "labels": results,
        "finished_at": _now(),
    })
    if status == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
''')


def _batch_csv(batch_id: int) -> Path:
    return ROOT / "data" / "mace_finetune" / "batches" / f"batch_{batch_id:03d}.csv"


def _job_dir(batch_id: int, candidate_id: str, runs_dir: Path = RUNS_DIR) -> Path:
    return runs_dir / f"batch_{batch_id:03d}" / candidate_id


def _load_candidate(candidate_id: str, index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    data = dict(index[candidate_id])
    data.pop("_json_source", None)
    return data


def _build_phase1_seed_structure(candidate: dict[str, Any], cfg: dict[str, Any], out_dir: Path) -> None:
    """Construye la misma semilla cubica idealizada de Fase 1 sin depender de pandas."""
    import numpy as np
    from ase import Atoms
    from ase.build import make_supercell
    from ase.io.trajectory import Trajectory

    structure_cfg = cfg.get("structure", {})
    organic_placeholder = structure_cfg.get("organic_A_placeholder", "Cs")
    supercell_mixed = list(structure_cfg.get("supercell_mixed", [2, 2, 2]))
    supercell_pure = list(structure_cfg.get("supercell_pure", [1, 1, 1]))
    formats = list(structure_cfg.get("export_formats", ["cif", "poscar", "traj"]))

    a0 = float(candidate.get("a0_est_A") or candidate.get("lattice_constant_A") or 6.0)
    a_species = list(candidate.get("A_site_species", []))
    b_species = list(candidate.get("B_site_species", []))
    x_species = list(candidate.get("X_site_species", []))
    fractions = candidate.get("fractions", {})
    is_organic = bool(candidate.get("is_organic_A"))
    is_mixed = len(a_species) > 1 or len(b_species) > 1 or len(x_species) > 1

    a_struct = organic_placeholder if is_organic else a_species[0]
    b_struct = b_species[0]
    x_struct = x_species[0]
    scaled = [
        (0.0, 0.0, 0.0),
        (0.5, 0.5, 0.5),
        (0.5, 0.5, 0.0),
        (0.5, 0.0, 0.5),
        (0.0, 0.5, 0.5),
    ]
    atoms = Atoms(
        symbols=[a_struct, b_struct, x_struct, x_struct, x_struct],
        scaled_positions=scaled,
        cell=[a0, a0, a0],
        pbc=True,
    )
    sc = supercell_mixed if is_mixed else supercell_pure
    if sc != [1, 1, 1]:
        atoms = make_supercell(atoms, np.diag(sc))

    if is_mixed:
        rng = np.random.RandomState(int(cfg.get("random_seed", 42)))
        symbols = list(atoms.get_chemical_symbols())

        def _ase_symbol(species: str) -> str:
            return organic_placeholder if species in {"MA", "FA"} else species

        def _assign(site_symbols: list[str], species_list: list[str], fracs: dict[str, float]) -> None:
            if len(species_list) <= 1:
                return
            idxs = [idx for idx, sym in enumerate(symbols) if sym in site_symbols]
            total = len(idxs)
            shuffled = idxs.copy()
            rng.shuffle(shuffled)
            remaining = total
            offset = 0
            for species in species_list[:-1]:
                n = min(remaining, int(round(float(fracs.get(species, 0.0)) * total)))
                for idx in shuffled[offset:offset + n]:
                    symbols[idx] = _ase_symbol(species)
                offset += n
                remaining -= n
            for idx in shuffled[offset:]:
                symbols[idx] = _ase_symbol(species_list[-1])

        _assign([a_struct, organic_placeholder], a_species, fractions.get("A", {}))
        _assign(b_species, b_species, fractions.get("B", {}))
        _assign(x_species, x_species, fractions.get("X", {}))
        atoms.set_chemical_symbols(symbols)

    out_dir.mkdir(parents=True, exist_ok=True)
    if "cif" in formats:
        atoms.write(str(out_dir / "structure.cif"))
    if "poscar" in formats:
        atoms.write(str(out_dir / "POSCAR"), format="vasp")
    if "traj" in formats:
        with Trajectory(str(out_dir / "structure.traj"), "w") as traj:
            traj.write(atoms)

    metadata = {
        "candidate_id": candidate["candidate_id"],
        "formula": candidate["formula"],
        "reduced_formula": candidate.get("reduced_formula"),
        "generation_mode": candidate.get("generation_mode"),
        "A_site_species": a_species,
        "B_site_species": b_species,
        "X_site_species": x_species,
        "fractions": fractions,
        "molecular_A_placeholder": is_organic,
        "lattice_constant_A": round(a0, 4),
        "supercell": sc,
        "n_atoms": len(atoms),
        "tolerance_t": candidate.get("tolerance_t"),
        "oct_factor": candidate.get("oct_factor"),
        "random_seed": cfg.get("random_seed", 42),
        "build_date": datetime.utcnow().isoformat() + "Z",
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_input(job_dir: Path, labels: list[dict[str, Any]], n_cores: int) -> None:
    script = INPUT_TEMPLATE.substitute(
        labels_json=json.dumps(labels, indent=2),
        n_cores=int(n_cores),
    )
    path = job_dir / "input.py"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def _write_job_metadata(job_dir: Path, row: dict[str, str], labels: list[dict[str, Any]]) -> None:
    metadata_path = job_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    metadata.update({
        "phase": "2A",
        "fidelity": "phase2_force",
        "phase2_batch_id": int(row["phase2_batch_id"]),
        "selection_rank": int(row["selection_rank"]),
        "slot_in_batch": int(row["slot_in_batch"]),
        "dft_labels_expected": labels,
        "fire_steps_requested": 2,
        "dft_policy": "Sn -> r2SCAN+U sweep; non-Sn -> r2SCAN",
        "selection_row": row,
        "prepared_at": datetime.utcnow().isoformat() + "Z",
    })
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_status(job_dir: Path, row: dict[str, str], labels: list[dict[str, Any]]) -> None:
    status = {
        "status": "pending",
        "candidate_id": row["candidate_id"],
        "formula": row["formula"],
        "phase2_batch_id": int(row["phase2_batch_id"]),
        "selection_rank": int(row["selection_rank"]),
        "n_labels_expected": len(labels),
        "labels_expected": labels,
        "created": datetime.utcnow().isoformat() + "Z",
    }
    (job_dir / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def prepare_batch(batch_id: int, config_path: Path = ROOT / "config" / "generator.yaml",
                  runs_dir: Path = RUNS_DIR, n_cores: int = 8, limit: int | None = None,
                  dry_run: bool = False) -> dict[str, Any]:
    batch_csv = _batch_csv(batch_id)
    if not batch_csv.exists():
        raise FileNotFoundError(f"No existe {batch_csv}; corre primero phase2_force_select.")

    rows = read_csv(batch_csv)
    if limit is not None:
        rows = rows[:limit]
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    candidate_index = load_candidate_index(ROOT)
    prepared: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []
    planned: list[dict[str, Any]] = []

    for row in rows:
        cid = row["candidate_id"]
        labels = label_plan_for_formula(row["formula"])
        job_dir = _job_dir(batch_id, cid, runs_dir)
        planned.append({
            "candidate_id": cid,
            "formula": row["formula"],
            "job_dir": display_path(job_dir),
            "labels": labels,
        })
        if dry_run:
            continue
        if cid not in candidate_index:
            missing.append(cid)
            continue

        st_path = job_dir / "status.json"
        if st_path.exists():
            try:
                st = json.loads(st_path.read_text(encoding="utf-8"))
                if st.get("status") in {"running", "converged", "partial"}:
                    skipped.append(cid)
                    continue
            except Exception:
                pass

        candidate = _load_candidate(cid, candidate_index)
        _build_phase1_seed_structure(candidate, cfg, job_dir)
        for label in labels:
            (job_dir / label["relative_dir"]).mkdir(parents=True, exist_ok=True)
        _write_input(job_dir, labels, n_cores=n_cores)
        _write_job_metadata(job_dir, row, labels)
        _write_status(job_dir, row, labels)
        if config_path.exists():
            shutil.copy2(config_path, job_dir / "generator_config.yaml")
        prepared.append(cid)

    manifest = {
        "batch_id": batch_id,
        "batch_csv": str(batch_csv.relative_to(ROOT)),
        "runs_dir": display_path(runs_dir / f"batch_{batch_id:03d}"),
        "n_candidates": len(rows),
        "n_planned": len(planned),
        "n_prepared": len(prepared),
        "n_skipped": len(skipped),
        "n_missing_candidate_json": len(missing),
        "dry_run": dry_run,
        "planned_examples": planned[:10],
        "prepared_at": datetime.utcnow().isoformat() + "Z",
    }
    if not dry_run:
        write_json(runs_dir / f"batch_{batch_id:03d}" / "phase2_force_batch_manifest.json", manifest)
    return manifest


def prepare_all(config_path: Path = ROOT / "config" / "generator.yaml", runs_dir: Path = RUNS_DIR,
                n_cores: int = 8, dry_run: bool = False) -> dict[str, Any]:
    batch_files = sorted((ROOT / "data" / "mace_finetune" / "batches").glob("batch_*.csv"))
    manifests = []
    for path in batch_files:
        batch_id = int(path.stem.split("_")[1])
        manifests.append(prepare_batch(batch_id, config_path, runs_dir, n_cores, dry_run=dry_run))
    summary = {
        "n_batches": len(manifests),
        "n_candidates": sum(m["n_candidates"] for m in manifests),
        "n_prepared": sum(m["n_prepared"] for m in manifests),
        "dry_run": dry_run,
        "batches": manifests,
    }
    if not dry_run:
        write_json(runs_dir / "phase2_force_manifest.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara jobs DFT Fase 2A.")
    parser.add_argument("--batch-id", type=int, default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--config", default=str(ROOT / "config" / "generator.yaml"))
    parser.add_argument("--runs-dir", default=str(RUNS_DIR))
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.all and args.batch_id is None:
        raise SystemExit("Usa --batch-id N o --all")
    if args.all:
        result = prepare_all(Path(args.config), Path(args.runs_dir), args.cores, dry_run=args.dry_run)
    else:
        result = prepare_batch(args.batch_id, Path(args.config), Path(args.runs_dir),
                               args.cores, args.limit, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
