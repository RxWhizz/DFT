# 02 — Plan de migración GPAW 25.7.0 → master

Migración incremental, preservando reproducibilidad científica.  
Pb-based materials (~75 .gpw) no requieren recalculo.

---

## Fase 0 — Pre-install: fix HSE06 eigensolver ✓ APLICADO

**Bug activo independiente del upgrade:**  
`calculator_factory.py` `_hse06_params()`:
```python
# ANTES (crash si eigensolver_niter configurado):
params["eigensolver"] = {"name": "dav", "niter": int(niter)}
# DESPUÉS:
from gpaw.eigensolvers import Davidson
params["eigensolver"] = Davidson(niter=int(niter))
```

---

## Fase 1 — Instalar GPAW master

```bash
cd /home/luis-ochoa/Documents/Vscode/py/dft

# Backup obligatorio
cp -r .venv .venv_25.7_backup

# Clonar e instalar
git clone https://gitlab.com/gpaw/gpaw.git /tmp/gpaw_master
cd /tmp/gpaw_master
/home/luis-ochoa/Documents/Vscode/py/dft/.venv/bin/pip install -e .
/home/luis-ochoa/Documents/Vscode/py/dft/.venv/bin/python setup.py build_ext --inplace

# Verificar
/home/luis-ochoa/Documents/Vscode/py/dft/.venv/bin/python -c "import gpaw; print(gpaw.__version__)"
gpaw info | grep -E "version|libxc"
```

**Rollback si hay regresión:**
```bash
rm -rf .venv && cp -r .venv_25.7_backup .venv
```

---

## Fase 2 — Verificaciones T0 post-install (<10 min)

```bash
cd /home/luis-ochoa/Documents/Vscode/py/dft

# T0.1 MSR1 disponible
.venv/bin/python3 -c "from gpaw.mixer import _backends; assert 'msr1' in _backends; print('MSR1 OK')"

# T0.2 Davidson
.venv/bin/python3 -c "from gpaw.eigensolvers import Davidson; Davidson(niter=4); print('Davidson OK')"

# T0.3 r²SCAN XC
.venv/bin/python3 -c "from gpaw.xc import XC; XC('MGGA_X_R2SCAN+MGGA_C_R2SCAN'); print('r2scan XC OK')"

# T0.4 non_self_consistent_eigenvalues
.venv/bin/python3 -c "
try:
    from gpaw.hybrids.eigenvalues import non_self_consistent_eigenvalues; print('path 1 OK')
except ImportError:
    from gpaw.hybrids import non_self_consistent_eigenvalues; print('path 2 OK — actualizar import')
"

# T0.5 SOC
.venv/bin/python3 -c "from gpaw.spinorbit import soc_eigenstates; print('SOC OK')"

# T0.6 GPW Pb-based legibles (regresión)
.venv/bin/python3 -c "
from gpaw import GPAW
for mat in ['MAPbI3','FAPbI3','CsPbI3','FAPbBr3']:
    import pathlib
    gpw = pathlib.Path(f'calculations/top8_r2scan/{mat}/06_r2scan/r2scan.gpw')
    if gpw.exists():
        c = GPAW(str(gpw), txt=None)
        print(mat, 'E=', round(c.get_potential_energy(),3), 'eV OK')
"
```

Si algún T0 falla → NO continuar a Fase 3 hasta resolver.

---

## Fase 3 — Parches de código (commits pequeños, en orden)

### Commit 1: MSR1 en config y preconv

**`configs/default_params.yaml`:**
```yaml
r2scan:
  mixer:
    backend: msr1   # era: pulay
    beta: 0.05
    nmaxold: 10
```

**`scripts/preconv_pbe_u.py`:**
```python
mixer={"backend": "msr1", "beta": 0.05, "nmaxold": 10},  # era: pulay
```

### Commit 2: Re-enable MGGA warm start (si T5 lo confirma)

**`src/dft_cspbi3/workflow_manager.py`**, `_run_r2scan()`:
```python
pre_gpw = step_dir / "pre_r2scan.gpw"
if pre_gpw.exists():
    logger.info("r²SCAN: warm start desde PBE+U preconv (%s)", pre_gpw)
    calc = GPAW(str(pre_gpw), **gpaw_kwargs)   # re-habilitar
else:
    calc = self.factory.create("r2scan", txt=str(step_dir / "r2scan.txt"))
```
*Solo aplicar si `mpirun -n 7 python -c "from gpaw import GPAW; GPAW('pre_r2scan.gpw', xc='MGGA...')"` no crashea.*

