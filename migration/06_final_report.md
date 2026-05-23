# 06 — Reporte final: GPAW 25.7.0 → master

Estado: **EN PROGRESO**

---

## Resumen ejecutivo

| Item | Resultado |
|------|-----------|
| Versión origen | GPAW 25.7.0 |
| Versión destino | GPAW master (HEAD) |
| Fecha inicio | 2026-05-20 |
| Fecha finalización | ⏳ |
| Materiales afectados | FASnBr3, MASnI3, FASnI3, CsSnI3 |
| Materiales intactos | MAPbI3, FAPbI3, CsPbI3, FAPbBr3 |

---

## Motivación

Los 4 materiales Sn-based no convergieron en 25.7.0 con ninguna combinación de mixer (Pulay/Broyden) ni parámetros probados durante ~5 días de cómputo:

- Oscilaciones Pulay de 1-2 eV incluso en PBE+U preconv (más fácil)
- MSR1 ausente en 25.7.0
- MGGA warm-start imposible (`psit_nG=None` bug)

---

## Cambios de código aplicados

Ver `03_claude_patch_notes.md` para el log completo.

**Pre-migración (25.7.0):**
- ✓ eigensolver r²SCAN: `{'name':'dav'}` → `Davidson(niter=4)`
- ✓ eigensolver HSE06: ídem
- ✓ mixer: revertido a `pulay` (temporal)
- ✓ warm start: deshabilitado (cold start, psit_nG=None bug)

**Post-migración (master 25.7.1b1):**
- ✓ Commit 1: mixer `pulay` → `msr1` (default_params.yaml + preconv_pbe_u.py)
- ✓ Commit 3: try/except ImportError para `non_self_consistent_eigenvalues` en `run_hse06_nsc_dos.py`
- ✓ Commit 4: SOC proxy hack `calc.hamiltonian.xc = _XC("PBE")` → `ignore_xc_potential=True` (API pública master)
- ✓ Commit 5: `_all_disp` inlineada en `validation/phonons.py` (removida en master)
- ✗ Commit 2 (warm start): NO aplicado — GPW format cambia en master (campo `ked` para MGGA); warm start GGA→MGGA requeriría patch en gpw.py del master

**Descubrimiento importante:** GPAW master cambió formato GPW para MGGA (requiere campo `ked` = kinetic energy density). Los ~10 GPW MGGA de 25.7.0 son **incompatibles** con master para lectura. GPW GGA/PBE (relax, scf, bands) SÍ son compatibles.

**libxc:** actualizado de 5.2.3 (sistema) a 7.0.0 (compilado en venv con DISABLE_FHC=ON). El warning FHC fue eliminado. GPAW reconstruido con rpath a libxc.so.15.

---

## Resultados de tests

Ver `05_test_matrix.md` para comandos detallados.

| Test | Estado | Observaciones |
|------|--------|---------------|
| T0 sanity imports | ✓ | MSR1 ✓ Davidson ✓ r²SCAN XC ✓ (sin FHC warning) SOC ✓ non_self_consistent ✓ |
| T1 MSR1 funcional | ✓ | backend='msr1' aceptado por GPAW sin crash |
| T2 dry-run pipeline | ⏳ | pendiente |
| T3 GPW compat Pb-based | ✗ INCOMPATIBLE | master requiere campo `ked` en GPW MGGA; archivos 25.7.0 incompatibles → recalcular todo, GPW legacy en `gpw-legacy/` |
| T4 preconv CsSnI3 (benchmark) | 🔄 corriendo | iter 21, dens convergida, eigst convergida iter 21; oscilación energía ~1 eV (MSR1 mejor que Pulay) |
| T5 r²SCAN+U warm start CsSnI3 | ⏳ | esperar T4 |
| T6 regresión Pb-based | ⏳ | recalcular (GPW incompatible) |

---

## Gaps r²SCAN+U esperados post-migración

| Material | PBE (ref) | r²SCAN+U objetivo | Resultado |
|----------|-----------|------------------|-----------|
| CsSnI3 | ~0.0 eV | 0.5–1.2 eV | ⏳ |
| MASnI3 | ~0.0 eV | 0.5–1.2 eV | ⏳ |
| FASnI3 | ~0.33 eV | 0.8–1.3 eV | ⏳ |
| FASnBr3 | ~0.0 eV | 0.5–1.5 eV | ⏳ |

---

## Conclusión

*(Rellenar al finalizar)*

---

## Lecciones aprendidas

*(Rellenar al finalizar)*
