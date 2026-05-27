# Bitácora de convergencia — Sn-based perovskites (GPAW master)

Registro de hallazgos empíricos sobre convergencia SCF para MASnI3, FASnI3, FASnBr3, CsSnI3
con r²SCAN+U (U=3.5 eV en Sn-5s). Actualizar con cada experimento nuevo.

---

## Contexto del problema

Los materiales Sn-based oscilan en SCF porque el orbital Sn-5s con U crea dos mínimos
locales en el paisaje DFT+U:
- **Estado A**: Sn 5s ocupado (Sn²⁺, par solitario localizado)
- **Estado B**: Sn 5s parcialmente ocupado (Sn~2.5+, deslocalizado)

El mixer alterna entre ambos estados → oscilación de energía de 1–4 eV por iteración.
La densidad puede converger (criterio `1e-2` del preconv) mientras la energía oscila,
porque dos ocupaciones distintas pueden dar densidades similares pero energías muy distintas.

---

## Hallazgos por parámetro

### smearing `width` (ocupaciones Fermi-Dirac)

| width (eV) | Comportamiento CsSnI3 r²SCAN | Comportamiento MASnI3 preconv |
|-----------|------------------------------|-------------------------------|
| 0.05 | Oscilación ±1.5 eV, densidad ~−2.6 @ iter 170 | Oscilación ±4 eV |
| 0.1 | **CsSnI3 preconv convergió** (iter ~80–100) | No probado |
| 0.2 | Oscilación baja a ±0.2 eV @ iter 165, densidad −2.8. Sweet spot. | Densidad converge `c`, energía ±1 eV |
| 0.3 | No probado r²SCAN | Densidad `c`, energía ±1 eV (igual que 0.2) |
| 0.5 | **PEOR que 0.2** — oscilación ±2 eV, densidad baja a −2.1. Contraproducente. | Demasiado temprano para juzgar |

**Conclusión crítica**: más smearing no siempre ayuda. Con `width=0.5` el r²SCAN empeora
porque más bandas entran en ocupación fraccionaria → la densidad cambia más por iteración,
no menos. El sweet spot para r²SCAN CsSnI3 es `width=0.2`.

### mixer `beta` (tasa de mezcla)

| beta | nmaxold | Resultado |
|------|---------|-----------|
| 0.05 | 10 | Oscilación ±2 eV (valor default original) |
| 0.02 | 20 | Primera mejora: ±1.5 eV @ iter 30, luego regresa |
| 0.01 | 3 | **PEOR** — historia corta hace extrapolación MSR1 pobre. Oscilación ±4 eV MASnI3 |
| 0.02 | 10 | Mejor combinación encontrada hasta ahora |

**Conclusión**: reducir `nmaxold` debajo de 10 empeora MSR1 porque necesita historia
suficiente para construir el subespacio de Krylov. Beta muy bajo (0.01) con nmaxold
pequeño (3) es peor que beta moderado (0.02) con historia larga (10).

### Número de MPI ranks

| Ranks totales | Cores físicos | Resultado |
|--------------|---------------|-----------|
| 4 × 20 = 80 | 22 | **Corrupción de datos** — energías físicamente incorrectas (CsSnI3 mostró −48 eV) |
| 3 × 20 = 60 | 22 | MPI slot error para el 3er proceso |
| 2 × 22 = 44 | 22 | **Configuración correcta** — 1 rank por CPU lógico, sin oversubscription |
| 2 × 10 = 20 | 22 | Funciona pero subutiliza el hardware |

**Conclusión**: con 44 CPUs lógicos (22 físicos), 2 jobs × 22 ranks es el límite.
Más de 2 jobs simultáneos requiere `--oversubscribe` o reduce ranks por job.

---

## Estrategia de convergencia por etapa

### Preconv (PBE+U, criterio `density=1e-2`)

```python
# Configuración que convergió CsSnI3:
occupations={"name": "fermi-dirac", "width": 0.1}
mixer={"backend": "msr1", "beta": 0.01, "nmaxold": 3}
```

Nota: CsSnI3 (5 átomos, celda pequeña, 1 Sn) convergió con estos params. MASnI3/FASnX
(celdas más grandes, catión orgánico) son más difíciles.

### r²SCAN+U (criterio `density=1e-4`, 100× más estricto)

```yaml
# Sweet spot encontrado empíricamente:
mixer:
  backend: msr1
  beta: 0.02
  nmaxold: 10
occupations:
  name: fermi-dirac
  width: 0.2
```

### Estrategia pendiente para r²SCAN+U Sn-based — falsos mínimos

**Diagnóstico clave (2026-05-22):** el problema raíz no es el smearing ni Kerker — es que
beta ≥ 0.02 permite que el mixer salte entre mínimos locales del paisaje DFT+U de Sn-5s.
Cada "salto" de energía de 1-2 eV observado corresponde a caer en un mínimo diferente.

**Estrategia correcta:** `beta muy pequeño (0.001–0.005)` para que el mixer solo pueda
moverse localmente en el paisaje de energía, evitando escaparse del mínimo correcto.
Combinar con `nmaxold=3–5` para no acumular historia de múltiples mínimos distintos.

```yaml
# Config activa r²SCAN+U Sn-based (2026-05-23, auditoría rigurosa):
mixer:
  backend: msr1
  beta: 0.002      # movimiento local — nmaxold=15 da subespacio Krylov bien condicionado
  nmaxold: 15      # historia más larga — necesaria con beta pequeño para MSR1
  weight: 100      # Kerker — suprime charge sloshing de largo alcance
occupations:
  width: 0.2       # sweet spot empírico confirmado
maxiter: 2000      # CRÍTICO — GPAW default 333 es insuficiente con beta=0.002
convergence:
  density: 1e-4    # criterio dominante para DFT+U
  eigenstates: 1e-6  # relajado de 1e-8 — AND lógico bloqueaba convergencia
  energy: 1e-5     # relajado de 1e-6 — sub-físico durante oscilación DFT+U
eigensolver: Davidson(niter=3)  # niter=4→3 ahorra ~25% CPU con potencial estable
```

### Próxima medida si el r²SCAN no converge en 300 iters

Kerker preconditioning (suprime charge sloshing de largo alcance):
```yaml
mixer:
  backend: msr1
  beta: 0.02
  nmaxold: 5
  weight: 100   # Kerker — no probado aún
occupations:
  width: 0.25
```

### U-ramping r²SCAN — estrategia adoptada (2026-05-24)

**Script:** `scripts/u_ramp_r2scan.py`

Reason: beta=0.002 + nmaxold=15 con 1487 iters no convergió (log₁₀(Δdens)≈−2.2 estancado).
El problema raíz es el double-well del paisaje DFT+U — el mixer no puede elegir el mínimo correcto
si empieza en territorio ambiguo. U-ramping evita el problema siguiendo el mínimo correcto desde U=0.

```
U=0.0 eV  cold start (relax_sym.gpw)  → u_ramp_U0p0.gpw   [fast: density=1e-2, beta=0.05, maxiter=500]
U=1.0 eV  warm desde U=0              → u_ramp_U1p0.gpw   [fast]
U=2.0 eV  warm desde U=1              → u_ramp_U2p0.gpw   [fast]
U=3.5 eV  warm desde U=2              → r2scan.gpw         [full: density=1e-4, beta=0.002, maxiter=2000]
```

```bash
mpirun -n 22 .venv/bin/python3 scripts/u_ramp_r2scan.py --mat CsSnI3
```

---

## Tamaño de celda y convergencia

- Celda más **pequeña** (primitiva, 1 fórmula) no causa el problema — ya usamos primitiva.
- Celda más **grande** (supercelda 2×2×2) permitiría ruptura de simetría Sn²⁺/Sn⁴⁺
  (ordering del par solitario), pero es 8× más costoso y cambia la física.
- El **charge sloshing** (oscilación de largo alcance) empeora en celdas más grandes →
  MASnI3/FASnBr3/FASnI3 (catión orgánico) son intrínsecamente más difíciles que CsSnI3.
- Kerker weight=100 es el fix correcto para charge sloshing sin cambiar la celda.

---

## Timeline de experimentos

| Fecha | Experimento | Resultado |
|-------|-------------|-----------|
| 2026-05-22 | CsSnI3 preconv: `width=0.1, beta=0.01, nmaxold=3` | ✅ **Convergió** — gap PBE+U = 0.298 eV |
| 2026-05-22 | MASnI3 preconv `width=0.1` | ❌ Oscilación ±4 eV |
| 2026-05-22 | CsSnI3 r²SCAN `width=0.05, beta=0.05` (default) | ❌ Oscilación ±1.5 eV, densidad −2.6 @ iter 170 |
| 2026-05-22 | CsSnI3 r²SCAN `width=0.2, beta=0.02` | 🔄 Oscilación baja a ±0.2 eV @ iter 165. Monitor disparó en iter 236 (threshold −3.0) |
| 2026-05-22 | CsSnI3 r²SCAN `width=0.5, beta=0.005` (medidas extremas) | ❌ **Peor** — oscilación ±2 eV, densidad −2.1 |
| 2026-05-22 | CsSnI3 r²SCAN vuelve a `width=0.2, beta=0.02` | Monitor disparó en iter 301 (densidad insuficiente) → Kerker activado |
| 2026-05-22 | MASnI3 preconv `width=0.5, beta=0.02, nmaxold=10` | ✅ **Convergió** — gap PBE+U = 2.720 eV |
| 2026-05-22 | FASnBr3 preconv `width=0.5, beta=0.02, nmaxold=10` | ✅ **Convergió** — gap PBE+U = 1.558 eV (directo) |
| 2026-05-22 | CsSnI3 r²SCAN Kerker `weight=100, width=0.25, beta=0.02, nmaxold=5` | ❌ Matado — no convergería. Diagnóstico: beta=0.02 permite caer en falsos mínimos locales del paisaje DFT+U |
| 2026-05-22 | FASnI3 preconv `width=0.5, beta=0.02, nmaxold=10` | 🔄 Corriendo |
| 2026-05-23 | r²SCAN+U todos los Sn-based: auditoría rigurosa → `beta=0.002, nmaxold=15, weight=100, width=0.2, maxiter=2000, eigenstates=1e-6, energy=1e-5, Davidson(niter=3)` | ❌ No convergió — CsSnI3 stuck log₁₀(Δdens)≈−2.2 @ iter 1487. Decisión: U-ramping |
| 2026-05-24 | U-ramping CsSnI3: U=3.0 convergió; U=3.5 osciló y sobrecorrige. Decisión: barrido fino 2.0–2.75 eV | ⚠️ U=3.5 descartado |
| 2026-05-24 | U fine scan CsSnI3: U=2.0, 2.25, 2.5, 2.75 eV con parámetros auditados. 16–19 iters cada uno | ✅ **Todos convergieron** |
| 2026-05-24 | SOC perturbativo CsSnI3 (u_scan_soc_dos.py): `ignore_xc_potential=True` para r²SCAN. Δ_SOC ≈ −0.49 a −0.55 eV | ✅ U=2.5 → gap SOC=1.359 eV ≈ exp 1.3 eV ✓ |
| 2026-05-24 | PDOS CsSnI3 (u_scan_pdos.py): FakeWFS con < 22 ranks. Fix: Reader API directo, `wfs.projections` shape (nspins, nk, nbands, nprojs_total). Sin `mode='all'` en save | ✅ VBM: I-p+Sn-s; CBM: Sn-p. Orbital ordering correcto |
| 2026-05-24 | Extensión a MASnI3, FASnBr3, FASnI3: fix PDOS dinámico (I→halide, Cs opcional), target gaps por material | 🔄 Lanzando 3×7 cores |

---

## Metodología validada — U fine scan (2026-05-24)

**Descubrimiento clave:** U=3.5 eV no es el valor óptimo para Sn-based perovskites —
sobrecorrige el gap. U=2.5 eV reproduce el gap experimental con r²SCAN+U.

### Pipeline completo validado en CsSnI3

```
1. preconv_pbe_u.py   → pre_r2scan.gpw    [7 cores, PBEsol+U, density=0.01]
2. u_scan_r2scan.py   → u_scan_U*.gpw     [22 cores, r²SCAN+U, U=2.0–2.75 eV]
3. u_scan_soc_dos.py  → u_scan_soc_summary.json  [4 cores, SOC perturbativo]
4. u_scan_pdos.py     → u_scan_U*_dos.npz [serial, Reader API directo]
```

### Parámetros que funcionaron (CsSnI3, u_scan)
- U_SCAN = [2.0, 2.25, 2.5, 2.75] eV
- Convergencia: 16–19 iters por punto (vs 1500+ iters fallidos con U=3.5)
- Seed: `pre_r2scan.gpw` (PBEsol+U) → estructura inicial para u_scan
- Todos los puntos: directo en R=[0.5,0.5,0.5], bandas 21→22

### Resultados CsSnI3 — referencia
| U (eV) | gap r²SCAN | gap SOC | Δ_SOC | En rango? |
|--------|-----------|---------|-------|-----------|
| 2.00 | 1.413 | 0.938 | −0.475 | No |
| 2.25 | 1.618 | 1.128 | −0.490 | No |
| **2.50** | **1.872** | **1.359** | **−0.514** | **✓ (exp ~1.3 eV)** |
| 2.75 | 2.190 | 1.638 | −0.552 | No |

