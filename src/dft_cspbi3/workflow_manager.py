"""Orchestrate multi-step DFT workflows: relax → scf → bands → dos → soc → vibrational."""

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
from gpaw.mixer import MixerSum

from .calculator_factory import GPAWCalculatorFactory
from .structure_builder import StructureBuilder

logger = logging.getLogger(__name__)


def _compute_scissor(hse_gpw: Path, bands_gpw: Path) -> float:
    """Return Eg(HSE06) − Eg(PBE) as scissor shift in eV."""
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
    "relax", "scf", "bands", "dos", "soc",
    "scan",               # SCAN meta-GGA SCF — mejor gap que PBE sin HSE06
    "scan_soc",           # SCAN + SOC autoconsistente (spinors=True, 2-componentes Pauli)
    "soc_scan",           # SOC perturbativo sobre SCAN (PBE-proxy augmentation)
    "r2scan",             # r²SCAN meta-GGA SCF — SCAN regularizado, mejor convergencia
    "soc_r2scan",         # SOC perturbativo sobre r²SCAN (PBE-proxy augmentation)
    "hse06",
    "hse06_nonscf",       # non-SCF HSE06@PBE: fixed density, converge eigenstates only
    "soc_hse06",          # SOC applied post-HSE06 (requires hse06.gpw or hse06_nonscf.gpw)
    "hse06_scissor",      # scissor correction: χSOC (computed) + χHSE (lit. fallback)
    "hessian", "phonons", "pes", "loto",
    "formation_energy",   # ΔHf from binary references (CsI + PbI₂ single-points)
    "effective_masses",   # parabolic fit from existing bands.gpw — no new GPAW
    "optical",            # RPA dielectric function → ε(ω), α(ω)
    "sq_limit",           # detailed Shockley-Queisser limit from α(ω)
    "oghma_device",       # optional OghmaNano device-physics handoff (not ML)
    "score",              # composite PV solar score from all collected data
]
STEP_DIRS = {
    "relax": "01_relax",
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


class DFTWorkflow:
    """Orchestrate a multi-step GPAW DFT workflow for a given crystal phase.

    Each step runs in its own subdirectory and checkpoints to .gpw files so
    that interrupted workflows can be resumed.

    Args:
        phase: Crystal phase name ('alpha'/'gamma'/'delta' for CsPbI3, or any name).
        config_path: Path to default_params.yaml.
        composition_config: Path to a composition YAML (structures, bandgap refs).
                            If None, falls back to the value in default_params.yaml.
        work_dir: Root directory for all calculation subdirectories.
        dry_run: If True, prepare input files without executing GPAW.
    """

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, steps: Sequence[str] = ("relax", "scf", "bands", "dos", "soc")) -> None:
        """Execute the requested steps in order."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        ordered = [s for s in STEP_ORDER if s in steps]
        for step in ordered:
            logger.info("Starting step: %s", step)
            self._start_time[step] = datetime.now()
            step_dir = self._step_dir(step)
            step_dir.mkdir(parents=True, exist_ok=True)

            try:
                runner = getattr(self, f"_run_{step}")
                runner(step_dir)
                self._completed[step] = True
                logger.info("Completed step: %s", step)
            except Exception as exc:
                logger.error("Step %s failed: %s", step, exc)
                raise

    def get_status(self) -> None:
        """Print a table of completed / pending steps."""
        print(f"\n{'Step':<12} {'Dir':<20} {'Status':<12} {'GPW file'}")
        print("-" * 65)
        for step in STEP_ORDER:
            step_dir = self._step_dir(step)
            done_file = step_dir / STEP_DONE_FILES.get(step, f"{step}.gpw")
            status = "DONE" if done_file.exists() else ("PENDING" if not self._completed[step] else "DONE")
            print(f"{step:<12} {str(step_dir.name):<20} {status:<12} {done_file.name if done_file.exists() else '-'}")

    def check_convergence(self, step: str) -> bool:
        """Check whether a completed step is converged by inspecting its log."""
        step_dir = self._step_dir(step)
        if step == "relax":
            log = step_dir / "relax.log"
            return self._check_bfgs_converged(log)
        done_file = step_dir / STEP_DONE_FILES.get(step, f"{step}.gpw")
        return done_file.exists()

    # ------------------------------------------------------------------
    # Step runners
    # ------------------------------------------------------------------

    def _run_relax(self, step_dir: Path) -> None:
        gpw_out = step_dir / "relax.gpw"
        if gpw_out.exists():
            logger.info("relax.gpw exists, skipping relaxation")
            return

        atoms = StructureBuilder.load_phase(self.phase)
        calc = self.factory.create("relax", txt=str(step_dir / "relax.txt"))
        atoms.calc = calc

        if self.dry_run:
            write(str(step_dir / "initial_structure.cif"), atoms)
            logger.info("Dry run: wrote initial_structure.cif")
            return

        opt = BFGS(
            atoms,
            trajectory=str(step_dir / "relax.traj"),
            logfile=str(step_dir / "relax.log"),
        )
        opt.run(fmax=self.factory.config["relax"]["convergence"]["forces"])
        calc.write(str(gpw_out))
        write(str(step_dir / "relaxed.cif"), atoms)

    def _run_scf(self, step_dir: Path) -> None:
        gpw_out = step_dir / "scf.gpw"
        if gpw_out.exists():
            logger.info("scf.gpw exists, skipping SCF")
            return

        relax_gpw = self._step_dir("relax") / "relax.gpw"
        if self.dry_run:
            logger.info("Dry run: would run SCF from %s", relax_gpw)
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
        calc.write(str(gpw_out), 'all')   # 'all' saves wavefunctions — required by DielectricFunction

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

        # Load the reference atoms for band path generation
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
        """Apply SOC perturbatively using spinorbit_eigenvalues() on an SCF .gpw."""
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
        """SCAN meta-GGA SCF — mejor aproximación al gap que PBE, sin HSE06."""
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
        """SCAN + SOC autoconsistente — NOT supported in GPAW 25.7.0.

        GPAW raises 'Only LDA supported for SC Non-collinear calculations' for
        any non-LDA XC when experimental={'soc': True} is set. This method logs
        the limitation and falls back to reporting the SCAN gap with the additive
        PBE SOC correction.
        """
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
            # PBE+SOC gap: perturbative SOC doubles the bands; each of the N electrons
            # fills one spinor level, so occupied = N (not N/2).
            nval = int(c_pbe.get_number_of_electrons())
            # eigenvalues shape: (nkpts, nbands*2) after SOC doubling
            # Use the stored array; gap = min(CBM) - max(VBM)
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
        """SOC perturbativo sobre el estado fundamental SCAN.

        GPAW 25.7.0 no implementa calculate_spherical para MGGA (SCAN), que es
        necesario para el término de augmentación PAW en soc_eigenstates.
        Workaround: sustituir temporalmente la XC por PBE solo para esa función.
        El SOC está dominado por el gradiente del potencial de Coulomb nuclear;
        la contribución XC a la augmentación es ~10-20% del total, y PBE ≈ SCAN
        en la región del núcleo.
        """
        from gpaw.spinorbit import soc_eigenstates
        from gpaw.xc import XC as _XC
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

        # Proxy: replace SCAN xc with PBE only for the PAW augmentation SOC call
        _orig_xc = calc.hamiltonian.xc
        calc.hamiltonian.xc = _XC("PBE")
        try:
            soc_cfg = self.factory.config.get("soc", {})
            result = soc_eigenstates(
                calc,
                n2=nb,
                theta=soc_cfg.get("theta", 0.0),
                phi=soc_cfg.get("phi", 0.0),
            )
        finally:
            calc.hamiltonian.xc = _orig_xc

        eigs = result.eigenvalues()
        np.save(str(done_flag), eigs)
        np.save(str(step_dir / "soc_scan_spin_projections.npy"), result.spin_projections())

        # Gap: SOC doubles bands; ne electrons fill ne spinor levels
        vbm = float(np.max(eigs[:, ne - 1]))
        cbm = float(np.min(eigs[:, ne]))
        gap = cbm - vbm
        logger.info(
            "SCAN+SOC (PBE-proxy augmentation) band gap: %.4f eV  VBM=%.4f  CBM=%.4f",
            gap, vbm, cbm,
        )
        logger.info("SCAN+SOC eigenvalues saved to %s", done_flag)

    def _run_r2scan(self, step_dir: Path) -> None:
        """r²SCAN meta-GGA SCF. Arranca desde relax.gpw."""
        from ase.dft.bandgap import bandgap
        gpw_out = step_dir / "r2scan.gpw"
        if gpw_out.exists():
            logger.info("r2scan.gpw exists, skipping")
            return

        relax_gpw = self.work_dir / "01_relax" / "relax.gpw"
        if self.dry_run:
            logger.info("Dry run: would run r²SCAN from %s", relax_gpw)
            return
        if not relax_gpw.exists():
            raise FileNotFoundError("relax.gpw not found. Run step 'relax' first.")

        calc = self.factory.create("r2scan", txt=str(step_dir / "r2scan.txt"))
        atoms = GPAW(str(relax_gpw), txt=None).get_atoms()
        atoms.calc = calc
        atoms.get_potential_energy()
        calc.write(str(gpw_out))

        gap, p1, p2 = bandgap(calc)
        logger.info("r²SCAN band gap: %.4f eV  VBM=%s CBM=%s", gap, p1, p2)

    def _run_soc_r2scan(self, step_dir: Path) -> None:
        """SOC perturbativo sobre r²SCAN con PBE-proxy para augmentación PAW."""
        from gpaw.spinorbit import soc_eigenstates
        from gpaw.xc import XC as _XC
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

        _orig_xc = calc.hamiltonian.xc
        calc.hamiltonian.xc = _XC("PBE")
        try:
            soc_cfg = self.factory.config.get("soc", {})
            result = soc_eigenstates(
                calc,
                n2=nb,
                theta=soc_cfg.get("theta", 0.0),
                phi=soc_cfg.get("phi", 0.0),
            )
        finally:
            calc.hamiltonian.xc = _orig_xc

        eigs = result.eigenvalues()
        np.save(str(done_flag), eigs)
        np.save(str(step_dir / "soc_r2scan_spin_projections.npy"), result.spin_projections())

        vbm = float(np.max(eigs[:, ne - 1]))
        cbm = float(np.min(eigs[:, ne]))
        gap = cbm - vbm
        logger.info(
            "r²SCAN+SOC (PBE-proxy augmentation) band gap: %.4f eV  VBM=%.4f  CBM=%.4f",
            gap, vbm, cbm,
        )
        logger.info("r²SCAN+SOC eigenvalues saved to %s", done_flag)

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

        # Auto-compute nbands = int(n_occ * 1.3) from SCF electron count.
        # Extra empty bands (≥20-30% of occupied) stabilise the Fock operator and
        # prevent eigensolver failures when the Davidson subspace is too small.
        nbands_override: int | None = None
        nbands_cfg = hse_cfg.get("nbands", "auto")
        if nbands_cfg == "auto":
            if scf_gpw.exists():
                _ref = GPAW(str(scf_gpw), txt=None)
                n_occ = int(_ref.get_number_of_electrons()) // 2  # spin-paired
                # n_occ + 50% extra vacías: el factor 1.3 aplicado al TOTAL daría solo 6
                # vacías para n_occ=22; con +50% se obtienen 11 vacías — suficiente para
                # que la corrección de Fock en la banda de conducción esté convergida
                nbands_override = n_occ + int(n_occ * 0.5)
                logger.info("HSE06 nbands auto: n_occ=%d → nbands=%d (+50%% vacías)", n_occ, nbands_override)
        elif isinstance(nbands_cfg, int):
            nbands_override = nbands_cfg

        if checkpoint.exists():
            logger.info("Resuming HSE06 from checkpoint: %s", checkpoint)
            # MixerSum (MSR1): mezcla densidad total con beta conservador para
            # estabilizar el potencial de intercambio exacto entre ciclos SCF.
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
        """Non-self-consistent HSE06@PBE: fix PBE density, converge eigenstates only.

        Loads the converged PBE wavefunction from scf.gpw, applies the HSE06
        Hamiltonian with the density permanently frozen (niter_fixdensity=9999).
        Only the eigenstates are converged under the fixed Fock potential built
        from the PBE orbitals. Avoids SCF oscillation entirely and runs in
        minutes. Standard approach for perovskite HSE06 band gaps in the literature.
        """
        out_gpw = step_dir / "hse06_nonscf.gpw"
        if out_gpw.exists():
            logger.info("hse06_nonscf.gpw exists, skipping")
            return

        scf_gpw = self._step_dir("scf") / "scf.gpw"
        if self.dry_run:
            logger.info("Dry run: would run non-SCF HSE06 from %s", scf_gpw)
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(f"SCF checkpoint not found: {scf_gpw}")

        txt = str(step_dir / "hse06_nonscf.txt")
        hse_cfg = self.factory.config.get("hse06", {})
        kpts = hse_cfg.get("kpts", [2, 2, 2])
        kpts_tag = "x".join(str(k) for k in kpts)

        # Step 1: converge PBE at the HSE06 k-mesh.
        # scf.gpw uses a denser mesh (6x6x6); loading it with a different
        # k-mesh reinitialises wavefunctions randomly, making a one-shot
        # HSE06 unreliable. A short PBE run at the target mesh (~minutes)
        # gives physically correct starting orbitals.
        pbe_gpw = step_dir / f"pbe_{kpts_tag}.gpw"
        if not pbe_gpw.exists():
            ref = GPAW(str(scf_gpw), txt=None)
            atoms_ref = ref.get_atoms()
            # nbands: "auto" → int(n_occ * 1.3); entero → usar directamente; None → GPAW default
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
                logger.info("PBE@%s nbands=%d (auto: n_occ=%d × 1.3)", kpts_tag, _nbands_pbe, _n_occ)
            calc_pbe = GPAW(**pbe_kwargs)
            atoms_ref.calc = calc_pbe
            atoms_ref.get_potential_energy()
            # 'all' guarda las funciones de onda (psit_nG) — requerido por
            # non_self_consistent_eigenvalues para calcular ⟨ψ|vxc|ψ⟩
            calc_pbe.write(str(pbe_gpw), mode="all")
            logger.info("PBE@%s converged: %s", kpts_tag, pbe_gpw)

        # Step 2: aplica corrección HSE06 no autoconsistente sobre los autovalores PBE.
        # Ruta principal: non_self_consistent_eigenvalues (gpaw.hybrids.eigenvalues).
        #   eig_hse = eig_pbe − vxc_pbe + vxc_hse
        # Es más ligera que maxiter=1 (sin reconstruir la densidad) y evita el error
        # de convergencia que maxiter=1 lanza por diseño.
        # Ruta fallback: maxiter=1 (una evaluación Fock + rediagonalización).
        _used_nsc_api = False
        try:
            from gpaw.hybrids.eigenvalues import non_self_consistent_eigenvalues

            # Pasar objeto GPAW con txt= para que la corrida quede registrada en el log
            _calc_for_nsc = GPAW(str(pbe_gpw), txt=txt)
            eig_pbe, vxc_pbe, vxc_hse = non_self_consistent_eigenvalues(
                _calc_for_nsc,
                xcname="HSE06",
            )
            eig_hse = eig_pbe - vxc_pbe + vxc_hse   # shape: (nspins, nk, nbands)
            np.save(str(step_dir / "hse06_nsc_eigenvalues.npy"), eig_hse)
            _used_nsc_api = True
            logger.info(
                "non_self_consistent_eigenvalues HSE06 complete — saved hse06_nsc_eigenvalues.npy"
            )

            # Log band gap from corrected eigenvalues
            _ref_pbe = _calc_for_nsc
            _ef = _ref_pbe.get_fermi_level()
            _eigs_flat = eig_hse.flatten()
            _occ = _eigs_flat[_eigs_flat < _ef]
            _unocc = _eigs_flat[_eigs_flat >= _ef]
            if len(_occ) and len(_unocc):
                _gap_nsc = float(_unocc.min() - _occ.max())
                logger.info("HSE06 non-SCF (eigenvalue correction) band gap: %.4f eV", _gap_nsc)
        except Exception as _exc:
            logger.warning(
                "non_self_consistent_eigenvalues failed (%s) — falling back to maxiter=1", _exc
            )

        if not _used_nsc_api:
            # Fallback: one-shot HSE06 — 1 Fock eval on PBE orbitals + 1 diagonalisation.
            # maxiter=1 levanta ConvergenceError por diseño; el resultado es válido.
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

        # Guardar el PBE como out_gpw si la ruta nsc_api funcionó (no hay calc HSE06 GPAW)
        if _used_nsc_api and not out_gpw.exists():
            import shutil as _shutil
            _shutil.copy(str(pbe_gpw), str(out_gpw))
            logger.info("hse06_nonscf.gpw es copia de pbe_%s.gpw (fuente de eigenvalores nsc)", kpts_tag)

        logger.info("Non-SCF HSE06 complete: %s", out_gpw)

    def _run_hse06_scissor(self, step_dir: Path) -> None:
        """Scissor correction: χSOC (computed) + χHSE (literature fallback).

        Uses ScissorCorrection to compute Eg(HSE06+SOC) without running a
        converged HSE06 SCF. χHSE defaults to literature value (~0.67 eV)
        when hse06.gpw is absent. Result saved as hse06_scissor.json.
        """
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

        # Use literature/YAML pbe_soc value (soc_npy is not a .gpw — can't pass directly)
        # Use computed hse06.gpw if it exists, else fall back to literature chi_hse
        gpw_hse_arg = str(hse_gpw) if hse_gpw.exists() else None

        result = sc.run_full_correction(
            gpw_pbe=str(scf_gpw),
            gpw_pbe_soc=None,   # reads pbe_soc from YAML reference
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
        """Apply SOC perturbatively to the HSE06 ground state.

        Requires hse06.gpw or hse06_nonscf.gpw (run step hse06 or hse06_nonscf first).
        Produces soc_hse06_eigenvalues.npy in the SOC step directory.
        Expected gap: HSE06 ~1.7 eV → HSE06+SOC ~1.35–1.45 eV (closer to exp. 1.73 eV).
        """
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

        # Log gap using the HSE06 Fermi level
        ref = GPAW(str(hse_gpw), txt=None)
        ef = ref.get_fermi_level()
        occupied   = eigs[eigs < ef]
        unoccupied = eigs[eigs >= ef]
        if len(occupied) and len(unoccupied):
            gap = float(unoccupied.min() - occupied.max())
            logger.info("HSE06+SOC band gap: %.4f eV", gap)
        logger.info("HSE06+SOC eigenvalues saved to %s", done_flag)

    def _run_hessian(self, step_dir: Path) -> None:
        """Compute the 3N×3N Hessian via finite differences on the relaxed geometry."""
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

        # symmetry must be off: finite displacements break crystal symmetry
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
        """Compute phonon dispersion — Phonopy or ASE backend selected from config."""
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
            # ASE backend: create a single shared calculator
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
        """Compute ΔHf = E(CsPbI₃) - E(CsI) - E(PbI₂) per formula unit.

        Runs two binary single-point SCF calculations (CsI rock salt + PbI₂ CdI₂)
        using the same xc/ecut as the main workflow. Results in formation_energy.json.
        """
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

        # Load perovskite total energy per formula unit (5 atoms = 1 f.u.)
        calc = GPAW(str(scf_gpw))
        E_perov = calc.get_potential_energy()
        n_atoms = len(calc.get_atoms())
        calc.__del__()
        n_fu = n_atoms / 5   # alpha: 5 atoms/f.u.
        E_perov_per_fu = E_perov / n_fu

        # Run binary references
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
        """Compute electron/hole effective masses.

        Gap type is read from the existing bands.gpw k-path.
        Effective masses are computed via a dedicated fine k-path non-SCF
        GPAW calculation (fixdensity=True, dk=0.005 Å⁻¹) around the CBM/VBM.
        This avoids the ~4× too-coarse resolution of the standard band path.
        """
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
            logger.info("Dry run: would compute effective masses from %s", bands_gpw)
            return
        if not bands_gpw.exists():
            raise FileNotFoundError(f"Bands checkpoint not found: {bands_gpw}")

        gap_result = classify_gap_type(bands_gpw)

        # Use fine non-SCF k-path around CBM/VBM when SCF gpw is available;
        # fall back to band-path fit (coarser) otherwise.
        if scf_gpw.exists() and gap_result.cbm_kpt_frac is not None:
            mass_result = compute_effective_masses_nscf(
                scf_gpw,
                cbm_kpt_frac=gap_result.cbm_kpt_frac,
                vbm_kpt_frac=gap_result.vbm_kpt_frac,
                step_dir=step_dir,
            )
        else:
            logger.warning("scf.gpw missing — falling back to band-path effective masses")
            mass_result = compute_effective_masses(bands_gpw)

        # SOC-corrected masses: apply soc_eigenstates to the existing fine k-path gpw.
        # The triply-degenerate PBE CBM at R splits under SOC giving the true light m_e.
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

        # Structural analysis from relaxed geometry
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
        """Compute optical dielectric function ε(ω) and absorption coefficient α(ω).

        Uses GPAW's linear response (RPA) at q→0. Reads from existing SCF checkpoint.
        Typical cost: 1–4 h for 5-atom cell with 6×6×6 k-mesh.

        Scissor correction: if scissor_eV is null in config, auto-detects the
        HSE06−PBE gap difference once hse06.gpw is available.
        """
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

        # Scissor: explicit value from config takes priority; otherwise auto-detect
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
            # Fallback: read chi_hse_eV from pre-computed hse06_scissor.json
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
        """Compute detailed Shockley-Queisser PV efficiency from DFT α(ω).

        Reads optical data from the optical step, applies Würfel detailed balance
        to compute J_sc, J₀, V_oc, FF, PCE for a range of film thicknesses.
        Also computes the classical ideal SQ limit (infinite thickness, step at Eg).
        Saves sq_limit.json, generation_rate.npy, depth_cm.npy.
        """
        import json as _json
        from .analysis.sq_limit import compute_sq_limit
        from .analysis.optical import load_optical_result

        opt_result = load_optical_result(self._step_dir("optical"))
        if opt_result is None:
            raise FileNotFoundError("Run the 'optical' step first — optical_frequencies.npy not found")

        cfg = self.factory.config.get("sq_limit", {})

        # If optical data is at PBE level (no scissor), use HSE06-corrected onset
        # to avoid artificially large J_sc/J₀ from sub-gap PBE absorption
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
        """Collect all completed analyses and compute composite PV solar score."""
        import json
        from .analysis.scoring import compute_solar_score, exciton_binding_energy
        from .analysis.optical import load_optical_result

        out_json = step_dir / "solar_score.json"
        if out_json.exists():
            logger.info("solar_score.json exists, re-computing (always refreshes)")

        # Gather available data
        kwargs: dict = {}

        # Electronic analysis (gap type + effective masses)
        # Prefer SOC-corrected masses (m_e_soc_m0 / m_h_soc_m0) when available;
        # they capture the CBM splitting that PBE-only misses.
        em_json = self._step_dir("effective_masses") / "electronic_analysis.json"
        if em_json.exists():
            em_data = json.loads(em_json.read_text())
            kwargs["gap_type"] = em_data.get("gap_type")
            kwargs["bandgap_eV"] = em_data.get("gap_eV")
            m_e_soc = em_data.get("m_e_soc_m0")
            m_h_soc = em_data.get("m_h_soc_m0")
            kwargs["m_e"] = m_e_soc if m_e_soc is not None else em_data.get("m_e_m0")
            kwargs["m_h"] = m_h_soc if m_h_soc is not None else em_data.get("m_h_m0")

        # HSE06 scissor: best available gap = PBE + HSE06 correction (closer to experiment)
        scissor_json = self._step_dir("hse06") / "hse06_scissor.json"
        if scissor_json.exists():
            import json as _json
            sc_data = _json.loads(scissor_json.read_text())
            pbe_gap = sc_data.get("e_pbe_eV")
            chi_hse = sc_data.get("chi_hse_eV")
            if pbe_gap is not None and chi_hse is not None:
                kwargs["bandgap_eV"] = float(pbe_gap + chi_hse)
                logger.info("Gap for scoring: PBE(%.3f) + HSE06(%.3f) = %.3f eV",
                            pbe_gap, chi_hse, kwargs["bandgap_eV"])

        # Formation energy
        fe_json = self._step_dir("formation_energy") / "formation_energy.json"
        if fe_json.exists():
            fe_data = json.loads(fe_json.read_text())
            kwargs["delta_Hf_eV"] = fe_data.get("delta_Hf_eV")

        # Phonon stability
        ph_npy = self._step_dir("phonons") / "phonon_frequencies.npy"
        if ph_npy.exists():
            import numpy as np
            freqs = np.load(str(ph_npy))
            kwargs["phonon_stable"] = bool(np.all(freqs > -10))

        # Optical: ε∞
        opt_result = load_optical_result(self._step_dir("optical"))
        if opt_result is not None:
            kwargs["eps_r"] = opt_result.eps_inf

        # In-gap DOS: compute from dos.gpw eigenvalues if available
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
                    # Count eigenvalues in the gap interior (10% inset)
                    _inset = 0.05 * _gap_win
                    _ingap = _all_eigs[(_all_eigs > _vbm + _inset) & (_all_eigs < _cbm - _inset)]
                    _in_gap_dos = float(len(_ingap)) / _gap_win  # rough states/eV
                    kwargs["in_gap_dos"] = _in_gap_dos
                    logger.info(
                        "In-gap DOS: %d states in [%.3f, %.3f] eV → %.4f states/eV",
                        len(_ingap), _vbm + _inset, _cbm - _inset, _in_gap_dos,
                    )
            except Exception as _e:
                logger.warning("In-gap DOS computation failed: %s", _e)

        score = compute_solar_score(**kwargs)

        # Exciton binding energy (if data available)
        if kwargs.get("m_e") and kwargs.get("m_h") and kwargs.get("eps_r"):
            E_b = exciton_binding_energy(kwargs["m_e"], kwargs["m_h"], kwargs["eps_r"])
        else:
            E_b = None

        # SQ limit metrics — informational only, do not affect scoring weights
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
        """Prepare optional OghmaNano device-simulation inputs.

        OghmaNano is a GUI-first device-physics solver, not an ML model. By
        default this step writes a DFT-derived device package and parses an
        existing `sim_info.dat` if a validated Oghma project has been run.
        """
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
        """PES scan along soft Hessian modes; CI-NEB if a double well is detected."""
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

        # Scan the softest mode
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
        """Compute Born effective charges Z* and dielectric tensor ε_∞ for LO-TO splitting.

        Results are saved as born_charges.npy and dielectric_tensor.npy in step_dir.
        If the phonons step has already been run, copies these files to the phonons
        work_dir so that compute_phonons() will apply the Gonze-Lee correction on
        the next phonons run.
        """
        from .validation.phonons import compute_born_charges
        import shutil

        scf_gpw = self._step_dir("scf") / "scf.gpw"
        if self.dry_run:
            logger.info("Dry run: would compute Born charges from %s", scf_gpw)
            return
        if not scf_gpw.exists():
            raise FileNotFoundError(f"SCF checkpoint not found: {scf_gpw}")

        Z_born, eps_inf = compute_born_charges(scf_gpw, work_dir=step_dir)

        # Copy to phonons work_dir so Gonze-Lee correction is picked up automatically
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _step_dir(self, step: str) -> Path:
        return self.work_dir / STEP_DIRS[step]

    @staticmethod
    def _check_bfgs_converged(log_path: Path) -> bool:
        """Return True if BFGS log contains a convergence line."""
        if not log_path.exists():
            return False
        text = log_path.read_text()
        return "Converged" in text or "fmax" in text