### Commit 3: Fix import `non_self_consistent_eigenvalues`

**`src/dft_cspbi3/workflow_manager.py`** y **`run_hse06_nsc_dos.py`**:
```python
try:
    from gpaw.hybrids.eigenvalues import non_self_consistent_eigenvalues
except ImportError:
    from gpaw.hybrids import non_self_consistent_eigenvalues
```

### Commit 4: Verificar SOC XC proxy

Correr dry-run SOC sobre CsSnI3 con master.  
Si `calc.hamiltonian.xc = _XC("PBE")` falla → investigar API pública de master para SOC+MGGA.  
**No cambiar parámetros físicos** del cálculo SOC — solo adaptar la llamada API.

### Commit 5 (condicional): Born charges API privada

Si `gpaw.borncharges._all_disp` se eliminó en master:
```python
# Alternativa: copiar _all_disp localmente en validation/phonons.py
# o usar equivalente público si master lo provee
```

---

## Fase 4 — Relanzar materiales Sn

```bash
cd /home/luis-ochoa/Documents/Vscode/py/dft

# Limpiar preconv fallidos (25.7.0)
for MAT in FASnBr3 MASnI3 FASnI3 CsSnI3; do
  rm -f calculations/top8_r2scan/$MAT/06_r2scan/pre_r2scan.{gpw,txt}
done

# Preconv PBE+U con MSR1 (debe converger sin ciclo Pulay)
for MAT in FASnBr3 MASnI3 FASnI3 CsSnI3; do
  nohup mpirun -n 7 .venv/bin/python3 scripts/preconv_pbe_u.py --mat $MAT \
    > calculations/top8_r2scan/logs/preconv_${MAT}_master.log 2>&1 &
done

# Cuando pre_r2scan.gpw aparezca para todos → r²SCAN+U warm start
PHASES="FASnBr3 MASnI3 FASnI3 CsSnI3" \
STEPS="r2scan,soc_r2scan,effective_masses,score" \
bash calculations/top8_r2scan/run_top8_r2scan.sh
```

Criterio de éxito preconv (sin oscilación): energía monótonamente descendente, dens log10 < -3, escribe .gpw.

---

## Fase 5 — Regresión y cierre

```bash
# Gaps Pb-based no deben cambiar
python3 -c "
import json, pathlib
for mat in ['MAPbI3','FAPbI3','CsPbI3','FAPbBr3']:
    d = json.loads(pathlib.Path(f'calculations/top8_r2scan/{mat}/06_r2scan/r2scan_bandgap.json').read_text())
    print(mat, d['gap_eV'], 'eV', d['gap_type'])
"
# Gaps Sn-based deben ser > 0.3 eV post-corrección
python3 -c "
thresholds = {'CsSnI3':0.5,'MASnI3':0.5,'FASnI3':0.3,'FASnBr3':0.3}
import json, pathlib
for mat, thr in thresholds.items():
    d = json.loads(pathlib.Path(f'calculations/top8_r2scan/{mat}/06_r2scan/r2scan_bandgap.json').read_text())
    ok = '✓' if d['gap_eV'] > thr else '✗'
    print(ok, mat, d['gap_eV'], 'eV')
"
```

Completar `migration/06_final_report.md` con resultados reales.

---

## Parámetros físicos — sin cambios

Los siguientes parámetros NO se modifican durante la migración:

| Parámetro | Valor | Justificación |
|-----------|-------|---------------|
| ecut | 450 eV | Convergido y documentado |
| kpts bulk | 6×6×6 | Convergido |
| kpts HSE06 | 2×2×2 | Coste computacional |
| xc r²SCAN | `MGGA_X_R2SCAN+MGGA_C_R2SCAN` | Reproducibilidad |
| U (Sn-5s) | 3.5 eV Dudarev | Parámetro físico justificado |
| smearing | Fermi-Dirac 0.05 eV | Estándar perovskitas |
| forces threshold | 0.01 eV/Å | Convergido |
| SOC | perturbativo, θ=φ=0 | Convención del proyecto |

Si algún parámetro debe cambiar para hacer correr master → marcarlo explícitamente como **cambio metodológico** en `03_claude_patch_notes.md`.
