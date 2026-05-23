# 00 — Context: Por qué migrar al GPAW master

## Versión instalada
- **GPAW 25.7.0** (pip, venv en `.venv/`)
- Python 3.12 | ASE 3.24 | OpenMPI 7×

## Problema raíz
Los materiales **Sn-based con DFT+U** (MASnI3, FASnI3, FASnBr3, CsSnI3) no convergen en GPAW 25.7.0:

| Síntoma | Causa en 25.7.0 |
|---------|----------------|
| Ciclo Pulay (~1-2 eV oscilación) | Mixer Pulay/Broyden insuficiente para Sn+U+MGGA |
| MSR1 no disponible | Ausente en 25.7.0; solo en master |
| MGGA warm-start imposible | `psit_nG=None` durante `wfs.initialize` antes de `hamiltonian.update` |
| eigensolver dict crash | `{'name':'dav','niter':4}` inválido; necesita `Davidson(niter=4)` |

## Lo que ofrece el master
- **MSR1 mixer** como default (más estable que Pulay para metales/MGGA)
- **ppcg eigensolver** (mejor convergencia banda a banda)
- **fullspin spin-driver** integrado
- Inicialización MGGA corregida (τ inicial desde superposición de átomos)
- Peso mixerdefault cambia 50→20 para sistemas periódicos

## Historial de intentos en 25.7.0
| Intento | Resultado |
|---------|-----------|
| Pulay β=0.05 nmaxold=8 | Oscila, nunca converge |
| Pulay β=0.05 nmaxold=10-12 | Oscila igual |
| Broyden β=0.05-0.1 | Oscila, dens stuck -2.3 a -2.7 |
| PBE+U preconv → warm start MGGA | Crash: `psit_nG=None` |
| MSR1 dict | Crash: `_backends` no tiene msr1 en 25.7.0 |

## Decisión
Migrar a **GPAW master** (commit HEAD de la rama `master` de GitLab de GPAW).
Materiales Pb-based ya convergidos en 25.7.0 (MAPbI3, FAPbI3, CsPbI3, FAPbBr3) no requieren recalculo.
