# Reporte Resultados DFT α-CsPbI₃

_Generado: 2026-05-09 13:41_  
_Método: GPAW · PBE-PW · PAW · Phonopy_

## Estado Cálculo
| Paso | Estado |
|---|---|
| 01 Relax | ✓ |
| 02 SCF | ✓ |
| 03 Bandas | ✓ |
| 04 DOS | ✓ |
| 05 SOC | ✓ |
| 05 HSE06+SOC | pendiente |
| 06 HSE06 | pendiente |
| 07 Hessiano | ✓ |
| 07 Fonones (disp 0) | ✓ |
| 07 Fonones (disp 1) | ✓ |
| 07 Fonones (disp 2) | ✓ |
| 07 Fonones (dispersión) | ✓ |
| 07 PES | ✓ |
| 08 LOTO | ✓ |
| 09 Energía formación | ✓ |
| 10 Masas efectivas | ✓ |
| 11 Óptica | ✓ |
| 11 Óptica dispositivo | ✓ |
| 13 Defectos | pendiente |
| 14 Migración NEB | pendiente |
| 15 kMC | pendiente |
| 15 QHA | pendiente |
| 16 AIMD-MLIP | pendiente |

## Estructura
| Parámetro | Valor |
|---|---|
| Fórmula | CsPbI₃ (fase α, Pm-3m) |
| Constante red a | 6.1800 Å |
| Volumen | 236.029 Å³ |
| Átomos celda | 5 (Cs×1, Pb×1, I×3) |
| d(Cs-I) | 4.3699 Å |
| d(Cs-Pb) | 5.3520 Å |
| d(I-I) | 4.3699 Å |
| d(I-Pb) | 3.0900 Å |

## Estructura Electrónica
### SCF (PBE)
| Magnitud | Valor |
|---|---|
| Energía total | -14.053696 eV |
| Nivel Fermi | 3.6576 eV |
| Electrones valencia | 44 |
| puntos k (BZ) | 216 |
| Bandas | 26 |

### Bandas (PBE)
| Magnitud | Valor |
|---|---|
| VBM (rel. Eᶠ) | -0.4738 eV |
| CBM (rel. Eᶠ) | +0.6153 eV |
| Gap (PBE) | **1.0891 eV** |
| Tipo gap | Directo (punto R) |
| puntos k ruta | 40 |

### SOC perturbativo (PBE+SOC)
| Magnitud | Valor |
|---|---|
| Gap (PBE+SOC) | **0.2999 eV** |
| Corrección gap SOC | -0.7892 eV |
| Bandas SOC | 52 (2× original) |
| puntos k | 216 |
| Forma proyección espín | (216, 52, 3) |

### Funcional Híbrido HSE06
_Estado: pendiente - hse06.gpw no generado_

## Masas Efectivas y Métricas Estructurales
| Magnitud | Valor |
|---|---|
| Tipo gap | directo |
| Gap | 1.0891 eV |
| Gap directo | 1.0891 eV |
| punto k VBM | [0.5, 0.5, 0.5] |
| punto k CBM | [0.5, 0.5, 0.5] |
| Masa efectiva electrón | 0.670 m₀ |
| Masa efectiva hueco | 0.098 m₀ |
| Masa reducida | 0.086 m₀ |
| Factor tolerancia Goldschmidt t | 0.822 |
| Factor octaédrico μ | 0.541 |
| Enlace Pb-I medio | 3.0900 Å |
| Varianza enlace Pb-I | 0.0000e+00 Å² |
| Flags | ninguno |

## Propiedades Vibracionales
### Hessiano Γ (desplazamiento finito, ASE)
| Magnitud | Valor |
|---|---|
| Modos en Γ | 15 (3N, N=5) |
| Modos imaginarios (< -10 cm⁻¹) | 0 |
| Rango acústico | 5.5 – 14.4 cm⁻¹ |
| Rango óptico | 16.9 – 106.3 cm⁻¹ |

**Frecuencias Γ (cm⁻¹):**

