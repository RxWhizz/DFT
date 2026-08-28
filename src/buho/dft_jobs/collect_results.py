"""Recolecta resultados de relajaciones DFT básicas.

Lee cada runs/relax_basic/{candidate_id}/ e intenta extraer:
  - Convergencia (de status.json o gpaw.txt)
  - Energía final y energía por átomo
  - Volumen y parámetros de red finales
  - Fuerza máxima final
  - Bandgap preliminar (si .gpw disponible)
  - Tiempo de cálculo

Todos los resultados se etiquetan con fidelity="relax_basic" — NO son
valores de alta fidelidad ni representan propiedades de producción.

Usa postprocessing.py del proyecto cuando el .gpw está disponible.
Cae a parseo de texto para resultados parciales.

Uso:
    collector = ResultCollector(project_root=ROOT)
    df = collector.collect_all(Path("runs/relax_basic"))
    collector.save(df, Path("data/processed"))
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd


class ResultCollector:
    """Recoge resultados de las relajaciones DFT del cribado (PBE).

    Parámetros
    ----------
    project_root : raíz del proyecto para importar módulos de postprocesado
    """

    FIDELITY = "relax_basic"

    def __init__(self, project_root: Optional[Path] = None):
        import sys
        self._root = Path(project_root) if project_root else Path.cwd()
        if str(self._root / "src") not in sys.path:
            sys.path.insert(0, str(self._root / "src"))

    def collect_all(self, relax_dir: Path) -> pd.DataFrame:
        """Recolecta resultados de todos los subdirectorios en relax_dir."""
        relax_dir = Path(relax_dir)
        if not relax_dir.exists():
            return pd.DataFrame()

        rows = []
        job_dirs = [d for d in relax_dir.iterdir() if d.is_dir()]
        job_dirs.sort()

        for job_dir in job_dirs:
            row = self._collect_one(job_dir)
            rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["fidelity"] = self.FIDELITY
        df = self._flag_outliers(df)
        return df

    # ── Guard de calidad de etiquetas ────────────────────────────────────────────
    @staticmethod
    def _flag_outliers(df: pd.DataFrame, z_thresh: float = 5.0) -> pd.DataFrame:
        """Marca etiquetas no fiables para el entrenamiento del generador.

        El cribado por single-point sobre geometrías idealizadas (cúbica,
        lattice_est) puede producir etiquetas patológicas cuando una supercelda
        random tiene choques atómicos. Esta función NO descarta filas: añade
        columnas booleanas para que el entrenamiento filtre por `is_outlier`.

        Criterios de outlier:
          - no convergió el SCF (converged != True), o
          - energy_per_atom_eV no finita, o
          - |z robusto (MAD)| de energy_per_atom_eV > z_thresh dentro de su
            generation_mode (separa puros/mezclas, cuyas energías difieren).
        """
        import numpy as np

        df = df.copy()
        epa = pd.to_numeric(df.get("energy_per_atom_eV"), errors="coerce")
        df["energy_per_atom_eV"] = epa

        # z-score robusto por grupo (generation_mode); fallback global si falta
        df["robust_z_epa"] = np.nan
        grp_key = "generation_mode" if "generation_mode" in df.columns else None
        groups = df.groupby(grp_key) if grp_key else [(None, df)]
        for _, idx in (df.groupby(grp_key).groups.items() if grp_key
                       else [(None, df.index)]):
            sub = epa.loc[idx].dropna()
            if len(sub) < 4:
                continue
            med = sub.median()
            mad = (sub - med).abs().median()
            if mad == 0 or np.isnan(mad):
                continue
            # 1.4826 escala MAD a sigma gaussiano
            z = (epa.loc[idx] - med) / (1.4826 * mad)
            df.loc[idx, "robust_z_epa"] = z

        not_conv = df.get("converged") != True  # noqa: E712
        non_finite = ~np.isfinite(epa.fillna(np.nan).to_numpy(dtype=float))
        energy_outlier = df["robust_z_epa"].abs() > z_thresh

        df["is_outlier"] = (not_conv | non_finite | energy_outlier.fillna(False)).astype(bool)
        df["trusted_label"] = ~df["is_outlier"]

        n_out = int(df["is_outlier"].sum())
        n_energy = int(energy_outlier.fillna(False).sum())
        print(f"Guard: {n_out}/{len(df)} outliers marcados "
              f"(no_conv={int(not_conv.sum())}, energy_z>{z_thresh}={n_energy})")
        return df

    def save(self, df: pd.DataFrame, out_dir: Path) -> None:
        """Guarda resultados en CSV y JSONL."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        csv_path = out_dir / "relax_basic_results.csv"
        df.to_csv(csv_path, index=False)

        jsonl_path = out_dir / "relax_basic_results.jsonl"
        with open(jsonl_path, "w") as f:
            for rec in df.to_dict(orient="records"):
                f.write(json.dumps(rec) + "\n")

        print(f"Guardado: {csv_path}  ({len(df)} registros)")

    # ── Per-job collection ───────────────────────────────────────────────────────

    def _collect_one(self, job_dir: Path) -> dict:
        """Extrae resultados de un directorio de job."""
        meta = self._load_metadata(job_dir)
        status = self._load_status(job_dir)

        row: dict = {
            "candidate_id": meta.get("candidate_id", job_dir.name),
            "formula": meta.get("formula", "unknown"),
            "generation_mode": meta.get("generation_mode", "unknown"),
            "is_organic_A": meta.get("molecular_A_placeholder", False),
            "n_atoms": meta.get("n_atoms", None),
            "path_to_outputs": str(job_dir),
            "converged": None,
            "final_energy_eV": None,
            "energy_per_atom_eV": None,
            "final_volume_A3": None,
            "lattice_a_A": None,
            "forces_max_eVA": None,
            "bandgap_preliminary_eV": None,
            "calc_time_s": None,
            "error_message": None,
        }

        if status.get("status") == "pending":
            row["converged"] = False
            row["error_message"] = "not_run"
            return row

        # ── Preferir .gpw para extracción precisa ────────────────────────────
        gpw = job_dir / "relaxed.gpw"
        if gpw.exists():
            self._extract_from_gpw(gpw, row)
        else:
            # Fallback: parsear archivos de texto
            self._extract_from_text(job_dir, row, status)

        # Tiempo de cálculo desde status.json
        if "elapsed_s" in status:
            row["calc_time_s"] = status["elapsed_s"]

        # Convergencia desde status.json (más fiable)
        if status.get("status") == "converged":
            row["converged"] = True
        elif status.get("status") == "failed":
            row["converged"] = False

        return row

    def _extract_from_gpw(self, gpw: Path, row: dict) -> None:
        try:
            from dft_cspbi3.postprocessing import get_total_energy, get_bandgap, extract_summary
            summary = extract_summary(str(gpw), soc=False)
            row["converged"] = True
            row["final_energy_eV"] = summary.get("total_energy_eV")
            n = summary.get("n_atoms") or row.get("n_atoms")
            if row["final_energy_eV"] is not None and n:
                row["energy_per_atom_eV"] = row["final_energy_eV"] / n
                row["n_atoms"] = n
            row["final_volume_A3"] = summary.get("volume_A3")
            row["bandgap_preliminary_eV"] = summary.get("bandgap_eV")
        except Exception as e:
            row["error_message"] = f"gpw_parse_error: {e}"
            # Intenta energía directa
            try:
                from dft_cspbi3.postprocessing import get_total_energy
                row["final_energy_eV"] = get_total_energy(str(gpw))
                row["converged"] = True
            except Exception:
                pass

    def _extract_from_text(self, job_dir: Path, row: dict, status: dict) -> None:
        # Energía desde status.json (guardada por input.py)
        if "final_energy_eV" in status:
            row["final_energy_eV"] = status["final_energy_eV"]
            n = row.get("n_atoms")
            if n and row["final_energy_eV"] is not None:
                row["energy_per_atom_eV"] = row["final_energy_eV"] / n

        # Convergencia desde r2scan.txt o gpaw.txt
        for txt_name in ("r2scan.txt", "gpaw.txt", "relax.log"):
            txt = job_dir / txt_name
            if txt.exists():
                converged, e = self._parse_gpaw_txt(txt)
                if converged is not None:
                    row["converged"] = converged
                if e is not None and row["final_energy_eV"] is None:
                    row["final_energy_eV"] = e
                break

        # Volumen desde relaxed.cif
        relaxed_cif = job_dir / "relaxed.cif"
        if relaxed_cif.exists():
            try:
                from ase.io import read as ase_read
                atoms = ase_read(str(relaxed_cif))
                row["final_volume_A3"] = round(float(atoms.get_volume()), 4)
                cell = atoms.get_cell()
                row["lattice_a_A"] = round(float(cell.lengths()[0]), 4)
            except Exception:
                pass

        # Fuerzas máximas desde relax.log
        log = job_dir / "relax.log"
        if log.exists():
            row["forces_max_eVA"] = self._parse_max_force(log)

        # Error desde error.txt
        err = job_dir / "error.txt"
        if err.exists():
            row["error_message"] = err.read_text().strip()[:200]

    @staticmethod
    def _parse_gpaw_txt(txt: Path) -> tuple[Optional[bool], Optional[float]]:
        converged = None
        energy = None
        try:
            content = txt.read_text(errors="replace")
            if "SCF Converged" in content or "Converged" in content:
                converged = True
            elif "Did not converge" in content:
                converged = False
            # Buscar última energía
            for m in re.finditer(r"energy:\s*([-\d.]+)", content):
                energy = float(m.group(1))
        except Exception:
            pass
        return converged, energy

    @staticmethod
    def _parse_max_force(log: Path) -> Optional[float]:
        try:
            lines = log.read_text(errors="replace").splitlines()
            # FIRE log: "FIRE: ..." or "Step ...  Fmax ..."
            forces = []
            for line in lines:
                m = re.search(r"Fmax[=\s]+([\d.]+)", line)
                if m:
                    forces.append(float(m.group(1)))
            if forces:
                return round(forces[-1], 6)
        except Exception:
            pass
        return None

    @staticmethod
    def _load_metadata(job_dir: Path) -> dict:
        meta_file = job_dir / "metadata.json"
        if meta_file.exists():
            try:
                return json.loads(meta_file.read_text())
            except Exception:
                pass
        return {"candidate_id": job_dir.name}

    @staticmethod
    def _load_status(job_dir: Path) -> dict:
        status_file = job_dir / "status.json"
        if status_file.exists():
            try:
                return json.loads(status_file.read_text())
            except Exception:
                pass
        return {"status": "unknown"}