### SOC — nota técnica
- `soc_eigenstates(calc, ignore_xc_potential=True)` — necesario para r²SCAN
- MGGA no implementa `calculate_spherical`; contribución XC al SOC es ~meV (negligible)
- `soc.eigenvalues()` devuelve BZ completa (216 k-pts para 6×6×6), no IBZ

### PDOS — nota técnica
- GPW guardado sin `mode='all'` → FakeWFS al cargar con cualquier número de ranks
- Fix: leer directamente `Reader(gpw).wave_functions.projections` shape `(nspins, nk, nbands, nprojs_total)`
- `nprojs_total` = suma de todos los proyectores PAW de todos los átomos
- Split por átomo via `sum(2*l+1 for l in setup.l_j)`

### Targets experimentales por material
| Material | Exp. gap (eV) | Target SOC range |
|---------|---------------|-----------------|
| CsSnI3  | 1.30 | 1.2–1.5 eV |
| MASnI3  | 1.24 | 1.1–1.4 eV |
| FASnI3  | 1.41 | 1.2–1.5 eV |
| FASnBr3 | 2.05 | 1.8–2.3 eV |

---

## G0W0 — benchmark independiente para materiales Pb-based (2026-05-25)

### Motivación

Los 4 materiales Sn-based ya tienen gaps validados con r²SCAN+U+SOC (U=2.5 eV, metodología
auditada). Los 4 Pb-based (CsPbI3, MAPbI3, FAPbI3, FAPbBr3) tienen solo r²SCAN sin U —
no se sabe si Pb necesita corrección Hubbard. G0W0 da un benchmark sin parámetros empíricos.

### ¿Qué es G0W0?

Teoría de perturbación de muchos cuerpos (MBPT). En DFT, el potencial de XC V_xc es una
aproximación local/semi-local. G0W0 lo reemplaza por la auto-energía exacta (en primer orden):

    ε_QP = ε_KS + ⟨ψ|Σ(ε_QP) - V_xc|ψ⟩

Donde Σ = G₀W₀ (auto-energía de intercambio-correlación):
- **G₀**: función de Green del DFT de partida — describe cómo se propaga un electrón/hueco
- **W₀**: interacción de Coulomb apantallada — cuánto se repelen dos electrones después
  de que el sistema electrónico apantalla esa repulsión

El ingrediente clave es **chi0** (polarizabilidad irreducible): describe la respuesta
del sistema a perturbaciones. Se calcula sumando sobre pares (k, k+q) en el espacio
recíproco — ese es el cuello de botella computacional.

### Workflow implementado

```
relax.gpw  →  g0w0_groundstate.py  →  g0w0_pbe.gpw (PBE, 600 bandas, ecut=600 eV)
                                              ↓
                                    g0w0_run.py (G0W0@PBE, PPA, ecut_gw=100 eV)
                                              ↓
                                    g0w0_soc.py (SOC perturbativo)
                                              ↓
                                    g0w0_soc.json (gap_GW+SOC)
```

**Por qué PBE y no r²SCAN como punto de partida:**
r²SCAN es MGGA (depende de la densidad cinética ked). GPAW tiene un bug al leer GPW
de MGGA (`AttributeError: ked`) en la versión actual — PBE evita este problema.
G0W0@PBE es además el estándar de literatura para perovskitas haluro.

**PPA (Plasmon-Pole Approximation):**
En vez de integrar chi0 sobre ~800 frecuencias reales (full-frequency), PPA evalúa
solo en 2 frecuencias imaginarias y ajusta un modelo ω_p(q,G). Reduce el costo ~400×
con pérdida de precisión de ±0.1-0.2 eV. Adecuado para celdas de 5-12 átomos.

**ecut_extrapolation:**
GPAW corre G0W0 a ecut_gw = {74, 86, 100} eV y extrapola Σ ~ A + B/ecut³ → ecut→∞.
Mejora la precisión sin aumentar linealmente el costo. El bottleneck es chi0 a ecut_1=100 eV.

### Infraestructura y problemas resueltos

| Problema | Causa | Solución |
|----------|-------|----------|
| `ScaLAPACK crash` en diagonalize_full_hamiltonian | MPI paralelo incompatible | `nbands=600` en constructor GPAW → Davidson maneja bandas vacías sin ScaLAPACK |
| OOM: chi0_wGG 4.2 GB/rank × 22 | chi0 no distribuido | `nblocksmax=True` → 190 MB/rank |
| G0W0 colgado en q≠Γ con 22 ranks | Comunicación MPI O(N²) entre ranks | Reducir a 4 ranks → sweet spot cómputo/comunicación |
| `RuntimeError: nbands con ecut_extrapolation` | Incompatibilidad GPAW master | Solo pasar `nbands` cuando `--no-extrap` |

### Estado actual (2026-05-25)

| Paso | Material | Estado | Resultado |
|------|----------|--------|-----------|
| Groundstate PBE | CsPbI3 | ✅ Done | gap_PBE=1.288 eV, EF=3.562 eV, 600 bandas |
| G0W0 PPA | CsPbI3 | 🔄 Corriendo | 4/19 q-points off-Γ completados |
| SOC | CsPbI3 | ⏳ Automático tras G0W0 | — |
| G0W0+SOC | MAPbI3, FAPbI3, FAPbBr3 | ⏳ Pendiente | — |

**Parámetros de corrida CsPbI3:**
- Ranks: 4 MPI (óptimo — con 22 se cuelga por comunicación O(N²))
- ecut_gw: 100 eV + extrapolación
- PPA: True
- Tiempo estimado: ~8 horas total (corriendo desde 14:13 MST, termina ~22:00)

**Tiempos por q-point observados:**
- q=Γ: ~11 min total (wings+body × 3 ecut) — alta simetría (48 ops)
- q off-Γ: 84s–1459s por q, dependiendo de simetría del vector q
  - Rápidos (~85s): q con muchas operaciones de simetría → pocos pares k únicos
  - Lentos (~1000-1500s): q con pocas simetrías (8 ops) → más pares (k, k+q) a sumar

### Verificación esperada

| Material | gap_PBE | gap_GW+SOC objetivo | Exp |
|----------|---------|---------------------|-----|
| CsPbI3 | 1.288 eV | ~1.5-1.7 eV | 1.73 eV |
| MAPbI3 | 1.864 eV (r²SCAN) | ~1.5-1.7 eV | 1.55-1.60 eV |
| FAPbI3 | 0.652 eV (r²SCAN indirect) | ~1.4-1.6 eV | 1.48 eV |
| FAPbBr3 | 0.854 eV (r²SCAN indirect) | ~2.0-2.3 eV | 2.23 eV |

---

## G0W0 — Patrón de simetría en q-points (2026-05-26)

### Observación empírica

Durante el cálculo G0W0 de CsPbI₃ (malla 6×6×6, 4 ranks MPI, PPA) se observó un patrón
sistemático en los tiempos de los q-points irreducibles off-Γ:

