# Contexto DFT para comparar Top 8 ML

## Objetivo

Construir una base DFT consistente para comparar contra los 8 candidatos que el pipeline ML marco como validos/prometedores. La comparacion actual H2H solo es rigurosa para CsPbI3 porque es el unico material con referencia DFT real disponible en los archivos cargados.

## Candidatos ML validos

| Rank ML | Formula | Bandgap ML rapido (eV) | Factor tolerancia | Score ML | Valido |
|---:|---|---:|---:|---:|---:|
| 1 | MAPbI3 | 1.5000 | 0.9115 | 1.9885 | 1 |
| 2 | MASnI3 | 1.3000 | 0.9142 | 1.9858 | 1 |
| 3 | FAPbI3 | 1.5000 | 0.9866 | 1.9134 | 1 |
| 4 | FASnI3 | 1.3000 | 0.9895 | 1.9105 | 1 |
| 5 | CsSnI3 | 1.3000 | 0.8096 | 1.9096 | 1 |
| 6 | CsPbI3 | 1.5000 | 0.8072 | 1.9072 | 1 |
| 7 | FAPbBr3 | 1.8000 | 1.0079 | 1.8921 | 1 |
| 8 | FASnBr3 | 1.6000 | 1.0111 | 1.8889 | 1 |

## DFT ya disponible

Para CsPbI3 fase alpha se encontro una referencia DFT con:

| Propiedad | Valor | Metodo/fuente |
|---|---:|---|
| Bandgap HSE06+SOC/RPA referencia | 1.5858 eV | GPAW PBE+HSE06_nsc+SOC+RPA |
| Bandgap PBE | 1.0891 eV | GPAW PBE |
| Energia de formacion | -0.037882 eV/atom | GPAW, referencia DFT existente |
| Masa efectiva electron | 0.1108 m0 | PBE+SOC, ajuste parabolico |
| Masa efectiva hueco | 0.1510 m0 | PBE+SOC, ajuste parabolico |
| Dielectrico epsilon_r | 6.1648 | RPA |
| Energia enlace exciton | 22.9 meV | postproceso con masas/dielectrico |
| PCE SQ | 27.23 % | limite Shockley-Queisser |
| Solar score | 83.8 | score DFT/postproceso |
| Fonos Gamma min | -29.9 cm^-1 | GPAW FD + Phonopy |

Tambien se encontro el equivalente ML atomistico para CsPbI3:

| Propiedad ML | Valor | Modelo |
|---|---:|---|
| Bandgap mBJ | 1.598224759 eV | ALIGNN `jv_mbj_bandgap_alignn` |
| Energia de formacion | -0.997459999 eV/atom | ALIGNN `jv_formation_energy_peratom_alignn` |
| Masa efectiva electron | 0.453535894 m0 | ALIGNN |
| Masa efectiva hueco | 0.418411929 m0 | ALIGNN |
| Dielectrico max | 28.505573 | ALIGNN DFPT/JARVIS |
| Energia relajada | -14.195730596 eV | MACE-small |
| Fuerza maxima | 7.72e-17 eV/A | MACE-small |
| Fono minimo | -0.041761847 cm^-1 | MACE-small + Phonopy |
| Hessiano min eigenvalue | -2.95221 eV/A^2 | MACE autograd |

## Calculos DFT requeridos para la base comparativa

Ejecutar los mismos calculos para los 8 candidatos ML validos, usando estructura ABX3 consistente y la misma convencion de referencias. La meta es producir una tabla con pares `dft_*` vs `ml_*` para cada material.

### 1. Relajacion estructural

Calcular relajacion DFT para cada formula:

- Funcional sugerido: PBE.
- Pseudopotenciales/metodo: el mismo stack usado en CsPbI3, idealmente GPAW + PAW.
- Corte y k-points base: mantener consistencia con CsPbI3, por ejemplo `E_cut = 450 eV`, malla `4x4x4` Gamma-centrada si aplica.
- Convergencia: energia `1e-8 eV` para SCF cuando sea viable; fuerzas finales documentadas.
- Guardar: estructura relajada, energia total, volumen, parametro de red, fuerza maxima.

Salida minima:

```text
dft_lattice_parameter
dft_volume
dft_total_energy
dft_max_force
relaxed_structure_path
```

### 2. Bandgap

Calcular dos niveles para que la comparacion sea clara:

- `dft_bandgap_pbe`: gap PBE desde SCF/bandas.
- `dft_bandgap`: gap HSE06 non-SCF o el nivel hibrido equivalente usado para CsPbI3.

