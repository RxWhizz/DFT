# Reporte validacion DFT — alpha-CsPbI3

*Generado: 2026-05-09 13:41:42*

## 1. Sistema

| Propiedad | Valor |
|----------|-------|
| Fase | alpha |
| Formula | CsPbI3 |
| N atomos | 5 |
| Volumen | nan Å³ |

## 2. Parametros DFT

| Parametro | Valor |
|-----------|-------|
| Funcional XC | PBEsol |
| Corte ondas planas | 450 eV |
| k-point mesh | 6×6×6 |
| Metodo PAW | GPAW (libxc) |
| Condiciones borde | Periodicas (3D) |

## 3. Convergencia SCF

| Revision | Resultado |
|-------|--------|
| Flag convergencia | ✅ Convergido |
| Iteraciones | 12 |
| Final |ΔE| | 0.00e+00 eV |
| Oscilacion | ✅ estable |

## 4. Consistencia fisica

| Revision | Valor | Estado |
|-------|-------|--------|
| Energia total | -14.053696 eV | ✅ negativa |
| Nivel Fermi | 3.6576 eV | ✅ |
| N electrones | 44.0 | ✅ |
| Σ ocupaciones | 44.000 | ✅ consistente |

## 5. Estructura electronica y correccion bandgap

| Propiedad | Valor |
|----------|-------|
| Clasificacion | semiconductor |
| Eg(PBE) | 1.0891 eV |
| Eg(PBE+SOC) | 0.2999 eV |
| χSOC | -0.7892 eV (calculado) |

## 6. Pruebas convergencia

*Prueba convergencia Ecut no ejecutada.*

*Prueba convergencia k-point no ejecutada.*

## 7. Acoplamiento spin-orbita (SOC)

| Revision | Resultado |
|-------|--------|
| SOC aplicado | ✅ Aplicado |
| Gap sin SOC | 1.0891 eV |
| Gap con SOC | 0.2999 eV |
| χSOC | -0.7892 eV | ✅ Plausible |
| Desdoblamiento spin | ✅ Detectado |
| Magnetizacion espuria | ✅ Ninguna |

## 8. Validez global

**ESTADO / STATUS: ✅ VALID**
