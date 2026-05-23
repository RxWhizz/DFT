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
# Próximo intento r²SCAN+U Sn-based:
mixer:
  backend: msr1
  beta: 0.002      # muy pequeño — movimiento local únicamente
  nmaxold: 5
  weight: 100      # Kerker para charge sloshing
occupations:
  width: 0.2       # sweet spot encontrado
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

### Si Kerker tampoco funciona

Ramping de U (más costoso pero más robusto):
1. Converger con U=0 (PBE puro, siempre converge)
2. Reiniciar con U=1.0 eV desde el GPW anterior
3. Reiniciar con U=2.0 eV
4. Reiniciar con U=3.5 eV

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

---

## Notas de infraestructura

- `/tmp/gpaw_master` se borra en cada reboot — recrear desde `/tmp/siteconfig_gpaw.py`
- `siteconfig.py` incluye: `mpicxx`, libxc-7, BLAS, ScaLAPACK-OpenMPI
- Sin ScaLAPACK: crash `BLACSDistribution.desc` en sistemas grandes (FASnBr3, FASnI3)
- `setuptools` debe ser ≥77.0.3 para compilar GPAW master (pyproject.toml license field)
- `pybind11` debe estar instalado en venv para `--no-build-isolation`
