"""Cache ligero para resultados derivados."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def stable_key(parts: list[str] | tuple[str, ...]) -> str:
    """Crea una clave estable para cache."""
    payload = json.dumps(list(parts), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_json_cache(path: str | Path) -> dict[str, Any] | None:
    """Lee un cache JSON si existe."""
    cache_path = Path(path)
    if not cache_path.exists():
        return None
    return json.loads(cache_path.read_text(encoding="utf-8"))


def write_json_cache(path: str | Path, payload: dict[str, Any]) -> None:
    """Escribe un cache JSON atomico."""
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(cache_path)


class SQLiteCache:
    """Cache SQLite de pares clave-JSON."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS cache "
                "(key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )

    def get(self, key: str) -> dict[str, Any] | None:
        """Obtiene un registro JSON desde cache."""
        with self._connect() as con:
            row = con.execute("SELECT payload FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def set(self, key: str, payload: dict[str, Any]) -> None:
        """Guarda un registro JSON en cache."""
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO cache(key, payload, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (key, encoded),
            )

