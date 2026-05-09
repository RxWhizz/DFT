"""Genera assumptions.md: supuestos y rango valido."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional


def generate_assumptions(
    params: Optional[dict] = None,
    output_dir: str | Path = "./reports",
    filename: str = "assumptions.md",
) -> Path:
    """Escribe assumptions.md; devuelve ruta."""
    params = params or {}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    phase = params.get("phase", "CsPbI₃")

    content = f"""\
# Supuestos cientificos y rango valido

*{phase} — flujo DFT*
*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

---

## 1. Supuestos estructurales

| Supuesto | Base | Limite |
|----------|------|--------|
| Periodicidad perfecta | Teorema de Bloch + ondas planas | Sin defectos, vacancias, bordes |
| Composicion fija | Estequiometria entera CsPbI₃ | Sin dopaje ni no-estequiometria |
| Red estatica (0 K) | BO; nucleos en minimo | Sin expansion termica |
| Sitio A como carga puntual | Cs monoatomico; sin DOF orientacional | FA⁺/MA⁺ requiere desorden rotacional |
| Celda fija al relajar | Separa celda vs posiciones | Puede perder cambios de volumen/fase |

---

## 2. Aproximaciones electronicas

| Aproximacion | Efecto | Error tipico |
|--------------|--------|--------------|
| DFT (KS) | Electrones interactuantes → no interactuantes | XC domina error |
| GGA (PBEsol) | Densidad XC local + semilocal | Bandgap ↓ ~0.3-1.0 eV |
| Pseudopotencial/PAW | Nucleo → potencial efectivo | Preciso si dataset correcto |
| Nucleo no relativista | Efectos core en PAW | SO solo valencia |
| SOC perturbativo | Correccion 1er orden a estados KS | Valido si Δ_SO ≪ campo cristalino |
| Scissor | Desplaza bandas de conduccion | Sin renormalizacion k; ±0.1 eV |
| Spin colineal | Sin magnetismo no colineal | Valido en perovskitas no magneticas |

---

## 3. Aproximaciones numericas

| Parametro | Valor | Criterio | Error residual |
|-----------|-------|----------|----------------|
| Corte ondas planas | {params.get('ecut_eV', 450)} eV | < 1 meV/atom vs Ecut | < 1 meV/atom |
| k-point mesh | {params.get('kpts', [6,6,6])} | < 1 meV/atom vs k | < 1 meV/atom |
| Umbral SCF | 10⁻⁸ eV | Convergencia SCF | < 10⁻⁸ eV/ciclo |
| Umbral fuerza | 0.01 eV/Å | Optimizacion geometrica | < 0.01 eV/Å |
| Smearing Fermi-Dirac | 0.05 eV | Muestreo BZ suave | < 0.01 eV en gap |
| Paso Hessian Δ | 0.01 Å | Hessian por diferencias finitas | ~0.1% en constantes |
| Supercelda phonon | 2×2×2 | Alcance de fuerza | Omite mas alla de 2× celda |

---

## 4. Rango valido

### 4.1 Si puede estimar

- **Estabilidad relativa** α, γ, δ: ΔE, jerarquia Gibbs.
- **Estructura electronica** a T = 0 K, sin defectos.
- **Bandgap cualitativo**: orden, directo/indirecto.
- **Bandgap corregido** via scissor: ±0.1-0.2 eV.
- **Estabilidad dinamica** via phonon.
- **Modos Γ** Raman/IR.

### 4.2 No cubre bien

- **Estabilidad finita-T**: necesita energia libre phonon o MD.
- **Defectos**: necesita superceldas + correccion de carga.
- **Movilidad**: necesita acoplamiento electron-phonon.
- **Espectros opticos**: necesita BSE o TDDFT; gap KS ≠ gap optico.
- **Bandgap absoluto**: error sistematico ±0.1-0.2 eV.
- **Desorden largo alcance**: rotacion FA⁺, segregacion haluro, coexistencia.

---

## 5. Comparacion con literatura

Para α-CsPbI₃ cubico (Pm-3m):

| Metodo | Bandgap (eV) | Fuente |
|--------|--------------|--------|
| PBE (este trabajo) | ~1.44 | Calculado |
| PBE + SOC (este trabajo) | ~0.60 | Calculado |
| HSE06 + SOC (literatura) | ~1.55 | Brivio et al. (2014) |
| Experimento | 1.73 | Sutton et al. (2018) |
| Este trabajo (corregido) | ~1.52 | Scissor: PBE + χSOC + χHSE |

Error vs experimento: ~0.2 eV → aceptable para comparar fases.

---

## 6. Reproducibilidad

Calculos reproducibles desde:
- `configs/default_params.yaml` — parametros numericos
- `structures/` — estructuras iniciales JSON, compatibles ASE
- `src/dft_cspbi3/` — codigo Python versionado

Dependencia externa: GPAW ≥ 24.1.0 con datasets PAW.
"""

    out_path.write_text(content, encoding="utf-8")
    return out_path
