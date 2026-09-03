"""Runtime helpers for launching BUHO DFT jobs.

The calculation scripts are intentionally small schedulers.  All decisions
about the Python/GPAW runtime live here so Windows, WSL and Linux use the same
rules and the paths are not copied into every runner.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from buho import gpaw_setup


class RuntimeCheckError(RuntimeError):
    """Raised when the configured DFT runtime cannot execute GPAW jobs."""


@dataclass(frozen=True)
class DFTRuntime:
    launcher: str
    setup_path: str
    conda_bin: str | None = None
    conda_env: str | None = None
    python: str | None = None
    mpi_launcher: str | None = None
    bash: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "launcher": self.launcher,
            "setup_path": self.setup_path,
            "conda_bin": self.conda_bin,
            "conda_env": self.conda_env,
            "python": self.python,
            "mpi_launcher": self.mpi_launcher,
            "bash": self.bash,
        }


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_env(*names: str) -> str | None:
    for name in names:
        value = _clean(os.environ.get(name))
        if value:
            return value
    return None


def _resolve_program(value: str | None, *, fallback_names: tuple[str, ...] = ()) -> str | None:
    if value:
        if any(sep in value for sep in ("/", "\\")):
            return value if Path(value).expanduser().exists() else None
        found = shutil.which(value)
        return found or value
    for name in fallback_names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _default_conda_bin(explicit: str | None = None) -> str | None:
    declared = explicit or _first_env("BUHO_CONDA_BIN", "CONDA_EXE")
    if declared:
        return _resolve_program(declared)
    found = shutil.which("conda")
    if found:
        return found
    home = Path.home()
    candidates = [
        home / "miniforge3" / ("Scripts" if os.name == "nt" else "bin") / ("conda.exe" if os.name == "nt" else "conda"),
        home / "mambaforge" / ("Scripts" if os.name == "nt" else "bin") / ("conda.exe" if os.name == "nt" else "conda"),
        home / "miniconda3" / ("Scripts" if os.name == "nt" else "bin") / ("conda.exe" if os.name == "nt" else "conda"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _default_bash(explicit: str | None = None) -> str | None:
    return _resolve_program(explicit or _first_env("BUHO_BASH"), fallback_names=("bash",))


def _default_python(explicit: str | None = None) -> str:
    declared = explicit or _first_env("BUHO_GPAW_PYTHON", "GPAW_PYTHON")
    if declared:
        return _resolve_program(declared, fallback_names=(declared,)) or declared
    return sys.executable


def _default_mpi(explicit: str | None = None) -> str | None:
    declared = explicit or _first_env("BUHO_MPI_LAUNCHER", "MPIEXEC", "MPIRUN")
    return _resolve_program(declared, fallback_names=("mpiexec", "mpirun"))


def _default_conda_env(explicit: str | None = None) -> str:
    return explicit or _first_env("BUHO_GPAW_CONDA_ENV", "GPAW_CONDA_ENV") or "gpaw246"


def _resolve_setup_path(repo_root: Path | None, explicit: str | None = None) -> str:
    setup = explicit or _first_env("BUHO_GPAW_SETUP_PATH", "GPAW_SETUP_PATH")
    if setup:
        setup_path = Path(setup).expanduser()
        if (setup_path / gpaw_setup.MARCADOR).is_file():
            return str(setup_path)
        raise RuntimeCheckError(
            f"GPAW_SETUP_PATH no contiene {gpaw_setup.MARCADOR}: {setup_path}"
        )
    try:
        return gpaw_setup.resolve(repo_root)
    except SystemExit as exc:
        raise RuntimeCheckError(str(exc)) from exc


def build_runtime(
    *,
    repo_root: Path | None = None,
    launcher: str = "auto",
    conda_bin: str | None = None,
    conda_env: str | None = None,
    python: str | None = None,
    mpi_launcher: str | None = None,
    setup_path: str | None = None,
    bash: str | None = None,
) -> DFTRuntime:
    """Resolve a runnable GPAW context from CLI args, env vars and defaults."""
    requested = (launcher or "auto").lower()
    if requested not in {"auto", "conda", "direct"}:
        raise RuntimeCheckError(f"launcher DFT no reconocido: {launcher}")

    resolved_setup = _resolve_setup_path(repo_root, setup_path)
    resolved_conda = _default_conda_bin(conda_bin)
    resolved_env = _default_conda_env(conda_env)
    resolved_python = _default_python(python)
    resolved_mpi = _default_mpi(mpi_launcher)
    resolved_bash = _default_bash(bash)

    if requested == "auto":
        env_launcher = _first_env("BUHO_DFT_LAUNCHER")
        if env_launcher in {"conda", "direct"}:
            requested = env_launcher
        elif python or _first_env("BUHO_GPAW_PYTHON", "GPAW_PYTHON"):
            requested = "direct"
        elif resolved_conda:
            requested = "conda"
        else:
            requested = "direct"

    if requested == "conda":
        if not resolved_conda:
            raise RuntimeCheckError(
                "No se encontro conda. Define BUHO_CONDA_BIN/CONDA_EXE o usa --launcher direct."
            )
        if not resolved_bash:
            raise RuntimeCheckError(
                "No se encontro bash para conda run. Instala bash en el entorno o usa --launcher direct."
            )
        return DFTRuntime(
            launcher="conda",
            setup_path=resolved_setup,
            conda_bin=resolved_conda,
            conda_env=resolved_env,
            mpi_launcher=mpi_launcher or "mpiexec",
            bash=resolved_bash,
        )

    return DFTRuntime(
        launcher="direct",
        setup_path=resolved_setup,
        python=resolved_python,
        mpi_launcher=resolved_mpi,
        bash=resolved_bash,
    )


def _base_env(runtime: DFTRuntime) -> dict[str, str]:
    env = os.environ.copy()
    env["GPAW_SETUP_PATH"] = runtime.setup_path
    env["OMP_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    if _running_in_wsl():
        env.setdefault("OMPI_MCA_btl", "self,vader,tcp")
        env.setdefault("OMPI_MCA_btl_vader_single_copy_mechanism", "none")
    executable_dirs: list[str] = []
    for value in (runtime.python, runtime.mpi_launcher, runtime.conda_bin, runtime.bash):
        if value and any(sep in value for sep in ("/", "\\")):
            executable_dirs.append(str(Path(value).expanduser().parent))
    if executable_dirs:
        path_sep = ";" if os.name == "nt" else ":"
        existing_path = env.get("PATH", "")
        env["PATH"] = path_sep.join([*executable_dirs, existing_path]) if existing_path else path_sep.join(executable_dirs)
        for value in (runtime.python, runtime.mpi_launcher):
            if value and any(sep in value for sep in ("/", "\\")):
                prefix = Path(value).expanduser().parent.parent
                lib_dir = prefix / "lib"
                if lib_dir.is_dir():
                    current = env.get("LD_LIBRARY_PATH", "")
                    env["LD_LIBRARY_PATH"] = f"{lib_dir}:{current}" if current else str(lib_dir)
                    env.setdefault("CONDA_PREFIX", str(prefix))
    return env


def _running_in_wsl() -> bool:
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    return "microsoft" in release.lower() or "wsl" in release.lower()


def build_job_command(job_dir: Path, runtime: DFTRuntime, n_cores: int) -> tuple[list[str], dict[str, str]]:
    """Return command/env for one DFT job directory."""
    cores = max(1, int(n_cores))
    env = _base_env(runtime)
    env["NCORES"] = str(cores)

    if runtime.launcher == "conda":
        if not runtime.conda_bin or not runtime.conda_env:
            raise RuntimeCheckError("Runtime conda incompleto.")
        mpi = runtime.mpi_launcher or "mpiexec"
        if (job_dir / "job.sh").exists():
            inner = (
                f"export GPAW_SETUP_PATH={shlex.quote(runtime.setup_path)}; "
                f"export NCORES={cores}; exec bash job.sh"
            )
        elif cores > 1:
            inner = (
                f"export GPAW_SETUP_PATH={shlex.quote(runtime.setup_path)}; "
                f"exec {shlex.quote(mpi)} -n {cores} python input.py"
            )
        else:
            inner = (
                f"export GPAW_SETUP_PATH={shlex.quote(runtime.setup_path)}; "
                "exec python input.py"
            )
        return [runtime.conda_bin, "run", "-n", runtime.conda_env, "bash", "-lc", inner], env

    if (job_dir / "job.sh").exists():
        if not runtime.bash:
            raise RuntimeCheckError("Este job usa job.sh, pero no se encontro bash.")
        return [runtime.bash, "job.sh"], env
    if not runtime.python:
        raise RuntimeCheckError("Runtime directo sin interprete Python.")
    if cores > 1:
        if not runtime.mpi_launcher:
            raise RuntimeCheckError(
                "No se encontro mpiexec/mpirun para correr con mas de un core."
            )
        return [runtime.mpi_launcher, "-n", str(cores), runtime.python, "input.py"], env
    return [runtime.python, "input.py"], env


def preflight(runtime: DFTRuntime, *, n_cores: int = 1, needs_bash: bool = False, timeout: int = 60) -> None:
    """Fail fast if GPAW jobs cannot start with this runtime."""
    setup_path = Path(runtime.setup_path)
    if not (setup_path / gpaw_setup.MARCADOR).is_file():
        raise RuntimeCheckError(
            f"No se encontro {gpaw_setup.MARCADOR} en GPAW_SETUP_PATH={setup_path}"
        )

    cores = max(1, int(n_cores))
    env = _base_env(runtime)
    code = "import ase, gpaw; print('GPAW_RUNTIME_OK')"
    mpi_code = (
        "from gpaw import mpi; "
        "import sys; "
        "print(f'GPAW_MPI_SIZE={mpi.world.size}'); "
        "sys.exit(0 if mpi.world.size > 1 else 7)"
    )

    if runtime.launcher == "conda":
        if not runtime.conda_bin or not Path(runtime.conda_bin).exists():
            raise RuntimeCheckError(f"No existe conda: {runtime.conda_bin}")
        checks = [f"python -c {shlex.quote(code)}"]
        if cores > 1:
            mpi = runtime.mpi_launcher or "mpiexec"
            checks.insert(0, f"command -v {shlex.quote(mpi)} >/dev/null")
            checks.append(f"{shlex.quote(mpi)} -n 2 python -c {shlex.quote(mpi_code)}")
        if needs_bash:
            checks.insert(0, "test -n \"$BASH_VERSION\"")
        cmd = [
            runtime.conda_bin,
            "run",
            "-n",
            runtime.conda_env or "base",
            "bash",
            "-lc",
            " && ".join(checks),
        ]
    else:
        if not runtime.python:
            raise RuntimeCheckError("Runtime directo sin Python.")
        if any(sep in runtime.python for sep in ("/", "\\")) and not Path(runtime.python).exists():
            raise RuntimeCheckError(f"No existe Python para GPAW: {runtime.python}")
        if cores > 1 and not runtime.mpi_launcher:
            raise RuntimeCheckError("No se encontro mpiexec/mpirun para MPI.")
        if needs_bash and not runtime.bash:
            raise RuntimeCheckError("Hay jobs con job.sh, pero no se encontro bash.")
        if cores > 1:
            cmd = [runtime.mpi_launcher or "mpiexec", "-n", "2", runtime.python, "-c", f"{code}; {mpi_code}"]
        else:
            cmd = [runtime.python, "-c", code]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except OSError as exc:
        raise RuntimeCheckError(f"No se pudo ejecutar el preflight DFT: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeCheckError(f"Preflight DFT excedio {timeout}s: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if not detail:
            detail = f"codigo de salida {result.returncode}"
        raise RuntimeCheckError(f"Preflight DFT fallo: {detail}")
