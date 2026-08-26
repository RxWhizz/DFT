"""Carga de configs/monitor.yaml.

Vive aparte de `main.py` porque ese módulo instancia la app al importarse
(`app = create_app()`, que necesita uvicorn para resolver "monitor_api.main:app").
El lanzador solo quiere leer la configuración, no levantar una app de más.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from . import paths


def load_config(config_path: Path | None = None) -> dict:
    """Lee monitor.yaml y le superpone monitor.local.yaml si existe."""
    path = config_path or paths.config_file()
    cfg: dict = {}
    if path.exists():
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}

    local = path.with_suffix(".local.yaml")
    if local.exists():
        with open(local) as f:
            local_cfg = yaml.safe_load(f) or {}
        # deep merge a un nivel
        for k, v in local_cfg.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg
