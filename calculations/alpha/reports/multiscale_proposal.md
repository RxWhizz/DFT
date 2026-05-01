# Propuesta Multiescala: Respuesta de α-CsPbI₃ bajo Iluminación Solar

_Fecha: 2026-04-26_  
_Estado del pipeline base: SCF ✓ · Bandas ✓ · SOC ✓ · Fonones ✓ · LO-TO ✓ · HSE06 en curso_

---

## 1. Motivación

El pipeline actual (PBE+SOC, fonones, Born charges) caracteriza las propiedades del
estado fundamental de α-CsPbI₃. Para evaluar su viabilidad fotovoltaica real es
necesario extender el análisis hacia:

1. **Perfil de absorción en el dispositivo** — cómo penetra la luz en la capa activa
2. **Estados excitados y gap corregido** — HSE06+SOC para gap realista (~1.35–1.45 eV)
3. **Defectos intrínsecos** — trampas profundas que limitan V_oc y τ_n
4. **Migración iónica** — inestabilidad operacional bajo campo eléctrico
5. **Evolución cinética** — distribución temporal de defectos e iones (kMC)
6. **Estabilidad térmica** — viabilidad a temperatura de operación (300–400 K)

Esta propuesta define la estrategia, prioriza por factibilidad computacional y
especifica la implementación en el pipeline existente.

---

## 2. Aclaración: Ray Tracing vs. Física de Materiales

**Ray tracing y Monte Carlo óptico** modelan exclusivamente *propagación de fotones*:
reflexión, refracción, transmisión geométrica. Son herramientas de óptica de dispositivo,
no de física de materiales. **No predicen** ruptura de enlaces, migración iónica ni degradación.

Para este pipeline se usa **Beer-Lambert con integración AM1.5G** (implementado en
`analysis/optical_device.py`), equivalente a un Monte Carlo óptico 1D determinístico.
Esto es suficiente para obtener G(x), η_óptica y J_sc(límite) sin overhead de software.

---

## 3. Inventario: Implementado vs. Pendiente

### 3.1 Ya implementado (en este pipeline)

| Módulo | Archivo | Nivel físico |
|--------|---------|-------------|
| ε(ω), n(ω), k(ω), α(ω) | `analysis/optical.py` | L1 — óptica lineal |
| Perfil G(x) Beer-Lambert | `analysis/optical_device.py` | L1 — dispositivo |
| AM1.5G score, J_sc límite | `analysis/optical.py`, `optical_device.py` | L1 |
| Born charges Z\*, ε∞ | `validation/phonons.py` | L1 — LO-TO |
| SOC perturbativo (PBE) | `validation/soc.py` | L2 — parcial |
| **HSE06+SOC** | ext. `workflow_manager._run_soc_hse06()` | **L2 — completo** |
| Fonones, F_vib(T) | `analysis/phonopy_workflow.py` | L6 — parcial |
| **QHA** | ext. `phonopy_workflow.compute_quasiharmonic()` | **L6 — completo** |
| CI-NEB framework | `analysis/neb_workflow.py` | L4 — reutilizable |
| **Endpoints migración** | ext. `neb_workflow.build_migration_endpoints()` | **L4 — completo** |
| PES scan, double-well | `analysis/pes.py` | L4 — modos blandos |
| **Defectos** | `analysis/defects.py` (nuevo) | **L3 — completo** |
| **kMC BKL** | `analysis/kmc.py` (nuevo) | **L5 — completo** |
| **AIMD-MLIP (MACE)** | `analysis/aimd_mlip.py` (nuevo) | **L6b — completo** |
| PV scoring | `analysis/scoring.py` | resumen |

---

## 4. Estrategia por Nivel

### Nivel 1 — Óptica de Dispositivo ✓ IMPLEMENTADO

**Física**: Beer-Lambert I(x,ω) = I₀(ω) exp(−α(ω)x)  
**Inputs**: α(ω) y n(ω) de `11_optical/`  
**Outputs**: G(x) [photons/cm³/s], η_óptica, J_sc(límite, IQE=1)

```python
from src.dft_cspbi3.analysis.optical_device import compute_device_optics
result = compute_device_optics(step_dir="calculations/alpha/11_optical", thickness_nm=500)
# → G(x), η_opt, J_sc_limit_mA_cm2
```

**Parámetros por defecto**: d = 500 nm (capa activa típica para perovskitas),
integración AM1.5G sobre ω ≥ onset de absorción.

