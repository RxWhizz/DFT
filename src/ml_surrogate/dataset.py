"""SQLite cache for GNN predictions — extends hts_repository candidates table.

New columns added (idempotent migration):
  gnn_bandgap_eV        REAL  — MEGNet-BandGap-mfi prediction
  gnn_eform_eV_atom     REAL  — ensemble formation energy (MEGNet+M3GNet mean)
  gnn_eform_std_eV_atom REAL  — ensemble spread (uncertainty proxy)
  gnn_struct_source     TEXT  — "gpw" | "cubic" | "pseudoatom"
  gnn_computed_at       TEXT  — ISO-8601 UTC timestamp
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ml_surrogate.gnn_predictor import GNNResult

_GNN_COLUMNS: dict[str, str] = {
    "gnn_bandgap_eV":        "REAL DEFAULT NULL",
    "gnn_eform_eV_atom":     "REAL DEFAULT NULL",
    "gnn_eform_std_eV_atom": "REAL DEFAULT NULL",
    "gnn_struct_source":     "TEXT DEFAULT NULL",
    "gnn_computed_at":       "TEXT DEFAULT NULL",
}


@dataclass
class PredictionRecord:
    A: str
    B: str
    X: str
    experiment_id: int
    gnn_result: GNNResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(v: Optional[float]) -> Optional[float]:
    if v is None or math.isnan(v) or math.isinf(v):
        return None
    return v


class GNNPredictionCache:
    """Read/write GNN predictions in the AINAGENT SQLite database.

    Parameters
    ----------
    db_path : Path
        Path to the AINAGENT/HTS SQLite database file.
    """

    def __init__(self, db_path: Path) -> None:
        self._db = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self._db))
        con.row_factory = sqlite3.Row
        return con

    def migrate(self) -> None:
        """Add GNN columns to candidates table (idempotent)."""
        con = self._connect()
        try:
            existing = {
                r[1] for r in con.execute("PRAGMA table_info(candidates)").fetchall()
            }
            for col, typedef in _GNN_COLUMNS.items():
                if col not in existing:
                    con.execute(f"ALTER TABLE candidates ADD COLUMN {col} {typedef}")
            con.commit()
        finally:
            con.close()

    def write(self, record: PredictionRecord) -> None:
        """Upsert GNN predictions for (experiment_id, A, B, X)."""
        r = record.gnn_result
        con = self._connect()
        try:
            con.execute(
                """
                UPDATE candidates
                SET gnn_bandgap_eV=?, gnn_eform_eV_atom=?, gnn_eform_std_eV_atom=?,
                    gnn_struct_source=?, gnn_computed_at=?
                WHERE experiment_id=? AND A=? AND B=? AND X=?
                """,
                (
                    _finite(r.Eg_eV),
                    _finite(r.Eform_eV_atom),
                    _finite(r.Eform_std_eV_atom),
                    r.structure_source,
                    _now(),
                    record.experiment_id,
                    record.A, record.B, record.X,
                ),
            )
            con.commit()
        finally:
            con.close()

    def is_cached(
        self, experiment_id: int, A: str, B: str, X: str
    ) -> bool:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT 1 FROM candidates "
                "WHERE experiment_id=? AND A=? AND B=? AND X=? AND gnn_bandgap_eV IS NOT NULL",
                (experiment_id, A, B, X),
            ).fetchone()
            return row is not None
        finally:
            con.close()

    def read_all(self, experiment_id: int) -> List[Dict[str, Any]]:
        """Return all candidates with GNN data, ordered by bandgap proximity to 1.45 eV."""
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT * FROM candidates "
                "WHERE experiment_id=? AND gnn_bandgap_eV IS NOT NULL "
                "ORDER BY ABS(gnn_bandgap_eV - 1.45) ASC",
                (experiment_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()

    def get_leaderboard(
        self,
        experiment_id: int,
        n: int = 20,
    ) -> List[Dict[str, Any]]:
        """Top-N candidates by blended_reward (DFT-refined) or by GNN bandgap."""
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT *,
                    COALESCE(blended_reward, reward) AS final_reward,
                    (dft_solar_score IS NOT NULL) AS dft_done,
                    (gnn_bandgap_eV IS NOT NULL)  AS gnn_done
                FROM candidates
                WHERE experiment_id=?
                ORDER BY final_reward DESC
                LIMIT ?
                """,
                (experiment_id, n),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()