Indicaciones:

- Usar la estructura relajada PBE.
- Para HSE06 non-SCF, usar la misma densidad/base y malla comparable entre materiales.
- Registrar si el gap es directo/indirecto y el punto k de VBM/CBM cuando este disponible.

Salida minima:

```text
dft_bandgap_pbe
dft_bandgap
dft_gap_type
dft_vbm_kpoint
dft_cbm_kpoint
```

### 3. Energia de formacion

Calcular energia de formacion con una convencion unica para todos los top 8. Este punto es critico porque el ML ALIGNN y el DFT actual pueden usar referencias distintas.

Indicaciones:

- Definir y documentar referencias elementales o binarias antes de comparar.
- Usar la misma formula:

```text
E_form = (E_total(ABX3) - n_A*mu_A - n_B*mu_B - n_X*mu_X) / N_atoms
```

- Si se usan referencias binarias, documentar cada mu efectiva.
- No mezclar valores de formacion con distinta referencia en las metricas de error.

Salida minima:

```text
dft_formation_energy
dft_formation_reference_scheme
dft_reference_energies_json
```

### 4. Masas efectivas

Calcular masas efectivas con SOC para Pb/Sn/Ge cuando aplique, porque el ML actual no incluye SOC y esa es una causa principal de discrepancia.

Indicaciones:

- Usar PBE+SOC no colineal o el metodo equivalente usado para CsPbI3.
- Ajustar parabolas alrededor de VBM/CBM.
- Reportar electron y hueco, y si son direccionales o promedio.

Salida minima:

```text
dft_electron_effective_mass_m0
dft_hole_effective_mass_m0
dft_effective_mass_method
dft_effective_mass_fit_window
```

### 5. Dielectrico y exciton

Para comparacion con CsPbI3 y score FV:

- Calcular `epsilon_r` con RPA o DFPT de forma consistente.
- Si se reporta exciton binding, usar la misma formula/postproceso en todos los materiales.

Salida minima:

```text
dft_dielectric_constant
dft_exciton_binding_mev
```

### 6. Fonos, hessiano y estabilidad dinamica

Recomendado para validar estabilidad:

- Fonos Gamma por diferencias finitas + Phonopy.
- Hessiano 3N x 3N si se requiere comparar contra MACE autograd.
- Reportar frecuencia minima y si hay modos imaginarios.

Salida minima:

```text
dft_phonon_min_frequency_cm1
dft_has_imaginary_phonon_modes
dft_hessian_min_eigenvalue
```

### 7. Score FV y PCE

Para cerrar la comparacion con el ML score:

- Calcular limite SQ si existe espectro de absorcion o aproximacion consistente.
- Guardar `dft_solar_score` y `dft_pce_pct_sq` con la misma receta para todos.

Salida minima:

```text
dft_solar_score
dft_pce_pct_sq
dft_score_method
```

## Esquema CSV recomendado

Cada fila debe ser un material. Columnas minimas:

```text
material_id,formula,
ml_bandgap,ml_bandgap_mbj,ml_score,ml_reward,goldschmidt_tolerance,ml_valid,
ml_formation_energy,ml_electron_effective_mass_m0,ml_hole_effective_mass_m0,
ml_dielectric_constant,ml_phonon_min_frequency_cm1,
dft_bandgap,dft_bandgap_pbe,dft_formation_energy,
dft_electron_effective_mass_m0,dft_hole_effective_mass_m0,
dft_dielectric_constant,dft_exciton_binding_mev,
dft_phonon_min_frequency_cm1,dft_solar_score,dft_pce_pct_sq,
dft_source,dft_formation_reference_scheme
```

## Criterio de comparacion posterior

Cuando existan los 8 pares DFT/ML:

- Usar MAE/RMSE/error relativo por propiedad.
- Usar error firmado para detectar sesgo sistematico.
- Para ranking: Spearman, Kendall y overlap top-k.
- Para clasificacion: promising/no-promising con ventana de bandgap y estabilidad.
- Mantener advertencia si una propiedad usa convenciones no equivalentes, especialmente energia de formacion y masas sin SOC vs con SOC.

## Prioridad sugerida

1. Bandgap HSE06-equivalente para los 8.
2. Energia de formacion con referencias consistentes.
3. Masas efectivas con SOC.
4. Dielectrico/exciton.
5. Fonos Gamma y hessiano para estabilidad dinamica.
6. PCE/SQ y score FV.