**Extensión futura**: TMM multicapa (ya implementada en `multilayer_tmm_profile()`)
para simular stack completo FTO/TiO₂/CsPbI₃/spiro-OMeTAD/Au.

---

### Nivel 2 — Estados Excitados ✓ IMPLEMENTADO (HSE06+SOC en curso)

**Física**: SOC perturbativo aplicado post-HSE06 con `soc_eigenstates(hse06.gpw)`  
**Gap esperado**: HSE06 ~1.7 eV → HSE06+SOC ~1.35–1.45 eV  
**Gap experimental**: 1.73 eV (incluye efectos excitónicos y temperatura)

```python
# Una vez hse06.gpw disponible:
wf.run(steps=["soc_hse06"])
# → 05_soc/soc_hse06_eigenvalues.npy
```

**Corrección scissor automática**: `_run_optical()` detecta hse06.gpw y calcula
eshift = E_g(HSE06) − E_g(PBE), pasándolo a `DielectricFunction(eshift=...)`.

**BSE (Bethe-Salpeter)**: da espectro excitónico correcto pero requiere k-mesh
8×8×8 y ~100 bandas desocupadas → costo ~10–50× RPA. Diferido para hardware
externo (cluster o GPU). GPAW lo soporta via `gpaw.response.bse`.

---

### Nivel 3 — Defectos Intrínsecos ⚠ FACTIBLE, ~50 h en 7 cores

**Defectos implementados** (en `analysis/defects.py`):

| Defecto | Tipo | Relevancia PV | Charges |
|---------|------|---------------|---------|
| V_I | donor shallow/deep | **CRÍTICA** — trampa + migración | 0, +1 |
| I_i | acceptor | alta — par Frenkel con V_I | 0, −1 |
| V_Pb | acceptor profundo | alta — recombinación no-radiativa | 0, −1, −2 |
| V_Cs | acceptor | media — movilidad A-site | 0, −1 |
| Pb_I | antisite donor | alta — trampa profunda conocida | 0, +1, +2 |
| I_Pb | antisite acceptor | media | 0, −1, −2 |

**Estrategia híbrida** (MACE geom. + DFT single-point):
1. `build_defect_supercell()` → supercell 2×2×2 con defecto
2. `mace_relax_defect()` → geometría relajada en segundos (MACE-MP-0)
3. `gpaw_single_point()` → energía DFT precisa (~1 h/cálculo)
4. `compute_formation_energy()` → E_f(q, E_F) con corrección Makov-Payne

**Corrección de tamaño finito**: Makov-Payne monopole usando ε∞ = 3.647
(ya calculado). Para publicación: Freysoldt full (requiere potencial electrostático).

**Costo**: ~50 h continuas en 7 cores. Reducible a ~20 h con geometrías MACE.

```python
from src.dft_cspbi3.analysis.defects import compute_all_defects
results = compute_all_defects(atoms, factory, work_dir="calculations/alpha/13_defects",
                               bandgap_eV=1.089, use_mace_geometry=True)
```

---

### Nivel 4 — Migración Iónica ⚠ FACTIBLE, ~15 h en 7 cores

**Física**: CI-NEB entre sitios vacantes vecinos (mecanismo de salto vacancy)

**Rutas implementadas** (en `neb_workflow.build_migration_endpoints()`):

| Defecto | Ruta | Descripción | Barrera lit. [eV] |
|---------|------|-------------|-------------------|
| V_I | `<100>` | Salto octaedro vecino | 0.1–0.25 |
| V_I | `<110>` | Salto diagonal | 0.3–0.4 |
| I_i | `<100>` | Migración intersticial | ~0.2 |
| V_Cs | `<100>` | Salto A-site | ~0.4–0.6 |

**Tasa térmica** (Arrhenius): k(T) = ν₀ × exp(−E_b/kT)  
ν₀ = frecuencia fonónica del modo de migración (disponible de los fonones ya calculados).

**Fotoactivación**: bajo iluminación los portadores excitados pueden reducir E_b
efectiva. Requiere ΔSCF en estado excitado — complejidad alta, diferido.

```python
from src.dft_cspbi3.analysis.neb_workflow import run_migration_neb
neb_results = run_migration_neb(atoms, "V_I", factory,
                                 work_dir="calculations/alpha/14_migration")
```

---

### Nivel 5 — Kinetic Monte Carlo ✓ IMPLEMENTADO (post L3+L4)

**Algoritmo**: BKL (Bortz-Kalos-Lebowitz), O(N) por evento

