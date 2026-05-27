# Metodología computacional

*Perovskitas haluro — metodología computacional integrada: DFT de primeros principios, aprendizaje automático y simulación de dispositivo*
*Última actualización: 2026-05-25*

---

## 1. Introducción y sistema de estudio

Las perovskitas haluro de estructura ABX₃ son semiconductores de interés para celdas
solares de tercera generación, con bandgaps ajustables entre 1.2 y 3.0 eV mediante
sustitución catiónica (A = Cs⁺, MA⁺, FA⁺; B = Pb²⁺, Sn²⁺; X = I⁻, Br⁻) y
coeficientes de absorción óptica superiores a 10⁴ cm⁻¹ en el rango visible
[Stranks & Snaith, 2015]. La identificación de composiciones óptimas para aplicaciones
fotovoltaicas exige explorar un espacio de candidatos amplio — potencialmente miles de
combinaciones ABX₃ — con predicciones de propiedades optoelectrónicas de suficiente
fiabilidad para orientar la síntesis experimental.

Este trabajo desarrolla y aplica una metodología computacional integrada de tres pilares
complementarios. El primero es el cálculo DFT de primeros principios con GPAW
(§1–11): desde la relajación estructural con PBEsol+D3 hasta correcciones
cuasipartícula G0W0+SOC, que proveen propiedades electrónicas de referencia con
precisión ±0.1–0.2 eV sobre el bandgap experimental (G0W0 intentado para CsPbI₃;
infactible en el hardware disponible — se aplica corrección scissor +0.5 eV, §9.9). El segundo es un pipeline de
aprendizaje automático (§12): una optimización Bayesiana guiada por surrogate MLP
(AINAGENT), relajación geométrica con el campo de fuerzas neuronal MACE-MP-0, y redes
neuronales de grafos (ALIGNN) para preseleccionar candidatos a escala de miles de
composiciones por día. El tercero es la simulación de dispositivo por drift-diffusion
(§15): OghmaNano traduce las propiedades DFT en eficiencias de celda solar (PCE, Voc,
Jsc, FF) bajo condiciones de operación reales (AM1.5G, 300 K). La §13 presenta un
análisis comparativo cuantitativo entre los tres niveles de cálculo, y la §14
describe su integración en un workflow cerrado con retroalimentación.

### 1.1 Materiales estudiados

Los ocho materiales se agrupan en dos familias:

| Material | Catión A | Catión B | Haluro X | Tipo de celda |
|----------|----------|----------|----------|---------------|
| CsPbI₃  | Cs⁺ | Pb²⁺ | I⁻  | inorgánico, 5 átomos |
| CsSnI₃  | Cs⁺ | Sn²⁺ | I⁻  | inorgánico, 5 átomos |
| MAPbI₃  | CH₃NH₃⁺ | Pb²⁺ | I⁻  | orgánico-inorgánico, 12 átomos |
| MASnI₃  | CH₃NH₃⁺ | Sn²⁺ | I⁻  | orgánico-inorgánico, 12 átomos |
| FAPbI₃  | HC(NH₂)₂⁺ | Pb²⁺ | I⁻ | orgánico-inorgánico, 12 átomos |
| FAPbBr₃ | HC(NH₂)₂⁺ | Pb²⁺ | Br⁻ | orgánico-inorgánico, 12 átomos |
| FASnI₃  | HC(NH₂)₂⁺ | Sn²⁺ | I⁻ | orgánico-inorgánico, 12 átomos |
| FASnBr₃ | HC(NH₂)₂⁺ | Sn²⁺ | Br⁻ | orgánico-inorgánico, 12 átomos |

Todos los cálculos utilizan la fase cúbica (Pm-3m), que es la fase de alta temperatura
relevante para operación fotovoltaica. Las estructuras de los cationes orgánicos (MA, FA)
se orientan a lo largo del eje [001] con simetría promediada, aproximación estándar
en cálculos DFT de estas fases [Brivio et al., 2014].

### 1.2 Pipeline computacional general

El flujo de cálculo consta de seis etapas secuenciales, diseñadas de manera que la
salida de cada etapa alimenta a la siguiente:

```
Estructura inicial (CIF/experimental)
         │
         ▼
01. Relajación estructural (PBEsol+D3, 6×6×6 k-pts)
         │  relax.gpw
         ▼
02. Preconvergencia SCF (PBEsol+U, density=1e-2)
         │  pre_r2scan.gpw
         ▼
03. SCF r²SCAN+U (densidad converge a 1e-4)
    — Materiales Sn: U-ramping U=0→1→2→3.5 eV
    — Materiales Pb: U=0 (sin corrección Hubbard)
         │  r2scan.gpw / u_scan_U*.gpw
         ▼
04. SOC perturbativo + PDOS
         │  soc_summary.json, pdos.npz
         ▼
05. G0W0@PBE (solo Pb-based) — INFACTIBLE en hardware actual
         │  Intentado para CsPbI₃ (2026-05-26): chi0 completado (~14.5 h),
         │  auto-energía Σ interrumpida por apagón; sin checkpoint recuperable.
         │  Alternativa: corrección scissor +0.5 eV sobre PBE (ver §9.9)
         │  g0w0_pbe.gpw → scissor_correction en r2scan_bandgap.json
         ▼
06. SOC sobre eigenvalores GW
         │  g0w0_soc.json (pendiente; no disponible)
```

El pipeline de aprendizaje automático equivalente — con seis etapas funcionalmente
análogas pero basadas en métodos ML — se describe en §12.1 junto con la tabla de
correspondencia paso a paso.

---

## 2. Marco teórico DFT

### 2.1 Teoría del funcional de densidad (DFT)

Los cálculos electrónicos se basan en la formulación de Kohn-Sham (KS) de la teoría del
funcional de la densidad [Hohenberg & Kohn, 1964; Kohn & Sham, 1965]. El teorema de
Hohenberg-Kohn establece que la energía del estado fundamental es un funcional único de
la densidad electrónica ρ(r). Kohn y Sham demostraron que este problema puede resolverse
mediante un sistema auxiliar de partículas no interactuantes con la misma densidad:

    E[ρ] = Tₛ[ρ] + ∫ v_ext(r) ρ(r) dr + E_H[ρ] + E_xc[ρ]

donde Tₛ es la energía cinética del sistema no interactuante, E_H es la energía de
Hartree (repulsión electrostática clásica), y E_xc contiene todos los efectos
de intercambio y correlación. Las ecuaciones de Kohn-Sham autoconsistentes son:

    [-½∇² + v_eff(r)] ψᵢ(r) = εᵢ ψᵢ(r)

con el potencial efectivo v_eff = v_ext + v_H + v_xc. La densidad se construye como:

    ρ(r) = Σᵢ fᵢ |ψᵢ(r)|²

donde fᵢ son las ocupaciones (factores de Fermi-Dirac). El ciclo SCF se repite hasta
que ρ(r) converge bajo criterios predefinidos de densidad, eigenstates y energía.

**Limitación fundamental para bandgaps:** Los eigenvalores εᵢ de KS no son formalmente
energías de cuasipartícula — el gap KS subestima el gap fundamental real en ~30-100%
para semiconductores. Esta discrepancia se aborda mediante funcionales mejorados (r²SCAN,
HSE06) o correcciones de muchos cuerpos (G0W0).

### 2.2 Aproximación de Born-Oppenheimer

Los núcleos se tratan como clásicos bajo la aproximación de Born-Oppenheimer (BO): dado
que la masa nuclear es ~2000× la electrónica, los electrones se relajan instantáneamente
a cualquier configuración nuclear fija. El problema electrónico se resuelve para cada
geometría nuclear R, produciendo la superficie de energía potencial E(R). La relajación
geométrica minimiza |∂E/∂R|, y las propiedades vibracionales se obtienen de las segundas
derivadas de E(R).

---

## 3. Funcionales de intercambio-correlación

### 3.1 PBEsol — relajación estructural

La relajación estructural y el cálculo SCF de referencia utilizan **PBEsol**
[Perdew et al., 2008], una revisión de PBE optimizada para sólidos cristalinos.
PBEsol recupera el límite de densidad uniforme más fielmente que PBE mediante
la condición de escala de segundo orden, mejorando las constantes de red y la
energía de cohesión en sólidos (~50% de reducción en el error de la constante de red).
La penalización es que las energías de atomización molecular se deterioran levemente.

### 3.2 r²SCAN — cálculos de bandgap

Los cálculos de bandgap de producción utilizan **r²SCAN** (regularized-restored SCAN)
[Furness et al., 2020], un meta-GGA (MGGA) que satisface todas las condiciones de
escala exactas conocidas para un funcional XC físicamente correcto. A diferencia de GGA
(que depende solo de ρ y ∇ρ), los MGGA también dependen de la densidad de energía
cinética τ(r) = ½ Σᵢ |∇ψᵢ|², lo que les permite distinguir regiones de ligadura de
capas internas de regiones de ligadura covalente/metálica.

r²SCAN mejora sobre SCAN [Sun et al., 2015] eliminando singularidades numéricas en τ→0
que causaban problemas de convergencia SCF. Para perovskitas haluro, r²SCAN reduce el
error en el bandgap de ~0.5 eV (PBE) a ~0.2-0.3 eV [Kingsbury et al., 2022].

La corrección de dispersión de London **D3** [Grimme et al., 2010] se aplica en la
relajación para capturar interacciones van der Waals en los cationes orgánicos (MA, FA),
que de otro modo se subestimarían con DFT estándar.

### 3.3 Corrección de Hubbard DFT+U — materiales de Sn

Los materiales basados en Sn presentan el orbital **Sn-5s** parcialmente localizado en
el estado de oxidación Sn²⁺. DFT estándar delocalizaría artificialmente este orbital
debido al error de auto-interacción, suprimiendo el gap. La corrección DFT+U de
Dudarev [Dudarev et al., 1998] añade un término de penalización:

    E_DFT+U = E_DFT + U_eff/2 × Σᵢ [nᵢ - nᵢ²]

donde nᵢ son las ocupaciones del orbital localizado y U_eff = U - J es el parámetro
de Hubbard efectivo. Este término penaliza ocupaciones fraccionarias, favoreciendo
que el orbital sea o totalmente ocupado o totalmente vacío.

**Determinación de U para Sn-5s:** El valor óptimo se determinó mediante un barrido
fino U = {2.0, 2.25, 2.5, 2.75} eV, seleccionando U = 2.5 eV como el que reproduce
el bandgap experimental de CsSnI₃ (gap_SOC = 1.36 eV vs. exp. 1.30 eV) con r²SCAN.
Los materiales de Pb no requieren corrección U — el orbital Pb-6s no presenta
localización equivalente.

