"""Genera methodology.md: metodologia cientifica."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional


def generate_methodology(
    params: Optional[dict] = None,
    output_dir: str | Path = "./reports",
    filename: str = "methodology.md",
) -> Path:
    """Escribe methodology.md; devuelve ruta."""
    params = params or {}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    xc = params.get("xc", "PBEsol")
    ecut = params.get("ecut_eV", 450)
    kpts = params.get("kpts", [6, 6, 6])
    kstr = f"{kpts[0]}×{kpts[1]}×{kpts[2]}"
    soc_mode = params.get("soc_mode", "perturbative (spinorbit_eigenvalues)")
    phase = params.get("phase", "CsPbI₃")

    content = f"""\
# Metodologia computacional

*{phase} — flujo DFT con GPAW/ASE*
*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

---

## 1. Marco teorico

### 1.1 DFT Kohn-Sham

Calculos electronicos usan formulacion Kohn-Sham (KS) de DFT
[Hohenberg & Kohn, 1964; Kohn & Sham, 1965]. Energia electronica total
se minimiza respecto a densidad ρ(r):

    E[ρ] = Ts[ρ] + ∫ v_ext(r)ρ(r)dr + E_H[ρ] + E_xc[ρ]

Ts = energia cinetica no interactuante. E_H = Hartree. E_xc =
intercambio-correlacion. Ecuaciones KS autoconsistentes:

    (-½∇² + v_eff(r)) ψᵢ(r) = εᵢ ψᵢ(r)

Se resuelven hasta converger densidad y energia bajo umbral.

### 1.2 Aproximacion Born-Oppenheimer

Nucleos = clasicos bajo Born-Oppenheimer (BO). Problema electronico se
resuelve para cada geometria fija. Resultado: superficie E(R). Optimizacion
minimiza |∇_R E(R)|. Propiedades vibracionales (Hessian, phonon) = segundas
derivadas de E(R).

---

## 2. Funcional intercambio-correlacion

**Funcional**: {xc}

{xc} se usa en relajacion estructural y calculos SCF. {_xc_note(xc)}

**Limites conocidos**:
- PBE/PBEsol subestima bandgap ~0.3-0.8 eV en perovskitas haluro.
- SOC de Pb 6p reduce gap KS ~0.84 eV.
- Scissor: Eg_corr = E_PBE + χSOC + χHSE.

---

## 3. Metodo PAW

Densidades electronicas usan PAW [Blöchl, 1994] en GPAW. Datasets:

| Elemento | Dataset | Electrones valencia |
|----------|---------|--------------------|
| Cs      | Cs.9.PBE       | 9 (5s²5p⁶6s¹)    |
| Pb      | Pb.14.PBE      | 14 (5d¹⁰6s²6p²)  |
| I       | I.7.PBE        | 7 (5s²5p⁵)        |

Pb.14.PBE incluye semicore 5d. Necesario para SOC preciso: hibridacion 5d-6p.

---

## 4. Base ondas planas y corte

**Modo**: PW (ondas planas)
**Energia corte**: Ecut = {ecut} eV

Funciones KS se expanden en ondas planas:

    ψᵢₖ(r) = Σ_G cᵢₖ(G) exp(i(k+G)·r)

G recorre vectores reciprocos con |k+G|² < 2Ecut (Hartree). Corte sale de
pruebas de convergencia (`validation_report.md`): ΔE < 1 meV/atom.

---

## 5. Muestreo k

**Malla**: {kstr} Monkhorst-Pack centrada en Γ

Zona Brillouin usa malla Monkhorst-Pack uniforme. Malla Γ sirve con simetria
inversion temporal. DOS usa malla mas densa: {kstr} → 12×12×12.

Ocupaciones: smearing Fermi-Dirac 0.05 eV (≈ 580 K). Menor que bandgap.
SCF suave; error termico en estado base bajo.

---

## 6. Optimizacion geometrica

Posiciones atomicas relajan con BFGS en ASE. Parada:

    max |F_i| < {params.get('fmax', 0.01)} eV/Å

Celda queda fija en valores experimento/referencia. Mixer β = 0.05 estabiliza
SCF en atomos pesados.

---

## 7. Acoplamiento spin-orbita (SOC)

**Modo**: {soc_mode}

SOC se incluye perturbativamente con `spinorbit_eigenvalues()` de GPAW:

    H_SOC = (ħ/4m²c²) σ · (∇V × p)

Correccion relativista de primer orden sobre autoestados KS colineales.
Valido si SOC no domina frente a campo cristalino. Pb 6p: error ~0.05 eV.

χSOC = Eg(SOC) − Eg(PBE). Se guarda separado para sumar correccion hibrida.

---

## 8. Correccion bandgap (scissor)

PBE subestima gap. SOC lo reduce mas. Correccion:

    Eg_corrected = Eg(PBE+D3) + χSOC + χHSE

donde:
- χSOC = Eg(PBE+SOC) − Eg(PBE)   [tipico −0.84 eV en CsPbI₃]
- χHSE = Eg(HSE06) − Eg(PBE)      [tipico +0.32 eV en CsPbI₃]

Evita costo O(N³) de HSE06+SOC autoconsistente. Error tipico vs experimento:
~0.1-0.2 eV.

---

## 9. Propiedades vibracionales

### 9.1 Matriz Hessian

Hessian H por diferencias finitas centrales en fuerzas:

    H_{{ij}} ≈ -(F_i(R + Δê_j) - F_i(R - Δê_j)) / (2Δ)

Δ = 0.01 Å. Simetrizacion H → (H + Hᵀ)/2 quita asimetria numerica.
Autovalores ≥ 0 → minimo estable.

### 9.2 Dispersion phonon

Frecuencias phonon usan desplazamientos finitos en supercelda. Constantes
C(R) salen de calculos GPAW desplazados. Luego Fourier → matriz dinamica D(q):

    ω²(q) = autovalores de D(q) = autovalores de [C(q) / √(MᵢMⱼ)]

Regla suma acustica quita deriva translacional. Frecuencias imaginarias
(ω² < 0) → inestabilidad dinamica.

---

## 10. Software

| Componente | Versión |
|------------|---------|
| GPAW      | ≥ 24.1.0 |
| ASE       | ≥ 3.23.0 |
| NumPy     | ≥ 1.26   |
| Python    | ≥ 3.11   |

Calculos reproducibles desde `configs/default_params.yaml` y `structures/`.
"""

    # No pisa resultados expandidos.
    # Plantilla no regenera datos phonon reales.
    if out_path.exists():
        existing = out_path.read_text(encoding="utf-8")
        if "### 9.3 Phonon Dispersion" in existing or "Results and Discussion" in existing:
            return out_path

    out_path.write_text(content, encoding="utf-8")
    return out_path


def _xc_note(xc: str) -> str:
    notes = {
        "PBEsol": (
            "PBEsol = PBE revisado para solidos cristalinos (Perdew et al., 2008). "
            "Constantes de red y energia cohesiva mejoran vs PBE. "
            "Energias de atomizacion molecular bajan algo."
        ),
        "PBE": (
            "PBE (Perdew-Burke-Ernzerhof, 1996) = GGA comun. "
            "Suele sobreestimar constantes de red ~1-2% en solidos."
        ),
        "HSE06": (
            "HSE06 = hybrid/hibrido separado por rango. Mezcla 25% Hartree-Fock "
            "a corto alcance (ω = 0.11 Bohr⁻¹). Bandgap mejora vs GGA. "
            "Costo ↑ ~10-50×."
        ),
    }
    return notes.get(xc, "")