**Inputs**:
- Barreras de migración de L4 (V_I, I_i, V_Cs)
- G(x) de L1 (tasa de generación de portadores)
- ε∞ = 3.647 (captura electrostática)

**Outputs**:
- `defect_population_vs_time(T)`
- `recombination_risk_vs_time`
- `photostability_label` ∈ {stable, degrading, unstable}

```python
from src.dft_cspbi3.analysis.kmc import KMCLattice, run_kmc
barriers = {"V_I_hop": 0.25, "I_i_hop": 0.18}
lattice = KMCLattice.from_atoms(atoms, barriers, temperature_K=300,
                                  generation_rate_cm3s=1e21)
result = run_kmc(lattice, total_time_s=1e-6)
```

**Costo**: segundos a minutos (sin DFT). Alta relación impacto/costo.

---

### Nivel 6 — Estabilidad Térmica

#### 6a. Quasi-Harmónica (QHA) ✓ IMPLEMENTADO, ~42 h en 7 cores

**Física**: F_vib(T,V) = kT × Σ_q [½ħω + kT ln(1 − e^{−ħω/kT})]  
Integrada sobre volúmenes escalados → G(T), α(T), C_p(T), V_eq(T)

**Implementación**: `phonopy_workflow.compute_quasiharmonic()`, Phonopy QHA  
**Volúmenes**: 6 puntos, strains ±4% en torno a V₀ = 236.03 Å³  
**Validez**: T < 0.5–0.7 × T_melt ~ 320–450 K para CsPbI₃ α-phase

⚠ **Limitación crítica**: α-CsPbI₃ tiene modo blando R₄⁺ (tilting octaedros).
QHA falla en la transición α→γ (Pnma) porque asume potencial armónico desplazado;
la transición es displaciva y no puede representarse como variación suave de ω(V).

```python
from src.dft_cspbi3.analysis.phonopy_workflow import compute_quasiharmonic
result = compute_quasiharmonic(atoms, factory,
                                work_dir="calculations/alpha/15_qha",
                                volume_strains=(-0.04,-0.02,0,0.02,0.04,0.06))
```

#### 6b. AIMD-MLIP (MACE) ✓ IMPLEMENTADO, ~5 min/temperatura

**Reemplaza**: AIMD-DFT (~400 h en 7 cores) → **MACE-MP-0 (~5 min en CPU)**

**Métricas de estabilidad**:
- RMSD(t) vs. estructura de referencia [Å]
- RDF Pb-I: pico debe permanecer en 3.0–3.5 Å
- Ángulo Pb-I-Pb: media debe ser 160–180° (octaedros intactos)
- Label: `stable` (RMSD < 0.5 Å) | `distorted` (0.5–0.8) | `decomposed` (> 0.8)

```python
from src.dft_cspbi3.analysis.aimd_mlip import screen_thermal_stability
results = screen_thermal_stability(
    atoms.repeat((2,2,2)),
    work_dir="calculations/alpha/16_aimd_mlip",
    temperatures_K=(300, 400, 500, 600),
    n_steps=5000,
)
```

**Instalación** (una sola vez): `pip install mace-torch`  
MACE-MP-0 descarga automáticamente ~150 MB el primer uso.

---

## 5. Comparación QHA vs. MACE para L6

| Aspecto | QHA (Phonopy/DFT) | MACE-MP-0 |
|---------|-------------------|-----------|
| Base física | Armónica + expansión V | Potencial ML completo |
| Anarmonicidad | Solo quasi-armónica | Completa (todos los órdenes) |
| Transiciones de fase | **No** (diverge en modo blando) | **Sí** (detecta α→γ) |
| C_p(T), α(T) precisos | Sí (precisión DFT) | Aprox (~50-100 meV/atom MAE) |
| Costo computacional | ~42 h DFT | **~5 min CPU** |
| Validez T < T_melt | Sí (parcialmente) | Sí |

**Pipeline recomendado**:
```
MACE (screening, minutos):
  └─ AIMD NVT 300/400/500/600 K → label {stable|distorted|decomposed}
  └─ Si stable en T < 400 K → proceder a QHA

QHA DFT (~42 h, usa datos de fonones ya calculados):
  └─ G(T), α(T) cuantitativos
  └─ ΔG_decomp(T) = G_α(T) − G_{CsI+PbI₂}(T)
```

Factor de ahorro: ~10× vs. AIMD-DFT puro para screening.

---

## 6. Impacto del Doble Xeon (cuando disponible)

