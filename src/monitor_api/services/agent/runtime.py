"""Gestión opcional del servicio Ollama externo desde el launcher."""
from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import AgentConfig


def is_ollama_up(base_url: str, *, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/version", timeout=timeout):
            return True
    except (OSError, urllib.error.URLError):
        return False


def ensure_managed_ollama(cfg: AgentConfig, *, data_root: Path, wait_sec: float = 45.0) -> bool:
    """Arranca `make ollama-serve` en revive si Ollama no responde."""
    if not (cfg.enabled and cfg.provider == "ollama" and cfg.manage_service):
        return is_ollama_up(cfg.base_url)
    if is_ollama_up(cfg.base_url):
        return True
    if cfg.revive_repo is None:
        raise RuntimeError(
            "manage_service está activo pero falta monitor.agent.revive_repo. "
            "Apúntalo al repositorio que provee `make ollama-serve`."
        )
    if not cfg.revive_repo.is_dir():
        raise RuntimeError(f"revive_repo no existe: {cfg.revive_repo}")

    env = {
        "DFT_DATA_ROOT": str(data_root),
        "OLLAMA_MODELS_HOST": str(cfg.models_dir),
    }
    full_env = None
    try:
        import os

        full_env = {**os.environ, **env}
    except Exception:
        full_env = env

    subprocess.run(
        ["make", "ollama-serve"],
        cwd=cfg.revive_repo,
        env=full_env,
        check=True,
    )

    deadline = time.time() + wait_sec
    while time.time() < deadline:
        if is_ollama_up(cfg.base_url):
            return True
        time.sleep(0.5)
    return False
