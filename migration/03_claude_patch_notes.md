# 03 — Log de parches: GPAW 25.7.0 → master

Registro cronológico. Cada entrada incluye: qué cambia, por qué, impacto científico.

---

## Parches aplicados en GPAW 25.7.0 (pre-migración)

### [FIX] eigensolver r²SCAN: dict → Davidson object
- **Archivos:** `calculator_factory.py` `_r2scan_params()`, `scripts/preconv_pbe_u.py`
- **Antes:** `eigensolver={"name":"dav","niter":4}` → crash `TypeError: 'str' object is not callable`
- **Después:** `from gpaw.eigensolvers import Davidson; eigensolver=Davidson(niter=4)`
- **Impacto científico:** ninguno — mismo eigensolver, solo sintaxis corregida
- **Estado:** ✓ aplicado

### [FIX] eigensolver HSE06: dict → Davidson object  ← NUEVO (2026-05-20)
- **Archivo:** `calculator_factory.py` `_hse06_params()` ~línea 237
- **Antes:** `params["eigensolver"] = {"name": "dav", "niter": int(niter)}` → crash idéntico al r²SCAN
- **Después:** `from gpaw.eigensolvers import Davidson; params["eigensolver"] = Davidson(niter=int(niter))`
- **Condición:** solo si `eigensolver_niter` está configurado en YAML (actualmente `eigensolver_niter: 3`)
- **Impacto científico:** ninguno — mismo eigensolver, solo sintaxis
- **Estado:** ✓ aplicado

### [TEMP] MSR1 → pulay (mixer r²SCAN)
- **Archivos:** `default_params.yaml`, `calculator_factory.py`
- **Razón:** MSR1 ausente en 25.7.0 (`_backends` solo tiene pulay/fft/broyden)
- **Cambio:** `backend: msr1` → `backend: pulay`
- **Impacto científico:** Pulay oscila para Sn+U+MGGA; ninguno para Pb-based
- **Estado:** ✓ aplicado (revertir en master → Commit 1)

### [TEMP] MGGA warm start → cold start
- **Archivo:** `workflow_manager.py` `_run_r2scan()` ~590
- **Razón:** `GPAW(pre_gpw, xc='MGGA...')` crashea — `psit_nG=None` durante `wfs.initialize`
- **Cambio:** `calc = GPAW(str(pre_gpw), **gpaw_kwargs)` → `calc = self.factory.create("r2scan", ...)`
- **Impacto científico:** pierde el warm start de densidad; posiblemente más iteraciones SCF
- **Estado:** ✓ aplicado (re-evaluar en master → Commit 2)

### [ADD] Script preconv_pbe_u.py
- **Archivo:** `scripts/preconv_pbe_u.py` (nuevo)
- **Razón:** PBE+U con setups={'Sn':':s,3.5'} para garantizar que warm start funcione (mismos PAW)
- **Impacto científico:** ninguno — solo densidad inicial, no cambia resultado SCF final
- **Estado:** ✓ aplicado

### [ADD] relax_sym step + FixSymmetry
- **Archivos:** `calculator_factory.py`, `workflow_manager.py`, `default_params.yaml`
- **Razón:** Materiales FA+ tienen tilting octaédrico artificial sin FixSymmetry → gap subestimado
- **Impacto científico:** cambia geometría relajada para FA-based; justificado físicamente
- **Estado:** ✓ aplicado

### [ADD] DFT+U Dudarev Sn-5s (U=3.5 eV)
- **Archivos:** `default_params.yaml` (`dft_u.Sn`), `calculator_factory.py` (`_paw_setups_u()`)
- **Razón:** Autointeracción en Sn-5s colapsa gap a ~0 eV sin corrección U
- **Impacto científico:** **cambio metodológico** — gap Sn-based aumenta de ~0 a ~0.5-1.2 eV esperado
- **Estado:** ✓ aplicado

---

## Parches pendientes post-install master