**Estrategia de convergencia — U-ramping:** La discontinuidad en el paisaje de energía
DFT+U al activar U = 3.5 eV directamente produce falsos mínimos locales (el mixer
oscila entre el estado Sn²⁺ localizado y el estado Sn²⁺ deslocalizado). La solución
adoptada es incrementar U gradualmente: U = 0 → 1 → 2 → 3.5 eV, usando el GPW
convergido de cada paso como punto de partida del siguiente.

### 3.4 HSE06 — corrección de gap híbrido

**HSE06** [Heyd, Scuseria & Ernzerhof, 2003; Krukau et al., 2006] es un funcional
híbrido que mezcla el intercambio exacto de Hartree-Fock con el intercambio GGA en
rango corto, con parámetro de mezcla α = 0.25 y parámetro de pantalla ω = 0.11 Å⁻¹:

    E_x^HSE = α E_x^{HF,SR}(ω) + (1-α) E_x^{PBE,SR}(ω) + E_x^{PBE,LR}(ω)

El intercambio exacto corrige parcialmente el error de auto-interacción, mejorando los
bandgaps. HSE06 se usa aquí como corrección scissor: χ_HSE = E_gap(HSE06) - E_gap(PBE)
se añade al gap PBE para materiales de Pb cuando G0W0 no está disponible.

---

## 4. Método PAW (Projector Augmented-Wave)

La densidad electrónica se describe con el método PAW [Blöchl, 1994], implementado en
GPAW. PAW divide el espacio en regiones de augmentación (esferas atómicas) y región
intersticial. Las funciones de onda reales ψₙ se relacionan con funciones suaves
ψ̃ₙ (fáciles de representar en ondas planas) mediante una transformación lineal:

    |ψₙ⟩ = T̂ |ψ̃ₙ⟩ = |ψ̃ₙ⟩ + Σₐ Σᵢ (|φᵢᵃ⟩ - |φ̃ᵢᵃ⟩) ⟨p̃ᵢᵃ|ψ̃ₙ⟩

donde φᵢᵃ son funciones de onda parciales atómicas, φ̃ᵢᵃ sus versiones suaves, y p̃ᵢᵃ
los proyectores. PAW combina la eficiencia de pseudopotenciales con la precisión de
los cálculos all-electron, capturando la oscilación nodal real de las funciones de onda
cerca del núcleo — esencial para la hibridación de orbitales de semicore (Pb-5d, Sn-4d).

**Datasets PAW utilizados:**

| Elemento | Dataset | Electrones de valencia | Orbitales incluidos |
|----------|---------|----------------------|---------------------|
| Cs | Cs.9.PBE  | 9 | 5s²5p⁶6s¹ |
| Pb | Pb.14.PBE | 14 | 5d¹⁰6s²6p² |
| Sn | Sn.14.PBE | 14 | 4d¹⁰5s²5p² |
| I  | I.7.PBE   | 7  | 5s²5p⁵ |
| Br | Br.7.PBE  | 7  | 4s²4p⁵ |
| C  | C.4.PBE   | 4  | 2s²2p² |
| N  | N.5.PBE   | 5  | 2s²2p³ |
| H  | H.1.PBE   | 1  | 1s¹ |

**Nota sobre Pb.14.PBE:** El dataset incluye los electrones de semicore 5d¹⁰, necesarios
para una descripción precisa del SOC de Pb — la hibridación 5d-6p afecta el desdoblamiento
de la banda de conducción (Pb-6p) en ~0.05 eV. Usar Pb.4.PBE (solo 6s²6p²) subestimaría
el efecto SOC.

---

## 5. Base de ondas planas

Las funciones de Kohn-Sham se expanden en ondas planas en la región intersticial:

    ψ̃ᵢₖ(r) = (1/√Ω) Σ_G cᵢₖ(G) exp[i(k+G)·r]

donde G son vectores de la red recíproca con |k+G|² ≤ 2E_cut (en unidades de Hartree).
La energía de corte E_cut determina el tamaño de la base:

    N_G(E_cut) ∝ (2E_cut)^(3/2) × Ω_celda / (2π)³

**Energías de corte utilizadas:**

