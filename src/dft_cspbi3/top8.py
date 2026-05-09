"""Utilities for the PBE comparison set requested in DFT_CONTEXT_TOP8.md.

The goal of this module is deliberately modest: prepare reproducible PBE
starting structures, write the ML/DFT comparison CSV schema, and collect DFT
outputs that already exist.  It does not invent missing DFT values.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.io import write

from .structure_builder import StructureBuilder


PBE_DEFAULT_STEPS = ("relax", "scf", "bands", "dos", "soc", "effective_masses", "score")


COMPARISON_COLUMNS = [
    "material_id",
    "formula",
    "ml_bandgap",
    "ml_bandgap_mbj",
    "ml_score",
    "ml_reward",
    "goldschmidt_tolerance",
    "ml_valid",
    "ml_formation_energy",
    "ml_electron_effective_mass_m0",
    "ml_hole_effective_mass_m0",
    "ml_dielectric_constant",
    "ml_phonon_min_frequency_cm1",
    "dft_bandgap",
    "dft_bandgap_pbe",
    "dft_gap_type",
    "dft_vbm_kpoint",
    "dft_cbm_kpoint",
    "dft_formation_energy",
    "dft_electron_effective_mass_m0",
    "dft_hole_effective_mass_m0",
    "dft_effective_mass_method",
    "dft_dielectric_constant",
    "dft_exciton_binding_mev",
    "dft_phonon_min_frequency_cm1",
    "dft_has_imaginary_phonon_modes",
    "dft_hessian_min_eigenvalue",
    "dft_solar_score",
    "dft_pce_pct_sq",
    "dft_source",
    "dft_formation_reference_scheme",
    "dft_reference_energies_json",
    "dft_lattice_parameter",
    "dft_volume",
    "dft_total_energy",
    "dft_max_force",
    "relaxed_structure_path",
    "initial_structure_path",
    "structure_status",
    "dft_status",
    "pbe_run_command",
    "notes",
]


@dataclass(frozen=True)
class Top8Candidate:
    """One ML candidate plus enough chemistry to build a PBE starting cell."""

    rank_ml: int
    formula: str
    a_site: str
    b_site: str
    x_site: str
    ml_bandgap: float
    goldschmidt_tolerance: float
    ml_score: float
    initial_a0_ang: float
    ml_bandgap_mbj: float | None = None
    ml_formation_energy: float | None = None
    ml_electron_effective_mass_m0: float | None = None
    ml_hole_effective_mass_m0: float | None = None
    ml_dielectric_constant: float | None = None
    ml_phonon_min_frequency_cm1: float | None = None
    ml_hessian_min_eigenvalue: float | None = None

    @property
    def material_id(self) -> str:
        return self.formula

    @property
    def n_atoms_per_formula(self) -> int:
        if self.a_site == "Cs":
            return 5
        if self.a_site in {"MA", "FA"}:
            return 12
        raise ValueError(f"Unsupported A-site species: {self.a_site}")


TOP8_CANDIDATES = [
    Top8Candidate(1, "MAPbI3", "MA", "Pb", "I", 1.5000, 0.9115, 1.9885, 6.31),
    Top8Candidate(2, "MASnI3", "MA", "Sn", "I", 1.3000, 0.9142, 1.9858, 6.24),
    Top8Candidate(3, "FAPbI3", "FA", "Pb", "I", 1.5000, 0.9866, 1.9134, 6.36),
    Top8Candidate(4, "FASnI3", "FA", "Sn", "I", 1.3000, 0.9895, 1.9105, 6.31),
    Top8Candidate(5, "CsSnI3", "Cs", "Sn", "I", 1.3000, 0.8096, 1.9096, 6.20),
    Top8Candidate(
        6,
        "CsPbI3",
        "Cs",
        "Pb",
        "I",
        1.5000,
        0.8072,
        1.9072,
        6.2965,
        ml_bandgap_mbj=1.598224759,
        ml_formation_energy=-0.997459999,
        ml_electron_effective_mass_m0=0.453535894,
        ml_hole_effective_mass_m0=0.418411929,
        ml_dielectric_constant=28.505573,
        ml_phonon_min_frequency_cm1=-0.041761847,
        ml_hessian_min_eigenvalue=-2.95221,
    ),
    Top8Candidate(7, "FAPbBr3", "FA", "Pb", "Br", 1.8000, 1.0079, 1.8921, 5.99),
    Top8Candidate(8, "FASnBr3", "FA", "Sn", "Br", 1.6000, 1.0111, 1.8889, 5.94),
]


def candidate_by_formula(formula: str) -> Top8Candidate:
    for candidate in TOP8_CANDIDATES:
        if candidate.formula == formula:
            return candidate
    raise KeyError(f"Unknown Top 8 formula: {formula}")


def build_initial_structure(candidate: Top8Candidate) -> Atoms:
    """Build a cubic ABX3 PBE starting structure for a Top 8 candidate."""
    if candidate.a_site == "Cs":
        atoms = StructureBuilder.build_perovskite_cubic(
            candidate.a_site,
            candidate.b_site,
            candidate.x_site,
            candidate.initial_a0_ang,
        )
    elif candidate.a_site == "MA":
        atoms = _build_ma_perovskite(candidate.b_site, candidate.x_site, candidate.initial_a0_ang)
    elif candidate.a_site == "FA":
        atoms = _build_fa_perovskite(candidate.b_site, candidate.x_site, candidate.initial_a0_ang)
    else:
        raise ValueError(f"Unsupported A-site species: {candidate.a_site}")

    atoms.info.update(
        {
            "phase": candidate.material_id,
            "formula": candidate.formula,
            "space_group": "Pm-3m starting lattice; molecular A-site lowers symmetry",
            "space_group_number": 221,
            "functional_level": "PBE",
            "structure_status": "cubic_initial_guess",
            "initial_a0_ang": candidate.initial_a0_ang,
        }
    )
    return atoms


def generate_top8_structures(
    output_dir: str | Path = "structures/top8",
    overwrite: bool = False,
) -> dict[str, Path]:
    """Write JSON and CIF starting structures for every Top 8 material."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for candidate in TOP8_CANDIDATES:
        atoms = build_initial_structure(candidate)
        json_path = output / f"{candidate.material_id}.json"
        cif_path = output / f"{candidate.material_id}.cif"
        if overwrite or not json_path.exists():
            StructureBuilder.save_json(atoms, json_path)
        if overwrite or not cif_path.exists():
            write(str(cif_path), atoms)
        written[candidate.material_id] = json_path
    return written


