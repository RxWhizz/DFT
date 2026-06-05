"""Prepara directorios y scripts para relajaciones DFT básicas (r2SCAN).

Crea para cada candidato:
    runs/relax_basic/{candidate_id}/
    ├── structure.cif
    ├── POSCAR
    ├── input.py          # r2SCAN via GPAWCalculatorFactory + FIRE
    ├── metadata.json
    ├── run.sh            # script de ejecución
    ├── status.json       # {"status": "pending", ...}
    └── generator_config.yaml

Principios:
  - No sobrescribe si status.json existe con status != "pending"
  - Copia la config usada para reproducibilidad
  - Template de input.py importa GPAWCalculatorFactory del proyecto
  - Para superceldas (mixtas): reduce k-points a [2,2,2]

Uso:
    prep = RelaxationJobPreparer(config, project_root=ROOT)
    prep.prepare(scored_candidates, out_root=Path("runs/relax_basic"))
"""
from __future__ import annotations

import json
import shutil
import string
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from buho.generator.heuristic_generator import GeneratedCandidate
from buho.scoring.pre_dft_score import ScoredCandidate
from buho.structure.build_abx3 import ABX3StructureBuilder

# Usa string.Template ($var) para evitar conflictos con llaves de Python en el código generado
_INPUT_TEMPLATE = string.Template('''\
"""Relajación DFT básica — PBE — generada por BUHO.

Material  : $formula  |  Sn=$has_sn  |  MA=$has_ma  |  supercell=$is_supercell  |  cores=$n_cores
Candidate : $candidate_id
Generado  : $generated_at

CONFIG DE CRIBADO PBE (validado FASE 0, 2026-06-04):
  - XC=PBE (no r2SCAN): GGA estable y rápido; r2SCAN+U+SOC se reserva para
    refinamiento de candidatos top. domain>1 crashea GPAW master (PBE y MGGA),
    y r2SCAN Γ a 1-core = 195s/iter (inviable). PBE Γ ecut300 = 37s/iter.
  - ecut=$ecut eV (cribado; producción usa 450).
  - k-points: Γ-only [1,1,1] superceldas (la 2x2x2 ya pliega la BZ) /
    [2,2,2] celdas unidad.
  - parallel: kpt-only (domain/band rompen GPAW master en modo PW).
    Superceldas → 1 core/job (1 k-pt); puras → hasta 8 cores.
  - convergencia relajada: density=1e-3, eigenstates=1e-4, energy=1e-4.
  - Sn: width=0.2 eV (suaviza estados cerca de E_F); sin Hubbard U en cribado.
"""
import sys
sys.path.insert(0, "$src_path")

from pathlib import Path
from ase.io import read
from ase.optimize import FIRE
from gpaw import GPAW, PW, FermiDirac
from gpaw.mixer import Mixer

# Γ-only para superceldas (40 átomos): la celda 2x2x2 pliega la malla [2,2,2]
# primitiva en Γ → 1 k-pt suficiente para relajación básica, ~8× más barato.
_kpts = [1, 1, 1] if $is_supercell else [2, 2, 2]
_n_kpts = 1 if $is_supercell else 8

# Paralelización kpt-only (domain/band crashean: assert c==1 en GPAW master PW).
def _kpt_ranks(n_cores, n_kpts):
    for k in range(min(n_cores, n_kpts), 0, -1):
        if n_cores % k == 0 and n_kpts % k == 0:
            return k
    return 1

_kpt = _kpt_ranks($n_cores, _n_kpts)
_parallel = {"kpt": _kpt, "domain": 1, "band": 1}
if _kpt != $n_cores:
    raise RuntimeError(
        f"Layout MPI no soportado: n_cores={$n_cores}, k-pts={_n_kpts}. "
        "GPAW master solo soporta kpt-only (domain/band crashean). "
        "Superceldas (1 k-pt) deben correr con n_cores=1."
    )

# Ocupaciones: Sn con width amplio (0.2 eV) para suavizar oscilación SCF.
_occ_width = 0.2 if $has_sn else $smearing
# Mixer Pulay estándar — PBE converge limpio sin MSR1.
_mixer = Mixer(0.05, 8, 50)

calc = GPAW(
    mode=PW($ecut),
    xc="PBE",
    kpts={"size": _kpts, "gamma": True},
    occupations=FermiDirac(_occ_width),
    convergence={"density": 1e-3, "eigenstates": 1e-4, "energy": 1e-4},
    mixer=_mixer,
    parallel=_parallel,
    maxiter=$maxiter,
    txt="r2scan.txt",
)

atoms = read("structure.cif")
atoms.calc = calc

from ase.io import write as ase_write
import json, time

t0 = time.time()
opt = FIRE(atoms, trajectory="relax.traj", logfile="relax.log")
try:
    converged = opt.run(fmax=$fmax, steps=$max_steps)
except Exception as exc:
    Path("error.txt").write_text(str(exc))
    converged = False

e_total = float(atoms.get_potential_energy())
ase_write("relaxed.cif", atoms)

try:
    atoms.calc.write("relaxed.gpw")
except Exception:
    pass

elapsed = time.time() - t0
status = {
    "status": "converged" if converged is not False else "failed",
    "final_energy_eV": e_total,
    "energy_per_atom_eV": e_total / len(atoms),
    "n_atoms": len(atoms),
    "xc_method": "PBE",
    "ecut_eV": $ecut,
    "kpts": _kpts,
    "fidelity": "relax_basic",
    "elapsed_s": round(elapsed, 1),
    "finished_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
}
Path("status.json").write_text(json.dumps(status, indent=2))
print(f"Done. E={e_total:.6f} eV  t={elapsed:.0f}s  converged={converged}")
''')