### [REVERT] pulay → msr1 (Commit 1)
- **Archivos:** `default_params.yaml`, `scripts/preconv_pbe_u.py`
- `backend: pulay` → `backend: msr1`, `beta: 0.02 → 0.05`, `nmaxold: 15 → 10`
- Condición previa: T0.1 (MSR1 en _backends) pasado ✓
- **Estado:** ✓ aplicado (2026-05-20)

### [REVERT] Cold start → warm start MGGA (Commit 2)
- **Archivo:** `workflow_manager.py` `_run_r2scan()`
- Re-habilitar `calc = GPAW(str(pre_gpw), **gpaw_kwargs)`
- Condición previa: verificar que master no crashea con `psit_nG`
- **Estado:** pendiente (verificar con test T5)

### [FIX] non_self_consistent_eigenvalues import (Commit 3)
- **Archivos:** `run_hse06_nsc_dos.py` ~101 (workflow_manager ya tenía try/except)
- try/except para fallback de import si el módulo se mueve en master
- T0.4 confirmó: path 1 (`gpaw.hybrids.eigenvalues`) funciona en 25.7.1b1
- **Estado:** ✓ aplicado (2026-05-20)

### [FIX] SOC XC proxy → ignore_xc_potential=True (Commit 4)
- **Archivo:** `workflow_manager.py` `_run_soc_scan()`, `_run_soc_r2scan()`
- Antes: `calc.hamiltonian.xc = _XC("PBE")` (proxy hack, API interna)
- Después: `soc_eigenstates(..., ignore_xc_potential=True)` — API pública master
- master/gpaw/spinorbit.py confirmó que `ignore_xc_potential` existe como parámetro público
- **Impacto científico:** negligible — dU/dr dominada por Hartree; XC aporta <5% a SOC
- **Estado:** ✓ aplicado (2026-05-20)

### [FIX] Born charges _all_disp inlining (Commit 5)
- **Archivo:** `validation/phonons.py` ~181
- `_all_disp` fue eliminada de `gpaw.borncharges` en master
- Fix: try/except ImportError → función inlined desde 25.7.0 (6 líneas, lógica trivial)
- La función generaba desplazamientos cartesianos para todas las combinaciones (ia, iv, sign)
- **Estado:** ✓ aplicado (2026-05-20)

---

## Tabla de estado

| Parche | Tipo | Estado | Impacto físico |
|--------|------|--------|----------------|
| eigensolver r²SCAN | Fix bug | ✓ done | ninguno |
| eigensolver HSE06 | Fix bug | ✓ done | ninguno |
| MSR1 mixer | Revert temp | ⏳ post-install | mejora convergencia Sn |
| MGGA warm start | Revert temp | ⏳ post-install | menos iteraciones |
| non_self_consistent_eigenvalues | Fix import | ⏳ post-install | ninguno |
| SOC XC proxy | Verificar | ⏳ post-install | potencial si cambia |
| Born charges _all_disp | Fix condicional | ⏳ post-install | ninguno si API equivalente |
| relax_sym / FixSymmetry | Feature | ✓ done | cambio geom FA-based |
| DFT+U Sn (U=3.5 eV) | Feature | ✓ done | **cambio metodológico** |
| preconv_pbe_u.py | Feature | ✓ done | solo densidad inicial |

---

## Errores encontrados y resueltos (cronológico)

| Fecha | Error | Causa raíz | Fix |
|-------|-------|-----------|-----|
| 2026-05-19 | `TypeError: 'str' object is not callable` | eigensolver dict en r²SCAN | `Davidson(niter=4)` |
| 2026-05-19 | `AttributeError: 'NoneType'.shape` | MGGA warm start PW mode | cold start |
| 2026-05-19 | `_backends` no tiene 'msr1' | MSR1 ausente en 25.7.0 | pulay temporal |
| 2026-05-20 | Oscilación Pulay 1–2 eV | Pulay insuficiente para Sn+U+MGGA | migrar a master |
| 2026-05-20 | `TypeError` en HSE06 (eigensolver) | mismo bug que r²SCAN, no corregido | `Davidson(niter=int(niter))` |