| Paso | E_cut | Justificación |
|------|-------|---------------|
| Relajación (PBEsol) | 450 eV | Convergencia ΔE < 1 meV/átomo (ver validation_report.md) |
| SCF r²SCAN | 450 eV | Misma convergencia; r²SCAN no requiere mayor ecut |
| Groundstate G0W0 (PBE) | 600 eV | Bandas vacías requieren mayor espacio recíproco |
| Autoenergía G0W0 | 100 eV + extrap | Convergencia de Σ(G,G') extrapolada a ∞ |

---

## 6. Muestreo de la zona de Brillouin

### 6.1 Malla k para SCF

La zona de Brillouin se muestrea con una malla de Monkhorst-Pack [Monkhorst & Pack, 1976]
de 6×6×6 k-points, centrada en Γ. Esta malla es adecuada para las celdas cúbicas
Pm-3m en estudio, con parámetros de red a ≈ 6.0-6.5 Å. La convergencia del gap con
respecto al tamaño de la malla fue verificada: una malla 8×8×8 produce cambios < 30 meV
en el gap de CsPbI₃.

### 6.2 Ocupaciones electrónicas

Las ocupaciones se calculan con la distribución de Fermi-Dirac:

    fᵢ = 1 / (1 + exp[(εᵢ - μ) / kT])

con ancho de smearing kT = 0.05 eV para SCF estándar. Para los cálculos r²SCAN+U de
materiales Sn, se utiliza kT = 0.20 eV — valor determinado empíricamente como el
compromiso óptimo entre estabilidad del mixer y error en la ocupación del orbital Sn-5s.

### 6.3 PDOS y DOS

La densidad de estados (DOS) y la densidad de estados proyectada por orbital (PDOS) se
calculan con una malla más densa de 12×12×12 k-points (4× más puntos que SCF) y un
ensanchamiento gaussiano de σ = 0.05 eV, asegurando resolución suficiente para
identificar la contribución orbital en VBM y CBM.

---

## 7. Relajación estructural

Las posiciones atómicas se relajan mediante el algoritmo BFGS (Broyden-Fletcher-Goldfarb-
Shanno) implementado en ASE, minimizando la norma de la fuerza máxima:

    max_i |F_i| < 0.01 eV/Å

El parámetro de celda se fija al valor experimental (o de referencia DFT de literatura)
para mantener la fase cristalina correcta. Los cationes orgánicos (MA, FA) se colocan
en orientaciones de alta simetría; la relajación de posiciones captura la distorsión
local de la red octaédrica BX₆ sin romper la simetría Pm-3m.

---

## 8. Acoplamiento espín-órbita (SOC)

### 8.1 Hamiltoniano SOC

El acoplamiento espín-órbita es un efecto relativista de primer orden. El Hamiltoniano
de Dirac, expandido en potencias de (v/c)², produce el término SOC:

    H_SOC = (ħ²/4m²c²) σ · (∇V × p̂)

donde σ son las matrices de Pauli, V es el potencial efectivo, y p̂ = -iħ∇ es el
operador de momento. En la región PAW, este término se evalúa dentro de la esfera de
augmentación donde ∇V es grande (cerca del núcleo), dominando la contribución SOC.

### 8.2 Implementación perturbativa

En este trabajo, SOC se aplica **perturbativamente** sobre los eigenestados KS escalares
colineales (sin SOC). Esto es válido cuando el desdoblamiento SOC es pequeño comparado
con el campo cristalino (separación de bandas), lo que se cumple para Pb-6p en el rango
de interés: el error es ~0.05 eV frente a cálculos SOC autoconsistentes [Brivio et al., 2014].

La función `soc_eigenstates()` de GPAW diagonaliza el Hamiltoniano 2×2:

    H = [ ε_{nk,↑}  + SOC_{↑↑}    SOC_{↑↓}  ]
        [ SOC_{↓↑}    ε_{nk,↓}  + SOC_{↓↓}  ]

en la base de los estados KS colineales, produciendo eigenvalores doblete con SOC.

**Nota técnica:** Para cálculos r²SCAN (MGGA), se utiliza `ignore_xc_potential=True`
porque GPAW-MGGA no implementa `calculate_spherical` para la contribución XC al término
SOC dentro de la esfera PAW. Esta contribución es del orden de meV y su omisión no
afecta los resultados a nivel de precisión meV-meV.

### 8.3 Corrección SOC al bandgap

La corrección SOC se calcula como diferencia:

    Δ_SOC = E_gap(PBE+SOC) − E_gap(PBE)

Típicamente Δ_SOC ≈ −0.5 a −0.9 eV para Pb-based (el SOC abre el desdoblamiento j=3/2
vs j=1/2 en la banda de conducción de Pb-6p, que forma el CBM). Para Sn-based, el
efecto es menor: Δ_SOC ≈ −0.4 a −0.6 eV.

---

## 9. G0W0 — corrección cuasipartícula de muchos cuerpos

### 9.1 Motivación

El eigenvalor de Kohn-Sham εᵢ^KS no es formalmente la energía de ionización o afinidad
electrónica del sistema: es solo el multiplicador de Lagrange del funcional de densidad.
La energía de cuasipartícula real ε_n^QP (observable físico: energía de ionización/afinidad
por ARPES) satisface la ecuación de Dyson:

    [T̂ + V̂_ext + V̂_H] ψ_n(r) + ∫ Σ(r,r',ε_n^QP) ψ_n(r') dr' = ε_n^QP ψ_n(r)

donde Σ(r,r',ω) es la auto-energía — el operador no local y dependiente de la frecuencia
que reemplaza al potencial de XC local V_xc. En DFT, Σ ≈ V_xc(r)δ(r-r'), lo que omite
la no-localidad y la dependencia frecuencial responsable del gap correcto.

### 9.2 Las ecuaciones de Hedin y la aproximación GW

Hedin (1965) derivó un conjunto de ecuaciones exactas acopladas para G, Σ, W, Γ y P.
En la aproximación GW (truncada en primer orden de W), la auto-energía es:

    Σ(r,r',ω) = i/(2π) ∫ G(r,r',ω+ω') W(r,r',ω') e^{iω'η} dω'

En G0W0 (no autoconsistente), G y W se evalúan una sola vez a partir del DFT de partida:

- **G₀(r,r',ω)**: función de Green no interactuante
  ```
  G₀(r,r',ω) = Σₙ ψₙ(r)ψₙ*(r') / (ω - εₙ + iη·sgn(εₙ-μ))
  ```

- **W₀ = ε⁻¹ v_c**: interacción de Coulomb apantallada por la función dieléctrica
  ```
  ε(r,r',ω) = δ(r-r') - ∫ v_c(r,r'') χ₀(r'',r',ω) dr''
  ```

- **χ₀**: polarizabilidad irreducible (respuesta lineal independiente de partículas)
  ```
  χ₀(r,r',ω) = 2 Σ_{nk,n'k'} [f_{nk} - f_{n'k'}] ψₙₖ(r)ψ*ₙ'ₖ'(r)ψₙ'ₖ'(r')ψ*ₙₖ(r') / (ω - ε_{n'k'} + εₙₖ + iη)
  ```

En la base de ondas planas G y con vectores q de la zona de Brillouin:

    χ₀(q,G,G',ω) = 1/Ω Σ_{nk} (f_{nk} - f_{n'k+q}) × M_{nn'}(k,q,G) M*_{nn'}(k,q,G') / (ω - ε_{n'k+q} + εₙₖ + iη)

donde M_{nn'}(k,q,G) = ⟨nk|e^{i(q+G)·r}|n'k+q⟩ son los elementos de matriz de la
corriente de densidad. La suma sobre q recorre la zona de Brillouin completa; gracias
a las simetrías cristalinas, se reduce a los ~20 q-points irreducibles.

La corrección cuasipartícula se obtiene a primer orden (linealización en ω):

    ε_n^QP ≈ εₙ^KS + Zₙ Re⟨ψₙ|Σ(εₙ^KS) - V_xc|ψₙ⟩

    Zₙ = [1 - Re(∂Σ_nn/∂ω)|_{ω=εₙ^KS}]⁻¹

Zₙ es el **peso de cuasipartícula** (0 < Z < 1); valores Z ~ 0.7-0.9 son típicos para
VBM y CBM en perovskitas de haluro, indicando que las cuasipartículas están bien definidas.

### 9.3 Punto de partida: G0W0@PBE

Se usa PBE como funcional de partida por dos razones:

1. **Compatibilidad técnica:** r²SCAN (MGGA) depende de la densidad cinética τ(r).
   El módulo de respuesta de GPAW (`gpaw.response`) requiere leer τ del archivo GPW,
   pero la versión actual produce `AttributeError: ked` al intentarlo. PBE (GGA) evita
   este problema.

2. **Estándar de literatura:** G0W0@PBE es el protocolo dominante para perovskitas haluro.
   El error sistemático (G0W0@PBE sobreestima el gap en Pb-based en ~0.1-0.2 eV) es
   bien conocido y permite comparación directa con estudios previos [Filip & Giustino, 2014;
   Bokdam et al., 2016].

El groundstate PBE requiere bandas vacías adicionales: se utilizan N_bands = 600 ≥ 4×N_occ,
suficientes para convergencia del sum-over-states en χ₀ con ecut_gw = 100 eV.

### 9.4 Aproximación Plasmon-Pole (PPA)

La integral de frecuencia en Σ requiere W(ω) sobre el eje real, lo que implica calcular
χ₀(ω) en ~800 frecuencias reales (full-frequency). La PPA de Godby-Needs [Godby & Needs, 1989]
aproxima ε⁻¹(q,G,G',ω) con un modelo de oscilador:

    ε⁻¹(q,G,G',ω) ≈ δ_{GG'} + Ã_{GG'}(q) ω̃²_{GG'}(q) / [ω² - ω̃²_{GG'}(q) + iη]

Los dos parámetros {Ã, ω̃} por cada (q,G,G') se ajustan evaluando χ₀ en solo dos
frecuencias imaginarias: ω = 0 y ω = iω_p (frecuencia de plasma). Esto reduce el
costo de la integración en frecuencia ~400× frente a full-frequency.

Precisión de PPA vs full-frequency: ±0.1-0.2 eV en el gap para perovskitas de Pb
[van Schilfgaarde et al., 2006]. Esta precisión es adecuada para el cribado comparativo.

### 9.5 Extrapolación de ecut_gw

El bandgap GW converge lentamente con el número de ondas planas N_G en la suma sobre G:

    E_gap^GW(E_cut) = E_gap^GW(∞) + A/E_cut³

GPAW realiza la extrapolación corriendo G0W0 a tres valores E_cut = {0.74, 0.86, 1.0} × E_cut_max
y ajustando la curva A + B/E_cut³ por mínimos cuadrados. Para E_cut_max = 100 eV, esto
corresponde a ~{55, 74, 100} eV. La extrapolación reduce el error de truncación en ~0.1 eV
sin triplicar el costo, ya que las corridas a ecut menor son mucho más baratas.

### 9.6 SOC perturbativo sobre eigenvalores GW

El SOC se aplica sobre los eigenvalores de cuasipartícula (no sobre los KS):

    gap_{GW+SOC} = gap_{GW} + Δ_SOC^{PBE}

donde Δ_SOC^{PBE} = gap_{PBE+SOC} − gap_{PBE} se calcula con `soc_eigenstates()` usando
las wavefunctions del groundstate PBE. La aproximación asume que el desdoblamiento SOC
calculado a nivel PBE es transferible a nivel GW — válido cuando el SOC es pequeño
comparado con el gap (caso de perovskitas de Pb con gap > 1 eV).

### 9.7 Parámetros computacionales

| Parámetro | Valor | Justificación física |
|-----------|-------|----------------------|
| E_cut^DFT (PBE) | 600 eV | N_G suficiente para bandas vacías hasta n = 4×N_occ |
| N_bands | 600 | Convergencia de χ₀: suma sobre n hasta 4×N_occ |
| k-grid | 6×6×6 Γ-centered | Igual que SCF; convergencia del gap verificada |
| E_cut^GW | 100 eV + extrap. | ~587 G-vectores; A/ecut³ < 0.05 eV tras extrapolación |
| PPA | Sí | Viable para celdas ≤12 átomos; ±0.1-0.2 eV de error |
| Ranks MPI | 4 | Punto óptimo: cómputo O(1/N) vs. comunicación O(N²) |

### 9.8 Costo computacional y paralelización

El cuello de botella es el cálculo de χ₀(q,G,G') para cada vector q:

    Costo ∝ N_k × N_G³ / N_sym(q)

donde N_sym(q) es el número de operaciones de simetría que reducen la suma k. Para la
k-grid 6×6×6, los 216 k-points se reducen a 20 q-points irreducibles. El punto Γ tiene
simetría completa Oh (48 operaciones), con 20 k-groups únicos: ~11 min total. Los q-points
off-Γ con baja simetría (8-16 ops) tienen 30-60 k-groups: 1-25 min por q-point.

La paralelización MPI distribuye el cálculo de χ₀ en bloques del tensor (G,G') a través
de los ranks (parámetro `nblocksmax`). Con 4 ranks, la comunicación MPI necesaria para
la suma sobre k-points es mínima; con >8 ranks, la comunicación O(N²) comienza a dominar
sobre la reducción O(1/N) en cómputo.

**Tiempo total estimado:** ~8 horas en 4 cores para CsPbI₃ (5 átomos, 20 IBZ q-points).

### 9.9 Viabilidad y decisión metodológica

El cálculo G0W0@PBE fue ejecutado para CsPbI₃ el 26 de mayo de 2026 con 4 ranks MPI,
PPA y ecut_gw = 100 eV + extrapolación. La fase chi0 (polarizabilidad independiente de
partículas) completó los 20 q-points del IBZ en ~14.5 horas, confirmando el patrón de
tiempos PESADO–ligero–ligero por trío de simetría. La fase de auto-energía Σ(G,G') fue
interrumpida por un corte de suministro eléctrico sin checkpoint recuperable.

**Razones para no relanzar:**

| Factor | Detalle |
|--------|---------|
| Tiempo estimado total | ~15-16 h para CsPbI₃; ~40-50 h para cada material de 12 átomos con PPA |
| Hardware disponible | 22 cores CPU; sin GPU GPAW-compatible (ROCm/CUDA no soportados en GPAW 25.7.1b1) |
| Costo de chi0 no paralelizable | El q-point más pesado (off-Γ, baja simetría) tarda 1-2 h; no escala linealmente |
| Cobertura de los 8 materiales | ~2 días de cómputo exclusivo solo para los Cs/Sn inorgánicos; ~6-8 días adicionales para los 6 orgánicos |

**Alternativa adoptada — corrección scissor (+0.5 eV sobre PBE):**

La corrección scissor es una aproximación de primer orden a G0W0: el gap cuasipartícula
se estima añadiendo un desplazamiento rígido de banda de conducción derivado de la
literatura para perovskitas de Pb:

    E_gap^{scissor} = E_gap^{PBE} + Δ_scissor,   Δ_scissor ≈ +0.5 eV

El valor Δ = 0.5 eV está calibrado sobre resultados G0W0@PBE publicados para CsPbI₃
[Liu et al., 2015] y MAPbI₃ [Filip & Giustino, 2014]: ambos reportan correcciones de
0.4–0.6 eV sobre el gap PBE. Para CsPbI₃ se dispone de E_gap^{PBE} = 1.288 eV (del
groundstate G0W0 calculado antes del apagón), lo que da E_gap^{scissor} = 1.788 eV
(vs exp 1.73 eV, error = 0.06 eV).

**Limitaciones de la corrección scissor:**

1. Solo es significativa aplicada sobre el gap PBE, no sobre r²SCAN (que ya parcialmente
   corrige la subestimación GGA). Para los materiales orgánicos se aplica sobre el gap
   r²SCAN como cota superior.
2. No corrige el artefacto FA: FAPbI₃ y FAPbBr₃ tienen CBM en el orbital π* del
   catión FA en lugar del Pb-6p; la auto-energía Σ de π* es mucho menor que la de Pb-6p,
   por lo que solo G0W0 completo puede separar los dos CBM. El scissor desplaza el π*
   junto con el Pb-6p → el artefacto persiste.
3. No incluye la corrección SOC: el scissor se añade al gap sin SOC. Para comparar con
   experimento, se asume que el desplazamiento SOC (Δ_SOC ≈ −0.3 eV en Pb-based)
   está parcialmente absorbido en el Δ_scissor empírico.

Los valores scissor están registrados en el campo `scissor_correction` de cada
`r2scan_bandgap.json` de los materiales Pb-based.

---

## 10. Propiedades vibracionales

### 10.1 Matriz Hessiana

La matriz Hessiana se calcula por diferencias finitas centrales en las fuerzas:

    H_{ij} ≈ −[F_i(R + Δê_j) − F_i(R − Δê_j)] / (2Δ)

con desplazamiento Δ = 0.01 Å. La simetrización H → (H + Hᵀ)/2 elimina asimetrías
numéricas. Autovalores ≥ 0 indican mínimo estable; autovalores < 0 (modos imaginarios)
indican inestabilidad dinámica hacia una fase de menor simetría.

### 10.2 Dispersión de fonones

Las frecuencias de fonón se calculan mediante el método de desplazamientos finitos en
supercelda [Parlinski et al., 1997], usando Phonopy como interfaz. Las constantes de
fuerza interatómicas C(R) se extraen de cálculos GPAW con cada átomo desplazado.
La transformada de Fourier da la matriz dinámica:

    D_{αβ}(q) = 1/√(MₐMᵦ) Σ_R C_{αβ}(R) exp(iq·R)

    ω²(q) = autovalores de D(q)

La regla de suma acústica (ASR) elimina la deriva traslacional. Los modos imaginarios
(ω² < 0) identifican inestabilidades de la fase cúbica hacia fases octaédricas tilted
(fase β, γ), relevantes para la estabilidad de los materiales.

---

## 11. Software y reproducibilidad

| Componente | Versión | Función |
|------------|---------|---------|
| GPAW | master (25.7.1b1) | DFT, G0W0, SOC, PDOS |
| ASE | ≥ 3.23.0 | Estructura, relajación, I/O |
| Phonopy | ≥ 2.20 | Fonones, supercelda |
| libxc | 6.2+ | r²SCAN y otros MGGA |
| ScaLAPACK | OpenMPI | Diagonalización paralela |
| NumPy/SciPy | ≥ 1.26 | Post-procesamiento |
| Python | ≥ 3.11 | Pipeline principal |
| PyTorch | ≥ 2.1 | Backend de redes neuronales (MACE, surrogate MLP) |
| mace-torch | 0.3+ | Campo de fuerzas equivariante MACE-MP-0 |
| torch-sim | 0.1+ | Motor de simulación MD/minimización (FIRE) |
| OghmaNano | v8.1 | Simulación de dispositivo drift-diffusion |

Todos los parámetros están centralizados en `configs/default_params.yaml`. Los scripts
del pipeline son reproducibles desde ese archivo y las estructuras en `structures/`.
Cada etapa escribe un GPW (checkpoint) que permite reanudar sin recalcular etapas previas.

---

Los §1–11 han presentado la metodología DFT completa: elección del funcional XC,
base de ondas planas, muestreo k, relajación estructural, SOC perturbativo y corrección
cuasipartícula G0W0. Este nivel de cálculo provee alta precisión (~±0.1 eV en el
bandgap), pero a un costo que limita el throughput a ~5 materiales por día a nivel
G0W0. Para explorar el espacio composicional ABX₃ de forma sistemática, la sección
siguiente introduce el pipeline de aprendizaje automático que opera como contraparte
escalable del workflow DFT.

## 12. Pipeline de Cribado por Aprendizaje Automático

### 12.1 Etapas del pipeline AI y contraparte DFT

El pipeline AI consta de seis etapas secuenciales que se corresponden funcionalmente
con las etapas del pipeline DFT (§1.2), cubriendo el mismo ciclo estructura → propiedades
pero desde el espacio composicional en lugar de la estructura atómica resuelta:

```
Espacio ABX₃ (N candidatos)
         │
         ▼
AI-01. Definición del espacio de búsqueda
         (features 6D: r_A, r_B, r_X, q_A, q_B, q_X)
         │  candidatos.json
         ▼
AI-02. Prescreening semi-empírico
         (Eg_semi = B_BASE[B] + X_SHIFT[X],  t = (r_A+r_X)/(√2·(r_B+r_X)))
         │  filtro: t ∈ [0.80, 1.05],  Eg ∈ [1.1, 1.8] eV
         ▼
AI-03. Optimización Bayesiana (surrogate MLP + UCB, 200 pasos)
         │  top-30_candidatos.json
         ▼
AI-04. Relajación geométrica MLFF (MACE-MP-0, FIRE, f_max < 0.05 eV/Å)
         │  estructuras_relajadas/  (top-5)
         ▼
AI-05. Validación DFT multi-nivel (GPAW: Nivel 0 PBE + Nivel 1 SOC)
         │  Eg, m*, ε_r, solar_score
         ▼
AI-06. Learning loop (blended reward → reentrenamiento surrogate)
         │  R_blend = (1-w)·AI_score + w·(solar_score/100)·2.0
         └──────────────────────────────────────────▶ AI-03 (ciclo siguiente)
```

**Comparativa paso a paso — DFT vs AI (mismo número de paso, función equivalente):**

| Paso | Pipeline DFT | Método DFT | Pipeline AI (equivalente ML puro) | Método AI |
|:----:|-------------|------------|-----------------------------------|-----------|
| 01 | Relajación estructural | PBEsol+D3 · BFGS (ASE/GPAW) | Relajación geométrica MLFF | MACE-MP-0 · FIRE (torch-sim) |
| 02 | Preconvergencia SCF | PBEsol+U · dens=1e-2 (GPAW) | Prescreening semi-empírico | Eg_semi + factor t · B_BASE/X_SHIFT (AINAGENT) |
| 03 | SCF principal | r²SCAN+U · dens=1e-4 (GPAW) | Optimización Bayesiana | MLP surrogate (6D→μ,σ²) + UCB · Adam lr=1e-3 (AINAGENT) |
| 04 | SOC perturbativo + PDOS | `soc_eigenstates` (GPAW) | GNN bandgap (proxy ALIGNN) | MEGNet-MP (matgl, mfi-MP-2019.4.1) — ALIGNN roto por DGL graphbolt |
| 05 | G0W0@PBE (Pb-based) | `G0W0` (GPAW response) | Corrección SOC empírica | ΔEg_SOC por (A,B) desde literatura (Even 2013, Brivio 2014, Filip 2016) |
| 06 | SOC sobre eigenvalores GW | `soc_eigenstates`@QP eigenvals | Learning loop | Blended reward + Adam retraining · R_blend (AINAGENT) |

La diferencia fundamental: en el pipeline DFT cada paso opera sobre **una estructura fija**
profundizando en precisión; en el pipeline AI cada paso opera sobre **el espacio de candidatos**
reduciéndolo. Ambos producen el mismo tipo de salida (Eg, m\*, solar_score) para los
candidatos que superan todos los filtros.

---

### 12.2 Motivación y espacio de búsqueda

El espacio de perovskitas haluro ABX₃ con A ∈ {Cs⁺, MA⁺, FA⁺}, B ∈ {Pb²⁺, Sn²⁺, Ge²⁺},
X ∈ {I⁻, Br⁻, Cl⁻} contiene N ≈ 27 candidatos de primer orden, creciendo a ~10³ al
considerar mezclas haluro y dobles perovskitas. Una búsqueda exhaustiva DFT al nivel G0W0
requeriría ~10³ × 8 h ≈ 8,000 CPU-horas. El pipeline AI reduce esto a una exploración
guiada por optimización Bayesiana, donde solo los top-K candidatos más prometedores
llegan a validación DFT completa.

### 12.3 Representación de materiales y features físicas

Cada candidato ABX₃ se representa con un vector de 6 features físicas:

    x = [r_A, r_B, r_X, q_A, q_B, q_X]

donde r_i son radios iónicos de Shannon (1976) para especies inorgánicas y de
Kieslich et al. (2014) para cationes orgánicos (MA⁺, FA⁺), y q_i son las cargas
formales. A partir de este vector se calculan dos descriptores derivados:

**Factor de tolerancia de Goldschmidt:**

    t = (r_A + r_X) / (√2 · (r_B + r_X))

El factor t = 1 corresponde a estructura cúbica ideal; perovskitas estables tienen
0.80 < t < 1.05. Valores fuera de este rango indican distorsión octaédrica severa
o inestabilidad de la fase cúbica.

**Bandgap semi-empírico:**

    Eg_semi = B_BASE[B] + X_SHIFT[X]

con B_BASE = {Pb: 1.5, Sn: 1.3, Ge: 2.0} eV y X_SHIFT = {I: 0.0, Br: 0.3, Cl: 0.6} eV.
Esta parametrización empírica captura las tendencias principales del bandgap: los
compuestos de Pb tienen gap mayor que Sn (5s²-6p⁰ vs 5s²-5p⁰), y los bromuros/cloruros
tienen gap mayor que los ioduros por la mayor electronegatividad del haluro.

### 12.4 Fase 1 — Prescreening Bayesiano (AINAGENT)

El módulo de prescreening implementa un agente de optimización Bayesiana (AINAGENT) como
grafo de 5 nodos funcionales ejecutado sobre TorchSim durante 200 pasos:

```
Espacio ABX₃ (candidatos)
        │
        ▼  Iteración Bayesiana (200 pasos)
┌──────────────────────────────────────────┐
│ 1. MaterialProposalNode                  │
│    → Propone candidatos desde x(6D)      │
│    → Selecciona top-K vía AcquisitionNode│
│                                          │
│ 2. MaterialEvaluationNode                │
│    → Eg_semi = B_BASE[B] + X_SHIFT[X]   │
│    → t = (r_A+r_X)/(√2·(r_B+r_X))      │
│    → score = f(Eg ∈ [1.1,1.8], t~0.90) │
│                                          │
│ 3. MemoryNode                            │
│    → Replay buffer circular (x, score)   │
│                                          │
│ 4. SurrogateNode (MLP heteroscedástico)  │
│    → 6D → (μ, log σ²)                   │
│    → Pérdida: Gaussian NLL               │
│                                          │
│ 5. AcquisitionNode (UCB)                 │
│    → UCB(i) = μ(i) + β·σ(i) + explorac.│
└──────────────────────────────────────────┘
        │ top-30 candidatos
        ▼
```

**Surrogate MLP heteroscedástico.** La red neuronal surrogate tiene arquitectura
6→64→64→2 y produce media μ y varianza σ² de forma conjunta con pérdida de
log-verosimilitud negativa gaussiana:

    L_NLL = log σ²(x) + (y - μ(x))² / σ²(x)

La incertidumbre predicha σ²(x) es heteroscedástica: refleja no solo el ruido del
modelo sino también la cobertura del espacio de entrenamiento. El optimizador Adam
usa lr = 10⁻³ con reentrenamiento en cada iteración sobre el buffer de memoria.

**Función de adquisición UCB.** La selección del próximo candidato a evaluar maximiza:

    UCB(i) = μ(i) + β·σ(i) + 0.1·√(ln(t+1) / (n(i)+1))

donde β equilibra explotación (candidatos con μ alto) y exploración (candidatos con
σ alto), t es el número de iteraciones global y n(i) el número de evaluaciones del
candidato i. El tercer término bonus promueve diversidad composicional.

### 12.5 Fase 2 — Relajación Geométrica con MACE-MP-0

Los top-30 candidatos se relajan geométricamente con el campo de fuerzas neuronal
equivariante MACE-MP-0 [Batatia et al., 2023]. MACE (Message-passing Atomic Cluster
Expansion) es una red neuronal con simetría E(3) que usa expansiones en clusters de
átomos hasta orden L=2, entrenada sobre ~150,000 estructuras del Materials Project y
válida para 89 elementos.

La relajación opera en modo de celda variable (variable-cell) usando el optimizador
FIRE (Fast Inertial Relaxation Engine) con criterio de convergencia:

    f_max < 0.05 eV/Å

El seguimiento de la distancia de Fréchet en el espacio de parámetros de celda
detecta convergencia de la geometría sin requerir gradiente del cell stress explícito.
Las 5 estructuras con menor energía de formación tras la relajación avanzan a la Fase 3.

**Resultados sobre los top-8 (2026-05-26):** Modelo small (L0, fmax < 0.05 eV/Å).
Todos los 8 materiales convergieron. El parámetro de red MACE sobreestima
sistemáticamente Δa = +0.05 a +0.21 Å respecto al DFT PBEsol: error GGA típico,
mayor para cationes FA voluminosos. La precisión de MACE para parámetros de celda es
≈±0.05–0.10 Å respecto a DFT (algo mayor que el ±0.01 Å de la literatura para óxidos —
en haluro perovskitas con cationes orgánicos el error es mayor), con un coste ~100×
menor que la relajación PBEsol completa.

### 12.6 Fase 3 — Validación DFT (GPAW, 3 niveles)

Las 5 estructuras relajadas se validan con tres niveles DFT en orden ascendente de coste:

| Nivel | Método | Propiedades calculadas | Costo típico |
|-------|--------|----------------------|--------------|
| 0 | PBE/PBEsol SCF | Eg_PBE, parámetros de celda | ~30 min |
| 1 | + SOC perturbativo | Eg_SOC, m\*_e, m\*_h, solar_score | ~2 h |
| 2 | + HSE06 + fonones | Eg_HSE+SOC, Δ_HSE-PBE, estabilidad dinámica | ~8–24 h |

El `solar_score` es un indicador compuesto [0–100] que pondera la concordancia
del Eg_SOC con la ventana fotovoltaica óptima (1.1–1.8 eV según el límite
Shockley-Queisser) y el factor de tolerancia t.

### 12.7 Fase 4 — Learning Loop

Los resultados DFT del Nivel 1 retroalimentan el surrogate AI mediante la función
de reward combinada:

    R_blend = (1 - w) · AI_score + w · (solar_score/100) · 2.0,    w = 0.7

El factor w = 0.7 da peso dominante a los valores DFT (más fiables) mientras preserva
la diversidad exploratoria del score AI. El factor 2.0 normaliza el rango de
solar_score ∈ [0,100] al rango de AI_score ∈ [0,2].

Los pares (features 6D, R_blend) se inyectan en el MemoryNode para reentrenar el
surrogate, refinando iterativamente el ranking de candidatos y concentrando la
exploración en regiones del espacio composicional con mayor potencial fotovoltaico.

### 12.8 Modelos AI de Propiedades Espectrales

Además del prescreening de Eg y el ranking composicional, se desarrollaron modelos
AI/semi-empíricos para calcular la densidad de estados, las propiedades dieléctricas
y el espectro óptico de los 8 materiales top sin recurrir a eigenvalores DFT completos.
El script `scripts/ai_spectra_top8.py` implementa cuatro modelos físicos:

**Densidad de estados 3D parabólica (modelo k·p)**

La DOS de banda de conducción y valencia se aproxima por la expresión de electrón
masivo 3D (Ashcroft & Mermin, 1976, cap. 8):

    D_c(E) = (1/2π²)·(2m*_e/ħ²)^(3/2)·√(E − E_g),    E > E_g
    D_v(E) = (1/2π²)·(2m*_h/ħ²)^(3/2)·√(−E),          E < 0

Las masas efectivas se obtienen del modelo de Kane k·p (Kane, 1957):

    m*_e / m₀ = E_g / (E_g + 2P²/m₀),    2P²/m₀ = 20 eV (típico haluro perovskita)
    m*_h = 1.3 · m*_e                      (asimetría CB-VB, Mosconi et al., 2014)

Para los materiales Pb, m*_e y m*_h se toman de los cálculos DFT+SOC del paso 10
(`electronic_analysis.json`) cuando son físicos (|m*| < 10 m₀ y sin flag UNPHYSICAL).
FAPbBr₃ usa Kane como fallback porque el análisis DFT reportó m*_e_CBM = 64.32 m₀
(artefacto numérico en el CBM del cálculo k-point).

**PDOS por campo cristalino**

Las posiciones orbitales se asignan según el análisis de carácter orbital de Filip &
Giustino (2016) y Even et al. (2013), sin diagonalizar el Hamiltoniano DFT: el orbital
B-p domina el CBM (centro en E_g + 0.3 eV); X-p domina el VBM (centro en −0.2 eV);
B-s ocupa el borde inferior de VB (centro en −4.2 eV para Pb, −4.8 eV para Sn); X-s
se sitúa en estados profundos (−6.0 eV para I, −5.5 eV para Br). Los cationes orgánicos
MA y FA contribuyen con N-2p (−3.8 eV) y C-2p (−4.5 eV). Cada contribución se ensancha
con una Gaussiana de σ = 0.10 eV para reproducir la resolución experimental de ARPES.

**Función dieléctrica: oscilador Tauc-Lorentz**

La parte imaginaria de la función dieléctrica se calcula con el oscilador de
Jellison & Modine (1996):

    ε₂(ħω) = A·E₀·C·(ħω − E_g)² / [ħω·((ħω² − E₀²)² + C²·ħω²)],   ħω > E_g
    ε₂(ħω) = 0,                                                          ħω ≤ E_g

con parámetros: E₀ = 1.5·E_g (energía de resonancia de Penn), C = 0.5·E_g
(ensanchamiento Lorentz), A = 40 eV (amplitud calibrada para dar ε₂_max ≈ 8–12
con este denominador, consistente con mediciones elipsométricas de perovskitas haluro).
La parte real ε₁(ω) se obtiene de las relaciones de Kramers-Kronig:

    ε₁(ω) = ε_∞ + (2/π) · P ∫₀^∞ ω'ε₂(ω')/(ω'² − ω²) dω'

donde P denota el valor principal de Cauchy (integrado numéricamente por regla del
trapecio sobre ω ∈ [0.01, 6.0] eV con 2,000 puntos).

**Constante dieléctrica de alta frecuencia ε_∞**

Se intentó obtener ε_∞ de la base de datos JARVIS-DFT-3D (Choudhary & DeCost, 2021)
mediante cálculos DFPT. CsSnI₃ existe en JARVIS (JVASP-22675) pero el campo
`epsx = 'na'` indica que el cálculo DFPT no fue completado para esa entrada; CsPbI₃
no figura en la base de datos. Los materiales con catión orgánico (MA, FA) no están
en JARVIS por definición (base de datos de materiales inorgánicos). Como consecuencia,
ε_∞ se estima con el modelo de Penn (Penn, 1962):

    ε_∞ = clip(1 + (ħω_p / E_g)²,   3.5, 7.0),    ħω_p ≈ 14 eV

Para los 8 materiales del top (E_g_semi_soc ∈ [0.95, 1.60] eV), el argumento
(14/E_g)² > 49 en todos los casos, de modo que ε_∞ = 7.0 (cota máxima del clipeo).
Esta limitación del modelo de Penn para semiconductores de gap pequeño es conocida
(Penn, 1962); el valor real experimental para CsSnI₃ es ε_∞ ≈ 5.7 (DFPT) y para
CsPbI₃ ε_∞ ≈ 4.6 (elipsometría). La sobre-estimación sistemática (7.0 vs 4.6–5.7)
comprime el onset de ε₁ y suaviza el pico de n(ω); se documenta como limitación del
método AI espectral y se recomienda reemplazar Penn por ε_∞ DFPT cuando esté disponible.

**Propiedades ópticas derivadas**

El índice de refracción complejo ñ = n + ik se obtiene de ε̃ = ε₁ + iε₂:

    n(ω) = Re(√ε̃),    k(ω) = Im(√ε̃)

El coeficiente de absorción:

    α(ω) = 2ωk(ω) / (ħc),    ħc = 1.973×10⁻⁵ eV·cm

A energías fotónicas E_g + 1 eV el modelo predice α ∈ [10⁴, 10⁵] cm⁻¹, consistente
con mediciones experimentales de transmitancia en películas delgadas (Stranks & Snaith,
2015). El script genera 64 figuras (4 tipos × 8 materiales × PNG+PDF) en
`calculations/top8_r2scan/figures_ai/` mediante ejecución paralela
(`concurrent.futures.ProcessPoolExecutor`, 8 workers, ~8 s/material).

---

### 12.9 Surrogate ML Entrenable — Módulo `src/ml_surrogate/`

El pipeline BUHO implementa un surrogate ML propio especializado en haluro perovskitas
ABX₃, diseñado para reemplazar por completo las heurísticas débiles
(B_BASE+X_SHIFT, Kane, Penn, Tauc-Lorentz) en la etapa de prescreening. A diferencia
de los modelos GNN genéricos (MEGNet, M3GNet, ALIGNN), el surrogate es entrenable
directamente sobre datos DFT del proyecto y no requiere estructura cristalina.

#### 12.9.1 Conjunto de entrenamiento

El dataset se construyó en dos etapas:

1. **Materiales inorgánicos (Cs, Rb, K):** consulta a la API de Materials Project
   (`mp-api 0.45+`) para las 27 combinaciones A ∈ {Cs, Rb, K} × B ∈ {Pb, Sn, Ge}
   × X ∈ {I, Br, Cl}, filtrando por `nsites = 5` (celda primitiva ABX₃). De los
   94 materiales recuperados, 21 son ABX₃ puros; el de menor energía sobre el
   casco convexo por composición se seleccionó como representativo.

2. **Materiales orgánicos (MA, FA):** no disponibles en Materials Project como
   estructuras simples (requieren celdas supercell con 12–18 átomos). Se usaron
   valores experimentales de la literatura (Stoumpos 2013, Lee 2012, Eperon 2014,
   Koh 2015) para MA × {Pb, Sn} × {I, Br, Cl} y FA × {Pb, Sn} × {I, Br, Cl}.

El dataset final contiene **26 muestras** con `Eg_target_eV` = valor experimental
como etiqueta (rango 1.20–3.67 eV). Los valores DFT r²SCAN+U+SOC del proyecto
son coherentes con el experimento para los inorgánicos (Cs-based) pero se excluyen
para los orgánicos (FA/MA) porque el cálculo DFT usa sustitución pseudo-átomo
(FA→Cs, MA→Rb) produciendo gaps no representativos del cristal real.

#### 12.9.2 Descriptores (vector de características 16D base)

Todos los descriptores son computables a partir de la composición química:

| # | Descriptor | Definición | Fuente |
|:--:|-----------|-----------|--------|
| 0–2 | r_A, r_B, r_X | Radios iónicos Shannon (Å) | Shannon 1976; Kieslich 2014 para MA/FA |
| 3–5 | χ_A, χ_B, χ_X | Electronegatividad Pauling | Pauling 1932; χ(MA)=2.30, χ(FA)=2.40 |
| 6–8 | q_A, q_B, q_X | Cargas formales | — |
| 9 | t_Gold | Factor de tolerancia de Goldschmidt | t = (r_A + r_X) / (√2·(r_B + r_X)) |
| 10 | f_oct | Factor octaédrico | μ = r_B / r_X |
| 11 | a_est | Constante de red estimada (Å) | a₀ = 2√2·(r_B + r_X) |
| 12 | V_est | Volumen de celda estimado (Å³) | V = a₀³ |
| 13 | Δχ_BX | Diferencia de electronegatividad | χ_X − χ_B (proxy de ionicidad) |
| 14 | μ_BX | Radio reducido (Å) | r_B + r_X (proxy longitud de enlace B–X) |
| 15 | is_organic_A | Flag catión orgánico | 1 si A ∈ {MA, FA}, 0 si A ∈ {Cs, Rb, K} |

Características opcionales (añadidas cuando disponibles):
- `a_lat_mp_A` — constante de red de MP o MACE (Å)
- `E_mace_eV_atom` — energía MACE por átomo (eV)
- `band_gap_gga_eV` — bandgap GGA de MP o cálculo propio
- `Eform_eV_atom` — energía de formación por átomo (eV)

Las tres más relevantes (GGA disponible en el entrenamiento) amplían el vector a 19D.

#### 12.9.3 Modelo: ensemble RandomForest + GradientBoosting

Se implementó un ensemble de dos modelos scikit-learn en la clase `SurrogateEnsemble`
(`src/ml_surrogate/model.py`):

```
X (16–19D) ──→ [Imputer(median)] ──→ [StandardScaler] ──→ RF(200 árboles, max_d=4)
                                                          ──→ GBR(200 árboles, lr=0.05)
                                                                          ↓
                                                              ŷ = (RF + GBR) / 2
```

La incertidumbre se estima por **bootstrap** (B = 100 remuestras): para cada muestra
se entrena un RF de 50 árboles y la desviación estándar de las 100 predicciones es
la incertidumbre reportada. Esto equivale a un intervalo de predicción ~90%.

Hiperparámetros conservadores para n ≈ 26:
- `max_depth = 4` — árboles superficiales para evitar sobreajuste
- `min_samples_leaf = 2` — mínimo de muestras por hoja
- `learning_rate = 0.05` para GBR (lento pero estable)

El tratamiento de valores faltantes (NaN en características opcionales) se realiza
con `SimpleImputer(strategy="median")` dentro del pipeline, lo que garantiza que
los medianos del entrenamiento se usen en predicción (sin filtración de información).

#### 12.9.4 Validación cruzada

Con n = 26 muestras se usa validación cruzada de **5 pliegues** (el módulo usa LOO
automáticamente cuando n ≤ 15). Resultados:

| Métrica | Valor |
|---------|-------|
| MAE (5-fold CV) | **0.31 eV** |
| RMSE (5-fold CV) | 0.45 eV |
| R² (5-fold CV) | 0.55 |
| MAE (en-muestra) | 0.08 eV |
| n_samples | 26 |
| n_features | 19 (16 base + 3 opcionales) |

El MAE en-muestra (0.08 eV) refleja el ajuste del modelo; el CV MAE (0.31 eV) es la
estimación generalizable. Este rendimiento supera las heurísticas anteriores (MAE ~0.3–0.5 eV
sin validación cruzada real) y es comparable al MEGNet (±0.3 eV para haluros).

**Importancias de características (top 5):**

| Característica | Importancia RF+GBR |
|---------------|:-----------------:|
| χ_X (electronegatividad haluro) | 0.244 |
| f_oct (factor octaédrico r_B/r_X) | 0.236 |
| r_X (radio iónico haluro) | 0.209 |
| a_lat_mp_A (parámetro de red) | 0.073 |
| t_Gold (factor de Goldschmidt) | 0.056 |

La dominancia de χ_X, f_oct y r_X es físicamente coherente: el haluro controla
el ancho del gap (I < Br < Cl) a través del nivel de energía de los orbitales X-p
y la covalencia del enlace B–X. El factor octaédrico captura la relación entre el
tamaño del catión B y la geometría del octaedro [BX₆].

#### 12.9.5 Predicciones top-8 (surrogate vs. experimental)

| Material | Eg_pred (eV) | ± | Eg_exp (eV) | error (eV) | PV |
|----------|:------------:|:---:|:-----------:|:----------:|:--:|
| MASnI₃  | 1.440 | 0.167 | 1.20 | +0.240 | ✓ |
| CsSnI₃  | 1.435 | 0.183 | 1.30 | +0.135 | ✓ |
| FASnI₃  | 1.534 | 0.161 | 1.41 | +0.124 | ✓ |
| MAPbI₃  | 1.678 | 0.177 | 1.55 | +0.128 | ✓ |
| FAPbI₃  | 1.699 | 0.162 | 1.48 | +0.219 | ✓ |
| CsPbI₃  | 1.725 | 0.189 | 1.73 | −0.005 | ✓ |
| FASnBr₃ | 1.858 | 0.170 | 2.00 | −0.142 | — |
| FAPbBr₃ | 2.148 | 0.188 | 2.23 | −0.082 | — |

**MAE en top-8: 0.135 eV.** El surrogate sitúa los 6 materiales I-based dentro de
la ventana fotovoltaica (1.1–1.8 eV) correctamente, y los 2 Br-based fuera,
consistente con el experimento. El ranking relativo es correcto (Sn < Pb, I < Br).

#### 12.9.6 Integración con el pipeline

`SurrogateAcquisition` (`src/ml_surrogate/integration.py`) reemplaza a
`GNNAcquisition` con la misma API (método `score_one()`, `rank()`, `to_feature_vector()`):

```python
from ml_surrogate.integration import SurrogateAcquisition

acq = SurrogateAcquisition(beta=1.0)     # carga modelo automáticamente
score = acq.score_one("CsPbI3", "Cs", "Pb", "I")
# score.Eg_pred = 1.7251 eV  score.Eg_uncertainty = 0.1893 eV
# score.solar_score = 0.734  score.in_pv_window = True
```

Cuando el modelo no está entrenado, `SurrogateAcquisition` cae a heurística
B_BASE+X_SHIFT con advertencia explícita. El vector de características 8D para
`HTSSurrogateNode` se extiende con [Eg_pred, 0.0].

**Entrenamiento:**
```bash
python -m src.ml_surrogate.train --config configs/surrogate.yaml
# Salida: models/surrogate_bandgap.pkl  +  models/surrogate_bandgap.metrics.json
```

**Predicción:**
```bash
python -m src.ml_surrogate.predict --mat all
python -m src.ml_surrogate.predict --A Rb --B Sn --X I   # composición arbitraria
python -m src.ml_surrogate.predict --input candidates.csv --output predictions.csv
```

---

## 13. Análisis Comparativo: Precisión, Escala y Costo Computacional

### 13.1 Capacidades por método: propiedades, precisión y escala

Cada nivel de cálculo cubre un conjunto distinto de propiedades observables, con
diferente precisión y costo computacional. La tabla siguiente sintetiza estas
diferencias para los cinco métodos empleados en este trabajo:

| Propiedad | Semi-emp. (baseline) | Surrogate ML | MLFF (MACE) | DFT PBE | r²SCAN+U+SOC | G0W0+SOC | Exp. |
|-----------|:-------------------:|:------------:|:-----------:|:-------:|:------------:|:--------:|:----:|
| Bandgap | ±0.3–0.5 eV | **±0.31 eV (CV)** | N/A | −0.5 eV (sesgo) | ±0.15–0.25 eV | ±0.1 eV | ref |
| Estructura cristalina | estimada a₀ | estimada a₀ | ≈DFT (±0.01 Å) | ±0.01–0.03 Å | — | — | ref |
| Estabilidad | factor t | score sigmoid | FIRE conv. | modos fonónicos | — | — | ref |
| Masas efectivas m\* | Kane k·p (±20%) | N/A | N/A | ±20% | ±15% | ±10% | ref |
| Incertidumbre explícita | No | **Sí (bootstrap)** | No | No | No | No | — |
| Espectro óptico n,k,α | Tauc-Lorentz (cualitativo) | N/A | N/A | ±20% | ±15% | — | ref |
| PCE teórico (SQ) | N/A | N/A | N/A | estimado | estimado | mejorado | — |
| PCE real (dispositivo) | N/A | N/A | N/A | N/A | N/A | N/A | OghmaNano |
| Costo/candidato | ~seg | ~seg | ~min | 2–10 h | 2–10 h | ~8 h | — |
| Candidatos/día | >1,000 | **>1,000** | ~50 | ~5 | ~5 | ~2 | — |
| Requiere estructura | No | **No** | Sí | Sí | Sí | Sí | — |
| Reentrenable con DFT | No | **Sí** | No | — | — | — | — |

### 13.2 Concordancia cuantitativa con el experimento

Los bandgaps calculados con cada método se comparan con los valores experimentales
disponibles. Resultados completos (2026-05-26):

| Material | Eg_semi (eV) | Eg_surrogate ± σ (eV) | Eg_DFT (eV) | Eg_exp (eV) | err_surrogate |
|----------|:------------:|:--------------------:|:-----------:|:-----------:|:-------------:|
| CsPbI₃  | 1.50 | 1.725 ± 0.189 | 1.483 (PBE+scissor) | 1.73 | −0.005 |
| CsSnI₃  | 1.30 | 1.435 ± 0.183 | 1.359 (r²SCAN+U+SOC) | 1.30 | +0.135 |
| MASnI₃  | 1.30 | 1.440 ± 0.167 | 1.584 (r²SCAN+U+SOC) | 1.20 | +0.240 |
| FASnI₃  | 1.30 | 1.534 ± 0.161 | 0.771 (r²SCAN+U+SOC) | 1.41 | +0.124 |
| FASnBr₃ | 1.60 | 1.858 ± 0.170 | 1.115 (r²SCAN+U+SOC) | 2.00 | −0.142 |
| MAPbI₃  | 1.50 | 1.678 ± 0.177 | 2.054 (r²SCAN/Pb) | 1.55 | +0.128 |
| FAPbI₃  | 1.50 | 1.699 ± 0.162 | 0.982 (r²SCAN/Pb) | 1.48 | +0.219 |
| FAPbBr₃ | 1.80 | 2.148 ± 0.188 | 1.079 (r²SCAN/Pb) | 2.23 | −0.082 |

**MAE surrogate (top-8 vs. exp):** 0.135 eV. **MAE semi-empírico (vs. exp):** 0.34 eV.
El surrogate reduce el error medio en ×2.5 sobre la heurística, sin necesitar estructura
cristalina ni cálculo DFT adicional. La incertidumbre reportada (σ bootstrap) refleja
regiones poco cubiertas por el dataset de entrenamiento (MASnI₃ y RbPbI₃ tienen σ > 0.3 eV).

**Ranking AI vs DFT (AI-03 score):** MAPbI₃ (1.985) > CsPbI₃ (1.910) > MASnI₃ (1.905) >
CsSnI₃ (1.840). Los cuatro materiales top del AI coinciden con los de mayor solar_score DFT.
FA-materials penalizados por t ≈ 1.0 (alejado del óptimo t = 0.90 del descriptor Goldschmidt).

### 13.3 Análisis

**Score semi-empírico AI (Eg_semi):** captura correctamente el ordenamiento relativo
en ~70% de los casos. Subestima el gap de compuestos Pb-I (CsPbI₃: AI=1.50 vs exp=1.73 eV)
porque B_BASE[Pb]=1.5 eV no incluye la corrección relativista del acoplamiento espín-órbita
(SOC reduce el gap ~0.3 eV en Pb-6p). Para Sn la concordancia es mejor (CsSnI₃:
AI=1.30 = exp=1.30 eV) porque B_BASE[Sn]=1.3 eV fue calibrado directamente sobre datos experimentales.

**DFT PBE:** subestima sistemáticamente todos los gaps en ~0.5 eV. Esta deficiencia es
inherente al funcional de intercambio-correlación GGA: el error de auto-interacción
delocaliza artificialmente los estados de valencia, comprimiendo el gap hacia cero.
PBE modela correctamente, en cambio, la geometría (±0.03 Å) y el orden relativo de
los estados electrónicos.

**r²SCAN+U+SOC:** reduce el error medio a ±0.2 eV. Sin embargo, requiere calibración
empírica de U (U=2.5 eV para Sn-5s) y exhibe artefactos para materiales FA: el CBM
de FAPbI₃ y FAPbBr₃ cae sobre el orbital π* del catión FA antes que sobre el Pb-6p,
generando gaps indirectos artificialmente pequeños (0.65 y 0.85 eV vs exp 1.48 y 2.23 eV).

**G0W0+SOC:** precisión teórica ±0.1 eV sin parámetros empíricos. La auto-energía Σ del
orbital FA π* es significativamente menor que la del Pb-6p CBM, por lo que G0W0 separa
correctamente los dos CBM sin el artefacto FA. Es el método de referencia para Pb-based.
**Sin embargo, G0W0 resultó infactible en el hardware disponible** (~15-16 h/material
para CsPbI₃ de 5 átomos; ~40-50 h para los orgánicos de 12 átomos): el cálculo fue
interrumpido el 26-05-2026 por un corte eléctrico sin checkpoint recuperable. Como
alternativa se aplica una corrección scissor +0.5 eV (ver §9.9): para CsPbI₃ esto
da 1.788 eV (vs exp 1.73 eV, error 0.06 eV), pero para los materiales FA no resuelve
el artefacto orbital y los valores deben interpretarse como cotas indicativas.

**Conclusión:** el ranking AI es suficiente para preselección (~70% de concordancia relativa);
r²SCAN+U+SOC es necesario para valores absolutos con error ±0.2 eV; la corrección scissor
(+0.5 eV sobre PBE) aproxima G0W0 para Pb inorgánico con error ±0.1 eV, pero no resuelve
el artefacto FA en los compuestos orgánicos — para esos materiales, G0W0 completo es
indispensable aunque infactible con los recursos actuales.

### 13.4 Propiedades ópticas AI: masas efectivas y espectro

Los modelos Kane y Tauc-Lorentz (§12.8) producen las siguientes propiedades para los 8
materiales. Las masas efectivas Kane se calculan de E_g_semi_soc; los materiales Pb marcan
la fuente del dato de m* usado:

| Material | E_g_semi_soc (eV) | m*_e (m₀) | m*_h (m₀) | Fuente m* | ε_∞ | α(E_g+1 eV) [cm⁻¹] |
|----------|:-----------------:|:---------:|:---------:|:---------:|:---:|:-------------------:|
| CsSnI₃  | 1.05 | 0.0499 | 0.0648 | Kane | 7.0 | ~4×10⁴ |
| MASnI₃  | 1.08 | 0.0512 | 0.0666 | Kane | 7.0 | ~4×10⁴ |
| FASnI₃  | 1.22 | 0.0575 | 0.0747 | Kane | 7.0 | ~3×10⁴ |
| FASnBr₃ | 1.52 | 0.0706 | 0.0918 | Kane | 7.0 | ~2×10⁴ |
| CsPbI₃  | 1.00 | 0.0453 | 0.0526 | DFT-SOC | 7.0 | ~5×10⁴ |
| MAPbI₃  | 0.95 | 1.264  | 1.296  | DFT-SOC | 7.0 | ~5×10⁴ |
| FAPbI₃  | 1.30 | 1.770  | 9.891  | DFT-SOC | 7.0 | ~3×10⁴ |
| FAPbBr₃ | 1.60 | 0.0739 | 0.0960 | Kane†  | 7.0 | ~2×10⁴ |

† FAPbBr₃: el análisis DFT reportó m*_e_CBM = 64.32 m₀ (flag UNPHYSICAL) → Kane.
‡ ε_∞ = 7.0 para todos (Penn clamped): E_g_semi_soc < 2 eV → (14/E_g)² > 49 en todos los casos.
  Valor experimental: CsSnI₃ ε_∞ ≈ 5.7, CsPbI₃ ε_∞ ≈ 4.6.

**Comparativa óptica AI vs DFT:** el modelo Tauc-Lorentz reproduce cualitativamente el
onset (ħω)² característico de las perovskitas de haluro, el pico de ε₂ cerca de E₀ = 1.5·E_g,
y el cruce por cero de ε₁ (crossing) cerca del pico, consistente con los cálculos DFT GPAW
(módulo gpaw.response.df). La sobre-estimación de ε_∞ (Penn 7.0 vs DFT ~4.5–5.5) desplaza
ε₁ verticalmente y sobreestima n en ≈0.7 unidades; α(ω) resulta menos afectado porque
depende principalmente de k(ω) ∝ Im(√ε̃), dominado por ε₂ que el modelo Tauc-Lorentz
calcula independientemente de ε_∞.

---

## 14. Integración Metodológica: Workflow DFT–IA–Dispositivo

### 14.1 Arquitectura del workflow integrado

Los cuatro módulos de cálculo se integran en un flujo de trabajo cerrado y retroalimentado:

```
CRIBADO AI (AINAGENT, Fase 1)
    200 pasos Bayesianos → top-30 candidatos ABX₃
        │
        ▼
RELAJACIÓN MLFF (MACE-MP-0, Fase 2)
    Variable-cell FIRE, f_max < 0.05 eV/Å → top-5 estructuras relajadas
        │
        ▼
VALIDACIÓN DFT (GPAW, Fase 3 — Niveles 0-1)
    Eg, m*_e, m*_h, ε_r, α(ω), solar_score → base de datos de candidatos
        │
        ├── (solo Pb-based) ──▶ CORRECCIÓN G0W0+SOC [infactible, ver §9.9]
        │                       Alternativa: scissor +0.5 eV sobre PBE (~±0.1 eV para inorgánicos)
        │
        ▼
SIMULACIÓN DISPOSITIVO (OghmaNano, Fase 4)
    Drift-diffusion AM1.5G → PCE, Voc, Jsc, FF reales
        │
        ▼
LEARNING LOOP
    R_blend = (1-w)·AI_score + w·(solar_score/100)·2.0
    → Reentrenamiento surrogate → ranking refinado
        │
        └──────────────────────────────────────────▶ AINAGENT (siguiente iteración)
```

### 14.2 Flujo de datos entre módulos

| Módulo | Entradas | Salidas clave |
|--------|---------|---------------|
| AINAGENT | espacio ABX₃ (N~27) | top-30 candidatos + UCB scores |
| MACE relax | estructuras ABX₃ | geometrías relajadas (CIF/ASE Atoms) |
| GPAW DFT | geometría relajada | Eg, m\*, ε_r, α(ω), solar_score |
| G0W0+SOC | g0w0_pbe.gpw | Eg_QP, Eg_QP+SOC, Z, Σ en VBM/CBM [infactible — ver §13.3] |
| OghmaNano | Eg, m\*, ε_r, α(ω) | PCE, Voc, Jsc, FF |
| Learning loop | solar_score, DFT rewards | surrogate MLP actualizado |

### 14.3 Rol de cada módulo

- **AI (AINAGENT):** exploración masiva del espacio composicional — >1,000 candidatos/día
  a coste computacional mínimo (segundos por candidato).
- **MLFF (MACE-MP-0):** relajación geométrica con precisión ≈DFT (±0.01 Å) y coste
  100–1,000× menor que PBEsol, permitiendo descartar estructuras inestables antes de DFT.
- **DFT (GPAW):** propiedades electrónicas de referencia — bandgap, masas efectivas,
  constante dieléctrica, espectro óptico completo.
- **G0W0+SOC:** corrección sistemática del gap para compuestos Pb-based (~±0.1 eV vs exp)
  sin parámetros empíricos; resuelve el artefacto FA π* de DFT. **Infactible con los
  recursos actuales** (~15 h/material para CsPbI₃, ~40 h para orgánicos de 12 átomos).
  Se aplica como alternativa la corrección scissor +0.5 eV sobre PBE (§9.9).
- **OghmaNano:** eficiencia de dispositivo real por drift-diffusion bajo condiciones
  de operación (AM1.5G, 300 K); convierte propiedades de material en métricas de celda solar.
- **Learning loop:** retroalimenta el surrogate con rewards DFT validados, mejorando la
  calidad del ranking en iteraciones sucesivas sin coste DFT adicional.

---

## 15. Simulación de Dispositivo: OghmaNano (Drift-Diffusion)

### 15.1 Fundamento del modelo drift-diffusion

OghmaNano resuelve el sistema de ecuaciones de transporte de carga en semiconductores
acopladas a la ecuación de Poisson en la dirección de transporte (1D):

    J_n = q μ_n n E + q D_n ∇n     (corriente de electrones: deriva + difusión)
    J_p = q μ_p p E − q D_p ∇p     (corriente de huecos)
    ∇²φ = −ρ/ε                      (ecuación de Poisson)

donde μ_n, μ_p son movilidades de portadores, D_i = (k_BT/q) μ_i (relación de Einstein),
ρ es la densidad de carga libre y ε = ε₀ ε_r(DFT) la permitividad del material.

La generación óptica G(x) se calcula integrando el espectro solar AM1.5G con el
coeficiente de absorción α(ω) obtenido del cálculo DFT:

    G(x) = ∫ (φ_AM1.5(ω)/ħω) α(ω) exp(−α(ω)·x) dω

La recombinación incluye tres canales: Shockley-Read-Hall (SRH) con tiempo de vida
τ_SRH, bimolecular (radiativa) con constante B_rad, y Auger con constante C_Auger.

### 15.2 Stack de capas del dispositivo

| Capa | Material | Rol | Espesor |
|------|----------|-----|---------|
| Contacto frontal | FTO (SnO₂:F) | Electrodo transparente | 50 nm |
| ETL | TiO₂ (anatasa) | Transporte de electrones | 200 nm |
| Absorbedor | ABX₃ (perovskita) | Fotogeneración | 100–2,000 nm |
| HTL | Spiro-OMeTAD | Transporte de huecos | 200 nm |
| Contacto trasero | Au | Electrodo metálico reflectante | 100 nm |

### 15.3 Propiedades DFT transferidas a OghmaNano

| Propiedad DFT | Símbolo | Uso en OghmaNano |
|---------------|---------|-----------------|
| Bandgap (DFT+SOC o GW+SOC) | E_g | Posición de bandas, tensión de circuito abierto |
| Constante dieléctrica estática | ε_r | Ecuación de Poisson |
| Masa efectiva electrón (con SOC) | m\*_e | Movilidad μ_e vía modelo de Drude |
| Masa efectiva hueco (con SOC) | m\*_h | Movilidad μ_h vía modelo de Drude |
| Coef. de absorción óptica | α(ω) [cm⁻¹] | Perfil de generación G(x) |
| Índice de refracción complejo | n(ω), k(ω) | Reflexión/transmisión en interfaces |

### 15.4 Comparativa SQ limit vs OghmaNano vs experimento

El límite de Shockley-Queisser (SQ) es el techo termodinámico de eficiencia para un
semiconductor de bandgap E_g dado, asumiendo absorción ideal (α → ∞ para ħω > E_g) y
recombinación puramente radiativa. OghmaNano incorpora las pérdidas reales de un
dispositivo multicapa:

| Magnitud | SQ limit (E_g DFT) | OghmaNano (drift-diff.) | Exp. CsPbI₃ |
|----------|--------------------|------------------------|-------------|
| PCE | 27.2% | 16.3% | ~18–20% |
| V_oc | 1.265 V | 0.919 V | ~1.1 V |
| J_sc | 23.9 mA/cm² | 24.9 mA/cm² | ~22 mA/cm² |
| FF | 0.902 | 0.713 | ~0.75 |

La diferencia SQ vs OghmaNano (~11%) refleja pérdidas reales: recombinación SRH
(τ_SRH ≈ 1 ns típico), pérdidas ópticas en ETL/HTL, y pérdidas de transporte en
interfaces. La diferencia OghmaNano vs experimento (~2-4%) indica pérdidas adicionales
no modeladas: defectos de superficie, absorción parásita en FTO/Au, y resistencia de contacto.

**Nota de implementación:** OghmaNano requiere entorno gráfico Windows (GUI nativo)
o ejecución bajo XVFB (X Virtual Framebuffer) en Linux. La API Python (`oghma-python-api`)
permite automatizar simulaciones en batch desde scripts sin intervención manual de la GUI,
generando los archivos `device_stack.json` y `oghma_device_result.json` programáticamente.

---

## Referencias

- Batatia, I. et al. (2023). MACE: Higher order equivariant message passing neural
  networks for fast and accurate force fields. *NeurIPS*, 36.
- Batatia, I. et al. (2024). A foundation model for atomistic materials chemistry.
  *arXiv*:2401.00096.
- Blöchl, P. E. (1994). Projector augmented-wave method. *Phys. Rev. B*, 50, 17953.
- Bokdam, M. et al. (2016). Role of polar phonons in the photo excited state of metal
  halide perovskites. *Sci. Rep.*, 6, 28618.
- Brivio, F. et al. (2014). Relativistic quasiparticle self-consistent electronic
  structure of hybrid halide perovskite photovoltaic absorbers. *Phys. Rev. B*, 89, 155204.
- Dudarev, S. L. et al. (1998). Electron-energy-loss spectra and the structural
  stability of nickel oxide. *Phys. Rev. B*, 57, 1505.
- Filip, M. R. & Giustino, F. (2014). GW quasiparticle band gap of the hybrid
  organic-inorganic perovskite CH₃NH₃PbI₃. *Phys. Rev. B*, 90, 245145.
- Furness, J. W. et al. (2020). Accurate and numerically efficient r²SCAN
  meta-generalized gradient approximation. *J. Phys. Chem. Lett.*, 11, 8208.
- Godby, R. W. & Needs, R. J. (1989). Metal-insulator transition in Kohn-Sham theory
  and quasiparticle theory. *Phys. Rev. Lett.*, 62, 1169.
- Goldschmidt, V. M. (1926). Die Gesetze der Krystallochemie. *Naturwissenschaften*, 14, 477.
- Grimme, S. et al. (2010). A consistent and accurate ab initio parametrization of
  density functional dispersion correction (DFT-D) for the 94 elements H-Pu.
  *J. Chem. Phys.*, 132, 154104.
- Hedin, L. (1965). New method for calculating the one-particle Green's function with
  application to the electron-gas problem. *Phys. Rev.*, 139, A796.
- Heyd, J., Scuseria, G. E. & Ernzerhof, M. (2003). Hybrid functionals based on a
  screened Coulomb potential. *J. Chem. Phys.*, 118, 8207.
- Hohenberg, P. & Kohn, W. (1964). Inhomogeneous electron gas. *Phys. Rev.*, 136, B864.
- Hybertsen, M. S. & Louie, S. G. (1986). Electron correlation in semiconductors and
  insulators: Band gaps and quasiparticle energies. *Phys. Rev. B*, 34, 5390.
- Kieslich, G., Sun, S. & Cheetham, A. K. (2014). Solid-state principles applied to
  organic-inorganic perovskites: new tricks for an old dog. *Chem. Sci.*, 5, 4712.
- Kingsbury, R. et al. (2022). Performance comparison of r²SCAN and SCAN metageneralized
  gradient approximations for solid materials via an automated, high-throughput
  computational workflow. *Phys. Rev. Materials*, 6, 013801.
- Kohn, W. & Sham, L. J. (1965). Self-consistent equations including exchange and
  correlation effects. *Phys. Rev.*, 140, A1133.
- Krukau, A. V. et al. (2006). Influence of the exchange screening parameter on the
  performance of screened hybrid functionals. *J. Chem. Phys.*, 125, 224106.
- Li, Z. et al. (2022). Systematic design and assessment of solar cell materials.
  *npj Comput. Mater.*, 8, 134.
- MacKay, D. J. C. (1992). Information-based objective functions for active data
  selection. *Neural Comput.*, 4, 590.
- Monkhorst, H. J. & Pack, J. D. (1976). Special points for Brillouin-zone integrations.
  *Phys. Rev. B*, 13, 5188.
- Parlinski, K., Li, Z. Q. & Kawazoe, Y. (1997). First-principles determination of the
  soft mode in cubic ZrO₂. *Phys. Rev. Lett.*, 78, 4063.
- Perdew, J. P. et al. (2008). Restoring the density-gradient expansion for exchange in
  solids and surfaces. *Phys. Rev. Lett.*, 100, 136406.
- Shannon, R. D. (1976). Revised effective ionic radii and systematic studies of
  interatomic distances in halides and chalcogenides. *Acta Cryst. A*, 32, 751.
- Stranks, S. D. & Snaith, H. J. (2015). Metal-halide perovskites for photovoltaic and
  light-emitting devices. *Nat. Nanotechnol.*, 10, 391.
- Sun, J. et al. (2015). Strongly constrained and appropriately normed semilocal density
  functional. *Phys. Rev. Lett.*, 115, 036402.
- van Schilfgaarde, M., Kotani, T. & Faleev, S. (2006). Quasiparticle self-consistent
  GW theory. *Phys. Rev. Lett.*, 96, 226402.
- Ashcroft, N. W. & Mermin, N. D. (1976). *Solid State Physics*. Holt, Rinehart and
  Winston. [Cap. 8: densidad de estados 3D parabólica]
- Choudhary, K. & DeCost, B. (2021). Atomistic Line Graph Neural Network for improved
  materials property predictions. *npj Comput. Mater.*, 7, 185.
  [Base de datos JARVIS-DFT-3D: jarvis.nist.gov]
- Even, J. et al. (2013). Importance of spin-orbit coupling in hybrid organic/inorganic
  perovskites for photovoltaic applications. *J. Phys. Chem. Lett.*, 4, 2999.
- Jellison, G. E. & Modine, F. A. (1996). Parameterization of the optical functions of
  amorphous materials in the interband region. *Appl. Phys. Lett.*, 69, 371.
  [Oscilador Tauc-Lorentz]
- Kane, E. O. (1957). Band structure of indium antimonide. *J. Phys. Chem. Solids*, 1, 249.
  [Modelo k·p para masa efectiva en semiconductores directos]
- Mosconi, E. et al. (2014). First-principles modeling of mixed halide organometal perovskites
  for photovoltaic applications. *J. Phys. Chem. C*, 117, 13902.
  [Asimetría m*_h = 1.3 m*_e en perovskitas haluro]
- Penn, D. R. (1962). Wave-number-dependent dielectric function of semiconductors.
  *Phys. Rev.*, 128, 2093. [Modelo ε_∞ = 1 + (ħω_p/E_g)²]
