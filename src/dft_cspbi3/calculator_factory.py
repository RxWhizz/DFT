"""Factory calculadoras GPAW desde YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from ase import Atoms
from ase.dft.kpoints import bandpath

CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "default_params.yaml"

# Valid cálculo types
CALC_TYPES = ("relax", "relax_sym", "scf", "bands", "dos", "soc", "hse06", "scan", "r2scan")


def _load_config(config_path: str | Path = CONFIG_PATH) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh)


def _gpaw_symbols():
    """Importa GPAW tarde; tests pueden parchear."""
    import gpaw

    mixer_sum = getattr(gpaw, "MixerSum", None)
    if mixer_sum is None:
        try:
            from gpaw.mixer import MixerSum as mixer_sum
        except Exception:
            mixer_sum = gpaw.Mixer
    return gpaw.GPAW, gpaw.Mixer, gpaw.PW, mixer_sum


class GPAWCalculatorFactory:
    """Crea calculadoras GPAW desde YAML."""

    def __init__(self, config_path: str | Path = CONFIG_PATH) -> None:
        self.config = _load_config(config_path)
        self._paw = self.config.get("paw_datasets", {})

    # Public API

    def create(
        self,
        calc_type: str,
        atoms: Atoms | None = None,
        params_override: dict[str, Any] | None = None,
        txt: str = "gpaw_output.txt",
    ) -> Any:
        """Devuelve calculadora GPAW configurada."""
        if calc_type not in CALC_TYPES:
            raise ValueError(f"Unknown calc_type '{calc_type}'. Choose from {CALC_TYPES}")

        builders = {
            "relax": self._relax_params,
            "relax_sym": self._relax_sym_params,
            "scf": self._scf_params,
            "bands": lambda: self._bands_params(atoms),
            "dos": self._dos_params,
            "soc": self._soc_params,
            "hse06": self._hse06_params,
            "scan": self._scan_params,
            "r2scan": self._r2scan_params,
        }
        kwargs = builders[calc_type]()
        kwargs["txt"] = txt
        kwargs.setdefault("parallel", {"domain": 1})
        # r²SCAN uses Hubbard U corrections when dft_u is configured
        use_u = calc_type == "r2scan"
        kwargs.setdefault("setups", self._paw_setups_u() if use_u else self._paw_setups())

        if params_override:
            kwargs.update(params_override)

        GPAW, _, _, _ = _gpaw_symbols()
        return GPAW(**kwargs)

    # Private builders

    def _paw_setups(self) -> dict[str, str]:
        """Mapea simbolos a datasets PAW."""
        return {sym: dataset for sym, dataset in self._paw.items()}

    def _paw_setups_u(self) -> dict[str, str]:
        """PAW datasets + correcciones Hubbard U (Dudarev) desde config dft_u.
        GPAW syntax: ':s,3.5' → U=3.5 eV en orbital s (Dudarev scheme).
        """
        base = dict(self._paw_setups())
        for element, u_cfg in self.config.get("dft_u", {}).items():
            orbital = u_cfg.get("orbital", "d")
            u_ev = float(u_cfg.get("u_ev", 0.0))
            if u_ev > 0:
                base[element] = f":{orbital},{u_ev}"
        return base

    def _relax_sym_params(self) -> dict:
        """Parámetros para relajación sym-constrained.
        Lee de config['relax_sym'] (PBE XC — datasets disponibles para C/N/H del catión FA).
        """
        _, Mixer, PW, _ = _gpaw_symbols()
        p = self.config.get("relax_sym", self.config["relax"])
        mixer_cfg = p.get("mixer", {})
        sym = p.get("symmetry", "on")
        params = {
            "mode": PW(p.get("ecut", 450)),
            "xc": p.get("xc", "PBE"),
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
        }
        # 'off' is the only valid GPAW symmetry string; omitting the key uses the default (on)
        if sym not in ("on", True):
            params["symmetry"] = "off"
        return params

    def _relax_params(self) -> dict:
        _, Mixer, PW, _ = _gpaw_symbols()
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
        _, _, PW, _ = _gpaw_symbols()
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
        _, _, PW, _ = _gpaw_symbols()
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
        _, _, PW, _ = _gpaw_symbols()
        p = self.config["dos"]
        return {
            "mode": PW(self.config["scf"].get("ecut", 450)),
            "xc": self.config["scf"].get("xc", "PBEsol"),
            "kpts": {"size": p.get("kpts", [12, 12, 12]), "gamma": True},
            "convergence": {"energy": 1e-8},
            "occupations": {"name": "fermi-dirac", "width": 0.05},
        }

    def _soc_params(self) -> dict:
        """SOC usa base SCF."""
        return self._scf_params()

    def _hse06_params(self) -> dict:
        _, _, PW, MixerSum = _gpaw_symbols()
        p = self.config["hse06"]
        mixer_cfg = p.get("mixer", {})
        conv_cfg = p.get("convergence", {})
        occ_cfg = p.get("occupations", {})
        params: dict = {
            "mode": PW(p.get("ecut", 450)),
            "xc": {"name": "HSE06", "omega": p.get("omega", 0.11)},
            "kpts": {"size": p.get("kpts", [2, 2, 2]), "gamma": True},
            "convergence": {
                "energy": conv_cfg.get("energy", 1e-6),
                "eigenstates": conv_cfg.get("eigenstates", 1e-4),
                "density": conv_cfg.get("density", 1e-4),
            },
            # width=0.01 eV
            # Para metales o sistemas con degeneración HOMO-LUMO usar 0.05-0.10 eV
            "occupations": {
                "name": occ_cfg.get("name", "fermi-dirac"),
                "width": occ_cfg.get("width", 0.01),
            },
            # MixerSum (MSR1)
            # beta=0.01 asegura actualizaciones lentas que estabilizan potencial
            # intercambio exacto Fock entre ciclos SCF en HSE06
            # nmaxold=8
            "mixer": MixerSum(
                beta=mixer_cfg.get("beta", 0.01),
                nmaxold=mixer_cfg.get("nmaxold", 8),
                weight=mixer_cfg.get("weight", 50.0),
            ),
            # Paralelización
            # intercambio exacto es embarazosamente paralelo sobre k
            "parallel": {"domain": (1, 1, 1)},
        }
        # nbands
        # valor entero explícito se usa directamente
        # Se necesitan al menos 20-30 % bandas vacías extra para estabilizar
        # operador Fock y evitar fallos eigensolver en HSE06
        nbands_cfg = p.get("nbands")
        if nbands_cfg is not None and nbands_cfg != "auto":
            params["nbands"] = int(nbands_cfg)
        niter = p.get("eigensolver_niter")
        if niter:
            from gpaw.eigensolvers import Davidson
            params["eigensolver"] = Davidson(niter=int(niter))
        return params

    def _scan_params(self) -> dict:
        _, _, PW, _ = _gpaw_symbols()
        p = self.config["scan"]
        occ = p.get("occupations", {})
        conv = p.get("convergence", {})
        return {
            "mode": PW(p.get("ecut", 450)),
            "xc": "SCAN",
            "kpts": {"size": p.get("kpts", [6, 6, 6]), "gamma": True},
            "convergence": {
                "energy": conv.get("energy", 1e-6),
                "eigenstates": conv.get("eigenstates", 1e-8),
                "density": conv.get("density", 1e-6),
            },
            "occupations": {
                "name": occ.get("name", "fermi-dirac"),
                "width": occ.get("width", 0.05),
            },
        }

    def _r2scan_params(self) -> dict:
        from gpaw.eigensolvers import Davidson
        _, Mixer, PW, _ = _gpaw_symbols()
        p = self.config["r2scan"]
        occ = p.get("occupations", {})
        conv = p.get("convergence", {})
        mixer_cfg = p.get("mixer", {})
        backend = mixer_cfg.get("backend", "pulay")

        # msr1 and similar backends must be passed as a dict (resolved via
        # get_mixer_from_keywords internally by GPAW); Pulay/Broyden can use objects.
        legacy_backends = {"pulay", "broyden", "fft"}
        if backend in legacy_backends:
            if backend == "broyden":
                from gpaw.mixer import BroydenMixer
                MixerCls = BroydenMixer
            else:
                MixerCls = Mixer
            mixer: dict | object = MixerCls(
                beta=mixer_cfg.get("beta", 0.05),
                nmaxold=mixer_cfg.get("nmaxold", 8),
                weight=mixer_cfg.get("weight", 100.0),
            )
        else:
            mixer = {k: v for k, v in mixer_cfg.items()}

        params = {
            "mode": PW(p.get("ecut", 450)),
            "xc": p.get("xc", "MGGA_X_R2SCAN+MGGA_C_R2SCAN"),
            "kpts": {"size": p.get("kpts", [6, 6, 6]), "gamma": True},
            "convergence": {
                "energy": conv.get("energy", 1e-5),
                "eigenstates": conv.get("eigenstates", 1e-6),
                "density": conv.get("density", 1e-4),
            },
            "occupations": {
                "name": occ.get("name", "fermi-dirac"),
                "width": occ.get("width", 0.05),
            },
            "eigensolver": Davidson(niter=3),
            "mixer": mixer,
        }
        if p.get("maxiter") is not None:
            params["maxiter"] = int(p["maxiter"])
        return params
