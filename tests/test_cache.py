"""Pruebas de cache ligero."""

from __future__ import annotations

from dft_cspbi3.cache import SQLiteCache, read_json_cache, stable_key, write_json_cache


def test_stable_key_is_reproducible() -> None:
    assert stable_key(("Cs", "Pb", "I")) == stable_key(("Cs", "Pb", "I"))
    assert stable_key(("Cs", "Pb", "I")) != stable_key(("Cs", "Sn", "I"))


def test_json_cache_round_trip(tmp_path) -> None:
    path = tmp_path / "cache" / "result.json"
    write_json_cache(path, {"material": "CsPbI3", "score": 1.0})
    assert read_json_cache(path) == {"material": "CsPbI3", "score": 1.0}


def test_sqlite_cache_round_trip(tmp_path) -> None:
    cache = SQLiteCache(tmp_path / "cache.sqlite")
    cache.set("key", {"material": "CsPbI3"})
    assert cache.get("key") == {"material": "CsPbI3"}

