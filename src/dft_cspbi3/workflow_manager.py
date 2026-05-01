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
    "relax", "scf", "bands", "dos", "soc", "hse06",
    "soc_hse06",          # SOC applied post-HSE06 (requires hse06.gpw)
    "hessian", "phonons", "pes", "loto",
    "formation_energy",   # ΔHf from binary references (CsI + PbI₂ single-points)
    "effective_masses",   # parabolic fit from existing bands.gpw — no new GPAW
    "optical",            # RPA dielectric function → ε(ω), α(ω)
    "score",              # composite PV solar score from all collected data
]
STEP_DIRS = {
    "relax": "01_relax",
    "scf": "02_scf",
    "bands": "03_bands",
    "dos": "04_dos",
    "soc": "05_soc",
    "hse06": "06_hse06",
    "soc_hse06": "05_soc",   # outputs into same soc dir (different filename)
    "hessian": "07_vibrational/hessian",
    "phonons": "07_vibrational/phonons",
    "pes": "07_vibrational/pes",
    "loto": "08_loto",
    "formation_energy": "09_formation_energy",
    "effective_masses": "10_effective_masses",
    "optical": "11_optical",
    "score": "12_score",
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
            gpw = step_dir / f"{step}.gpw"
            status = "DONE" if gpw.exists() else ("PENDING" if not self._completed[step] else "DONE")
            print(f"{step:<12} {str(step_dir.name):<20} {status:<12} {gpw.name if gpw.exists() else '-'}")

    def check_convergence(self, step: str) -> bool:
        """Check whether a completed step is converged by inspecting its log."""
        step_dir = self._step_dir(step)
        if step == "relax":
            log = step_dir / "relax.log"
            return self._check_bfgs_converged(log)
        gpw = step_dir / f"{step}.gpw"
        return gpw.exists()

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
        calc.write(str(gpw_out))

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

        if checkpoint.exists():
            logger.info("Resuming HSE06 from checkpoint: %s", checkpoint)
            mixer_cfg = self.factory.config.get("hse06", {}).get("mixer", {})
            mixer = Mixer(
                beta=mixer_cfg.get("beta", 0.05),
                nmaxold=mixer_cfg.get("nmaxold", 5),
                weight=mixer_cfg.get("weight", 50.0),
            )
            calc = GPAW(str(checkpoint), txt=txt, mixer=mixer)
            atoms = calc.get_atoms()
        else:
            if not scf_gpw.exists():
                raise FileNotFoundError(f"SCF checkpoint not found: {scf_gpw}")
            calc = self.factory.create("hse06", txt=txt)
            ref_calc = GPAW(str(scf_gpw))
            atoms = ref_calc.get_atoms()
            ref_calc.__del__()

        calc.attach(calc.write, 5, str(checkpoint), mode="all")
        atoms.calc = calc
        atoms.get_potential_energy()
        calc.write(str(gpw_out))
        checkpoint.unlink(missing_ok=True)

    def _run_soc_hse06(self, step_dir: Path) -> None:
        """Apply SOC perturbatively to the HSE06 ground state.

        Requires hse06.gpw to exist (run step 06 first).
        Produces soc_hse06_eigenvalues.npy in the SOC step directory.
        Expected gap: HSE06 ~1.7 eV → HSE06+SOC ~1.35–1.45 eV (closer to exp. 1.73 eV).
        """
        import numpy as np
        from gpaw.spinorbit import soc_eigenstates

        hse_gpw   = self._step_dir("hse06") / "hse06.gpw"
        done_flag = step_dir / "soc_hse06_eigenvalues.npy"

        if done_flag.exists():
            logger.info("soc_hse06_eigenvalues.npy exists, skipping HSE06+SOC")
            return
        if self.dry_run:
            logger.info("Dry run: would apply SOC to %s", hse_gpw)
            return
        if not hse_gpw.exists():
            raise FileNotFoundError(
                f"HSE06 checkpoint not found: {hse_gpw}. Run step 06 first."
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

        # Log gap estimate
        ef = float(np.median(eigs.flatten()))
        occupied   = eigs[eigs < ef]
        unoccupied = eigs[eigs >= ef]
        if len(occupied) and len(unoccupied):
            gap = float(unoccupied.min() - occupied.max())
            logger.info("HSE06+SOC band gap estimate: %.4f eV", gap)
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
        """Compute electron/hole effective masses from existing bands.gpw.

        No new GPAW calculation needed — reads eigenvalues from the bands step
        and fits a parabola near the CBM and VBM.
        """
        import json
        from .analysis.electronic import classify_gap_type, compute_effective_masses
        from .analysis.structural import analyze_perovskite_geometry
        from ase.io import read

        bands_gpw = self._step_dir("bands") / "bands.gpw"
        out_json = step_dir / "electronic_analysis.json"

        if out_json.exists():
            logger.info("electronic_analysis.json exists, skipping")
            return
        if self.dry_run:
            logger.info("Dry run: would compute effective masses from %s", bands_gpw)
            return
        if not bands_gpw.exists():
            raise FileNotFoundError(f"Bands checkpoint not found: {bands_gpw}")

        gap_result = classify_gap_type(bands_gpw)
        mass_result = compute_effective_masses(bands_gpw)

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
            "flags_gap": gap_result.flags,
            "flags_masses": mass_result.flags,
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

        # Band gap from SOC result
        soc_dir = self._step_dir("soc")
        soc_npy = soc_dir / "soc_eigenvalues.npy"
        if soc_npy.exists():
            try:
                import numpy as np
                eigs = np.load(str(soc_npy))
                # Approximate gap from eigenvalue array (sorted)
                ef_approx = np.median(eigs.flatten())
                occupied = eigs[eigs < ef_approx]
                unoccupied = eigs[eigs >= ef_approx]
                if len(occupied) and len(unoccupied):
                    kwargs["bandgap_eV"] = float(unoccupied.min() - occupied.max())
            except Exception:
                pass

        # Electronic analysis (gap type + effective masses)
        em_json = self._step_dir("effective_masses") / "electronic_analysis.json"
        if em_json.exists():
            em_data = json.loads(em_json.read_text())
            kwargs["gap_type"] = em_data.get("gap_type")
            if kwargs.get("bandgap_eV") is None:
                kwargs["bandgap_eV"] = em_data.get("gap_eV")
            kwargs["m_e"] = em_data.get("m_e_m0")
            kwargs["m_h"] = em_data.get("m_h_m0")

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

        # Optical: ε∞, absorption score
        opt_result = load_optical_result(self._step_dir("optical"))
        if opt_result is not None:
            kwargs["eps_r"]        = opt_result.eps_inf
            kwargs["optical_score"] = opt_result.visible_absorption_score

        score = compute_solar_score(**kwargs)

        # Exciton binding energy (if data available)
        if kwargs.get("m_e") and kwargs.get("m_h") and kwargs.get("eps_r"):
            E_b = exciton_binding_energy(kwargs["m_e"], kwargs["m_h"], kwargs["eps_r"])
        else:
            E_b = None

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
            "disqualified": score.disqualified,
            "flags": score.flags,
            "summary": score.summary,
        }, indent=2))
        logger.info("PV score: %s", score.summary)

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