def write_comparison_csv(
    output_path: str | Path,
    work_dir: str | Path = "calculations/top8_pbe",
    existing_cspbi3_dir: str | Path = "calculations/alpha",
) -> Path:
    """Collect available PBE results and write the Top 8 comparison CSV."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        _candidate_row(candidate, Path(work_dir), Path(existing_cspbi3_dir))
        for candidate in TOP8_CANDIDATES
    ]
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COMPARISON_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return output


def prepare_top8_pbe_workspace(
    work_dir: str | Path = "calculations/top8_pbe",
    structures_dir: str | Path = "structures/top8",
    comparison_csv: str | Path | None = None,
    run_script: str | Path | None = None,
    overwrite_structures: bool = False,
) -> dict[str, Path]:
    """Prepare structures, empty comparison CSV, and a PBE run script."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    structures = generate_top8_structures(structures_dir, overwrite=overwrite_structures)

    csv_path = Path(comparison_csv) if comparison_csv else work / "top8_pbe_comparison.csv"
    write_comparison_csv(csv_path, work_dir=work)

    script_path = Path(run_script) if run_script else work / "run_top8_pbe.sh"
    write_run_script(script_path, work_dir=work)

    return {
        "work_dir": work,
        "structures_dir": Path(structures_dir),
        "comparison_csv": csv_path,
        "run_script": script_path,
        **{f"structure_{key}": value for key, value in structures.items()},
    }


def write_run_script(
    output_path: str | Path,
    work_dir: str | Path = "calculations/top8_pbe",
    config_path: str | Path = "configs/default_params.yaml",
    composition_config: str | Path = "configs/top8_pbe.yaml",
) -> Path:
    """Write a shell script that runs the PBE workflow for every candidate."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    phases = " ".join(candidate.material_id for candidate in TOP8_CANDIDATES)
    default_steps = ",".join(PBE_DEFAULT_STEPS)
    text = f"""#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${{WORKDIR:-{work_dir}}}"