_RUN_TEMPLATE = '''\
#!/bin/bash
# Relajación r2SCAN — {formula}
# Generado por BUHO

cd "$(dirname "$0")"
mpirun -n {n_cores} {python} input.py
'''


class RelaxationJobPreparer:
    """Prepara directorios de trabajo para relajaciones DFT básicas.

    Parámetros
    ----------
    config      : dict completo de generator.yaml
    project_root: raíz del proyecto (para resolver rutas de src/ y config/)
    n_cores     : número de cores MPI para run.sh (default: 1)
    python      : ejecutable Python (default: python3)
    """

    def __init__(
        self,
        config: dict,
        project_root: Optional[Path] = None,
        n_cores: int = 1,
        python: str = "python3",
    ):
        self._cfg = config
        self._root = Path(project_root) if project_root else Path.cwd()
        self._n_cores = n_cores
        self._python = python
        self._dft = config.get("dft_basic", {})
        self._builder = ABX3StructureBuilder(config, random_seed=config.get("random_seed", 42))

        # Detectar si existe el config de GPAW del proyecto
        self._gpaw_config = self._root / "configs" / "default_params.yaml"

    def prepare(
        self,
        candidates: list,  # list[GeneratedCandidate] o list[ScoredCandidate]
        out_root: Optional[Path] = None,
        config_src: Optional[Path] = None,
    ) -> list[Path]:
        """Crea directorios de job para cada candidato.

        Returns
        -------
        Lista de rutas creadas (solo las nuevas, no las saltadas).
        """
        if out_root is None:
            out_root = Path(self._cfg.get("paths", {}).get("relax_dir", "runs/relax_basic"))

        prepared = []
        skipped = 0

        for item in candidates:
            c: GeneratedCandidate = item.candidate if isinstance(item, ScoredCandidate) else item
            job_dir = out_root / c.candidate_id

            if self._should_skip(job_dir):
                skipped += 1
                continue

            atoms, meta = self._builder.build(c, out_dir=job_dir, export=True)
            self._write_input(job_dir, c, atoms)
            self._write_run_sh(job_dir, c)
            self._write_status_pending(job_dir, c)

            if config_src is None:
                config_src = self._root / "config" / "generator.yaml"
            if config_src.exists():
                shutil.copy2(config_src, job_dir / "generator_config.yaml")

            prepared.append(job_dir)

        print(f"Preparados: {len(prepared)}  Saltados: {skipped}")
        return prepared

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _should_skip(self, job_dir: Path) -> bool:
        status_file = job_dir / "status.json"
        if not status_file.exists():
            return False
        try:
            st = json.loads(status_file.read_text())
            return st.get("status", "pending") != "pending"
        except Exception:
            return False

    def _write_input(self, job_dir: Path, c: GeneratedCandidate, atoms) -> None:
        is_mixed = (
            len(c.A_site_species) > 1
            or len(c.B_site_species) > 1
            or len(c.X_site_species) > 1
        )
        is_supercell = is_mixed and self._cfg.get("structure", {}).get("supercell_mixed", [1,1,1]) != [1,1,1]
        has_sn = any(sp == "Sn" for sp in c.B_site_species)
        has_ma = any(sp == "MA" for sp in c.A_site_species)

        dft = self._dft
        kpts = [int(k) for k in dft.get("kpts", [4, 4, 4])]
        sn_u_ev = float(dft.get("sn_u_ev", 2.5))
        kpt_rank_cap = int(dft.get("kpt_rank_cap", 4))

        script = _INPUT_TEMPLATE.substitute(
            formula=c.formula,
            candidate_id=c.candidate_id,
            generated_at=datetime.utcnow().isoformat() + "Z",
            src_path=str(self._root / "src"),
            config_path=str(self._gpaw_config) if self._gpaw_config.exists() else "",
            is_supercell=str(is_supercell),
            has_sn=str(has_sn),
            has_ma=str(has_ma),
            sn_u_ev=sn_u_ev,
            kpt_rank_cap=kpt_rank_cap,
            n_cores=int(self._n_cores),
            ecut=int(dft.get("ecut", 400)),
            kpts=kpts,
            smearing=float(dft.get("smearing", 0.01)),
            maxiter=int(dft.get("maxiter", 300)),
            conv_density=float(dft.get("conv_density", 1e-4)),
            fmax=float(dft.get("fmax", 0.05)),
            max_steps=int(dft.get("max_steps", 200)),
        )
        (job_dir / "input.py").write_text(script)

    def _write_run_sh(self, job_dir: Path, c: GeneratedCandidate) -> None:
        script = _RUN_TEMPLATE.format(
            formula=c.formula,
            n_cores=self._n_cores,
            python=self._python,
        )
        run_sh = job_dir / "run.sh"
        run_sh.write_text(script)
        run_sh.chmod(0o755)

    @staticmethod
    def _write_status_pending(job_dir: Path, c: GeneratedCandidate) -> None:
        status = {
            "status": "pending",
            "candidate_id": c.candidate_id,
            "formula": c.formula,
            "created": datetime.utcnow().isoformat() + "Z",
        }
        (job_dir / "status.json").write_text(json.dumps(status, indent=2))
