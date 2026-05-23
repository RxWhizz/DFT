"""Orchestrate multi-step DFT workflows."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Sequence

import numpy as np

from ase.io import read, write
from ase.optimize import BFGS
from gpaw import GPAW, Mixer
from gpaw.mixer import MixerSum, BroydenMixer

from .calculator_factory import GPAWCalculatorFactory
from .structure_builder import StructureBuilder

logger = logging.getLogger(__name__)


def _compute_scissor(hse_gpw: Path, bands_gpw: Path) -> float:
    """Devuelve Eg(HSE06) − Eg(PBE) as scissor shift en eV."""
    def _gap(gpw_path):
        from gpaw import GPAW as _GPAW
        c = _GPAW(str(gpw_path), txt=None)
        ef = c.get_fermi_level()
        nk = len(c.get_bz_k_points())
        eigs = np.array([c.get_eigenvalues(k) for k in range(nk)])
        e = eigs - ef
        return float(e[e > 0].min() - e[e < 0].max())
    return _gap(hse_gpw) - _gap(bands_gpw)

STEP_ORDER = [
    "relax", "relax_sym", "scf", "bands", "dos", "soc",
    "soc_pbe",            # SOC perturbativo sobre PBE ground state (alternativa a soc_hse06 cuando HSE06 bug)
    "scan",               # SCAN meta-GGA SCF - mejor gap que PBE sin HSE06
    "scan_soc",           # SCAN + SOC autoconsistente (spinors=True, 2-componentes Pauli)
    "soc_scan",           # SOC perturbativo sobre SCAN (ignore_xc_potential=True)
    "r2scan",             # r²SCAN meta-GGA SCF - SCAN regularizado, mejor convergencia
    "soc_r2scan",         # SOC perturbativo sobre r²SCAN (ignore_xc_potential=True)
    # r2scan_bands removed: GPAW 25.7.0 MGGA does not support fixdensity; VBM/CBM k-points
    # are read directly from the SCF MP grid via r2scan_bandgap.json instead.
    "hse06",
    "hse06_nonscf",       # non-SCF HSE06@PBE
    "soc_hse06",          # SOC applied post-HSE06 (requiere hse06.gpw o hse06_nonscf.gpw)
    "hse06_scissor",      # scissor correction
    "hessian", "phonons", "pes", "loto",
    "formation_energy",   # ΔHf desde binary references (CsI + PbI₂ único-points)
    "effective_masses",   # parabolic fit desde existente bands.gpw - no new GPAW
    "optical",
    "sq_limit",
    "oghma_device",
    "score",
]
STEP_DIRS = {
    "relax": "01_relax",
    "relax_sym": "01_relax_sym",
    "scf": "02_scf",
    "bands": "03_bands",
    "dos": "04_dos",
    "soc": "05_soc",
    "scan": "06_scan",
    "scan_soc": "06_scan",
    "soc_scan": "06_scan",
    "r2scan": "06_r2scan",
    "soc_r2scan": "06_r2scan",
    "hse06": "06_hse06",
    "hse06_nonscf": "06_hse06",
    "hse06_scissor": "06_hse06",
    "soc_hse06": "05_soc",
    "soc_pbe": "05_soc",
    "hessian": "07_vibrational/hessian",
    "phonons": "07_vibrational/phonons",
    "pes": "07_vibrational/pes",
    "loto": "08_loto",
    "formation_energy": "09_formation_energy",
    "effective_masses": "10_effective_masses",
    "optical": "11_optical",
    "sq_limit": "13_sq_limit",
    "oghma_device": "14_oghma_device",
    "score": "12_score",
}
STEP_DONE_FILES = {
    "relax_sym": "relax_sym.gpw",
    "soc": "soc_eigenvalues.npy",
    "soc_scan": "soc_scan_eigenvalues.npy",
    "soc_r2scan": "soc_r2scan_eigenvalues.npy",
    "hse06_scissor": "hse06_scissor.json",
    "hessian": "hessian.npy",
    "phonons": "phonon_frequencies.npy",
    "loto": "born_charges.npy",
    "formation_energy": "formation_energy.json",
    "effective_masses": "electronic_analysis.json",
    "optical": "optical_frequencies.npy",
    "sq_limit": "sq_limit.json",
    "oghma_device": "oghma_device_result.json",
    "score": "solar_score.json",
}


def _is_m_point(kpt: np.ndarray, tol: float = 0.02) -> bool:
    """True if kpt is the M-point [0.5, 0.5, 0.0] in fractional coordinates."""
    target = np.array([0.5, 0.5, 0.0])
    return bool(np.allclose(np.abs(kpt), target, atol=tol))


def _is_cubic_structure(relax_gpw: Path, tol_lengths: float = 0.05, tol_angles: float = 1.0) -> bool:
    """True if the relaxed structure has cubic symmetry (equal lattice params, 90° angles)."""
    try:
        calc = GPAW(str(relax_gpw), txt=None)
        atoms = calc.get_atoms()
        calc.__del__()
        cell = atoms.get_cell()
        a, b, c = (float(np.linalg.norm(cell[i])) for i in range(3))
        angles = atoms.cell.angles()  # [alpha, beta, gamma] in degrees
        lengths_equal = abs(a - b) < tol_lengths and abs(b - c) < tol_lengths
        angles_right = all(abs(ang - 90.0) < tol_angles for ang in angles)
        return lengths_equal and angles_right
    except Exception:
        return False


class DFTWorkflow:
    """Nota técnica."""

    def __init__(
        self,
        phase: str,
        config_path: str | Path | None = None,
        composition_config: str | Path | None = None,
        work_dir: str | Path = "./calculations",
        dry_run: bool = False,
    ) -> None:
        self.phase = phase
        self.work_dir = Path(work_dir) / phase
        self.dry_run = dry_run
        self.factory = GPAWCalculatorFactory(config_path) if config_path else GPAWCalculatorFactory()

        # Merge composition-specific config into factory config
        comp_cfg_path = Path(composition_config) if composition_config else None
        if comp_cfg_path is None:
            fallback = self.factory.config.get("composition_config")
            if fallback:
                comp_cfg_path = Path(fallback)
        if comp_cfg_path and comp_cfg_path.exists():
            import yaml
            with open(comp_cfg_path) as fh:
                comp_data = yaml.safe_load(fh) or {}
            self.factory.config.update(comp_data)

        self._completed: dict[str, bool] = {s: False for s in STEP_ORDER}
        self._start_time: dict[str, datetime] = {}

    # API publica.

    def run(self, steps: Sequence[str] = ("relax", "scf", "bands", "dos", "soc")) -> None:
        """Ejecuta pasos pedidos en orden."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        ordered = [s for s in STEP_ORDER if s in steps]
        for step in ordered:
            logger.info("Inicia paso: %s", step)
            self._start_time[step] = datetime.now()
            step_dir = self._step_dir(step)
            step_dir.mkdir(parents=True, exist_ok=True)

            try:
                runner = getattr(self, f"_run_{step}")
                runner(step_dir)
                self._completed[step] = True
                logger.info("Paso completo: %s", step)
            except Exception as exc:
                logger.error("Paso %s fallo: %s", step, exc)
                raise

    def get_status(self) -> None:
        """Imprime tabla pasos completos/pendientes."""
        print(f"\n{'Paso':<12} {'Dir':<20} {'Estado':<12} {'Archivo GPW'}")
        print("-" * 65)
        for step in STEP_ORDER:
            step_dir = self._step_dir(step)
            done_file = step_dir / STEP_DONE_FILES.get(step, f"{step}.gpw")
            status = "HECHO" if done_file.exists() else ("PENDIENTE" if not self._completed[step] else "HECHO")
            print(f"{step:<12} {str(step_dir.name):<20} {status:<12} {done_file.name if done_file.exists() else '-'}")

    def check_convergence(self, step: str) -> bool:
        """Revisa si paso completo convergio desde log."""
        step_dir = self._step_dir(step)
        if step == "relax":
            log = step_dir / "relax.log"
            return self._check_bfgs_converged(log)
        done_file = step_dir / STEP_DONE_FILES.get(step, f"{step}.gpw")
        return done_file.exists()

    # Runners de pasos.

    def _run_relax(self, step_dir: Path) -> None:
        gpw_out = step_dir / "relax.gpw"
        if gpw_out.exists():
            logger.info("relax.gpw existe; omite relajacion")
            return

        atoms = self._load_initial_structure()
        calc = self.factory.create("relax", txt=str(step_dir / "relax.txt"))
        atoms.calc = calc

        if self.dry_run:
            write(str(step_dir / "initial_structure.cif"), atoms)
            logger.info("Dry run: escribio initial_structure.cif")
            return

        opt = BFGS(
            atoms,
            trajectory=str(step_dir / "relax.traj"),
            logfile=str(step_dir / "relax.log"),
        )
        opt.run(fmax=self.factory.config["relax"]["convergence"]["forces"])
        calc.write(str(gpw_out))
        write(str(step_dir / "relaxed.cif"), atoms)

    def _run_relax_sym(self, step_dir: Path) -> None:
        """Relajación con FixSymmetry — preserva grupo espacial cúbico durante BFGS.
        Evita el tilting octaédrico causado por orientación asimétrica del catión FA+.
        Requiere spglib (ya instalado como dependencia de ASE).
        """
        from ase.constraints import FixSymmetry

        gpw_out = step_dir / "relax_sym.gpw"
        if gpw_out.exists():
            logger.info("relax_sym.gpw existe, omitiendo")
            return
        if self.dry_run:
            logger.info("Dry run: correría relax_sym con FixSymmetry")
            return

        atoms = self._load_initial_structure()
        atoms.set_constraint(FixSymmetry(atoms))
        calc = self.factory.create("relax_sym", txt=str(step_dir / "relax_sym.txt"))
        atoms.calc = calc
        opt = BFGS(
            atoms,
            trajectory=str(step_dir / "relax_sym.traj"),
            logfile=str(step_dir / "relax_sym.log"),
        )
        opt.run(fmax=self.factory.config["relax"]["convergence"]["forces"])
        calc.write(str(gpw_out))
        write(str(step_dir / "relax_sym.cif"), atoms)
        logger.info("relax_sym completo (grupo espacial preservado): %s", gpw_out)

    def _load_initial_structure(self):
        """Carga estructura inicial para fases internas o genericas."""
        structures_dir = self.factory.config.get("structures_dir")
        try:
            return StructureBuilder.load_phase_generic(self.phase, structures_dir=structures_dir)
        except FileNotFoundError:
            if self.phase in {"alpha", "beta", "gamma", "delta"}:
                return StructureBuilder.load_phase(self.phase)
            raise

    def _run_scf(self, step_dir: Path) -> None:
        gpw_out = step_dir / "scf.gpw"
        if gpw_out.exists():
            logger.info("scf.gpw existe; omite SCF")
            return

        relax_gpw = self._step_dir("relax") / "relax.gpw"
        if self.dry_run:
            logger.info("Dry run: correria SCF desde %s", relax_gpw)
            return
        if not relax_gpw.exists():
            raise FileNotFoundError(f"Relaxation checkpoint not found: {relax_gpw}")

        kpts = self.factory.config["scf"].get("kpts", [6, 6, 6])
        calc = GPAW(
            str(relax_gpw),
            kpts={"size": kpts, "gamma": True},
            convergence={"energy": self.factory.config["scf"]["convergence"]["energy"]},
            txt=str(step_dir / "scf.txt"),
        )
        atoms = calc.get_atoms()
        atoms.get_potential_energy()
        calc.write(str(gpw_out), 'all')

    def _run_bands(self, step_dir: Path) -> None:
        gpw_out = step_dir / "bands.gpw"
        if gpw_out.exists():
            logger.info("bands.gpw exists, skipping band structure")
            return

        scf_gpw = self._step_dir("scf") / "scf.gpw"
        if self.dry_run:
            logger.info("Dry run: would compute bands from %s", scf_gpw)
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(f"SCF checkpoint not found: {scf_gpw}")

        # Carga reference atoms para banda ruta generación
        ref_calc = GPAW(str(scf_gpw))
        atoms = ref_calc.get_atoms()
        ref_calc.__del__()

        bands_cfg = self.factory.config["bands"]
        path = atoms.cell.bandpath(
            bands_cfg.get("kpts_path", "XRMGR"),
            npoints=bands_cfg.get("npoints", 40),
        )

        calc = GPAW(
            str(scf_gpw),
            fixdensity=True,
            symmetry="off",
            kpts=path,
            convergence={"bands": bands_cfg["convergence"].get("bands", -10)},
            txt=str(step_dir / "bands.txt"),
        )
        atoms.calc = calc
        atoms.get_potential_energy()
        calc.write(str(gpw_out))

        bs = calc.band_structure()
        bs.write(str(step_dir / "band_structure.json"))

    def _run_dos(self, step_dir: Path) -> None:
        gpw_out = step_dir / "dos.gpw"
        if gpw_out.exists():
            logger.info("dos.gpw exists, skipping DOS")
            return

        scf_gpw = self._step_dir("scf") / "scf.gpw"
        dos_cfg = self.factory.config["dos"]

        if self.dry_run:
            logger.info("Dry run: would compute DOS from %s with kpts=%s", scf_gpw, dos_cfg["kpts"])
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(f"SCF checkpoint not found: {scf_gpw}")

        calc = GPAW(
            str(scf_gpw),
            kpts={"size": dos_cfg.get("kpts", [12, 12, 12]), "gamma": True},
            txt=str(step_dir / "dos.txt"),
        )
        atoms = calc.get_atoms()
        atoms.get_potential_energy()
        calc.write(str(gpw_out))

    def _run_soc(self, step_dir: Path) -> None:
        """Aplica SOC perturbatively usa spinorbit_eigenvalues() en SCF.gpw."""
        scf_gpw = self._step_dir("scf") / "scf.gpw"
        soc_cfg = self.factory.config.get("soc", {})
        mode = soc_cfg.get("mode", "perturbative")

        if self.dry_run:
            logger.info("Dry run: would apply SOC (%s) to %s", mode, scf_gpw)
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(f"SCF checkpoint not found: {scf_gpw}")

        if mode == "perturbative":
            from gpaw.spinorbit import soc_eigenstates
            import numpy as np

            result = soc_eigenstates(
                str(scf_gpw),
                theta=soc_cfg.get("theta", 0.0),
                phi=soc_cfg.get("phi", 0.0),
            )
            np.save(str(step_dir / "soc_eigenvalues.npy"), result.eigenvalues())
            np.save(str(step_dir / "soc_spin_projections.npy"), result.spin_projections())
            logger.info("SOC eigenvalues saved to soc_eigenvalues.npy")
        else:
            raise NotImplementedError(
                "Non-collinear SOC mode requires setting up a new GPAW calculation "
                "with nspins=4. Use calculator_factory with params_override={'nspins':4}."
            )

    def _run_scan(self, step_dir: Path) -> None:
        """SCAN meta-GGA SCF - mejor aproximación al gap que PBE, sin HSE06."""
        gpw_out = step_dir / "scan.gpw"
        if gpw_out.exists():
            logger.info("scan.gpw exists, skipping SCAN")
            return

        relax_gpw = self._step_dir("relax") / "relax.gpw"
        if self.dry_run:
            logger.info("Dry run: would run SCAN from %s", relax_gpw)
            return
        if not relax_gpw.exists():
            raise FileNotFoundError(f"relax.gpw not found: {relax_gpw}")

        calc = self.factory.create("scan", txt=str(step_dir / "scan.txt"))
        atoms = GPAW(str(relax_gpw), txt=None).get_atoms()
        atoms.calc = calc
        atoms.get_potential_energy()
        calc.write(str(gpw_out))

        from ase.dft.bandgap import bandgap
        gap, p1, p2 = bandgap(calc)
        logger.info("SCAN band gap: %.4f eV  VBM=%s CBM=%s", gap, p1, p2)

    def _run_scan_soc(self, step_dir: Path) -> None:
        """SCAN + SOC autoconsistente - NOT supported en GPAW 25.7.0."""
        scan_gpw = step_dir / "scan.gpw"
        scf_gpw = self.work_dir / "02_scf" / "scf.gpw"
        soc_npy = self.work_dir / "05_soc" / "soc_eigenvalues.npy"

        logger.warning(
            "scan_soc: GPAW 25.7.0 only supports LDA for self-consistent "
            "noncollinear SOC. SCAN+SOC is not available. "
            "Reporting SCAN gap with additive PBE SOC correction instead."
        )

        if self.dry_run:
            return

        if not scan_gpw.exists():
            raise FileNotFoundError("scan.gpw not found. Run step 'scan' first.")

        from ase.dft.bandgap import bandgap
        c_scan = GPAW(str(scan_gpw), txt=None)
        gap_scan, _, _ = bandgap(c_scan)
        logger.info("Eg(SCAN, no SOC) = %.4f eV", gap_scan)

        if scf_gpw.exists() and soc_npy.exists():
            c_pbe = GPAW(str(scf_gpw), txt=None)
            gap_pbe, _, _ = bandgap(c_pbe)
            eigs_soc = np.load(str(soc_npy))
            # PBE+SOC gap
            # fills one spinor level, so occupied = N (no N/2)
            nval = int(c_pbe.get_number_of_electrons())
            # eigenvalues shape
            # Usa stored array
            try:
                vbm = np.max(eigs_soc[:, nval - 1])
                cbm = np.min(eigs_soc[:, nval])
                gap_pbe_soc = cbm - vbm
            except (IndexError, ValueError):
                gap_pbe_soc = None

            if gap_pbe_soc is not None and gap_pbe_soc > 0:
                delta_soc = gap_pbe_soc - gap_pbe
                gap_scan_soc_est = gap_scan + delta_soc
                logger.info(
                    "Eg(PBE) = %.4f eV  Eg(PBE+SOC) = %.4f eV  "
                    "ΔSOC = %.4f eV  → Eg(SCAN+SOC, additive est.) = %.4f eV",
                    gap_pbe, gap_pbe_soc, delta_soc, gap_scan_soc_est,
                )

    def _run_soc_scan(self, step_dir: Path) -> None:
        """SOC perturbativo sobre estado fundamental SCAN."""
        from gpaw.spinorbit import soc_eigenstates
        scan_gpw = step_dir / "scan.gpw"
        done_flag = step_dir / "soc_scan_eigenvalues.npy"

        if done_flag.exists():
            logger.info("soc_scan_eigenvalues.npy exists, skipping")
            return
        if self.dry_run:
            logger.info("Dry run: would apply SOC to %s", scan_gpw)
            return
        if not scan_gpw.exists():
            raise FileNotFoundError(f"scan.gpw not found. Run step 'scan' first.")

        calc = GPAW(str(scan_gpw), txt=None)
        nb = calc.get_number_of_bands()
        ne = int(calc.get_number_of_electrons())

        soc_cfg = self.factory.config.get("soc", {})
        result = soc_eigenstates(
            calc,
            n2=nb,
            theta=soc_cfg.get("theta", 0.0),
            phi=soc_cfg.get("phi", 0.0),
            ignore_xc_potential=True,
        )

        eigs = result.eigenvalues()
        np.save(str(done_flag), eigs)
        np.save(str(step_dir / "soc_scan_spin_projections.npy"), result.spin_projections())

        # Gap
        vbm = float(np.max(eigs[:, ne - 1]))
        cbm = float(np.min(eigs[:, ne]))
        gap = cbm - vbm
        logger.info(
            "SCAN+SOC (ignore_xc_potential=True) band gap: %.4f eV  VBM=%.4f  CBM=%.4f",
            gap, vbm, cbm,
        )
        logger.info("SCAN+SOC eigenvalues saved to %s", done_flag)

    @staticmethod
    def _save_r2scan_bandgap(step_dir: Path, calc: object) -> None:
        """Compute and save r2scan_bandgap.json from an already-converged calculator."""
        import json as _json
        from ase.dft.bandgap import bandgap
        gap, p1, p2 = bandgap(calc)
        logger.info("r²SCAN band gap: %.4f eV  VBM=%s CBM=%s", gap, p1, p2)
        # p1/p2 are (spin, kpt_index, band_index); kpt_index can be None for metallic/edge cases
        vbm_k = int(p1[1]) if (p1 is not None and p1[1] is not None) else None
        cbm_k = int(p2[1]) if (p2 is not None and p2[1] is not None) else None
        direct = (vbm_k is not None and cbm_k is not None and vbm_k == cbm_k)
        # Save fractional k-point coordinates from the live calculator's IBZ array.
        # This avoids reloading the GPW file later (which fails in MPI context).
        ibz_kpts = calc.get_ibz_k_points()  # (nk, 3) array; kpt_index is into this array
        vbm_kpt_frac = ibz_kpts[vbm_k].tolist() if (vbm_k is not None and vbm_k < len(ibz_kpts)) else None
        cbm_kpt_frac = ibz_kpts[cbm_k].tolist() if (cbm_k is not None and cbm_k < len(ibz_kpts)) else None
        _bg_data = {
            "gap_eV": float(gap),
            "gap_type": "direct" if direct else "indirect",
            "vbm_kpt_index": vbm_k,
            "cbm_kpt_index": cbm_k,
            "vbm_kpt_frac": vbm_kpt_frac,
            "cbm_kpt_frac": cbm_kpt_frac,
            "functional": "r2SCAN",
        }
        (step_dir / "r2scan_bandgap.json").write_text(_json.dumps(_bg_data, indent=2))

    def _run_r2scan(self, step_dir: Path) -> None:
        """r²SCAN meta-GGA SCF."""
        gpw_out = step_dir / "r2scan.gpw"
        bg_json = step_dir / "r2scan_bandgap.json"

        # Regenerate JSON if missing or if it lacks fractional k-point coordinates
        if gpw_out.exists():
            needs_regen = not bg_json.exists()
            if bg_json.exists():
                import json as _json_check
                _d = _json_check.loads(bg_json.read_text())
                if _d.get("vbm_kpt_frac") is None or _d.get("cbm_kpt_frac") is None:
                    needs_regen = True
                    logger.info("r2scan_bandgap.json missing fractional k-points; regenerating")
            if needs_regen:
                logger.info("r2scan.gpw exists; regenerating r2scan_bandgap.json")
                calc = GPAW(str(gpw_out), txt=None)
                self._save_r2scan_bandgap(step_dir, calc)
            else:
                logger.info("r2scan.gpw and r2scan_bandgap.json exist, skipping")
            return

        relax_sym_gpw = self._step_dir("relax_sym") / "relax_sym.gpw"
        relax_gpw     = self._step_dir("relax")     / "relax.gpw"
        source_gpw    = relax_sym_gpw if relax_sym_gpw.exists() else relax_gpw
        if relax_sym_gpw.exists():
            logger.info("r²SCAN: usando estructura sym-constrained (relax_sym.gpw)")

        if self.dry_run:
            logger.info("Dry run: would run r²SCAN from %s", source_gpw)
            return
        if not source_gpw.exists():
            raise FileNotFoundError(f"relax.gpw not found: {source_gpw}. Run 'relax' (or 'relax_sym') first.")

        pre_gpw = step_dir / "pre_r2scan.gpw"
        if pre_gpw.exists():
            # GPAW 25.7 PW-MGGA cannot restart from GGA checkpoint: wfs.initialize
            # calls hamiltonian.update (which needs τ) before psit_nG is loaded.
            # pre_r2scan.gpw is retained for master-branch warm start; cold-start here.
            logger.info("r²SCAN: pre_r2scan.gpw found but MGGA restart not supported in PW mode "
                        "(GPAW 25.7); using cold start")

        # Always cold-start; factory.create includes Davidson(niter=4) and correct setups.
        calc = self.factory.create("r2scan", txt=str(step_dir / "r2scan.txt"))
        atoms = GPAW(str(source_gpw), txt=None).get_atoms()
        atoms.calc = calc
        atoms.get_potential_energy()
        calc.write(str(gpw_out))
        self._save_r2scan_bandgap(step_dir, calc)

    def _run_soc_r2scan(self, step_dir: Path) -> None:
        """SOC perturbativo sobre r²SCAN."""
        from gpaw.spinorbit import soc_eigenstates
        r2scan_gpw = step_dir / "r2scan.gpw"
        done_flag = step_dir / "soc_r2scan_eigenvalues.npy"

        if done_flag.exists():
            logger.info("soc_r2scan_eigenvalues.npy exists, skipping")
            return
        if self.dry_run:
            logger.info("Dry run: would apply SOC to %s", r2scan_gpw)
            return
        if not r2scan_gpw.exists():
            raise FileNotFoundError("r2scan.gpw not found. Run step 'r2scan' first.")

        calc = GPAW(str(r2scan_gpw), txt=None)
        nb = calc.get_number_of_bands()
        ne = int(calc.get_number_of_electrons())

        soc_cfg = self.factory.config.get("soc", {})
        result = soc_eigenstates(
            calc,
            n2=nb,
            theta=soc_cfg.get("theta", 0.0),
            phi=soc_cfg.get("phi", 0.0),
            ignore_xc_potential=True,
        )

        eigs = result.eigenvalues()
        np.save(str(done_flag), eigs)
        np.save(str(step_dir / "soc_r2scan_spin_projections.npy"), result.spin_projections())

        vbm = float(np.max(eigs[:, ne - 1]))
        cbm = float(np.min(eigs[:, ne]))
        gap = cbm - vbm
        logger.info(
            "r²SCAN+SOC (ignore_xc_potential=True) band gap: %.4f eV  VBM=%.4f  CBM=%.4f",
            gap, vbm, cbm,
        )
        logger.info("r²SCAN+SOC eigenvalues saved to %s", done_flag)

    def _run_r2scan_bands(self, step_dir: Path) -> None:
        """Non-SCF r²SCAN band structure on XRMGR k-path for VBM/CBM k-point detection."""
        r2scan_gpw = self._step_dir("r2scan") / "r2scan.gpw"
        gpw_out = step_dir / "r2scan_bands.gpw"

        if gpw_out.exists():
            logger.info("r2scan_bands.gpw exists, skipping")
            return
        if self.dry_run:
            logger.info("Dry run: would run r²SCAN non-SCF bands from %s", r2scan_gpw)
            return
        if not r2scan_gpw.exists():
            raise FileNotFoundError(f"r2scan.gpw not found at {r2scan_gpw}. Run step 'r2scan' first.")

        ref_calc = GPAW(str(r2scan_gpw), txt=None)
        atoms = ref_calc.get_atoms()
        ref_calc.__del__()
        bands_cfg = self.factory.config.get("bands", {})
        path = atoms.cell.bandpath(
            bands_cfg.get("kpts_path", "XRMGR"),
            npoints=bands_cfg.get("npoints", 40),
        )
        calc = GPAW(
            str(r2scan_gpw),
            fixdensity=True,
            symmetry="off",
            kpts=path,
            convergence={"bands": bands_cfg.get("convergence", {}).get("bands", -10)},
            txt=str(step_dir / "r2scan_bands.txt"),
        )
        atoms.calc = calc
        atoms.get_potential_energy()
        calc.write(str(gpw_out))
        calc.band_structure().write(str(step_dir / "r2scan_band_structure.json"))
        logger.info("r²SCAN band structure saved to %s", gpw_out)

    def _run_hse06(self, step_dir: Path) -> None:
        gpw_out = step_dir / "hse06.gpw"
        if gpw_out.exists():
            logger.info("hse06.gpw exists, skipping HSE06")
            return

        scf_gpw = self._step_dir("scf") / "scf.gpw"
        if self.dry_run:
            logger.info("Dry run: would run HSE06 from %s", scf_gpw)
            return

        txt = str(step_dir / "hse06.txt")
        checkpoint = step_dir / "hse06_checkpoint.gpw"

        hse_cfg  = self.factory.config.get("hse06", {})
        conv_cfg = hse_cfg.get("convergence", {})
        mixer_cfg = hse_cfg.get("mixer", {})

        # Auto-calcula nbands = int(n_occ * 1.3) desde SCF electron count
        # Extra empty bands (≥20-30% occupied) stabilise Fock operator y
        # prevent eigensolver failures when Davidson subspace too small
        nbands_override: int | None = None
        nbands_cfg = hse_cfg.get("nbands", "auto")
        if nbands_cfg == "auto":
            if scf_gpw.exists():
                _ref = GPAW(str(scf_gpw), txt=None)
                n_occ = int(_ref.get_number_of_electrons()) // 2
                # n_occ + 50% extra vacías
                # vacías para n_occ=22
                # que corrección Fock en banda conducción esté convergida
                nbands_override = n_occ + int(n_occ * 0.5)
                logger.info("HSE06 nbands auto: n_occ=%d → nbands=%d (+50%% vacías)", n_occ, nbands_override)
        elif isinstance(nbands_cfg, int):
            nbands_override = nbands_cfg

        if checkpoint.exists():
            logger.info("Resuming HSE06 from checkpoint: %s", checkpoint)
            # MixerSum (MSR1)
            # estabilizar potencial intercambio exacto entre ciclos SCF
            calc = GPAW(
                str(checkpoint),
                txt=txt,
                mixer=MixerSum(
                    beta=mixer_cfg.get("beta", 0.01),
                    nmaxold=mixer_cfg.get("nmaxold", 8),
                    weight=mixer_cfg.get("weight", 50.0),
                ),
                convergence={
                    "energy": conv_cfg.get("energy", 1e-6),
                    "eigenstates": conv_cfg.get("eigenstates", 1e-4),
                    "density": conv_cfg.get("density", 1e-4),
                },
            )
            atoms = calc.get_atoms()
        else:
            if not scf_gpw.exists():
                raise FileNotFoundError(f"SCF checkpoint not found: {scf_gpw}")
            override: dict = {}
            if nbands_override is not None:
                override["nbands"] = nbands_override
            calc = self.factory.create("hse06", txt=txt, params_override=override or None)
            atoms = GPAW(str(scf_gpw), txt=None).get_atoms()

        calc.attach(calc.write, 5, str(checkpoint), mode="all")
        atoms.calc = calc
        atoms.get_potential_energy()
        calc.write(str(gpw_out))
        checkpoint.unlink(missing_ok=True)

    def _run_hse06_nonscf(self, step_dir: Path) -> None:
        """Non-self-consistent HSE06@PBE."""
        out_gpw = step_dir / "hse06_nonscf.gpw"
        if out_gpw.exists():
            logger.info("hse06_nonscf.gpw exists, skipping")
            return

        scf_gpw = self._step_dir("scf") / "scf.gpw"
        if self.dry_run:
            logger.info("Dry run: correria HSE06 non-SCF desde %s", scf_gpw)
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(f"Checkpoint SCF no existe: {scf_gpw}")

        txt = str(step_dir / "hse06_nonscf.txt")
        hse_cfg = self.factory.config.get("hse06", {})
        kpts = hse_cfg.get("kpts", [2, 2, 2])
        kpts_tag = "x".join(str(k) for k in kpts)

        # Paso 1.
        # scf.gpw usa malla mas densa (6x6x6).
        # Cambiar malla reinicia orbitales; one-shot HSE06 falla.
        # PBE en malla HSE da orbitales iniciales fisicos.
        pbe_gpw = step_dir / f"pbe_{kpts_tag}.gpw"
        if not pbe_gpw.exists():
            ref = GPAW(str(scf_gpw), txt=None)
            atoms_ref = ref.get_atoms()
            # nbands
            _nbands_cfg = hse_cfg.get("nbands", None)
            if _nbands_cfg == "auto":
                _n_occ = int(ref.get_number_of_electrons()) // 2
                _nbands_pbe: int | None = _n_occ + int(_n_occ * 0.5)
            elif isinstance(_nbands_cfg, int):
                _nbands_pbe = _nbands_cfg
            else:
                _nbands_pbe = None
            pbe_kwargs: dict = dict(
                mode=self.factory._hse06_params()["mode"],
                xc="PBE",
                kpts={"size": kpts, "gamma": True},
                symmetry={"point_group": True, "time_reversal": True},
                convergence={"energy": 1e-6, "eigenstates": 1e-8, "density": 1e-6},
                occupations={"name": "fermi-dirac", "width": 0.01},
                txt=str(step_dir / f"pbe_{kpts_tag}.txt"),
            )
            if _nbands_pbe is not None:
                pbe_kwargs["nbands"] = _nbands_pbe
                logger.info("PBE@%s nbands=%d (auto: n_occ=%d × 1.5)", kpts_tag, _nbands_pbe, _n_occ)
            calc_pbe = GPAW(**pbe_kwargs)
            atoms_ref.calc = calc_pbe
            atoms_ref.get_potential_energy()
            # 'all' guarda funciones onda (psit_nG) - requerido por
            # non_self_consistent_eigenvalues para calcular ⟨ψ|vxc|ψ⟩
            calc_pbe.write(str(pbe_gpw), mode="all")
            logger.info("PBE@%s converged: %s", kpts_tag, pbe_gpw)

        # Paso 2.
        # Ruta principal
        # eig_hse = eig_pbe − vxc_pbe + vxc_hse
        # Es más ligera que maxiter=1 (sin reconstruir densidad) y evita error
        # convergencia que maxiter=1 lanza por diseño
        # Ruta fallback
        _used_nsc_api = False
        try:
            from gpaw.hybrids.eigenvalues import non_self_consistent_eigenvalues

            # Pasar objeto GPAW con txt= para que corrida quede registrada en log
            _calc_for_nsc = GPAW(str(pbe_gpw), txt=txt)
            eig_pbe, vxc_pbe, vxc_hse = non_self_consistent_eigenvalues(
                _calc_for_nsc,
                xcname="HSE06",
            )
            eig_hse = eig_pbe - vxc_pbe + vxc_hse
            np.save(str(step_dir / "hse06_nsc_eigenvalues.npy"), eig_hse)
            _used_nsc_api = True
            logger.info(
                "non_self_consistent_eigenvalues HSE06 completo; guardo hse06_nsc_eigenvalues.npy"
            )

            # Log bandgap desde autovalores corregidos.
            _ref_pbe = _calc_for_nsc
            _ef = _ref_pbe.get_fermi_level()
            _eigs_flat = eig_hse.flatten()
            _occ = _eigs_flat[_eigs_flat < _ef]
            _unocc = _eigs_flat[_eigs_flat >= _ef]
            if len(_occ) and len(_unocc):
                _gap_nsc = float(_unocc.min() - _occ.max())
                logger.info("HSE06 non-SCF (correccion autovalores) bandgap: %.4f eV", _gap_nsc)
        except Exception as _exc:
            logger.warning(
                "non_self_consistent_eigenvalues fallo (%s); usa fallback maxiter=1", _exc
            )

        if not _used_nsc_api:
            # Fallback
            # maxiter=1 levanta ConvergenceError por diseño
            calc = GPAW(
                str(pbe_gpw),
                txt=txt,
                xc="HSE06",
                kpts={"size": kpts, "gamma": True},
                symmetry={"point_group": True, "time_reversal": True},
                maxiter=1,
            )
            atoms = calc.get_atoms()
            atoms.calc = calc
            try:
                atoms.get_potential_energy()
            except Exception:
                pass
            calc.write(str(out_gpw))

            try:
                from ase.dft.bandgap import bandgap
                gap, p1, p2 = bandgap(calc)
                logger.info("HSE06@PBE (maxiter=1) band gap: %.4f eV  VBM=%s CBM=%s", gap, p1, p2)
            except Exception:
                pass

        # Guardar PBE como out_gpw si ruta nsc_api funcionó (no hay calc HSE06 GPAW)
        if _used_nsc_api and not out_gpw.exists():
            import shutil as _shutil
            _shutil.copy(str(pbe_gpw), str(out_gpw))
            logger.info("hse06_nonscf.gpw es copia de pbe_%s.gpw (fuente de eigenvalores nsc)", kpts_tag)

        logger.info("Non-SCF HSE06 complete: %s", out_gpw)

    def _run_hse06_scissor(self, step_dir: Path) -> None:
        """Scissor correction."""
        import json
        from .bandgap_correction import ScissorCorrection

        out_json = step_dir / "hse06_scissor.json"
        if out_json.exists():
            logger.info("hse06_scissor.json exists, skipping")
            return

        scf_gpw = self._step_dir("scf") / "scf.gpw"
        hse_gpw = step_dir / "hse06.gpw"

        if self.dry_run:
            logger.info("Dry run: would compute scissor correction")
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(f"scf.gpw not found: {scf_gpw}")

        comp_ref = self.factory.config.get("bandgap_reference", {})
        sc = ScissorCorrection(reference=comp_ref, phase=self.phase)

        # Usa literature/YAML pbe_soc value (soc_npy no.gpw - can't pass directly)
        # Usa computed hse06.gpw si it exists, else fall back literature chi_hse
        gpw_hse_arg = str(hse_gpw) if hse_gpw.exists() else None

        result = sc.run_full_correction(
            gpw_pbe=str(scf_gpw),
            gpw_pbe_soc=None,
            gpw_hse=gpw_hse_arg,
            phase=self.phase,
        )
        logger.info(
            "Scissor: Eg(PBE)=%.4f χSOC=%.4f χHSE=%.4f → Eg_corr=%.4f eV  "
            "(exp=%.2f, source: SOC=%s HSE=%s)",
            result.e_pbe_d3, result.chi_soc, result.chi_hse, result.e_corrected,
            result.e_experimental or float("nan"),
            result.chi_soc_source, result.chi_hse_source,
        )
        out_json.write_text(json.dumps({
            "e_pbe_eV": result.e_pbe_d3,
            "chi_soc_eV": result.chi_soc,
            "chi_hse_eV": result.chi_hse,
            "e_corrected_eV": result.e_corrected,
            "e_experimental_eV": result.e_experimental,
            "mae_vs_experiment_eV": result.mae_vs_experiment,
            "chi_soc_source": result.chi_soc_source,
            "chi_hse_source": result.chi_hse_source,
        }, indent=2))

    def _run_soc_hse06(self, step_dir: Path) -> None:
        """Aplica SOC perturbatively HSE06 ground state."""
        import numpy as np
        from gpaw.spinorbit import soc_eigenstates

        hse_dir = self._step_dir("hse06")
        hse_gpw = hse_dir / "hse06.gpw"
        if not hse_gpw.exists():
            hse_gpw = hse_dir / "hse06_nonscf.gpw"  # non-SCF fallback
        done_flag = step_dir / "soc_hse06_eigenvalues.npy"

        if done_flag.exists():
            logger.info("soc_hse06_eigenvalues.npy exists, skipping HSE06+SOC")
            return
        if self.dry_run:
            logger.info("Dry run: would apply SOC to %s", hse_gpw)
            return
        if not hse_gpw.exists():
            raise FileNotFoundError(
                f"HSE06 checkpoint not found: {hse_gpw}. Run step hse06 or hse06_nonscf first."
            )

        soc_cfg = self.factory.config.get("soc", {})
        result = soc_eigenstates(
            str(hse_gpw),
            theta=soc_cfg.get("theta", 0.0),
            phi=soc_cfg.get("phi", 0.0),
        )
        eigs = result.eigenvalues()
        np.save(str(done_flag), eigs)
        np.save(str(step_dir / "soc_hse06_spin_projections.npy"), result.spin_projections())

        # Log gap usa HSE06 Fermi level
        ref = GPAW(str(hse_gpw), txt=None)
        ef = ref.get_fermi_level()
        occupied   = eigs[eigs < ef]
        unoccupied = eigs[eigs >= ef]
        if len(occupied) and len(unoccupied):
            gap = float(unoccupied.min() - occupied.max())
            logger.info("HSE06+SOC band gap: %.4f eV", gap)
        logger.info("HSE06+SOC eigenvalues saved to %s", done_flag)

    def _run_soc_pbe(self, step_dir: Path) -> None:
        """SOC perturbativo sobre estado fundamental PBE.

        Alternativa a _run_soc_hse06() que falla con GPAW 25.7.0 bug
        (HybridXC has no attribute calculate_spherical). Lee scf.gpw en vez
        de hse06.gpw, por lo que es siempre ejecutable después del paso 'scf'.
        Output: soc_pbe_eigenvalues.npy (distinto del soc_eigenvalues.npy de PBE perturbativo
        estándar para evitar colisión).
        """
        from gpaw.spinorbit import soc_eigenstates

        scf_gpw = self._step_dir("scf") / "scf.gpw"
        done_flag = step_dir / "soc_pbe_eigenvalues.npy"

        if done_flag.exists():
            logger.info("soc_pbe_eigenvalues.npy exists, skipping SOC+PBE")
            return
        if self.dry_run:
            logger.info("Dry run: would apply SOC perturbatively to PBE ground state %s", scf_gpw)
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(
                f"SCF checkpoint not found: {scf_gpw}. Run step 'scf' first."
            )

        soc_cfg = self.factory.config.get("soc", {})
        result = soc_eigenstates(
            str(scf_gpw),
            theta=float(soc_cfg.get("theta", 0.0)),
            phi=float(soc_cfg.get("phi", 0.0)),
        )
        eigs = result.eigenvalues()
        np.save(str(done_flag), eigs)
        np.save(str(step_dir / "soc_pbe_spin_projections.npy"), result.spin_projections())

        # Log gap using SCF Fermi level
        ref = GPAW(str(scf_gpw), txt=None)
        ef = ref.get_fermi_level()
        occupied = eigs[eigs < ef]
        unoccupied = eigs[eigs >= ef]
        if len(occupied) and len(unoccupied):
            gap = float(unoccupied.min() - occupied.max())
            logger.info("PBE+SOC (perturbative on PBE ground state) band gap: %.4f eV", gap)
        logger.info("PBE+SOC eigenvalues saved to %s", done_flag)

    def _run_hessian(self, step_dir: Path) -> None:
        """Calcula 3N×3N Hessiano via finite differences en relaxed geometry."""
        from .validation import compute_hessian
        import numpy as np

        relax_gpw = self._step_dir("relax") / "relax.gpw"
        if self.dry_run:
            logger.info("Dry run: would compute Hessian from %s", relax_gpw)
            return
        if not relax_gpw.exists():
            raise FileNotFoundError(f"relax.gpw not found: {relax_gpw}")

        ref_calc = GPAW(str(relax_gpw))
        atoms = ref_calc.get_atoms()

        # symmetry debe be off
        hess_calc = self.factory.create(
            "scf",
            txt=str(step_dir / "hessian.txt"),
            params_override={"symmetry": "off"},
        )
        result = compute_hessian(
            atoms=atoms,
            calc=hess_calc,
            delta=0.01,
            work_dir=step_dir,
        )

        np.save(str(step_dir / "hessian.npy"), result.hessian)
        np.save(str(step_dir / "hessian_eigenvalues.npy"), result.eigenvalues)
        logger.info("Hessian saved. %s", result.summary)

        if result.flags:
            logger.warning("Hessian flags: %s", result.flags)

    def _run_phonons(self, step_dir: Path) -> None:
        """Calcula fonón dispersion - Phonopy o ASE backend selected desde config."""
        import numpy as np

        relax_gpw = self._step_dir("relax") / "relax.gpw"
        ph_cfg = self.factory.config.get("phonons", {})
        method = ph_cfg.get("method", "ase")
        delta = ph_cfg.get("delta", 0.02)
        supercell = tuple(ph_cfg.get("supercell", [2, 2, 2]))
        asr = ph_cfg.get("asr", "crystal")
        scf_conv = ph_cfg.get("scf_convergence", {})
        kpath_npoints = ph_cfg.get("kpath_npoints", 60)

        if self.dry_run:
            logger.info(
                "Dry run: would compute phonons (method=%s, Δ=%.3f Å, supercell=%s)",
                method, delta, supercell,
            )
            return
        if not relax_gpw.exists():
            raise FileNotFoundError(f"relax.gpw not found: {relax_gpw}")

        ref_calc = GPAW(str(relax_gpw))
        atoms = ref_calc.get_atoms()

        if method == "phonopy":
            from .validation.phonons import compute_phonons_phonopy
            logger.info(
                "Phonopy backend: Δ=%.3f Å, supercell=%s, ASR=%s", delta, supercell, asr
            )
            result = compute_phonons_phonopy(
                atoms=atoms,
                calc=None,
                supercell=supercell,
                delta=delta,
                work_dir=step_dir,
                kpath_npoints=kpath_npoints,
                asr=asr,
                scf_convergence=scf_conv,
                factory=self.factory,
            )
        else:
            from .validation import compute_phonons
            # ASE backend
            prim_kpts = self.factory.config["scf"].get("kpts", [6, 6, 6])
            kpts_sc = [max(1, k // n) for k, n in zip(prim_kpts, supercell)]
            phon_calc = self.factory.create(
                "scf",
                txt=str(step_dir / "phonons.txt"),
                params_override={"kpts": kpts_sc, "symmetry": "off"},
            )
            logger.info("ASE backend: Δ=%.3f Å, supercell=%s", delta, supercell)
            result = compute_phonons(
                atoms=atoms,
                calc=phon_calc,
                supercell=supercell,
                delta=delta,
                work_dir=step_dir,
            )

        np.save(str(step_dir / "phonon_frequencies.npy"), result.frequencies_cm1)
        logger.info("Phonons saved. %s", result.summary)

        if result.flags:
            logger.warning("Phonon flags: %s", result.flags)

    def _run_formation_energy(self, step_dir: Path) -> None:
        """Calcula ΔHf = E(CsPbI₃) - E(CsI) - E(PbI₂) per formula unit."""
        import json
        from .analysis.thermodynamic import compute_binary_energies, formation_enthalpy

        scf_gpw = self._step_dir("scf") / "scf.gpw"
        out_json = step_dir / "formation_energy.json"

        if out_json.exists():
            logger.info("formation_energy.json exists, skipping")
            return
        if self.dry_run:
            logger.info("Dry run: would compute ΔHf from %s", scf_gpw)
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(f"SCF checkpoint not found: {scf_gpw}")

        # Carga perovskita total energía per formula unit (5 atoms = 1 f.u.)
        calc = GPAW(str(scf_gpw))
        E_perov = calc.get_potential_energy()
        n_atoms = len(calc.get_atoms())
        calc.__del__()
        n_fu = n_atoms / 5   # alpha
        E_perov_per_fu = E_perov / n_fu

        # Ejecuta binary references
        binary_dir = step_dir / "binaries"
        binary_energies = compute_binary_energies(binary_dir, self.factory)

        result = formation_enthalpy(
            E_perovskite_per_fu=E_perov_per_fu,
            E_binary_A_per_fu=binary_energies["CsI_per_fu"],
            E_binary_B_per_fu=binary_energies["PbI2_per_fu"],
        )

        out_json.write_text(json.dumps({
            "delta_Hf_eV": float(result.delta_Hf_eV),
            "E_perovskite_per_fu_eV": float(result.E_perovskite_eV),
            "E_CsI_per_fu_eV": float(result.E_binary_A_eV),
            "E_PbI2_per_fu_eV": float(result.E_binary_B_eV),
            "stable": bool(result.stable),
            "summary": result.summary,
        }, indent=2))
        logger.info("Formation enthalpy: %s", result.summary)

    def _run_effective_masses(self, step_dir: Path) -> None:
        """Calcula electron/hole effective masses."""
        import json
        from .analysis.electronic import (
            classify_gap_type, compute_effective_masses,
            compute_effective_masses_nscf, compute_effective_masses_soc,
        )
        from .analysis.structural import analyze_perovskite_geometry

        bands_gpw = self._step_dir("bands") / "bands.gpw"
        scf_gpw   = self._step_dir("scf")   / "scf.gpw"
        out_json  = step_dir / "electronic_analysis.json"

        if out_json.exists():
            logger.info("electronic_analysis.json exists, skipping")
            return
        if self.dry_run:
            logger.info("Dry run: would compute effective masses")
            return

        # --- k-point topology: prefer r²SCAN MP-grid k-points from JSON -----------
        # GPAW 25.7.0 MGGA does not support fixdensity, so non-SCF band-path
        # calculations are not possible with r²SCAN. Instead, VBM/CBM k-points are
        # read directly from the SCF Monkhorst-Pack grid stored in r2scan_bandgap.json.
        r2scan_bg_json = self._step_dir("r2scan") / "r2scan_bandgap.json"
        r2scan_gpw     = self._step_dir("r2scan") / "r2scan.gpw"
        vbm_kpt_frac_override: np.ndarray | None = None
        cbm_kpt_frac_override: np.ndarray | None = None

        if r2scan_bg_json.exists():
            try:
                _bg = json.loads(r2scan_bg_json.read_text())
                _vbm_frac = _bg.get("vbm_kpt_frac")
                _cbm_frac = _bg.get("cbm_kpt_frac")
                if _vbm_frac is not None and _cbm_frac is not None:
                    vbm_kpt_frac_override = np.array(_vbm_frac)
                    cbm_kpt_frac_override = np.array(_cbm_frac)
                    logger.info(
                        "VBM/CBM k-points from r²SCAN MP grid: VBM=%s CBM=%s",
                        _vbm_frac, _cbm_frac,
                    )
                else:
                    logger.warning("r2scan_bandgap.json has no fractional k-points — run 'r2scan' step to regenerate")
            except Exception as _e:
                logger.warning("Could not read r²SCAN k-points from JSON: %s — falling back to PBE bands", _e)

        if vbm_kpt_frac_override is not None:
            # Use r²SCAN k-points; build a minimal gap_result compatible object
            from types import SimpleNamespace
            _bg_cached = json.loads(r2scan_bg_json.read_text())
            gap_result = SimpleNamespace(
                gap_type=_bg_cached.get("gap_type", "unknown"),
                gap_eV=float(_bg_cached.get("gap_eV", float("nan"))),
                direct_gap_eV=None,
                vbm_kpt_frac=vbm_kpt_frac_override,
                cbm_kpt_frac=cbm_kpt_frac_override,
                flags=[],
                summary=f"r²SCAN MP-grid gap={_bg_cached.get('gap_eV', '?'):.4g} eV",
            )
        elif r2scan_bg_json.exists():
            # r²SCAN JSON exists but k-points are null → metallic/zero-gap system
            _bg_cached = json.loads(r2scan_bg_json.read_text())
            _gap_ev = float(_bg_cached.get("gap_eV", 0.0))
            logger.warning(
                "r²SCAN gap=%.4f eV with null VBM/CBM k-points (metallic/semi-metal); "
                "effective masses will be NaN", _gap_ev,
            )
            # Compute structural metrics even for metallic systems
            relax_gpw = self._step_dir("relax") / "relax.gpw"
            struct_result = None
            if relax_gpw.exists():
                _calc = GPAW(str(relax_gpw))
                _atoms = _calc.get_atoms()
                _calc.__del__()
                from .analysis.structural import analyze_perovskite_geometry
                struct_result = analyze_perovskite_geometry(_atoms)
            out_dict: dict = {
                "gap_type": _bg_cached.get("gap_type", "unknown"),
                "gap_eV": _gap_ev,
                "direct_gap_eV": None,
                "vbm_kpt_frac": None,
                "cbm_kpt_frac": None,
                "m_e_m0": None,
                "m_h_m0": None,
                "m_reduced_m0": None,
                "m_e_soc_m0": None,
                "m_h_soc_m0": None,
                "m_reduced_soc_m0": None,
                "flags_gap": ["metallic_r2scan"],
                "flags_masses": ["metallic_no_masses"],
                "flags_masses_soc": ["metallic_no_masses"],
            }
            if struct_result is not None:
                out_dict["tolerance_factor"] = struct_result.tolerance_factor
                out_dict["octahedral_factor"] = struct_result.octahedral_factor
                out_dict["mean_bx_bond_Ang"] = struct_result.mean_bx_bond_Ang
                out_dict["bx_bond_variance"] = struct_result.bx_bond_variance
                out_dict["mean_bxb_angle_deg"] = struct_result.mean_bxb_angle_deg
                out_dict["tilt_angle_deg"] = struct_result.tilt_angle_deg
                out_dict["flags_structural"] = struct_result.flags
            out_json.write_text(json.dumps(out_dict, indent=2))
            logger.info("Electronic analysis saved (metallic): gap=%.4f eV", _gap_ev)
            return
        else:
            # Fallback: PBE band path
            if not bands_gpw.exists():
                raise FileNotFoundError(f"No r²SCAN JSON k-points and no PBE bands.gpw: {bands_gpw}")
            gap_result = classify_gap_type(bands_gpw)
            # D1 Fix: M-point bug for cubic structures
            relax_gpw_check = self._step_dir("relax") / "relax.gpw"
            if (
                gap_result.cbm_kpt_frac is not None
                and _is_m_point(np.array(gap_result.cbm_kpt_frac))
                and relax_gpw_check.exists()
                and _is_cubic_structure(relax_gpw_check)
            ):
                logger.warning(
                    "CBM at M=[0.5,0.5,0.0] for cubic structure; forcing R=[0.5,0.5,0.5] (D1 fix)"
                )
                try:
                    gap_result.cbm_kpt_frac = np.array([0.5, 0.5, 0.5])
                    gap_result.vbm_kpt_frac = np.array([0.5, 0.5, 0.5])
                except AttributeError:
                    gap_result = gap_result._replace(
                        cbm_kpt_frac=np.array([0.5, 0.5, 0.5]),
                        vbm_kpt_frac=np.array([0.5, 0.5, 0.5]),
                    )

        # --- Fine-k NSCF effective masses (always PBE SCF — MGGA fixdensity unsupported) ---
        # r²SCAN provides the bandgap; masses are computed at the correct k-point
        # using PBE density (acceptable: masses weakly sensitive to XC near gap edges).
        if scf_gpw.exists() and gap_result.cbm_kpt_frac is not None:
            mass_result = compute_effective_masses_nscf(
                scf_gpw,
                cbm_kpt_frac=gap_result.cbm_kpt_frac,
                vbm_kpt_frac=gap_result.vbm_kpt_frac,
                step_dir=step_dir,
            )
        elif gap_result.cbm_kpt_frac is not None and bands_gpw.exists():
            logger.warning("scf.gpw missing — falling back to band-path effective masses")
            mass_result = compute_effective_masses(bands_gpw)
        else:
            logger.warning("No SCF or band path available for effective masses — using r²SCAN band path")
            mass_result = compute_effective_masses(bands_gpw)

        # SOC-corrected masses
        # triply-degenerate PBE CBM en R splits under SOC giving verdadero light m_e
        fine_gpw = step_dir / "effmass_fine.gpw"
        soc_cfg = self.factory.config.get("soc", {})
        mass_soc: object = None
        if fine_gpw.exists():
            mass_soc = compute_effective_masses_soc(
                fine_gpw,
                n_fit=5,
                theta=float(soc_cfg.get("theta", 0.0)),
                phi=float(soc_cfg.get("phi", 0.0)),
            )
            logger.info("SOC masses: %s", mass_soc.summary)

        # Structural analysis desde relaxed geometry
        relax_gpw = self._step_dir("relax") / "relax.gpw"
        struct_result = None
        if relax_gpw.exists():
            calc = GPAW(str(relax_gpw))
            atoms = calc.get_atoms()
            calc.__del__()
            struct_result = analyze_perovskite_geometry(atoms)

        out_dict = {
            "gap_type": gap_result.gap_type,
            "gap_eV": gap_result.gap_eV,
            "direct_gap_eV": gap_result.direct_gap_eV,
            "vbm_kpt_frac": gap_result.vbm_kpt_frac.tolist() if gap_result.vbm_kpt_frac is not None else None,
            "cbm_kpt_frac": gap_result.cbm_kpt_frac.tolist() if gap_result.cbm_kpt_frac is not None else None,
            "m_e_m0": mass_result.m_e,
            "m_h_m0": mass_result.m_h,
            "m_reduced_m0": mass_result.m_reduced,
            "m_e_soc_m0": mass_soc.m_e if mass_soc else None,
            "m_h_soc_m0": mass_soc.m_h if mass_soc else None,
            "m_reduced_soc_m0": mass_soc.m_reduced if mass_soc else None,
            "flags_gap": gap_result.flags,
            "flags_masses": mass_result.flags,
            "flags_masses_soc": mass_soc.flags if mass_soc else [],
        }
        if struct_result is not None:
            out_dict["tolerance_factor"] = struct_result.tolerance_factor
            out_dict["octahedral_factor"] = struct_result.octahedral_factor
            out_dict["mean_bx_bond_Ang"] = struct_result.mean_bx_bond_Ang
            out_dict["bx_bond_variance"] = struct_result.bx_bond_variance
            out_dict["mean_bxb_angle_deg"] = struct_result.mean_bxb_angle_deg
            out_dict["tilt_angle_deg"] = struct_result.tilt_angle_deg
            out_dict["flags_structural"] = struct_result.flags

        out_json.write_text(json.dumps(out_dict, indent=2))
        logger.info("Electronic analysis saved: %s | %s", gap_result.summary, mass_result.summary)

    def _run_optical(self, step_dir: Path) -> None:
        """Calcula óptico dielectric function ε(ω) y absorption coefficient α(ω)."""
        from .analysis.optical import compute_optical_spectrum

        scf_gpw   = self._step_dir("scf") / "scf.gpw"
        done_flag = step_dir / "optical_frequencies.npy"

        if done_flag.exists():
            logger.info("optical_frequencies.npy exists, skipping optical")
            return
        if self.dry_run:
            logger.info("Dry run: would compute optical spectrum from %s", scf_gpw)
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(f"SCF checkpoint not found: {scf_gpw}")

        opt_cfg = self.factory.config.get("optical", {})

        # Scissor
        scissor_eV = opt_cfg.get("scissor_eV")
        if scissor_eV is None:
            hse_gpw   = self._step_dir("hse06") / "hse06.gpw"
            bands_gpw = self._step_dir("bands") / "bands.gpw"
            if hse_gpw.exists() and bands_gpw.exists():
                try:
                    scissor_eV = _compute_scissor(hse_gpw, bands_gpw)
                    logger.info("Auto scissor correction: %+.3f eV (HSE06 − PBE)", scissor_eV)
                except Exception as exc:
                    logger.warning("Auto scissor failed: %s — running without correction", exc)
        if scissor_eV is None:
            # Fallback
            scissor_json = self._step_dir("hse06") / "hse06_scissor.json"
            if scissor_json.exists():
                import json as _json
                sc_data = _json.loads(scissor_json.read_text())
                scissor_eV = sc_data.get("chi_hse_eV")
                if scissor_eV is not None:
                    logger.info("Scissor from hse06_scissor.json: %+.3f eV", scissor_eV)

        result = compute_optical_spectrum(
            scf_gpw, step_dir,
            omega_max_eV        = opt_cfg.get("omega_max_eV", 6.0),
            d_omega_eV          = opt_cfg.get("d_omega_eV", 0.025),
            eta_eV              = opt_cfg.get("eta_eV", 0.1),
            onset_threshold_cm1 = opt_cfg.get("onset_threshold_cm1", 1e4),
            scissor_eV          = scissor_eV,
            alpha_sample_eV     = tuple(opt_cfg.get("alpha_sample_eV", [1.5, 2.0, 2.5, 3.0])),
        )
        logger.info("Optical spectrum: %s", result.summary)
        if result.flags:
            logger.warning("Optical flags: %s", result.flags)

    def _run_sq_limit(self, step_dir: Path) -> None:
        """Calcula detailed Shockley-Queisser PV efficiency desde DFT α(ω)."""
        import json as _json
        from .analysis.sq_limit import compute_sq_limit
        from .analysis.optical import load_optical_result

        opt_result = load_optical_result(self._step_dir("optical"))
        if opt_result is None:
            raise FileNotFoundError("Run the 'optical' step first — optical_frequencies.npy not found")

        cfg = self.factory.config.get("sq_limit", {})

        # Si óptico data en PBE level (no scissor), use HSE06-corrected onset
        # evita artificially large J_sc/J₀ desde sub-gap PBE absorption
        onset_override: float | None = None
        scissor_json = self._step_dir("hse06") / "hse06_scissor.json"
        if scissor_json.exists():
            import json as _json2
            sc = _json2.loads(scissor_json.read_text())
            pbe_gap = sc.get("e_pbe_eV")
            chi_hse = sc.get("chi_hse_eV")
            if pbe_gap is not None and chi_hse is not None:
                onset_override = float(pbe_gap + chi_hse)
                logger.info(
                    "SQ onset override: PBE(%.3f) + HSE06(%.3f) = %.3f eV",
                    pbe_gap, chi_hse, onset_override,
                )

        result = compute_sq_limit(
            opt_result,
            thickness_nm=cfg.get("thickness_nm", 500.0),
            T_K=cfg.get("T_K", 300.0),
            thickness_scan_nm=cfg.get(
                "thickness_scan_nm", [100, 200, 300, 400, 500, 750, 1000, 2000]
            ),
            onset_eV_override=onset_override,
        )

        np.save(str(step_dir / "generation_rate.npy"), result.generation_x)
        np.save(str(step_dir / "depth_cm.npy"), result.x_cm)

        step_dir.joinpath("sq_limit.json").write_text(_json.dumps({
            "thickness_nm":   result.thickness_nm,
            "jsc_mA_cm2":     result.jsc_mA_cm2,
            "j0_mA_cm2":      result.j0_mA_cm2,
            "voc_V":          result.voc_V,
            "ff":             result.ff,
            "pce_pct":        result.pce_pct,
            "jsc_sq_ideal":   result.jsc_sq_ideal,
            "pce_sq_ideal":   result.pce_sq_ideal,
            "thickness_scan": result.thickness_scan,
            "flags":          result.flags,
        }, indent=2))
        logger.info(
            "SQ limit: J_sc=%.2f mA/cm², V_oc=%.3f V, FF=%.3f, PCE=%.1f%%",
            result.jsc_mA_cm2, result.voc_V, result.ff, result.pce_pct,
        )

    def _run_score(self, step_dir: Path) -> None:
        """Recolecta analisis completos y calcula score solar FV."""
        import json
        from .analysis.scoring import compute_solar_score, exciton_binding_energy
        from .analysis.optical import load_optical_result

        if self.dry_run:
            logger.info("Dry run: recolectaria salidas y calcularia score solar")
            return

        out_json = step_dir / "solar_score.json"
        if out_json.exists():
            logger.info("solar_score.json existe; recalcula")

        # Junta datos disponibles.
        kwargs: dict = {}

        # Analisis electronico: tipo gap + masas.
        # Prefiere masas con SOC; capturan splitting CBM ausente en PBE.
        em_json = self._step_dir("effective_masses") / "electronic_analysis.json"
        if em_json.exists():
            em_data = json.loads(em_json.read_text())
            kwargs["gap_type"] = em_data.get("gap_type")
            kwargs["bandgap_eV"] = em_data.get("gap_eV")
            m_e_soc = em_data.get("m_e_soc_m0")
            m_h_soc = em_data.get("m_h_soc_m0")
            kwargs["m_e"] = m_e_soc if m_e_soc is not None else em_data.get("m_e_m0")
            kwargs["m_h"] = m_h_soc if m_h_soc is not None else em_data.get("m_h_m0")

        # r²SCAN bandgap override (better than PBE, lower priority than HSE06 scissor)
        r2scan_bg_json = self._step_dir("r2scan") / "r2scan_bandgap.json"
        if r2scan_bg_json.exists():
            import json as _json_r2
            r2scan_bg = _json_r2.loads(r2scan_bg_json.read_text())
            old_gap = kwargs.get("bandgap_eV", float("nan"))
            kwargs["bandgap_eV"] = float(r2scan_bg["gap_eV"])
            if "gap_type" in r2scan_bg:
                kwargs["gap_type"] = r2scan_bg["gap_type"]
            logger.info(
                "Score: using r²SCAN gap %.4f eV (overrides PBE %.4f eV)",
                kwargs["bandgap_eV"], old_gap,
            )

        # Scissor HSE06.
        scissor_json = self._step_dir("hse06") / "hse06_scissor.json"
        if scissor_json.exists():
            import json as _json
            sc_data = _json.loads(scissor_json.read_text())
            pbe_gap = sc_data.get("e_pbe_eV")
            chi_hse = sc_data.get("chi_hse_eV")
            if pbe_gap is not None and chi_hse is not None:
                kwargs["bandgap_eV"] = float(pbe_gap + chi_hse)
                logger.info("Gap para score: PBE(%.3f) + HSE06(%.3f) = %.3f eV",
                            pbe_gap, chi_hse, kwargs["bandgap_eV"])

        # Energia formacion.
        fe_json = self._step_dir("formation_energy") / "formation_energy.json"
        if fe_json.exists():
            fe_data = json.loads(fe_json.read_text())
            kwargs["delta_Hf_eV"] = fe_data.get("delta_Hf_eV")

        # Estabilidad fonon.
        ph_npy = self._step_dir("phonons") / "phonon_frequencies.npy"
        if ph_npy.exists():
            import numpy as np
            freqs = np.load(str(ph_npy))
            kwargs["phonon_stable"] = bool(np.all(freqs > -10))

        # Optica.
        opt_result = load_optical_result(self._step_dir("optical"))
        if opt_result is not None:
            kwargs["eps_r"] = opt_result.eps_inf

        # DOS dentro de gap.
        dos_gpw = self._step_dir("dos") / "dos.gpw"
        if dos_gpw.exists():
            try:
                from gpaw import GPAW as _GPAW
                _c = _GPAW(str(dos_gpw), txt=None)
                _ef = _c.get_fermi_level()
                _nk = len(_c.get_bz_k_points())
                _all_eigs = np.array([_c.get_eigenvalues(k) for k in range(_nk)]).flatten()
                _occ = _all_eigs[_all_eigs < _ef]
                _unocc = _all_eigs[_all_eigs >= _ef]
                if len(_occ) and len(_unocc):
                    _vbm = float(_occ.max())
                    _cbm = float(_unocc.min())
                    _gap_win = _cbm - _vbm
                    # Cuenta autovalores dentro de gap (inset 10%).
                    _inset = 0.05 * _gap_win
                    _ingap = _all_eigs[(_all_eigs > _vbm + _inset) & (_all_eigs < _cbm - _inset)]
                    _in_gap_dos = float(len(_ingap)) / _gap_win  # aprox estados/eV
                    kwargs["in_gap_dos"] = _in_gap_dos
                    logger.info(
                        "DOS intra-gap: %d estados en [%.3f, %.3f] eV → %.4f estados/eV",
                        len(_ingap), _vbm + _inset, _cbm - _inset, _in_gap_dos,
                    )
            except Exception as _e:
                logger.warning("Calculo DOS intra-gap fallo: %s", _e)

        score = compute_solar_score(**kwargs)

        # Energia enlace exciton si hay datos.
        if kwargs.get("m_e") and kwargs.get("m_h") and kwargs.get("eps_r"):
            E_b = exciton_binding_energy(kwargs["m_e"], kwargs["m_h"], kwargs["eps_r"])
        else:
            E_b = None

        # SQ limit metrics - informational only, do no affect scoring weights
        pv_metrics: dict = {}
        sq_json = self._step_dir("sq_limit") / "sq_limit.json"
        if sq_json.exists():
            sq_data = json.loads(sq_json.read_text())
            pv_metrics["jsc_mA_cm2"]   = sq_data.get("jsc_mA_cm2")
            pv_metrics["voc_V"]        = sq_data.get("voc_V")
            pv_metrics["ff"]           = sq_data.get("ff")
            pv_metrics["pce_pct"]      = sq_data.get("pce_pct")
            pv_metrics["jsc_sq_ideal"] = sq_data.get("jsc_sq_ideal")
            pv_metrics["pce_sq_ideal"] = sq_data.get("pce_sq_ideal")
            pv_metrics["thickness_nm"] = sq_data.get("thickness_nm")
            logger.info(
                "SQ from file: J_sc=%.2f mA/cm², PCE=%.1f%%",
                pv_metrics["jsc_mA_cm2"] or 0, pv_metrics["pce_pct"] or 0,
            )

        out_json.write_text(json.dumps({
            "total_score": score.total,
            "grade": score.grade,
            "components": {
                "bandgap": score.s_bandgap,
                "gap_type": score.s_gap_type,
                "stability": score.s_stability,
                "transport": score.s_transport,
                "exciton": score.s_exciton,
                "defects": score.s_defects,
            },
            "inputs": {
                "bandgap_eV": score.bandgap_eV,
                "gap_type": score.gap_type,
                "delta_Hf_eV": score.delta_Hf_eV,
                "m_e_m0": score.m_e,
                "m_h_m0": score.m_h,
                "eps_r": score.eps_r,
                "exciton_binding_meV": E_b * 1000 if E_b else None,
            },
            "pv_metrics": pv_metrics if pv_metrics else None,
            "disqualified": score.disqualified,
            "flags": score.flags,
            "summary": score.summary,
        }, indent=2))
        logger.info("PV score: %s", score.summary)

    def _run_oghma_device(self, step_dir: Path) -> None:
        """Prepara opcional OghmaNano dispositivo-simulation inputs."""
        from .analysis.oghma_device import prepare_oghma_device_step

        cfg = self.factory.config.get("oghma_device", {})
        result = prepare_oghma_device_step(
            self.work_dir,
            step_dir,
            phase=self.phase,
            config=cfg,
            dry_run=self.dry_run,
        )
        logger.info("OghmaNano device step: %s", result.to_dict())

    def _run_pes(self, step_dir: Path) -> None:
        """PES scan along soft Hessiano modes."""
        from .analysis.pes import detect_soft_modes, scan_pes_1d
        from .plotting import plot_pes_scan

        hessian_npy = self._step_dir("hessian") / "hessian.npy"
        pes_cfg = self.factory.config.get("pes", {})

        if self.dry_run:
            logger.info("Dry run: would run PES scan from %s", hessian_npy)
            return
        if not hessian_npy.exists():
            raise FileNotFoundError(
                f"hessian.npy not found at {hessian_npy}. Run the 'hessian' step first."
            )

        threshold = pes_cfg.get("soft_mode_threshold_eV_Ang2", 0.05)
        soft_modes = detect_soft_modes(hessian_npy, threshold=threshold)

        if not soft_modes:
            logger.info("No quasi-zero/negative Hessian modes below %.3f eV/Å². PES scan skipped.", threshold)
            (step_dir / "pes_no_soft_modes.flag").touch()
            return

        logger.info("%d quasi-zero/negative mode(s) detected (threshold=%.3f eV/Å²):", len(soft_modes), threshold)
        for idx, lam, _ in soft_modes:
            logger.info("  mode %d: λ = %.4f eV/Å²", idx, lam)

        # Scan softest mode
        mode_idx, lam_soft, evec_soft = soft_modes[0]
        relax_gpw = self._step_dir("relax") / "relax.gpw"
        ref_calc = GPAW(str(relax_gpw))
        atoms = ref_calc.get_atoms()

        scan_dir = step_dir / f"scan_mode{mode_idx}"
        scan_dir.mkdir(parents=True, exist_ok=True)

        result = scan_pes_1d(
            atoms=atoms,
            factory=self.factory,
            eigenvector=evec_soft,
            n_steps=pes_cfg.get("scan_n_steps", 20),
            amplitude=pes_cfg.get("scan_amplitude_Ang", 0.5),
            work_dir=scan_dir,
            mode_index=mode_idx,
            eigenvalue=lam_soft,
            barrier_threshold_meV=pes_cfg.get("double_well_barrier_meV", 10.0),
        )

        np.save(str(step_dir / "pes_energies.npy"), result.energies_eV)
        np.save(str(step_dir / "pes_displacements.npy"), result.displacements_Ang)
        logger.info(
            "PES scan done. Double well: %s (barrier=%.1f meV)",
            result.double_well_detected, result.barrier_meV,
        )

        plot_pes_scan(result, output_path=step_dir / "pes_scan")

        if result.double_well_detected and pes_cfg.get("run_neb_if_double_well", True):
            logger.info(
                "Saddle point detected at Q=%.3f Å — launching CI-NEB", result.saddle_Q_Ang
            )
            from .analysis.neb_workflow import run_cineb
            from .plotting import plot_neb_path

            neb_dir = step_dir / "neb"
            neb_dir.mkdir(exist_ok=True)
            neb_result = run_cineb(
                atoms_start=result.atoms_min1,
                atoms_end=result.atoms_min2,
                factory=self.factory,
                work_dir=neb_dir,
                n_images=pes_cfg.get("neb_n_images", 7),
                fmax=pes_cfg.get("neb_fmax_eV_Ang", 0.10),
                k=pes_cfg.get("neb_spring_constant", 0.10),
            )
            np.save(str(step_dir / "neb_energies.npy"), neb_result.energies_eV)
            logger.info(
                "CI-NEB done. Barrier(fwd)=%.1f meV, Barrier(rev)=%.1f meV, converged=%s",
                neb_result.barrier_forward_meV,
                neb_result.barrier_reverse_meV,
                neb_result.converged,
            )
            plot_neb_path(neb_result, output_path=step_dir / "neb_path")

    def _run_loto(self, step_dir: Path) -> None:
        """Calcula Born effective charges Z* y dielectric tensor ε_∞ para LO-TO splitting."""
        from .validation.phonons import compute_born_charges
        import shutil

        scf_gpw = self._step_dir("scf") / "scf.gpw"
        if self.dry_run:
            logger.info("Dry run: would compute Born charges from %s", scf_gpw)
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(f"SCF checkpoint not found: {scf_gpw}")

        Z_born, eps_inf = compute_born_charges(scf_gpw, work_dir=step_dir)

        # Copy fonones work_dir so Gonze-Lee correction picked up automatically
        phonons_dir = self._step_dir("phonons")
        if phonons_dir.exists():
            shutil.copy(str(step_dir / "born_charges.npy"), str(phonons_dir / "born_charges.npy"))
            shutil.copy(str(step_dir / "dielectric_tensor.npy"), str(phonons_dir / "dielectric_tensor.npy"))
            logger.info("LO-TO files copied to phonons dir. Re-run phonons to apply correction.")

        logger.info(
            "Born charges: mean |Z*| = %.3f, ε_∞ diagonal = %s",
            float(abs(Z_born).mean()),
            list(eps_inf.diagonal().round(3)),
        )

    # Helpers

    def _step_dir(self, step: str) -> Path:
        return self.work_dir / STEP_DIRS[step]

    @staticmethod
    def _check_bfgs_converged(log_path: Path) -> bool:
        """Devuelve True si BFGS log contains convergencia línea."""
        if not log_path.exists():
            return False
        text = log_path.read_text()
        return "Converged" in text or "fmax" in text
