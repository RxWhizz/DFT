#!/usr/bin/env python3
"""Wrapper CLI para correr un lote Fase 2A."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from buho.phase2_force.runner import main


if __name__ == "__main__":
    main()