| Modo | Frec (cm⁻¹) | Carácter |
|---|---|---|
|  1 |     5.47 | acústico |
|  2 |    10.53 | acústico |
|  3 |    14.41 | acústico |
|  4 |    16.90 | óptico |
|  5 |    17.30 | óptico |
|  6 |    18.19 | óptico |
|  7 |    19.18 | óptico |
|  8 |    21.23 | óptico |
|  9 |    22.53 | óptico |
| 10 |    23.75 | óptico |
| 11 |    25.03 | óptico |
| 12 |    25.70 | óptico |
| 13 |   105.39 | óptico |
| 14 |   106.03 | óptico |
| 15 |   106.28 | óptico |

### Fuerzas Phonopy (Δ = 0.02 Å, supercelda 2×2×2)
| Desplazamientos calculados | 3 / 3 |

| Disp | Átomo | Máx\|F\| (eV/Å) | Media\|F\| (eV/Å) | Residual ASR | ASR (%) |
|---|---|---|---|---|---|
| 0 | átomo 1  [0.02, 0.0, 0.0] | 0.00539 | 0.00045 | 9.00e-06 | 0.167% |
| 1 | átomo 9  [0.02, 0.0, 0.0] | 0.08778 | 0.00195 | 5.16e-04 | 0.587% |
| 2 | átomo 17  [0.014142135623731, 0.014142135623731, 0.0] | 0.07911 | 0.00171 | 2.07e-04 | 0.262% |

### Dispersión Fonónica (Phonopy + ASR)
| Magnitud | Valor |
|---|---|
| puntos q ruta | 60 |
| Ramas | 15 |
| Frecuencia mín | -29.89 cm⁻¹ |
| Frecuencia máx | 133.55 cm⁻¹ |
| Modos imaginarios (< -10 cm⁻¹) | 84 |
| Estabilidad | ⚠ 84 modos imaginarios, peor: -29.9 cm⁻¹ |

## Barrido PES Modo Casi-Cero/Negativo
| Magnitud | Valor |
|---|---|
| Puntos calculados | 20 (20 energías SCF cacheadas) |
| Rango Q | -0.500 a +0.500 Å |
| Mínimo E(Q)-E(0) | 0.000048 eV en Q = -0.026 Å |
| Máximo E(Q)-E(0) | 0.020414 eV en Q = -0.500 Å |
| Rango energía | 20.37 meV |
| Doble pozo detectado | no |
| Barrera criterio | 0.0 meV |
| CI-NEB | no lanzado (sin doble pozo) |
| Gráfica | `calculations/alpha/07_vibrational/pes/pes_scan.png` |

## Corrección LO-TO (Cargas Born + ε∞)
### Tensor Dieléctrico (ε∞)

| | x | y | z |
|---|---|---|---|
| x | 3.6472 | 0.0000 | 0.0000 |
| y | -0.0000 | 3.6472 | -0.0000 |
| z | -0.0000 | -0.0000 | 3.6472 |

Promedio isotrópico: ε∞ = 3.6472

### Cargas Efectivas Born Z* (diagonal)

| Átomo | Z*_xx | Z*_yy | Z*_zz | Media |Z*| |
|---|---|---|---|---|
| Cs1 | +1.3697 | +1.3699 | +1.3698 | 0.4568 |
| Pb2 | +4.9781 | +4.9794 | +4.9793 | 1.6597 |
| I3 | -0.7494 | -4.8497 | -0.7498 | 0.7058 |
| I4 | -4.8487 | -0.7499 | -0.7497 | 0.7057 |
| I5 | -0.7497 | -0.7497 | -4.8496 | 0.7057 |

ASR carga Born (Σ Z* → 0), elemento máx: 0.0000 e
(ASR OK ✓)

## Propiedades Ópticas
_RPA, respuesta lineal GPAW · scissor: N/A_

### Métricas Clave

| Magnitud | Valor |
|---|---|
| ε∞ (ω → 0) | 6.1648 |
| Inicio absorción | 0.900 eV |
| α @ 1.5 eV | 6.353e+04 cm⁻¹ |
| α @ 2.0 eV | 1.886e+05 cm⁻¹ |
| α @ 2.5 eV | 4.392e+05 cm⁻¹ |
| α @ 3.0 eV | 6.402e+05 cm⁻¹ |
| Score visible AM1.5G | 1.0000 [0–1] |
| Criterio PV (α ≥ 10⁴ cm⁻¹) | **prometedor** ✓ |

