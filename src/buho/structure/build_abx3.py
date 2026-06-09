"""Constructor de estructuras cristalinas ABX3 genéricas.

Reutiliza StructureBuilder de dft_cspbi3 para:
  - Composiciones puras (inorgánicas): cúbica Pm-3m, 5 átomos
  - Composiciones mixtas: supercelda 2×2×2 (40 átomos) con distribución aleatoria

Para A-sites orgánicos (MA, FA):
  - Se sustituye por el placeholder configurado (default: Cs)
  - Se registra en metadata["molecular_A_placeholder"] = True
  - Se añade advertencia explícita en metadata["organic_A_warning"]

Uso:
    builder = ABX3StructureBuilder(config)
    atoms, meta = builder.build(candidate, out_dir=Path("runs/relax_basic/abc123"))
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from buho.generator.heuristic_generator import GeneratedCandidate

ORGANIC_A = {"MA", "FA"}
_ORG_WARNING = (
    "Estructura usa catión orgánico simplificado en posición A. "
    "Reemplazar con geometría molecular explícita antes de DFT de producción."
)


class ABX3StructureBuilder:
    """Construye estructuras ASE para candidatos ABX3 generados.

    Parámetros
    ----------
    config : dict con sección "structure" del YAML del generador
    random_seed : semilla para distribución de especies en superceldas
    """

    def __init__(self, config: dict, random_seed: int = 42):
        st = config.get("structure", {})
        self._supercell_pure: list[int] = list(st.get("supercell_pure", [1, 1, 1]))
        self._supercell_mixed: list[int] = list(st.get("supercell_mixed", [2, 2, 2]))
        self._organic_placeholder: str = st.get("organic_A_placeholder", "Cs")
        self._formats: list[str] = list(st.get("export_formats", ["cif", "poscar", "traj"]))
        self._seed = random_seed

    def build(
        self,
        candidate: GeneratedCandidate,
        out_dir: Optional[Path] = None,
        export: bool = True,
    ) -> tuple:
        """Construye la estructura y opcionalmente la exporta.

        Returns
        -------
        (atoms, metadata)  — ASE Atoms y dict con información del candidato
        """
        from ase.build import make_supercell
        from dft_cspbi3.structure_builder import StructureBuilder
        from ml_surrogate.features import lattice_est, IONIC_RADII

        is_mixed = (
            len(candidate.A_site_species) > 1
            or len(candidate.B_site_species) > 1
            or len(candidate.X_site_species) > 1
        )
        has_organic = candidate.is_organic_A

        # ── Determine structural A/B/X for crystal building ──────────────────
        # Para A: usar placeholder si hay catión orgánico
        if has_organic:
            A_struct = self._organic_placeholder
        else:
            A_struct = candidate.A_site_species[0]  # caso puro o usaremos primera

        B_struct = candidate.B_site_species[0]

        X_struct = candidate.X_site_species[0]

        # ── Lattice constant ─────────────────────────────────────────────────
        r_B_eff = sum(
            candidate.fractions["B"][sp] * IONIC_RADII[sp]
            for sp in candidate.B_site_species
        )
        r_X_eff = sum(
            candidate.fractions["X"][sp] * IONIC_RADII[sp]
            for sp in candidate.X_site_species
        )
        a0 = lattice_est(r_B_eff, r_X_eff)

        # ── Build primitive cell ─────────────────────────────────────────────
        atoms = StructureBuilder.build_perovskite_cubic(A_struct, B_struct, X_struct, a0)

        # ── Supercell ────────────────────────────────────────────────────────
        sc = self._supercell_mixed if is_mixed else self._supercell_pure
        if sc != [1, 1, 1]:
            import numpy as np
            sc_matrix = np.diag(sc)
            atoms = make_supercell(atoms, sc_matrix)

        # ── Distribute mixed species ─────────────────────────────────────────
        if is_mixed:
            atoms = self._distribute_mixed_species(atoms, candidate, sc)

        n_atoms = len(atoms)

        # ── Metadata ─────────────────────────────────────────────────────────
        metadata = {
            "candidate_id": candidate.candidate_id,
            "formula": candidate.formula,
            "reduced_formula": candidate.reduced_formula,
            "generation_mode": candidate.generation_mode,
            "A_site_species": candidate.A_site_species,
            "B_site_species": candidate.B_site_species,
            "X_site_species": candidate.X_site_species,
            "fractions": candidate.fractions,
            "molecular_A_placeholder": has_organic,
            "organic_A_warning": _ORG_WARNING if has_organic else None,
            "lattice_constant_A": round(a0, 4),
            "supercell": sc,
            "n_atoms": n_atoms,
            "tolerance_t": candidate.tolerance_t,
            "oct_factor": candidate.oct_factor,
            "random_seed": self._seed,
            "build_date": datetime.utcnow().isoformat() + "Z",
        }

        if out_dir is not None and export:
            self.export(atoms, Path(out_dir), metadata)

        return atoms, metadata

    def export(self, atoms, out_dir: Path, metadata: dict) -> None:
        """Exporta estructura en los formatos configurados."""
        out_dir.mkdir(parents=True, exist_ok=True)

        if "cif" in self._formats:
            atoms.write(str(out_dir / "structure.cif"))

        if "poscar" in self._formats:
            atoms.write(str(out_dir / "POSCAR"), format="vasp")

        if "traj" in self._formats:
            from ase.io.trajectory import Trajectory
            with Trajectory(str(out_dir / "structure.traj"), "w") as traj:
                traj.write(atoms)

        (out_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, default=str)
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _distribute_mixed_species(self, atoms, candidate: GeneratedCandidate, sc: list):
        """Distribuye especies mezcladas en los sitios de la supercelda."""
        import numpy as np
        from ase import Atoms

        rng = np.random.RandomState(self._seed)
        symbols = list(atoms.get_chemical_symbols())
        positions = atoms.get_positions()
        cell = atoms.get_cell()

        # Identify site indices by original element (pre-supercell first species)
        # A-site: was A_struct; B-site: was B_struct; X-site: was X_struct
        A_struct = self._organic_placeholder if candidate.is_organic_A else candidate.A_site_species[0]
        B_struct = candidate.B_site_species[0]
        X_struct = candidate.X_site_species[0]

        A_idxs = [i for i, s in enumerate(symbols) if s == A_struct]
        B_idxs = [i for i, s in enumerate(symbols) if s == B_struct]
        X_idxs = [i for i, s in enumerate(symbols) if s == X_struct]

        def _ase_symbol(sp: str) -> str:
            """Convierte especie a símbolo ASE válido (organics → placeholder)."""
            return self._organic_placeholder if sp in ORGANIC_A else sp

        def _assign(idxs, species_list, fracs):
            if len(species_list) <= 1:
                return
            total = len(idxs)
            counts = []
            remaining = total
            for i, sp in enumerate(species_list[:-1]):
                n = int(round(fracs[sp] * total))
                n = min(n, remaining)
                counts.append(n)
                remaining -= n
            counts.append(remaining)

            shuffled = idxs.copy()
            rng.shuffle(shuffled)
            offset = 0
            for sp, n in zip(species_list, counts):
                ase_sp = _ase_symbol(sp)
                for idx in shuffled[offset:offset + n]:
                    symbols[idx] = ase_sp
                offset += n

        if len(candidate.A_site_species) > 1:
            _assign(A_idxs, candidate.A_site_species, candidate.fractions["A"])

        if len(candidate.B_site_species) > 1:
            _assign(B_idxs, candidate.B_site_species, candidate.fractions["B"])

        if len(candidate.X_site_species) > 1:
            _assign(X_idxs, candidate.X_site_species, candidate.fractions["X"])

        new_atoms = Atoms(
            symbols=symbols,
            positions=positions,
            cell=cell,
            pbc=True,
        )
        new_atoms.info.update(atoms.info)
        return new_atoms
