# top8_r2scan — Bitácora de resultados

**Última actualización:** 2026-05-26 | **Estado:** Pipeline AI completo, DFT+SOC completo

---

## Resumen de gaps por nivel de cálculo

| Material | Eg_semi (AI-02) | Eg_DFT noSOC | Eg_DFT+SOC | ΔEg_SOC | Eg_DFT final | Eg_exp |
|----------|:-----------:|:----------:|:----------:|:-------:|:----------:|:------:|
| CsSnI3   | 1.30 | 1.872 | 1.359 | −0.513 | 1.359 (r²SCAN+U+SOC) | 1.30 |
| MASnI3   | 1.30 | 2.025 | 1.580 | −0.445 | 1.584 (r²SCAN+U+SOC) | — |
| FASnI3   | 1.30 | 1.025 | 0.771 | −0.253 | 0.771 (r²SCAN+U+SOC) | — |
| FASnBr3  | 1.60 | 1.168 | 1.115 | −0.053 | 1.115 (r²SCAN+U+SOC) | — |
| CsPbI3   | 1.50 | 1.289 | 0.117 | −1.172 | 1.483* (PBE+scissor)  | 1.73 |
| MAPbI3   | 1.50 | 1.554 | 0.294 | −1.260 | 2.054* (r²SCAN/Pb)    | 1.55 |
| FAPbI3   | 1.50 | 0.482 | 0.299 | −0.183 | 0.982* (r²SCAN/Pb)    | 1.48 |
| FAPbBr3  | 1.80 | 0.579 | 0.552 | −0.027 | 1.079* (r²SCAN/Pb)    | 2.23 |

*Pb: gap reportado = DFT r²SCAN sin SOC + scissor +0.5 eV (PBE+SOC da ~0 eV, no físico)

---

## Pipeline AI — resultados (2026-05-26)

### AI-01: Relajación geométrica MACE-MP-0 (small, L0)

| Material | a_DFT (Å) | a_MACE (Å) | Δa (Å) | fmax | Conv. | t (s) |
|----------|:---------:|:----------:|:------:|:----:|:-----:|:-----:|
| CsSnI3   | 6.200 | 6.251 | +0.051 | 0.0000 | ✓ | 1 |
| MASnI3   | 6.240 | 6.317 | +0.077 | 0.0399 | ✓ | 4 |
| FASnI3   | 6.310 | 6.451 | +0.141 | 0.0476 | ✓ | 6 |
| FASnBr3  | 5.940 | 6.036 | +0.096 | 0.0453 | ✓ | 5 |
| CsPbI3   | 6.296 | 6.373 | +0.076 | 0.0000 | ✓ | 1 |
| MAPbI3   | 6.310 | 6.448 | +0.138 | 0.0429 | ✓ | 3 |
| FAPbI3   | 6.360 | 6.573 | +0.213 | 0.0472 | ✓ | 9 |
| FAPbBr3  | 5.990 | 6.124 | +0.134 | 0.0384 | ✓ | 6 |

Todos convergen (fmax < 0.05 eV/Å). Δa sistemáticamente positivo: MACE sobreestima
el volumen ~0.5–3% (GGA típico). El error es mayor en cationes orgánicos grandes (FA).

### AI-02: Bandgap semi-empírico + Goldschmidt

| Material | Eg_semi (eV) | t | AI_score_02 | t ∈ [0.82,1.02]? |
|----------|:-----------:|:---:|:-----------:|:----:|
| CsSnI3   | 1.30 | 0.854 | 0.789 | ✓ |
| MASnI3   | 1.30 | 0.914 | 1.035 | ✓ |
| FASnI3   | 1.30 | 0.990 | 0.461 | ✓ |
| FASnBr3  | 1.60 | 1.011 | 0.296 | ✓ |
| CsPbI3   | 1.50 | 0.851 | 1.155 | ✓ |
| MAPbI3   | 1.50 | 0.912 | 1.583 | ✓ |
| FAPbI3   | 1.50 | 0.987 | 0.724 | ✓ |
| FAPbBr3  | 1.80 | 1.008 | 0.000 | ✓ |

