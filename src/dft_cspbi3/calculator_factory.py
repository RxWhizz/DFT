"""Factory for GPAW calculator objects configured from YAML parameter sets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from ase import Atoms
from ase.dft.kpoints import bandpath
from gpaw import GPAW, Mixer, PW

CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "default_params.yaml"

# Valid calculation types
CALC_TYPES = ("relax", "scf", "bands", "dos", "soc", "hse06")


def _load_config(config_path: str | Path = CONFIG_PATH) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh)


class GPAWCalculatorFactory:
    """Create GPAW calculator objects from a YAML configuration file.

    Usage::

        factory = GPAWCalculatorFactory()
        calc = factory.create("relax")
        atoms.calc = calc
    """

    def __init__(self, config_path: str | Path = CONFIG_PATH) -> None:
        self.config = _load_config(config_path)
        self._paw = self.config.get("paw_datasets", {})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(
        self,
        calc_type: str,
        atoms: Atoms | None = None,
        params_override: dict[str, Any] | None = None,
        txt: str = "gpaw_output.txt",
    ) -> GPAW:
        """Return a configured GPAW calculator.

        Args:
            calc_type: One of 'relax', 'scf', 'bands', 'dos', 'soc', 'hse06'.
            atoms: Required for 'bands' (needed to generate BandPath).
            params_override: Dict of GPAW kwargs to override defaults.
            txt: Output filename for GPAW log.
        """
        if calc_type not in CALC_TYPES:
            raise ValueError(f"Unknown calc_type '{calc_type}'. Choose from {CALC_TYPES}")

        builders = {
            "relax": self._relax_params,
            "scf": self._scf_params,
            "bands": lambda: self._bands_params(atoms),
            "dos": self._dos_params,
            "soc": self._soc_params,
            "hse06": self._hse06_params,
        }
        kwargs = builders[calc_type]()
        kwargs["txt"] = txt
        kwargs["parallel"] = {"domain": 1}
        kwargs.setdefault("setups", self._paw_setups())

        if params_override:
            kwargs.update(params_override)

        return GPAW(**kwargs)

    # ------------------------------------------------------------------
    # Private builders
    # ------------------------------------------------------------------

    def _paw_setups(self) -> dict[str, str]:
        """Map element symbols to PAW dataset names."""
        return {sym: dataset for sym, dataset in self._paw.items()}

    def _relax_params(self) -> dict:
        p = self.config["relax"]
        mixer_cfg = p.get("mixer", {})
        return {
            "mode": PW(p.get("ecut", 450)),
            "xc": p.get("xc", "PBEsol"),
            "kpts": {"size": p.get("kpts", [6, 6, 6]), "gamma": True},
            "convergence": {
                "energy": p["convergence"].get("energy", 1e-6),
                "forces": p["convergence"].get("forces", 0.01),
            },
            "mixer": Mixer(
                beta=mixer_cfg.get("beta", 0.05),
                nmaxold=5,
                weight=50.0,
            ),
            "maxiter": p.get("maxiter", 333),
            "symmetry": "on" if p.get("symmetry", "on") == "on" else "off",
        }

    def _scf_params(self) -> dict:
        p = self.config["scf"]
        occ = p.get("occupations", {})
        return {
            "mode": PW(p.get("ecut", 450)),
            "xc": p.get("xc", "PBEsol"),
            "kpts": {"size": p.get("kpts", [6, 6, 6]), "gamma": True},
            "convergence": {"energy": p["convergence"].get("energy", 1e-8)},
            "occupations": {
                "name": occ.get("name", "fermi-dirac"),
                "width": occ.get("width", 0.05),
            },
        }

    def _bands_params(self, atoms: Atoms | None) -> dict:
        p = self.config["bands"]
        if atoms is None:
            raise ValueError("atoms must be provided for calc_type='bands'")
        kpts_path = p.get("kpts_path", "XRMGR")
        npoints = p.get("npoints", 40)
        path = atoms.cell.bandpath(kpts_path, npoints=npoints)
        return {
            "mode": PW(self.config["scf"].get("ecut", 450)),
            "xc": self.config["scf"].get("xc", "PBEsol"),
            "kpts": path,
            "fixdensity": True,
            "symmetry": "off",
            "convergence": {"bands": p["convergence"].get("bands", -10)},
        }

    def _dos_params(self) -> dict:
        p = self.config["dos"]
        return {
            "mode": PW(self.config["scf"].get("ecut", 450)),
            "xc": self.config["scf"].get("xc", "PBEsol"),
            "kpts": {"size": p.get("kpts", [12, 12, 12]), "gamma": True},
            "convergence": {"energy": 1e-8},
            "occupations": {"name": "fermi-dirac", "width": 0.05},
        }

    def _soc_params(self) -> dict:
        """SOC uses same setup as SCF; SOC applied post-SCF via spinorbit_eigenvalues()."""
        return self._scf_params()

    def _hse06_params(self) -> dict:
        p = self.config["hse06"]
        mixer_cfg = p.get("mixer", {})
        return {
            "mode": PW(p.get("ecut", 450)),
            "xc": "HSE06",  # omega=0.11 Bohr⁻¹ is HSE06 default; dict form rejected by this GPAW version
            "kpts": {"size": p.get("kpts", [3, 3, 3]), "gamma": True},
            "convergence": {"energy": p["convergence"].get("energy", 1e-6)},
            "occupations": {"name": "fermi-dirac", "width": 0.05},
            "mixer": Mixer(
                beta=mixer_cfg.get("beta", 0.05),
                nmaxold=mixer_cfg.get("nmaxold", 5),
                weight=mixer_cfg.get("weight", 50.0),
            ),
        }
