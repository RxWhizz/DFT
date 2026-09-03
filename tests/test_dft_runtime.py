"""Tests for configurable DFT runtime launch helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from buho import dft_runtime, gpaw_setup


def _setups(base: Path) -> Path:
    path = base / "setups"
    path.mkdir(parents=True)
    (path / gpaw_setup.MARCADOR).write_bytes(b"")
    return path


def test_direct_runtime_builds_single_core_command(tmp_path):
    setups = _setups(tmp_path)

    runtime = dft_runtime.build_runtime(
        launcher="direct",
        python="python-test",
        setup_path=str(setups),
    )
    cmd, env = dft_runtime.build_job_command(tmp_path, runtime, 1)

    assert cmd == ["python-test", "input.py"]
    assert env["GPAW_SETUP_PATH"] == str(setups)
    assert env["OMP_NUM_THREADS"] == "1"


def test_direct_runtime_requires_mpi_for_multi_core(tmp_path, monkeypatch):
    setups = _setups(tmp_path)
    monkeypatch.setenv("BUHO_MPI_LAUNCHER", "")

    runtime = dft_runtime.DFTRuntime(
        launcher="direct",
        setup_path=str(setups),
        python="python-test",
        mpi_launcher=None,
    )

    with pytest.raises(dft_runtime.RuntimeCheckError, match="mpiexec/mpirun"):
        dft_runtime.build_job_command(tmp_path, runtime, 8)


def test_conda_runtime_uses_configured_env_and_conda(tmp_path):
    setups = _setups(tmp_path)
    conda = tmp_path / "conda"
    conda.write_text("", encoding="utf-8")

    runtime = dft_runtime.build_runtime(
        launcher="conda",
        conda_bin=str(conda),
        conda_env="gpaw-local",
        setup_path=str(setups),
        bash="bash",
    )
    cmd, env = dft_runtime.build_job_command(tmp_path, runtime, 4)

    assert cmd[:4] == [str(conda), "run", "-n", "gpaw-local"]
    assert "GPAW_SETUP_PATH" in cmd[-1]
    assert "mpiexec -n 4" in cmd[-1]
    assert env["GPAW_SETUP_PATH"] == str(setups)
