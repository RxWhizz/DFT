"""Surrogate ML configuration dataclass + YAML loading."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class SurrogateConfig:
    # ── Feature set
    base_features: List[str] = field(default_factory=lambda: [
        "r_A", "r_B", "r_X",
        "chi_A", "chi_B", "chi_X",
        "q_A", "q_B", "q_X",
        "tolerance_t", "oct_factor",
        "a_lat_est_A", "vol_est_A3",
        "delta_chi_BX", "mu_BX",
        "is_organic_A",
    ])
    optional_features: List[str] = field(default_factory=lambda: [
        "a_lat_mp_A",       # from MP or MACE relaxation
        "E_mace_eV_atom",   # MACE total energy/atom
        "band_gap_gga_eV",  # GGA bandgap (MP or DFT)
        "Eform_eV_atom",    # formation energy
    ])

    # ── Model
    model_type: str = "ensemble"       # "rf" | "gbr" | "mlp" | "ensemble"
    n_estimators: int = 200
    max_depth: int = 4                 # conservative for small datasets
    min_samples_leaf: int = 2
    random_state: int = 42

    # ── Uncertainty
    n_bootstrap: int = 100
    uncertainty_method: str = "bootstrap"   # "bootstrap" | "ensemble_std"
    confidence_level: float = 0.90

    # ── Training
    target_col: str = "Eg_target_eV"
    test_size: float = 0.2
    cv_folds: int = 5                  # LOO when n_samples <= 10

    # ── Paths (relative to project root)
    training_data: str = "data/surrogate_training.csv"
    model_dir: str = "models"
    model_name: str = "surrogate_bandgap"
    predictions_db: str = "calculations/top8_r2scan/surrogate_cache.sqlite"

    @property
    def model_path(self) -> Path:
        root = Path(os.environ.get("BUHO_ROOT", Path(__file__).resolve().parents[2]))
        return root / self.model_dir / f"{self.model_name}.pkl"

    @property
    def training_data_path(self) -> Path:
        root = Path(os.environ.get("BUHO_ROOT", Path(__file__).resolve().parents[2]))
        return root / self.training_data

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SurrogateConfig":
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        cfg = cls()
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg

    def to_yaml(self, path: str | Path) -> None:
        import yaml, dataclasses
        d = {k: v for k, v in dataclasses.asdict(self).items()}
        Path(path).write_text(yaml.dump(d, default_flow_style=False))
