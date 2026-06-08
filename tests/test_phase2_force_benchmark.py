from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "phase2_force_benchmark.py"


def load_module():
    spec = importlib.util.spec_from_file_location("phase2_force_benchmark", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_matrix_contains_required_splits():
    bench = load_module()
    splits = {row["split"] for row in bench.MATRIX}
    assert {"2x8", "3x8", "22x1"}.issubset(splits)


def test_parallel_layout_uses_kpt_divisor_then_domain():
    bench = load_module()
    assert bench.parallel_layout(8) == {"kpt": 4, "domain": 2, "band": 1}
    assert bench.parallel_layout(22) == {"kpt": 2, "domain": 11, "band": 1}
    assert bench.parallel_layout(44) == {"kpt": 4, "domain": 11, "band": 1}


def test_watchdog_reason_thresholds():
    bench = load_module()
    sample = bench.MemSample(used_gb=60.0, available_gb=10.0, swap_gb=0.0, split_rss_gb=1.0)
    assert "ram_used_gb" in bench.watchdog_reason(sample, 60.0, 4.0, 10.0)
    sample = bench.MemSample(used_gb=10.0, available_gb=3.9, swap_gb=0.0, split_rss_gb=1.0)
    assert "mem_available_gb" in bench.watchdog_reason(sample, 60.0, 4.0, 10.0)
    sample = bench.MemSample(used_gb=10.0, available_gb=10.0, swap_gb=10.01, split_rss_gb=1.0)
    assert "swap_gb" in bench.watchdog_reason(sample, 60.0, 4.0, 10.0)


def test_parse_r2scan_extracts_iterations_and_memory(tmp_path):
    bench = load_module()
    txt = tmp_path / "r2scan.txt"
    txt.write_text(
        """
8 k-points: 2 x 2 x 2 Monkhorst-Pack grid
Number of coefficients (min, max): 120713, 120958
Memory estimate:
  Process memory now: 454.37 MiB
  Calculator: 1452.73 MiB
    Density: 491.92 MiB
    Wavefunctions: 847.30 MiB
Number of atoms: 40
Number of bands in calculation: 208
iter:   1  10:00:00
iter:   2  10:00:06
""",
        encoding="utf-8",
    )
    parsed = bench.parse_r2scan(txt)
    assert parsed["iters"] == 2
    assert parsed["t_iter_s"] == 6
    assert parsed["calculator_mib"] == 1452.73
    assert parsed["coeff_max"] == 120958