CONFIG="${{CONFIG:-{config_path}}}"
COMPOSITION_CONFIG="${{COMPOSITION_CONFIG:-{composition_config}}}"
STEPS="${{STEPS:-{default_steps}}}"
DRY_RUN="${{DRY_RUN:-0}}"
PYTHON="${{PYTHON:-.venv/bin/python}}"
PHASES=({phases})

if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

for phase in "${{PHASES[@]}}"; do
  echo "== PBE Top 8: $phase =="
  args=(
    main.py run
    --phase "$phase"
    --config "$CONFIG"
    --composition-config "$COMPOSITION_CONFIG"
    --workdir "$WORKDIR"
    --steps "$STEPS"
  )
  if [[ "$DRY_RUN" == "1" ]]; then
    args+=(--dry-run)
  fi
  "$PYTHON" "${{args[@]}}"
done

"$PYTHON" scripts/setup_top8_pbe.py --collect-only --workdir "$WORKDIR"
"""
    output.write_text(text)
    output.chmod(0o755)
    return output


def _build_ma_perovskite(b_site: str, x_site: str, a0: float) -> Atoms:
    center = np.array([a0 / 2.0] * 3)
    axis = _unit(np.array([1.0, 1.0, 1.0]))
    c_n = 1.47
    c_h = 1.09
    n_h = 1.04

    c_pos = center - 0.5 * c_n * axis
    n_pos = center + 0.5 * c_n * axis

    symbols = [b_site, x_site, x_site, x_site, "C", "N"]
    positions = [
        [0.0, 0.0, 0.0],
        [a0 / 2.0, 0.0, 0.0],
        [0.0, a0 / 2.0, 0.0],
        [0.0, 0.0, a0 / 2.0],
        c_pos,
        n_pos,
    ]
    positions.extend(c_pos + c_h * d for d in _trigonal_directions(axis, 109.47))
    positions.extend(n_pos + n_h * d for d in _trigonal_directions(-axis, 109.47))
    symbols.extend(["H"] * 6)

    atoms = Atoms(symbols=symbols, positions=np.array(positions), cell=[a0, a0, a0], pbc=True)
    atoms.wrap()
    return atoms


def _build_fa_perovskite(b_site: str, x_site: str, a0: float) -> Atoms:
    center = np.array([a0 / 2.0] * 3)
    ex = np.array([1.0, 0.0, 0.0])
    ey = np.array([0.0, 1.0, 0.0])
    ez = np.array([0.0, 0.0, 1.0])

    c_n = 1.28
    c_h = 1.10
    n_h = 1.02
    c_pos = center
    n1_pos = center - c_n * ex
    n2_pos = center + c_n * ex

    symbols = [b_site, x_site, x_site, x_site, "C", "N", "N", "H"]
    positions = [
        [0.0, 0.0, 0.0],
        [a0 / 2.0, 0.0, 0.0],
        [0.0, a0 / 2.0, 0.0],
        [0.0, 0.0, a0 / 2.0],
        c_pos,
        n1_pos,
        n2_pos,
        c_pos + c_h * ez,
    ]
    positions.extend(
        [
            n1_pos + n_h * (-0.5 * ex + np.sqrt(3.0) / 2.0 * ey),
            n1_pos + n_h * (-0.5 * ex - np.sqrt(3.0) / 2.0 * ey),
            n2_pos + n_h * (0.5 * ex + np.sqrt(3.0) / 2.0 * ey),
            n2_pos + n_h * (0.5 * ex - np.sqrt(3.0) / 2.0 * ey),
        ]
    )
    symbols.extend(["H"] * 4)

    atoms = Atoms(symbols=symbols, positions=np.array(positions), cell=[a0, a0, a0], pbc=True)
    atoms.wrap()
    return atoms


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        raise ValueError("Cannot normalize a zero vector")
    return vector / norm


def _orthonormal_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    axis = _unit(axis)
    ref = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(axis, ref))) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])
    e1 = _unit(np.cross(axis, ref))
    e2 = _unit(np.cross(axis, e1))
    return e1, e2


def _trigonal_directions(axis_to_neighbor: np.ndarray, angle_deg: float) -> list[np.ndarray]:
    axis = _unit(axis_to_neighbor)
    e1, e2 = _orthonormal_basis(axis)
    theta = np.radians(angle_deg)
    directions = []
    for phi in (0.0, 2.0 * np.pi / 3.0, 4.0 * np.pi / 3.0):
        direction = (
            np.cos(theta) * axis
            + np.sin(theta) * (np.cos(phi) * e1 + np.sin(phi) * e2)
        )
        directions.append(_unit(direction))
    return directions


def _candidate_row(
    candidate: Top8Candidate,
    work_dir: Path,
    existing_cspbi3_dir: Path,
) -> dict[str, Any]:
    row = {column: "" for column in COMPARISON_COLUMNS}
    row.update(
        {
            "material_id": candidate.material_id,
            "formula": candidate.formula,
            "ml_bandgap": candidate.ml_bandgap,
            "ml_bandgap_mbj": _blank_none(candidate.ml_bandgap_mbj),
            "ml_score": candidate.ml_score,
            "goldschmidt_tolerance": candidate.goldschmidt_tolerance,
            "ml_valid": 1,
            "ml_formation_energy": _blank_none(candidate.ml_formation_energy),
            "ml_electron_effective_mass_m0": _blank_none(
                candidate.ml_electron_effective_mass_m0
            ),
            "ml_hole_effective_mass_m0": _blank_none(candidate.ml_hole_effective_mass_m0),
            "ml_dielectric_constant": _blank_none(candidate.ml_dielectric_constant),
            "ml_phonon_min_frequency_cm1": _blank_none(candidate.ml_phonon_min_frequency_cm1),
            "initial_structure_path": str(Path("structures/top8") / f"{candidate.material_id}.json"),
            "structure_status": "cubic_initial_guess",
            "dft_status": "pending",
            "pbe_run_command": _run_command(candidate.material_id),
        }
    )

    phase_dir = work_dir / candidate.material_id
    source = f"PBE:{phase_dir}"
    if candidate.formula == "CsPbI3" and not _has_pbe_outputs(phase_dir) and existing_cspbi3_dir.exists():
        phase_dir = existing_cspbi3_dir
        source = f"PBE existing alpha:{existing_cspbi3_dir}"

    _merge_available_outputs(row, candidate, phase_dir, source)
    return row


def _merge_available_outputs(
    row: dict[str, Any],
    candidate: Top8Candidate,
    phase_dir: Path,
    source: str,
) -> None:
    electronic = _read_json(phase_dir / "10_effective_masses" / "electronic_analysis.json")
    has_real_electronic_outputs = bool(electronic)
    if electronic:
        gap = electronic.get("gap_eV")
        row["dft_bandgap_pbe"] = _blank_none(gap)
        row["dft_bandgap"] = _blank_none(gap)
        row["dft_gap_type"] = _blank_none(electronic.get("gap_type"))
        row["dft_vbm_kpoint"] = _json_list(electronic.get("vbm_kpt_frac"))
        row["dft_cbm_kpoint"] = _json_list(electronic.get("cbm_kpt_frac"))
        m_e = electronic.get("m_e_soc_m0")
        m_h = electronic.get("m_h_soc_m0")
        method = "PBE+SOC fine-k" if m_e is not None and m_h is not None else "PBE fine-k"
        row["dft_electron_effective_mass_m0"] = _blank_none(m_e or electronic.get("m_e_m0"))
        row["dft_hole_effective_mass_m0"] = _blank_none(m_h or electronic.get("m_h_m0"))
        row["dft_effective_mass_method"] = method
        row["dft_status"] = "pbe_electronic_done"
        row["dft_source"] = source

    formation = _read_json(phase_dir / "09_formation_energy" / "formation_energy.json")
    if formation:
        delta_hf_fu = formation.get("delta_Hf_eV")
        if delta_hf_fu is not None:
            row["dft_formation_energy"] = float(delta_hf_fu) / candidate.n_atoms_per_formula
        row["dft_formation_reference_scheme"] = "binary_AX_plus_BX2"
        row["dft_reference_energies_json"] = str(
            phase_dir / "09_formation_energy" / "formation_energy.json"
        )

    score = _read_json(phase_dir / "12_score" / "solar_score.json")
    if score and not has_real_electronic_outputs:
        row["notes"] = "ignored_score_without_pbe_electronic_outputs"
        score = {}
    if score:
        inputs = score.get("inputs", {})
        score_gap = inputs.get("bandgap_eV")
        pbe_gap = row.get("dft_bandgap_pbe")
        score_uses_pbe_gap = _same_float(score_gap, pbe_gap)
        row["dft_dielectric_constant"] = _blank_none(inputs.get("eps_r"))
        row["dft_exciton_binding_mev"] = _blank_none(inputs.get("exciton_binding_meV"))
        if score_uses_pbe_gap:
            row["dft_solar_score"] = _blank_none(score.get("total_score"))
            pv_metrics = score.get("pv_metrics") or {}
            row["dft_pce_pct_sq"] = _blank_none(pv_metrics.get("pce_pct"))
        elif score_gap is not None and pbe_gap not in ("", None):
            _append_note(row, "score_pce_skipped_non_pbe_gap")

    sq = _read_json(phase_dir / "13_sq_limit" / "sq_limit.json")
    sq_uses_override = any(str(flag).startswith("ONSET_OVERRIDE") for flag in sq.get("flags", []))
    if sq and not row["dft_pce_pct_sq"] and not sq_uses_override:
        row["dft_pce_pct_sq"] = _blank_none(sq.get("pce_pct"))
    elif sq_uses_override:
        _append_note(row, "sq_pce_skipped_non_pbe_onset")

    phonons = phase_dir / "07_vibrational" / "phonons" / "phonon_frequencies.npy"
    if phonons.exists():
        freqs = np.load(str(phonons))
        min_freq = float(np.min(freqs))
        row["dft_phonon_min_frequency_cm1"] = min_freq
        row["dft_has_imaginary_phonon_modes"] = bool(min_freq < -10.0)

    hessian = phase_dir / "07_vibrational" / "hessian" / "hessian.npy"
    if hessian.exists():
        values = np.load(str(hessian))
        if values.ndim == 2 and values.shape[0] == values.shape[1]:
            row["dft_hessian_min_eigenvalue"] = float(np.min(np.linalg.eigvalsh(values)))
        else:
            row["dft_hessian_min_eigenvalue"] = float(np.min(values))

    relaxed = phase_dir / "01_relax" / "relaxed.cif"
    if relaxed.exists():
        row["relaxed_structure_path"] = str(relaxed)
        try:
            atoms = StructureBuilder.from_cif(relaxed)
            lengths = atoms.cell.lengths()
            row["dft_lattice_parameter"] = float(np.mean(lengths))
            row["dft_volume"] = float(atoms.get_volume())
        except Exception as exc:
            row["notes"] = f"relaxed_cif_parse_failed:{exc}"

    if row["dft_status"] == "pending" and phase_dir.exists():
        row["dft_status"] = "workspace_prepared"


def _has_pbe_outputs(phase_dir: Path) -> bool:
    return (phase_dir / "10_effective_masses" / "electronic_analysis.json").exists()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _blank_none(value: Any) -> Any:
    return "" if value is None else value


def _same_float(left: Any, right: Any, tol: float = 1e-3) -> bool:
    if left in ("", None) or right in ("", None):
        return False
    try:
        return abs(float(left) - float(right)) <= tol
    except (TypeError, ValueError):
        return False


def _append_note(row: dict[str, Any], note: str) -> None:
    existing = row.get("notes")
    row["notes"] = f"{existing};{note}" if existing else note


def _json_list(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value)


def _run_command(material_id: str) -> str:
    steps = ",".join(PBE_DEFAULT_STEPS)
    return (
        ".venv/bin/python main.py run "
        f"--phase {material_id} "
        "--config configs/default_params.yaml "
        "--composition-config configs/top8_pbe.yaml "
        "--workdir calculations/top8_pbe "
        f"--steps {steps}"
    )
