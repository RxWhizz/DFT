# 05 — Test Matrix: Validación post-migración

Checklist a ejecutar en orden después de instalar GPAW master.

---

## T0 — Sanity checks (< 5 min)

```bash
cd /home/luis-ochoa/Documents/Vscode/py/dft

# T0.1 — Versión master instalada
.venv/bin/python3 -c "import gpaw; print(gpaw.__version__)"
# Esperado: algo como 25.x.x+git o 26.x.x (NO 25.7.0)

# T0.2 — MSR1 en _backends
.venv/bin/python3 -c "from gpaw.mixer import _backends; print(list(_backends.keys()))"
# Esperado: lista que incluye 'msr1'

# T0.3 — Davidson y PPCG
.venv/bin/python3 -c "from gpaw.eigensolvers import Davidson; Davidson(niter=4); print('Davidson OK')"

# T0.4 — r²SCAN XC
.venv/bin/python3 -c "
from gpaw.xc import XC
XC('MGGA_X_R2SCAN+MGGA_C_R2SCAN')
print('r2scan XC OK')
"

# T0.5 — HSE06 non-SCF import
.venv/bin/python3 -c "
from gpaw.hybrids.eigenvalues import non_self_consistent_eigenvalues
print('HSE06 non-SCF import OK')
"

# T0.6 — SOC import
.venv/bin/python3 -c "
from gpaw.spinorbit import soc_eigenstates
print('SOC import OK')
"
```

**Criterio de paso:** todos imprimen OK sin ImportError.

---

## T1 — MSR1 mixer funcional (< 10 min)

```bash
# T1.1 — Crear mixer MSR1 vía dict
.venv/bin/python3 -c "
from gpaw.mixer import get_mixer_from_keywords
m = get_mixer_from_keywords(pbc=True, nspins=1, backend='msr1', beta=0.05, nmaxold=10)
print('MSR1 mixer OK:', type(m))
"

# T1.2 — GPAW acepta mixer='msr1' dict
.venv/bin/python3 -c "
from gpaw import GPAW, PW
from gpaw.eigensolvers import Davidson
c = GPAW(
    mode=PW(200),
    xc='PBE',
    kpts={'size': [1,1,1], 'gamma': True},
    mixer={'backend': 'msr1', 'beta': 0.05, 'nmaxold': 5},
    eigensolver=Davidson(niter=2),
    txt=None,
)
print('GPAW con MSR1: OK')
"
```

**Criterio de paso:** sin crash.

---

## T2 — Dry-run pipeline completo (< 5 min)

```bash
# T2.1 — Todos los materiales Sn, dry-run
for MAT in FASnBr3 MASnI3 FASnI3 CsSnI3; do
  echo "=== $MAT ===" && \
  PHASES="$MAT" STEPS="r2scan" DRY_RUN=1 \
    bash calculations/top8_r2scan/run_top8_r2scan.sh 2>&1 | tail -3
done

# T2.2 — calculator_factory sin crash
.venv/bin/python3 -c "
from dft_cspbi3.calculator_factory import GPAWCalculatorFactory
f = GPAWCalculatorFactory()
print('relax setups:', f._paw_setups())
print('r2scan setups:', f._paw_setups_u())
"
```

**Criterio de paso:** sin ImportError, sin crash, dry-run logea steps correctamente.

---

## T3 — GPW compatibilidad hacia atrás (< 10 min)

```bash
# T3.1 — Leer GPW de materiales Pb ya convergidos
for MAT in MAPbI3 FAPbI3 CsPbI3 FAPbBr3; do
  echo "=== $MAT ===" && \
  .venv/bin/python3 -c "
from gpaw import GPAW
c = GPAW('calculations/top8_r2scan/$MAT/06_r2scan/r2scan.gpw', txt=None)
print('atoms:', len(c.get_atoms()), 'E=', round(c.get_potential_energy(), 3), 'eV')
"
done
```

**Criterio de paso:** todos leen sin error, energías coinciden con valores pre-migración.

---

## T4 — Preconv PBE+U con MSR1 (duración: ~30 min para CsSnI3)

```bash
# T4.1 — Lanzar preconv solo CsSnI3 (el más rápido, 5 átomos)
mpirun -n 7 .venv/bin/python3 scripts/preconv_pbe_u.py --mat CsSnI3 \
  > calculations/top8_r2scan/logs/preconv_CsSnI3_master.log 2>&1

# T4.2 — Verificar convergencia sin oscilación
grep "^iter:" calculations/top8_r2scan/CsSnI3/06_r2scan/pre_r2scan.txt | tail -10
```

**Criterio de paso:** converge sin ciclo Pulay, escribe `pre_r2scan.gpw`.

---

## T5 — r²SCAN+U warm start (duración: ~2-4 h CsSnI3)

```bash
# T5.1 — Lanzar r²SCAN para CsSnI3 (warm start desde pre_r2scan.gpw)
PHASES="CsSnI3" STEPS="r2scan" bash calculations/top8_r2scan/run_top8_r2scan.sh

# T5.2 — Verificar gap no-metálico
.venv/bin/python3 -c "
import json
d = json.load(open('calculations/top8_r2scan/CsSnI3/06_r2scan/r2scan_bandgap.json'))
print('CsSnI3 gap:', d['gap_eV'], 'eV (esperado: 0.5-1.2 eV)')
assert d['gap_eV'] > 0.3, 'gap todavía metálico!'
"
```

**Criterio de paso:** converge, escribe GPW, gap > 0.3 eV.

---

## T6 — Regresión materiales Pb (no deben cambiar)

```bash
# T6.1 — Re-leer bandgap de Pb-based para confirmar no regresión
for MAT in MAPbI3 FAPbI3 CsPbI3 FAPbBr3; do
  .venv/bin/python3 -c "
import json
d = json.load(open('calculations/top8_r2scan/$MAT/06_r2scan/r2scan_bandgap.json'))
print('$MAT  gap=', round(d['gap_eV'],3), 'eV  type=', d['gap_type'])
"
done
```

**Criterio de paso:** gaps idénticos a los pre-migración (± 0.01 eV rounding).

---

## Resumen de resultados

| Test | Estado | Notas |
|------|--------|-------|
| T0 sanity | ⏳ | |
| T1 MSR1 | ⏳ | |
| T2 dry-run | ⏳ | |
| T3 GPW compat | ⏳ | |
| T4 preconv MSR1 | ⏳ | |
| T5 r²SCAN warm start | ⏳ | |
| T6 regresión Pb | ⏳ | |