| q-point | Tiempo (s) | Tipo |
|---------|-----------|------|
| 1 | 1088 | **pesado** |
| 2 | 254 | ligero |
| 3 | 159 | ligero |
| 4 | 1498 | **pesado** |
| 5 | 93 | ligero |
| 6 | 207 | ligero |
| 7 | 1081 | **pesado** |
| 8 | 61 | ligero |
| 9 | 145 | ligero |
| 10 | 1093 | **pesado** |
| 11 | 79 | ligero |
| 12 | 102 | ligero |
| 13 | >3600 | **pesado** (en curso) |
| 14 | ~100 | ligero (esperado) |
| 15 | ~150 | ligero (esperado) |

**Patrón:** PESADO, ligero, ligero — repetido 5 veces para los 15 q-points off-Γ.

### Explicación física

El tiempo de cada q-point escala con el número de pares k irreducibles que GPAW
debe integrar para construir χ₀(q,G,G',ω). Esto está determinado por el
**grupo de pequeño del vector q** (little group): el conjunto de operaciones de
simetría del grupo espacial que dejan q invariante.

| Tipo de q-point | Posición en IBZ cúbica | Ops. del little group | Reducción k | Tiempo |
|----------------|----------------------|----------------------|-------------|--------|
| Punto general | [ξ₁, ξ₂, ξ₃], todos distintos | 2–4 ops | ~33% | **pesado** |
| Plano diagonal | [ξ, ξ, 0], dos componentes iguales | 8 ops | ~60% | ligero |
| Eje principal | [ξ, 0, 0] | 16 ops | ~80% | ligero |

Para la malla 6×6×6 con simetría cúbica Oh, los q-points de la cuña irreducible
se agrupan naturalmente en tríos: **1 punto general** (pocas simetrías → k-sum completa)
**+ 2 puntos sobre elementos de simetría** (ejes o planos → reducción significativa).
GPAW los recorre en este orden, generando el patrón 1 pesado + 2 ligeros.

La variación entre pesados (1088 vs 1498 vs >3600s) refleja diferencias en la
cantidad de procesos umklapp: cuando k+q cae fuera de la primera zona de Brillouin
se requiere replegamiento, aumentando el número efectivo de pares k únicos incluso
dentro del mismo tipo general de q-point.

### Consecuencia práctica

Conociendo el patrón, se puede estimar el progreso del cálculo G0W0 en tiempo real:
- Al completar 2 ligeros seguidos → el siguiente será pesado (~15-25 min)
- Al completar 1 pesado → los siguientes 2 serán rápidos (~2-5 min cada uno)
- Total off-Γ para 6×6×6 cúbico: 15 q-points = 5 tríos (5 pesados + 10 ligeros)

---

## G0W0 — Viabilidad para propiedades electrónicas y dinámicas (2026-05-26)

### Duración observada y viabilidad

CsPbI₃ (5 átomos, malla 6×6×6, PPA, ecut=100 eV, 4 MPI ranks):
- χ₀ completo: ~14 h
- Auto-energía Σ + corrección QP: ~1-2 h estimado
- **Total: ~15-16 h por material**

Para los 8 materiales del proyecto y un solo cálculo por material:
~15 h × 8 = **120 h de wall clock** (secuencial). Impracticable para un workflow iterativo.
Con los materiales orgánicos de 12 átomos (MAPbI₃, FAPbI₃...) el tiempo se multiplica ×3-5
con PPA → **40-80 h por material**.

**Conclusión:** G0W0 es viable como benchmark de un punto final (gap cuasipartícula de
referencia), pero **no** como método de producción para cribado sistemático ni para
propiedades que requieran múltiples cálculos de energía.

### Fonones y matriz Hessiana: ¿G0W0 viable?

Los fonones por diferencias finitas requieren N_desp cálculos de energía/fuerzas, donde
N_desp ≈ 6 × N_átomos (desplazamientos ±Δ en x,y,z por átomo). Para CsPbI₃:
- N_desp ≈ 30 cálculos DFT (manejable con PBEsol, ~1 h total)
- N_desp × G0W0 = 30 × 15 h = **450 h** → completamente inviable

**Alternativa práctica:** fonones y Hessiana se calculan a nivel PBEsol (o r²SCAN), y G0W0
se aplica solo al gap del estado fundamental relajado. Esto es metodológicamente correcto
porque fuerzas y derivadas de energía dependen de la densidad electrónica (bien descrita
por GGA/MGGA), no del gap de cuasipartícula.

### ¿Un gap con error grande afecta fonones y Hessiana?

**Respuesta corta: mayoritariamente NO**, con excepciones importantes.

Las frecuencias de fonón son derivadas segundas de la energía total respecto a
desplazamientos atómicos. La energía total DFT es funcional de la densidad ρ(r), que
PBEsol/r²SCAN describe bien independientemente del gap. El error en el gap KS no
refleja un error en ρ(r) sino en los eigenvalores — que no entran directamente en la
superficie de energía potencial.

**No afectan:**
- Frecuencias de fonón acústicos y ópticos no-polares
- Constantes de fuerza interatómicas (IFC)
- Identificación de modos imaginarios (inestabilidades estructurales)
- Parámetros de red y geometría del estado fundamental

**Sí pueden afectar (con gap erróneo significativo):**
- **Desdoblamiento LO-TO** (splitting fonón longitudinal-transversal): depende de
  cargas efectivas de Born (Z*) y constante dieléctrica ε_∞ — ambas sensibles al gap.
  Con gap PBE subestimado, ε_∞ se sobreestima → splitting LO-TO erróneo.
- **Cargas efectivas de Born Z***: se calculan como ∂²E/∂u∂E (respuesta al campo E) —
  sensibles a la descripción de estados electrónicos en el gap.
- **Acoplamiento electrón-fonón**: depende fuertemente de la posición de estados en la
  brecha → gap erróneo = acoplamiento erróneo.
- **Materiales incorrectamente metálicos en DFT**: si PBE colapsa el gap a cero (como
  puede ocurrir en algunos Sn-based), las fuerzas se calculan en un estado electrónico
  fundamentalmente incorrecto → fonones erróneos. Esto justifica r²SCAN+U para Sn.

**Estrategia adoptada:** fonones con r²SCAN+U (gap correcto para Sn) + corrección
LO-TO con ε_∞ de G0W0 cuando esté disponible.

---

## G0W0 — Corrida abortada y decisión de corrección scissor (2026-05-26)

### Cronología del fallo

| Hora (UTC-6) | Evento |
|-------------|--------|
| ~14:00 | Lanzamiento de G0W0 para CsPbI₃: 4 ranks MPI, PPA, ecut=100 eV + extrapolación |
| ~14:00–~04:30 (+1 día) | Fase chi0: 20 q-points × (PESADO + ligero + ligero) ≈ 14.5 h |
| ~04:30 (aprox.) | Inicio de fase auto-energía Σ (escritura de self-energy matrix) |
| ~05:00 | **Corte de suministro eléctrico** — proceso GPAW terminado abruptamente |
| 2026-05-26 mañana | Verificación post-apagón: `g0w0.w.txt` congelado en 43 KB (última entrada: chi0 del q-point final); sin `g0w0.json` generado; sin checkpoint de Σ |

El proceso `g0w0_run.py` usa `gpaw.response.g0w0.G0W0`, que escribe resultados únicamente
al final (`g0w0.json`). No hay escritura incremental durante la fase Σ → el trabajo de
~14.5 h de chi0 está completamente perdido.

### Decisión: no relanzar — corrección scissor como alternativa

**Razones para no relanzar G0W0:**

1. **Costo vs. beneficio:** ~15-16 h adicionales para CsPbI₃, con riesgo de nuevo fallo.
   Para los 6 materiales orgánicos (12 átomos, PPA), estimar 40-50 h por material → 
   semanas de cómputo exclusivo.
2. **Hardware:** 22 cores CPU sin aceleración GPU (GPAW 25.7.1b1 no soporta ROCm/CUDA).
   No existe camino de aceleración sin recompilación o hardware adicional.
3. **Cobertura parcial insuficiente:** un solo G0W0 para CsPbI₃ no permite comparación
   sistemática entre los 8 materiales del proyecto.

**Corrección scissor adoptada (+0.5 eV sobre PBE):**

    E_gap^{scissor} = E_gap^{PBE} + 0.5 eV

Fundamentación:
- Liu et al. (2015): G0W0@PBE para CsPbI₃ → corrección +0.44 eV sobre PBE
- Filip & Giustino (2014): G0W0@PBE para MAPbI₃ → corrección +0.47 eV
- Se redondea a 0.5 eV como estimación conservadora

Para CsPbI₃, el groundstate PBE completado antes del apagón dio gap_PBE = 1.288 eV:
- gap_scissor = 1.288 + 0.5 = **1.788 eV** (vs exp 1.73 eV → error 0.06 eV, dentro del objetivo ±0.1 eV)

Para los materiales orgánicos (sin PBE de referencia disponible):
- Se aplica scissor sobre el gap r²SCAN como cota indicativa
- MAPbI₃: 1.864 + 0.5 = 2.364 eV (sobreestima; r²SCAN sin SOC ya excede exp)
- FAPbI₃: 0.652 + 0.5 = 1.152 eV (subestima; artefacto FA no corregido)
- FAPbBr₃: 0.854 + 0.5 = 1.354 eV (subestima; artefacto FA no corregido)

El scissor **no resuelve el artefacto FA**: los CBM de FAPbI₃/FAPbBr₃ caen sobre el
orbital π* del formamidinio. Solo G0W0 completo puede re-ordenar estos orbitales porque
la auto-energía Σ de π* (orbital orgánico difuso) es sistemáticamente menor que la del
Pb-6p (orbital de semicore compacto), corriendo el π* hacia energías más altas y
recuperando el CBM inorgánico.

### Qué hacer si G0W0 es necesario en el futuro

- **Opción 1 — ALIGNN-GW / SchNet@GW:** modelos ML entrenados en gaps G0W0 del AFLOWML
  o JARVIS-DFT; no requieren GPW; inferencia en segundos; precisión ~0.15-0.2 eV.
- **Opción 2 — GPU cluster con GPAW-GPU:** compilar GPAW con CUDA en cluster institucional;
  G0W0 para CsPbI₃ en ~1-2 h con 4× A100.
- **Opción 3 — BerkeleyGW / ABINIT:** códigos alternativos con mejor soporte GPU y
  checkpoint robusto en fase Σ.

Los valores scissor están documentados en el campo `scissor_correction` de cada
`r2scan_bandgap.json` para los cuatro materiales Pb-based.

---

## Figuras top-8: plan y estado (2026-05-26)

### Qué se genera

Para cada uno de los 8 materiales se producen 4 figuras (PNG+PDF) en
`calculations/top8_r2scan/<mat>/figures/`:

| Figura | Script | Contenido |
|--------|--------|-----------|
| `pdos_<mat>` | `top8_figures.py --phase pdos` | PDOS por elemento (B-s, B-p, X-p, org) con EF, gap r²SCAN y gap scissor marcados |
| `bands_<mat>` | `top8_figures.py --phase bands` | Bandas IBZ + overlay SOC .npy donde disponible |
| `dielectric_<mat>` | `top8_figures.py --phase optical` | ε₁(ω) y ε₂(ω) IPA con línea de gap |
| `optical_<mat>` | `top8_figures.py --phase optical` | n(ω), k(ω), α(ω) en escala logarítmica |

### Corrección scissor en figuras Pb-based

Para CsPbI₃, MAPbI₃, FAPbI₃, FAPbBr₃ se aplica un desplazamiento rígido
Δ_scissor = gap_scissor - gap_r²SCAN (leído de `r2scan_bandgap.json`) a todos
los estados por encima de E_F en las figuras. En PDOS y bandas el gap scissor
se marca con línea roja. En los espectros ópticos las transiciones se calculan
con los eigenvalores corregidos.

### Estado al 2026-05-26 — **COMPLETADO**

- **Pb-based completado**: 4 materiales × 4 figuras = 16 archivos PNG+PDF generados ✓
- **Sn-based completado**: tras instalar GPAW master con rpath correcto → 4 materiales × 4 figuras = 16 PNG+PDF ✓
- **Total: 32 figuras generadas** (8 mat × 4 fig = pdos, bands, dielectric, optical)

### GPAW master — fix definitivo de libxc (2026-05-26)

**Problema:** `_gpaw.so` compilado con headers libxc 7 (`.venv/include/xc_version.h:
XC_MAJOR_VERSION=7`) pero linked contra `libxc.so.9` del sistema (libxc 5.2.3) →
`ImportError: xc_func_set_fhc_enforcement undefined symbol`.

**Fix:** añadir `library_dirs` y `extra_link_args` con rpath en `siteconfig.py`:

```python
libraries += ['xc']
library_dirs += ['/home/luis-ochoa/Documents/Vscode/py/dft/.venv/lib']
extra_link_args += ['-Wl,-rpath,/home/luis-ochoa/Documents/Vscode/py/dft/.venv/lib']
compiler = 'mpicc'
mpi = True
```

Después limpiar el build anterior (`rm -rf build/ _gpaw*.so`) y recompilar.
Verificación: `ldd _gpaw*.so | grep xc` debe mostrar `libxc.so.15 => .venv/lib/...`.

**Script de reconstrucción completa post-reboot:**

```bash
# Solo necesario tras reboot (borra /tmp/gpaw_master)
cd /home/luis-ochoa/Documents/Vscode/py/dft
git clone https://gitlab.com/gpaw/gpaw.git /tmp/gpaw_master
cd /tmp/gpaw_master
# siteconfig.py con rpath:
cat > siteconfig.py << 'EOF'
libraries += ['xc']
library_dirs += ['/home/luis-ochoa/Documents/Vscode/py/dft/.venv/lib']
extra_link_args += ['-Wl,-rpath,/home/luis-ochoa/Documents/Vscode/py/dft/.venv/lib']
compiler = 'mpicc'
mpi = True
EOF
/home/luis-ochoa/Documents/Vscode/py/dft/.venv/bin/pip install -e . --no-build-isolation
/home/luis-ochoa/Documents/Vscode/py/dft/.venv/bin/python setup.py build_ext --inplace
# Verificar:
ldd _gpaw*.so | grep xc   # debe mostrar libxc.so.15
.venv/bin/python -c "import gpaw; print(gpaw.__version__)"  # 25.7.1b1
```

---

## Notas de infraestructura

- `/tmp/gpaw_master` se borra en cada reboot — ver sección "GPAW master — cómo reinstalar tras reboot" abajo
- `siteconfig.py` con rpath es **crítico**: sin él se enlaza `libxc.so.9` del sistema (versión 5) en lugar de `libxc.so.15` del venv (versión 7) → `ImportError: xc_func_set_fhc_enforcement`
- Sin ScaLAPACK: crash `BLACSDistribution.desc` en sistemas grandes (FASnBr3, FASnI3)
- `setuptools` debe ser ≥77.0.3 para compilar GPAW master (pyproject.toml license field)
- `pybind11` debe estar instalado en venv para `--no-build-isolation`

---

## GPAW master — cómo reinstalar tras reboot

---

## Pipeline AI — Resultados (2026-05-26)

Ejecución completa de `scripts/ai_pipeline_top8.py` (AI-01 a AI-05) sobre los top-8
perovskitas. Datos guardados en `calculations/top8_r2scan/ai_predictions.json` y figuras
en `calculations/top8_r2scan/figures_ai/`.

### AI-01: Relajación MACE-MP-0 small (L0, 32 M parámetros)

Modelo usado: `20231210mace128L0_energy_epoch249model` (small, ya en caché desde 2026-05-05).
El checkpoint "medium" (`20231203mace128L1_epoch199model`) resultó corrupto (HF descarga
incompleta sin token). Se optó por small — validez comparable para perovskitas haluro.

| Material | a_DFT (Å) | a_MACE (Å) | Δa (Å) | fmax | Conv. |
|----------|:---------:|:----------:|:------:|:----:|:-----:|
| CsSnI3   | 6.200 | 6.251 | +0.051 | 0.0000 | ✓ |
| MASnI3   | 6.240 | 6.317 | +0.077 | 0.0399 | ✓ |
| FASnI3   | 6.310 | 6.451 | +0.141 | 0.0476 | ✓ |
| FASnBr3  | 5.940 | 6.036 | +0.096 | 0.0453 | ✓ |
| CsPbI3   | 6.296 | 6.373 | +0.076 | 0.0000 | ✓ |
| MAPbI3   | 6.310 | 6.448 | +0.138 | 0.0429 | ✓ |
| FAPbI3   | 6.360 | 6.573 | +0.213 | 0.0472 | ✓ |
| FAPbBr3  | 5.990 | 6.124 | +0.134 | 0.0384 | ✓ |

**Obs**: Δa > 0 sistemático (MACE/GGA sobreestima volumen). Error mayor en FA grande
(Δa ≈ +0.21 Å para FAPbI3 — catión voluminoso deforma más la red).

### AI-02: Bandgap semi-empírico y Goldschmidt t

| Material | Eg_semi (eV) | t | AI_score_02 |
|----------|:-----------:|:---:|:-----------:|
| CsSnI3   | 1.30 | 0.854 | 0.789 |
| MASnI3   | 1.30 | 0.914 | 1.035 |
| FASnI3   | 1.30 | 0.990 | 0.461 |
| FASnBr3  | 1.60 | 1.011 | 0.296 |
| CsPbI3   | 1.50 | 0.851 | 1.155 |
| MAPbI3   | 1.50 | 0.912 | 1.583 |
| FAPbI3   | 1.50 | 0.987 | 0.724 |
| FAPbBr3  | 1.80 | 1.008 | 0.000 |

### AI-03: Score AINAGENT (ranking Bayesiano)

Ranking: MAPbI3 (1.985) > CsPbI3 (1.910) > MASnI3 (1.905) > CsSnI3 (1.840) >
FAPbI3 (1.761) > FASnI3 (1.669) > FASnBr3 (1.564) > FAPbBr3 (1.274).
Coincide con ranking DFT en top-2.

### AI-04: MEGNet-MP bandgap (proxy de ALIGNN — ALIGNN roto por DGL)

ALIGNN requiere DGL graphbolt C++ (`libgraphbolt_pytorch_2.11.0.so`) ausente.
MEGNet (matgl 3.0.1) con monkey-patch de broadcast en `_broadcast_to_nodes`.
Requiere `state_attr=torch.tensor([[2]])` (insulator=2 en mfi convention).

| Material | Eg_MEGNet (eV) | Eg_DFT (eV) | Error (eV) |
|----------|:-------------:|:-----------:|:----------:|
| CsSnI3   | 2.398 | 1.359 | +1.04 |
| MASnI3   | 2.124 | 1.584 | +0.54 |
| FASnI3   | 2.772 | 0.771 | +2.00 |
| FASnBr3  | 3.140 | 1.115 | +2.02 |
| CsPbI3   | 2.802 | 1.483 | +1.32 |
| MAPbI3   | 2.223 | 2.054 | +0.17 |
| FAPbI3   | 2.121 | 0.982 | +1.14 |
| FAPbBr3  | 2.403 | 1.079 | +1.32 |

**Obs crítica**: MEGNet sobreestima sistemáticamente +0.2 a +2.0 eV. Entrenado en
óxidos Materials Project → fuera de distribución para haluro perovskitas. Solo sirve
como señal de ranking relativo (no valores absolutos).

### AI-05: Corrección SOC empírica (nueva, 2026-05-26)

Motivación: MEGNet es no-relativista. Corrección ΔEg_SOC por par (A,B) tomada de:
- Even et al. Phys. Rev. Lett. 109, 166805 (2013) — Pb SOC splitting
- Brivio et al. Phys. Rev. B 89, 155204 (2014) — MAPbI3
- Mosconi et al. J. Phys. Chem. C 117, 13902 (2013) — Sn
- Filip & Giustino Phys. Chem. Chem. Phys. 18, 9884 (2016) — FA dilución

| (A,B) | ΔEg_SOC (eV) |
|-------|:-----------:|
| Cs+Pb | -0.50 |
| MA+Pb | -0.55 |
| FA+Pb | -0.20 |
| Cs+Sn | -0.25 |
| MA+Sn | -0.22 |
| FA+Sn | -0.08 |

**Resultado con validación cruzada DFT:**

| Material | Eg_semi_SOC | Eg_MEGNet_SOC | Eg_DFT | Eg_exp | Error_semi_SOC |
|----------|:-----------:|:-------------:|:------:|:------:|:--------------:|
| CsSnI3   | 1.050 | 2.148 | 1.359 | 1.30 | -0.25 |
| MASnI3   | 1.080 | 1.904 | 1.584 | — | — |
| FASnI3   | 1.220 | 2.692 | 0.771 | — | — |
| FASnBr3  | 1.520 | 3.060 | 1.115 | — | — |
| CsPbI3   | 1.000 | 2.302 | 1.483 | 1.73 | -0.73 |
| MAPbI3   | 0.950 | 1.673 | 2.054 | 1.55 | -0.60 |
| FAPbI3   | 1.300 | 1.921 | 0.982 | 1.48 | -0.18 |
| FAPbBr3  | 1.600 | 2.203 | 1.079 | 2.23 | -0.63 |

**Diagnóstico**: Eg_semi_SOC sub-corrige para Pb (error -0.6 a -0.73 eV) porque
B_BASE[Pb]=1.5 eV ya fue calibrado sobre valores experimentales que incluyen SOC
implícitamente. Para la tesis: reportar Eg_semi sin corrección adicional para Pb.
Para Sn, Eg_semi_SOC da CsSnI3=1.05 eV (exp=1.30, error -0.25 eV) — razonable.
MEGNet+SOC mejora parcialmente pero el error residual de distribución (~0.5–2 eV) domina.

---

## AI-06: Espectros AI — DOS, PDOS, dieléctrico y óptico (2026-05-27)

Script: `scripts/ai_spectra_top8.py`. Ejecución paralela (8 workers, `ProcessPoolExecutor`).
64 figuras en `calculations/top8_r2scan/figures_ai/` (4 tipos × 8 materiales × PNG+PDF).

### Modelos AI implementados

| Propiedad | Modelo físico AI | Parámetros | Referencia |
|-----------|-----------------|------------|-----------|
| DOS total | D(E) ∝ m\*^(3/2)·√\|E−Eborde\| (3D parabólica) | m\*_e, m\*_h | Ashcroft & Mermin 1976 |
| m\* efectiva | Kane: m\*_e = Eg/(Eg+P²), P²=20 eV | Eg_semi_soc | Mosconi 2014 |
| m\*_h | 1.3·m\*_e (factor asimétrico) | m\*_e | Mosconi 2014 |
| PDOS | Posiciones orbitales de campo cristalino | composición (A,B,X), Eg | Filip 2016, Even 2013 |
| ε₂(ω) | Tauc-Lorentz: A=40 eV, E₀=1.5·Eg, C=0.5·Eg | Eg_semi_soc | Jellison-Modine 1996 |
| ε_∞ | Penn: clip(1+(14/Eg)², 3.5, 7.0) | Eg_semi_soc | Penn 1962 |
| ε₁(ω) | Kramers-Kronig numérico (trapecio) + ε_∞ | ε₂(ω) | Clásica |

**Herramientas matemáticas auxiliares (no son el contenido AI):** ensanchamiento gaussiano (σ=0.1 eV), K-K numérico.

**Intento JARVIS-DFT-3D para ε_∞:** `jarvis-tools 2026.4.2` instalado y dataset descargado (41 MB).
CsPbI3 **no está** en la base JARVIS-DFT-3D. CsSnI3 existe (JVASP-22675, Pm-3m) pero `epsx='na'`
(DFPT no calculado para esa entrada). Penn fallback usado para los 8 materiales.
ALIGNN sigue roto (DGL: `libgraphbolt_pytorch_2.11.0.so` ausente). CHGNet/matgl solo predicen
energía/fuerzas, no propiedades electrónicas.

### Masas efectivas: Kane vs DFT-SOC

| Material | m\*_e (m₀) | m\*_h (m₀) | Fuente | Nota |
|----------|:---------:|:---------:|--------|------|
| CsSnI3   | 0.0499 | 0.0648 | Kane   | Sn: siempre Kane |
| MASnI3   | 0.0512 | 0.0666 | Kane   | Sn: siempre Kane |
| FASnI3   | 0.0575 | 0.0747 | Kane   | Sn: siempre Kane |
| FASnBr3  | 0.0706 | 0.0918 | Kane   | Sn: siempre Kane |
| CsPbI3   | 0.0453 | 0.0526 | DFT-SOC | electrones ligeros, típico Pb |
| MAPbI3   | 1.264  | 1.296  | DFT-SOC | masas pesadas (distorsión orgánica) |
| FAPbI3   | 1.770  | 9.891  | DFT-SOC | heavy-hole (m\*_h grande pero físico) |
| FAPbBr3  | 0.0741 | 0.0963 | Kane   | flag `UNPHYSICAL_MASS_CBM_SOC:64.32` → Kane |

### Resultados ópticos AI

| Material | Eg_AI_soc (eV) | ε_∞ | n_max | α(2 eV) (cm⁻¹) |
|----------|:-------------:|:---:|:-----:|:--------------:|
| CsSnI3   | 1.050 | 7.0 (Penn) | 3.83 | 1.9×10⁵ |
| MASnI3   | 1.080 | 7.0 (Penn) | 3.80 | 2.0×10⁵ |
| FASnI3   | 1.220 | 7.0 (Penn) | 3.69 | 2.5×10⁵ |
| FASnBr3  | 1.520 | 7.0 (Penn) | 3.50 | 6.3×10⁴ |
| CsPbI3   | 1.000 | 7.0 (Penn) | 3.88 | 1.6×10⁵ |
| MAPbI3   | 0.950 | 7.0 (Penn) | 3.94 | 1.4×10⁵ |
| FAPbI3   | 1.300 | 7.0 (Penn) | 3.63 | 2.2×10⁵ |
| FAPbBr3  | 1.600 | 7.0 (Penn) | 3.46 | 3.3×10⁴ |

Penn ε_∞=7.0 en todos: Eg_semi_soc < 2 eV para todos los materiales → (14/Eg)² > 49 → siempre
clipea al máximo 7.0. Valor razonable (exp haluro perovskitas: 4.5–7.0, Löper 2015).

---

## Comparativa AI vs DFT (2026-05-27)

### Geometría: MACE vs DFT

Δa sistemáticamente positivo (+0.05 a +0.21 Å, 0.8–3.3%). Origen: MACE-MP-0 small entrenado
con GGA/PBE que sobreestima volúmenes. Error mayor en cationes FA orgánicos grandes (FAPbI3: +0.21 Å).
MACE es válido como pre-relajador antes de DFT (reduce ciclos SCF, no como resultado final).

### Bandgap: AI vs DFT+SOC vs experimento

| Material | Eg_semi | Eg_semi_SOC | Eg_DFT+SOC | Eg_exp | Err_semi vs exp | Err_DFT vs exp |
|----------|:-------:|:-----------:|:----------:|:------:|:---------------:|:--------------:|
| CsSnI3   | 1.30 | 1.05 | 1.359 | 1.30 | 0.00 | +0.06 |
| CsPbI3   | 1.50 | 1.00 | 1.483 | 1.73 | −0.23 | −0.25 |
| MAPbI3   | 1.50 | 0.95 | 2.054 | 1.55 | −0.05 | +0.50 |
| FAPbI3   | 1.50 | 1.30 | 0.982 | 1.48 | +0.02 | −0.50 |
| FAPbBr3  | 1.80 | 1.60 | 1.079 | 2.23 | −0.43 | −1.15 |

Conclusiones:
- **Eg_semi (AI-02) da mejor acuerdo con exp que Eg_DFT+SOC para MAPbI3** (−0.05 vs +0.50 eV).
  Esto revela que el modelo semi-empírico B_BASE[Pb]=1.5 eV fue calibrado implícitamente contra
  experimento (que ya incluye SOC y muchos-cuerpos). El DFT r²SCAN sin U sobreestima para MAPbI3.
- **FAPbBr3**: DFT falla gravemente (−1.15 eV vs exp); AI semi-empírico es más cercano (−0.43 eV).
  Indica que r²SCAN sin U es insuficiente para haluros mixtos FA+Br.
- **CsSnI3**: DFT con U=2.5 da el mejor resultado absoluto (+0.06 eV). AI sin SOC reproduce exp exacto.
- **AI-05 (SOC empírico) sobre-corrige Pb**: B_BASE[Pb] ya incluye SOC implícitamente → doble corrección.
  Para tesis: **usar Eg_semi (sin AI-05) como predictor AI para Pb**; AI-05 válido solo para Sn.

### DOS: parabólica AI vs DFT

La DOS parabólica 3D captura correctamente el **orden de masas** y la tendencia de anchura de banda:
- CsPbI3 (m\*=0.05 m₀): DOS ancha, alta mobilidad esperada. Consistente con DFT.
- MAPbI3 (m\*=1.3 m₀): DOS estrecha, masas pesadas por distorsión orgánica. Consistente con DFT.
- FAPbI3 heavy-hole (m\*_h=9.89 m₀): cola VB extremadamente angosta. Físicamente esperado (DFT confirma).
- FAPbBr3 Kane (m\*~0.07): Kane fallback evita artefacto m\*=64 m₀.

Limitaciones del modelo parabólico:
- No reproduce hibridación Pb-s/I-p en VBM (solo parábola continua).
- No captura estados orgánicos (N-2p, C-2p) que DFT muestra a −3 a −5 eV.
- PDOS de campo cristalino es cualitativamente correcto pero posiciones de pico son literatura
  para fase cúbica ideal — materiales FA distorsionados pueden variar ±0.3 eV.

### Función dieléctrica: Tauc-Lorentz AI vs DFT

| Propiedad | AI (TL) | DFT GPAW | Exp (CsPbI3) |
|-----------|:-------:|:--------:|:------------:|
| Onset ε₂ | cuadrático (ħω−Eg)² | abrupto (transiciones verticales) | — |
| n_max | 3.4–3.9 | 2.5–3.5 | ~3.0 (Löper 2015) |
| ε₁(0) ≈ ε_∞ | 7.0 (Penn, clamped) | — | ~4.5–5.0 (CsPbI3) |
| α(2 eV) | 10⁴–10⁵ cm⁻¹ | ~10⁴–10⁵ cm⁻¹ | ~10⁴–10⁵ cm⁻¹ |

AI sobreestima n_max en ~10–20% respecto a DFT (Penn ε_∞ alto). La forma del espectro es cualitativamente
correcta: onset en Eg, pico de ε₂ cerca de E₀=1.5·Eg, cruce de ε₁ por cero cerca del pico.
α(ω) está en el rango correcto para fotovoltaica (absorción fuerte en visible).

### Resumen de capacidades AI vs DFT

| Propiedad | AI (este trabajo) | DFT r²SCAN+SOC | Ganancia AI |
|-----------|:-----------------:|:--------------:|:-----------:|
| Geometría (a₀) | ±1–3% (MACE) | ±0.3% | 10× más rápido |
| Bandgap | ±0.05–0.5 eV | ±0.06–0.5 eV | comparable |
| DOS cualitativa | ✓ (tendencias) | ✓ (cuantitativa) | screening rápido |
| m\* | Kane ±20% / DFT-SOC | ±15% | — |
| ε₂(ω) espectral | onset correcto, forma aproximada | cuantitativa | cualitativa suficiente |
| n, k, α | orden magnitud correcto | cuantitativo | screening óptico |
| Tiempo/material | ~2 s (AI) | 2–10 h (DFT) | ~10000× |

**Conclusión**: el pipeline AI es viable para **screening de primer nivel** (selección de candidatos,
tendencias) a costo computacional despreciable. Para diseño de dispositivos (OghmaNano, eficiencia)
se requiere DFT+SOC cuantitativo.

---

`/tmp/gpaw_master` no persiste entre reboots. Ejecutar este bloque para restaurar:

```bash
cd /home/luis-ochoa/Documents/Vscode/py/dft

# 1. Clonar
git clone https://gitlab.com/gpaw/gpaw.git /tmp/gpaw_master

# 2. siteconfig.py con rpath (OBLIGATORIO — sin esto importar falla)
cat > /tmp/gpaw_master/siteconfig.py << 'EOF'
libraries += ['xc']
library_dirs += ['/home/luis-ochoa/Documents/Vscode/py/dft/.venv/lib']
extra_link_args += ['-Wl,-rpath,/home/luis-ochoa/Documents/Vscode/py/dft/.venv/lib']
compiler = 'mpicc'
mpi = True
EOF

# 3. Instalar paquete Python y compilar extensión C
cd /tmp/gpaw_master
/home/luis-ochoa/Documents/Vscode/py/dft/.venv/bin/pip install -e . --no-build-isolation
/home/luis-ochoa/Documents/Vscode/py/dft/.venv/bin/python setup.py build_ext --inplace

# 4. Verificar
ldd /tmp/gpaw_master/_gpaw*.so | grep xc
# → libxc.so.15 => /home/luis-ochoa/.../dft/.venv/lib/libxc.so.15
/home/luis-ochoa/Documents/Vscode/py/dft/.venv/bin/python -c "import gpaw; print(gpaw.__version__)"
# → 25.7.1b1
```

**Tiempo estimado:** ~5 min (clone) + ~3 min (compilación C) = ~8 min total.