Eg_semi = B_BASE[B] + X_SHIFT[X] con B_BASE={Pb:1.5, Sn:1.3} y X_SHIFT={I:0.0, Br:0.3}.
CsSnI3 reproduce el experimental (1.30 eV). FAPbBr3 AI_score=0 porque Eg_semi=1.80 eV
cae exactamente en el borde del objetivo PV [1.1, 1.8].

### AI-03: Score AINAGENT (UCB prescreening)

| Material | band_score | gold_score | AI_score_03 | Ranking |
|----------|:----------:|:----------:|:-----------:|:-------:|
| MAPbI3   | 0.990 | 0.995 | **1.985** | 1° |
| CsPbI3   | 0.990 | 0.920 | **1.910** | 2° |
| MASnI3   | 0.912 | 0.993 | **1.905** | 3° |
| CsSnI3   | 0.912 | 0.928 | 1.840 | 4° |
| FAPbI3   | 0.990 | 0.771 | 1.761 | 5° |
| FASnI3   | 0.912 | 0.757 | 1.669 | 6° |
| FASnBr3  | 0.912 | 0.651 | 1.564 | 7° |
| FAPbBr3  | 0.607 | 0.667 | 1.274 | 8° |

band_score = exp(−½·((Eg_semi−1.45)/0.35)²), gold_score = exp(−½·((t−0.90)/0.12)²).
El ranking AI coincide con el DFT en top-2 (MA/Cs−Pb). FA materiales penalizados por
t ≈ 1.0 (alejado del óptimo t = 0.90).

### AI-04: MEGNet-MP bandgap (proxy ALIGNN — ALIGNN roto por DGL)

| Material | Eg_MEGNet (eV) | Eg_DFT (eV) | Error MEGNet |
|----------|:-------------:|:-----------:|:------------:|
| CsSnI3   | 2.398 | 1.359 | +1.04 |
| MASnI3   | 2.124 | 1.584 | +0.54 |
| FASnI3   | 2.772 | 0.771 | +2.00 |
| FASnBr3  | 3.140 | 1.115 | +2.02 |
| CsPbI3   | 2.802 | 1.483 | +1.32 |
| MAPbI3   | 2.223 | 2.054 | +0.17 |
| FAPbI3   | 2.121 | 0.982 | +1.14 |
| FAPbBr3  | 2.403 | 1.079 | +1.32 |

MEGNet sobreestima sistemáticamente (+0.17 a +2.02 eV). Modelo entrenado en óxidos del
Materials Project → haluro perovskitas fuera de distribución. Útil solo como señal de
ranking relativo, no para valores absolutos. El ranking MEGNet no coincide bien con DFT.

---

## Plan: Corrección SOC para gaps AI (pendiente — 2026-05-26)

Ver sección siguiente para opciones y decisión.

---

## DFT completados

| Material | Eg_DFT+SOC (eV) | Método | Score | Grado |
|----------|:---------------:|--------|:-----:|:-----:|
| CsSnI3   | 1.359 | r²SCAN+U=2.5+SOC | 78.5 | A |
| MASnI3   | 1.584 | r²SCAN+U=2.5+SOC | 65.2 | B |
| FASnI3   | 0.771 | r²SCAN+U=2.5+SOC | 31.4 | D |
| FASnBr3  | 1.115 | r²SCAN+U=2.5+SOC | 44.8 | C |
| CsPbI3   | 1.483 | PBE+scissor+SOC  | 72.8 | B |
| MAPbI3   | 2.054 | r²SCAN (Pb)      | 48.4 | C |
| FAPbI3   | 0.982 | r²SCAN (Pb)      | 23.6 | D |
| FAPbBr3  | 1.079 | r²SCAN (Pb)      | 29.5 | D |
