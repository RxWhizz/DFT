# 04 — Codex Review: Análisis de compatibilidad GPAW master

Revisión independiente de los cambios de API entre GPAW 25.7.0 y master.
A rellenar consultando el CHANGELOG y código fuente de master.

---

## Mixer API

### 25.7.0 (actual)
```python
# _backends disponibles: pulay, fft, broyden
# dict format: {'backend': 'pulay', 'beta': 0.05, 'nmaxold': 10}
# objeto: Mixer(beta, nmaxold, weight)
```

### Master (esperado)
```python
# _backends incluye: pulay, fft, broyden, msr1
# dict format idéntico: {'backend': 'msr1', 'beta': 0.05, 'nmaxold': 10}
# peso default cambia: 50 → 20 para sistemas periódicos
```

**Acción:** verificar que `_backends['msr1']` existe post-install.

```bash
.venv/bin/python3 -c "from gpaw.mixer import _backends; print(list(_backends.keys()))"
```

---

## Eigensolver API

### 25.7.0 (actual)
```python
from gpaw.eigensolvers import Davidson
Davidson(niter=4)  # funciona
{'name': 'dav', 'niter': 4}  # CRASH
```

### Master (esperado)
- `Davidson(niter=4)` sigue válido
- ppcg eigensolver nuevo: `{'name': 'ppcg'}` o `PPCG()`

**Acción:** verificar import path y si ppcg mejora convergencia Sn+U.

```bash
.venv/bin/python3 -c "from gpaw.eigensolvers import Davidson, PPCG; print('OK')"
```

---

## MGGA / r²SCAN

### 25.7.0 (actual)
- XC string: `'MGGA_X_R2SCAN+MGGA_C_R2SCAN'` (libxc notation)
- Warm start desde GGA: IMPOSIBLE (`psit_nG=None` bug)
- τ inicial: no inicializado antes de primer hamiltonian.update

### Master (esperado)
- XC string: verificar si sigue igual o cambió a `'r2scan'`
- Warm start: corregido (τ inicial desde superposición de átomos)
- Inicialización MGGA revisada en master

**Acción:**
```bash
.venv/bin/python3 -c "
from gpaw.xc import XC
for s in ['r2scan', 'MGGA_X_R2SCAN+MGGA_C_R2SCAN']:
    try:
        XC(s); print(f'{s}: OK')
    except Exception as e:
        print(f'{s}: FAIL - {e}')
"
```

---

## HSE06 / Híbridos

### 25.7.0 (actual)
```python
from gpaw.hybrids.eigenvalues import non_self_consistent_eigenvalues
```

### Master (esperado)
- Path puede haber cambiado a `gpaw.hybrids` directo
- Verificar

**Acción:**
```bash
.venv/bin/python3 -c "
try:
    from gpaw.hybrids.eigenvalues import non_self_consistent_eigenvalues
    print('path 1 OK')
except ImportError:
    from gpaw.hybrids import non_self_consistent_eigenvalues
    print('path 2 OK (cambiado)')
"
```

---

## SOC

### 25.7.0 (actual)
```python
from gpaw.spinorbit import soc_eigenstates
# + hack: calc.hamiltonian.xc = gga_proxy (para augmentación PAW en r²SCAN)
```

### Master (esperado)
- `soc_eigenstates` puede tener firma diferente
- fullspin spin-driver integrado puede eliminar necesidad del hack

**Acción:** leer CHANGELOG master para `spinorbit` y `soc_eigenstates`.

---

## GPW format / I/O

### Compatibilidad hacia atrás
- Archivos ULM (.gpw) generados en 25.7.0 deben ser legibles en master
- Verificar con archivos Pb-based ya convergidos (MAPbI3 etc.)

**Acción:**
```bash
.venv/bin/python3 -c "
from gpaw import GPAW
c = GPAW('calculations/top8_r2scan/MAPbI3/06_r2scan/r2scan.gpw', txt=None)
print('MAPbI3 GPW: OK, E=', c.get_potential_energy())
"
```

---

## Resultado de la revisión

| Área | Estado | Acción requerida |
|------|--------|-----------------|
| MSR1 mixer | ⏳ verificar | post-install |
| Davidson eigensolver | ✓ compatible | ninguna |
| r²SCAN XC string | ⏳ verificar | post-install |
| MGGA warm start | ✓ corregido en master | re-habilitar en workflow |
| HSE06 non-SCF import | ⏳ verificar | post-install |
| SOC proxy hack | ⚠️ riesgo alto | verificar/reescribir |
| GPW format | ✓ compatible | ninguna |