| Nivel | 7 cores actual | 28 cores Xeon DDR4 | Cambio |
|-------|---------------|---------------------|--------|
| L3 defectos 2×2×2 | ~50 h | **~13 h** | MEDIA → **ALTA** |
| L3 defectos 3×3×3 | ~400 h (no factible) | **~100 h** | NO → MEDIA |
| L4 NEB por ruta | ~3 h | **~45 min** | MEDIA → **ALTA** |
| L6a QHA | ~42 h | **~10 h** | MEDIA → **ALTA** |
| L2b BSE (8×8×8) | días (no factible) | **~24 h** | BAJA → MEDIA |
| L6b AIMD-DFT 2 ps | ~80 h | **~20 h** | BAJA → MEDIA |

---

## 7. Radiación Ionizante — Fuera de Alcance

La radiación de alta energía (rayos γ, protones MeV) produce cascadas de
desplazamientos atómicos cualitativamente distintas a la fotogeneración visible.
Las herramientas adecuadas son SRIM/TRIM, Geant4 y LAMMPS con potenciales clásicos.

**Decisión**: marcado como **fuera del alcance** del pipeline PV terrestre.
Relevante únicamente para aplicaciones espaciales.

---

## 8. Tabla de Prioridad de Implementación

| # | Módulo | Nivel | Prioridad | Costo | Estado |
|---|--------|-------|-----------|-------|--------|
| 1 | `optical.py` (scissor HSE06) | L1+L2 | **P0 activa** | 1–3 h | ✓ corriendo |
| 2 | `optical_device.py` (G(x)) | L1 | **P0** | minutos | ✓ implementado |
| 3 | `soc_hse06` en workflow | L2 | **P1** | 30 min | ✓ implementado |
| 4 | `defects.py` (V_I, V_Pb…) | L3 | **P2** | ~50 h | ✓ implementado |
| 5 | `aimd_mlip.py` (MACE 300-600K) | L6b | **P2** | minutos | ✓ implementado |
| 6 | `phonopy_workflow.compute_quasiharmonic` | L6a | **P2** | ~42 h | ✓ implementado |
| 7 | `neb_workflow.run_migration_neb` (V_I) | L4 | **P3** | ~15 h | ✓ implementado |
| 8 | `kmc.py` (post L3+L4) | L5 | **P3** | minutos | ✓ implementado |
| 9 | BSE excitónica | L2b | **P4 (HPC)** | días | pendiente |
| 10 | AIMD-DFT completo (L6b) | L6b | **P4 (HPC)** | ~400 h | sustituido por MACE |

---

## 9. Orden de Ejecución Recomendado

```
Inmediato (sin DFT nuevo):
  1. pip install mace-torch
  2. screen_thermal_stability (atoms×2×2×2, T=300/400/500 K) → ~15 min
  3. Una vez hse06.gpw: wf.run(["soc_hse06"]) → 30 min

Semana 1 (tras HSE06 completado):
  4. wf.run(["optical"])  →  ε(ω) con scissor HSE06 (~2 h)
  5. compute_device_optics → G(x), J_sc límite (segundos)
  6. compute_all_defects (defectos 2×2×2, MACE+DFT) → ~50 h

Semana 2 (tras L3):
  7. run_migration_neb("V_I") → 3 rutas, ~10 h
  8. run_kmc(barriers_from_L4) → segundos

Semana 3 (opcional, ~42 h):
  9. compute_quasiharmonic (6 volúmenes) → α(T), C_p(T)
```

---

## 10. Referencias Bibliográficas Clave

1. Azpiroz et al., *Energy Environ. Sci.* **8**, 2118 (2015) — Migración V_I en MAPbI₃
2. Mosconi & De Angelis, *ACS Energy Lett.* **1**, 182 (2016) — Barreras NEB perovskitas
3. Zhang & Northrup, *Phys. Rev. Lett.* **67**, 2339 (1991) — Formalism defectos
4. Freysoldt et al., *Phys. Rev. Lett.* **102**, 016402 (2009) — Corrección tamaño finito
5. Becker et al., *npj Comput. Mater.* **7**, 45 (2021) — MACE universales halide perovskites
6. Togo & Tanaka, *Scr. Mater.* **108**, 1 (2015) — Phonopy QHA
7. Gonze & Lee, *Phys. Rev. B* **55**, 10355 (1997) — LO-TO Born charges
8. Stoumpos et al., *Inorg. Chem.* **52**, 9019 (2013) — Estructura α-CsPbI₃ experimental