### Función Dieléctrica (muestreada)

| ω (eV) | ε₁ | ε₂ | n | k | α (cm⁻¹) |
|---|---|---|---|---|---|
| 0.50 | 6.4631 | 0.1382 | 2.5424 | 0.0272 | 1.378e+03 |
| 1.00 | 7.9521 | 1.4773 | 2.8320 | 0.2608 | 2.644e+04 |
| 1.50 | 9.2763 | 2.5694 | 3.0742 | 0.4179 | 6.353e+04 |
| 1.73 | 5.6955 | 3.5002 | 2.4884 | 0.7035 | 1.233e+05 |
| 2.00 | 9.4558 | 5.9784 | 3.2127 | 0.9304 | 1.886e+05 |
| 2.50 | 6.0959 | 10.4586 | 3.0167 | 1.7334 | 4.392e+05 |
| 3.00 | 0.0529 | 8.9183 | 2.1179 | 2.1054 | 6.402e+05 |
| 3.50 | -0.2567 | 3.4524 | 1.2659 | 1.3636 | 4.837e+05 |
| 4.00 | 0.6697 | 3.7954 | 1.5039 | 1.2618 | 5.116e+05 |
| 5.00 | -0.0372 | 2.2446 | 1.0507 | 1.0682 | 5.413e+05 |

_Espectro completo guardado en [optical_spectrum_table.csv](calculations/alpha/11_optical/optical_spectrum_table.csv) para graficar._

## Óptica Dispositivo (Beer-Lambert)
| Magnitud | Valor |
|---|---|
| Espesor absorbedor | 500 nm |
| Eficiencia óptica η_opt | 0.9228 |
| Flujo fotones absorbidos | 4.497e+17 fotones/cm²/s |
| Flujo fotones incidente (AM1.5G) | 4.873e+17 fotones/cm²/s |
| Límite J_sc (IQE=1) | **72.04 mA/cm²** |

## HSE06 + Acoplamiento Espín-Órbita
_Estado: pendiente - hse06.gpw no generado_

## Energía Formación
| Magnitud | Valor |
|---|---|
| ΔHf | **-0.189414 eV/f.u.** |
| E(CsPbI₃) | -14.053696 eV/f.u. |
| E(CsI) | -5.394232 eV/f.u. |
| E(PbI₂) | -8.470050 eV/f.u. |
| Estabilidad vs CsI + PbI₂ | estable |
| Resumen | ΔHf = -0.189 eV/f.u. → STABLE vs descomposición binaria |

## Defectos Puntuales (Intrínsecos)
_Estado: pendiente - defectos no corridos_

**Defectos planeados**: V_I, I_i, V_Pb, V_Cs, Pb_I, I_Pb (2×2×2 supercelda, MACE geometría + DFT single-point)

## Migración Iónica (CI-NEB)
_Estado: pendiente - NEB no corrido_

**Rutas planeadas**: V_I ⟨100⟩, V_I ⟨110⟩, I_i ⟨100⟩, V_Cs ⟨100⟩
Literatura: V_I barrera ≈ 0.1–0.25 eV (Azpiroz 2015)

## Monte Carlo Cinético (Fotoestabilidad)
_Estado: pendiente - requiere barreras NEB (L4)_

**Método**: algoritmo BKL, O(N) por evento
**Entradas**: barrera salto V_I, tasa fotogeneración G(x)

## Estabilidad Térmica (Screening MACE-AIMD)
_Estado: pendiente - instalar mace-torch y correr screen_thermal_stability()_

**Método**: NVT Langevin + MACE-MP-0, 10 ps/temperatura
**Temperaturas**: 300/400/500/600 K
**Costo**: ~5 min/T en CPU

## Aproximación Cuasiarmónica (QHA)
_Estado: pendiente - requiere fonones en 6 volúmenes (~42 h)_

**Salidas**: G(T), α(T) expansión térmica, C_p(T), V_eq(T), B₀
**Validez**: T < ~320 K (límite modo blando fase α)
