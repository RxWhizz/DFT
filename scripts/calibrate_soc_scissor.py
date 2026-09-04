#!/usr/bin/env python3
"""Calibra chi_SOC(B) = Eg(PBE+SOC) - Eg(PBE) por elemento del sitio B.

Por que hace falta
------------------
El cribado etiqueta candidatos con un bandgap de PBE sin acoplamiento
espin-orbita, y luego lo compara contra una ventana fotovoltaica derivada del
limite de Shockley-Queisser -- que se calcula sobre el bandgap real. Son
magnitudes distintas.

El SOC no es un desplazamiento constante que se pueda ignorar por igual para
todos: es un efecto relativista que crece fuertemente con el numero atomico.
Divide y hunde el minimo de la banda de conduccion, que en estas perovskitas
tiene caracter p del cation B. Para Pb (Z=82) el efecto es de casi 1 eV; para
Ge (Z=32) es mucho menor. Aplicar una correccion unica a toda la familia
sesgaria la comparacion entre elementos B.

Este script mide chi_SOC por elemento, en vez de suponerlo.

Metodo
------
Para cada B en {Pb, Sn, Ge} construye la referencia CsBI3 cubica con la misma
constante de red que usa el pipeline (a = 2*(r_B + r_X)), corre un SCF con los
mismos parametros que el cribado (PBE, ecut 300, malla 2x2x2 centrada en gamma)
y extrae el bandgap dos veces: de los autovalores PBE y de los autovalores con
SOC perturbativo.

Bi e In no se calibran: con carga 3+ no pueden cumplir neutralidad en una
estequiometria ABX3 (1+3-3 = +1), y de hecho no aparecen en ningun candidato
del registro. Los haluros de Bi(III) forman A3B2X9 o dobles perovskitas
A2B'B''X6, que este generador no representa.

Uso (dentro de WSL, con el python de gpaw246):
    python scripts/calibrate_soc_scissor.py --out config/soc_scissor.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

#: Referencia por elemento B: A y X fijos para aislar el efecto del sitio B.
A_REF = "Cs"
X_REF = "I"

#: Radios ionicos (A). Coordinacion 12 para A, 6 para B y X.
RADII = {"Cs": 1.88, "Pb": 1.19, "Sn": 1.18, "Ge": 0.73, "I": 2.20}

#: La misma contraccion del enlace B-X que usa el constructor de estructuras
#: (buho.structure.build_abx3.BOND_CONTRACTION). Calibrar con la celda dilatada
#: daria un chi_SOC que no corresponde a la geometria sobre la que se aplicara:
#: medido, chi_SOC(CsPbI3) pasa de -0.70 eV a la geometria corregida a -1.62 eV
#: con la celda 10 % mas grande. Ge no se contrae (ver el modulo).
BOND_CONTRACTION = {"Pb": 0.912, "Sn": 0.920}

#: Parametros identicos a los del cribado (config/generator.yaml -> dft).
ECUT = 300
KPTS = [2, 2, 2]
SMEARING = 0.01


def _celda(b_site: str):
    from ase import Atoms

    a = 2.0 * (RADII[b_site] + RADII[X_REF]) * BOND_CONTRACTION.get(b_site, 1.0)
    # Perovskita cubica Pm-3m: A en la esquina, B en el centro, X en los centros
    # de cara -- el armazon de octaedros BX6 que comparten vertices.
    return Atoms(
        symbols=[A_REF, b_site, X_REF, X_REF, X_REF],
        scaled_positions=[
            (0.0, 0.0, 0.0),
            (0.5, 0.5, 0.5),
            (0.5, 0.5, 0.0),
            (0.5, 0.0, 0.5),
            (0.0, 0.5, 0.5),
        ],
        cell=[a, a, a],
        pbc=True,
    ), a


def _gap_desde_autovalores(eigenvalues, n_ocupados: int) -> float:
    """VBM = mayor ocupado sobre todos los k; CBM = menor desocupado."""
    vbm = max(e[n_ocupados - 1] for e in eigenvalues)
    cbm = min(e[n_ocupados] for e in eigenvalues)
    return float(cbm - vbm)


def calibrar(b_site: str, verbose: bool = True) -> dict:
    from gpaw import GPAW, PW, FermiDirac
    from gpaw.spinorbit import soc_eigenstates

    atoms, a = _celda(b_site)
    if verbose:
        print(f"  {A_REF}{b_site}{X_REF}3  a = {a:.4f} A", flush=True)

    calc = GPAW(
        mode=PW(ECUT),
        xc="PBE",
        kpts={"size": KPTS, "gamma": True},
        occupations=FermiDirac(SMEARING),
        convergence={"density": 1e-3, "eigenstates": 1e-4, "energy": 1e-4},
        symmetry="off",          # SOC perturbativo necesita la malla completa
        txt=f"soc_calib_{b_site}.txt",
    )
    atoms.calc = calc
    atoms.get_potential_energy()

    n_electrones = int(round(calc.get_number_of_electrons()))
    nk = len(calc.get_ibz_k_points())

    # Sin SOC: cada estado aloja 2 electrones.
    e_pbe = [calc.get_eigenvalues(kpt=k) for k in range(nk)]
    eg_pbe = _gap_desde_autovalores(e_pbe, n_electrones // 2)

    # Con SOC: los estados son espinores y alojan 1 electron cada uno.
    soc = soc_eigenstates(calc)
    e_soc = soc.eigenvalues()
    eg_soc = _gap_desde_autovalores(e_soc, n_electrones)

    chi = eg_soc - eg_pbe
    if verbose:
        print(f"    Eg(PBE) = {eg_pbe:.4f} eV   Eg(PBE+SOC) = {eg_soc:.4f} eV"
              f"   chi_SOC = {chi:+.4f} eV", flush=True)

    return {
        "B": b_site,
        "referencia": f"{A_REF}{b_site}{X_REF}3",
        "a_lat_A": round(a, 4),
        "n_electrones": n_electrones,
        "Eg_pbe_eV": round(eg_pbe, 4),
        "Eg_pbe_soc_eV": round(eg_soc, 4),
        "chi_soc_eV": round(chi, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--elements", default="Pb,Sn,Ge",
                    help="Elementos del sitio B a calibrar (coma-separados).")
    ap.add_argument("--out", default="config/soc_scissor.json",
                    help="Donde escribir la tabla de calibracion.")
    args = ap.parse_args()

    elementos = [e.strip() for e in args.elements.split(",") if e.strip()]
    print(f"Calibrando chi_SOC para: {', '.join(elementos)}")
    print(f"PBE / ecut {ECUT} eV / kpts {KPTS} -- los mismos del cribado\n")

    resultados = []
    for b in elementos:
        if b not in RADII:
            print(f"  {b}: sin radio ionico, se omite", file=sys.stderr)
            continue
        try:
            resultados.append(calibrar(b))
        except Exception as exc:  # noqa: BLE001
            print(f"  {b}: FALLO -- {type(exc).__name__}: {exc}", file=sys.stderr)

    if not resultados:
        print("No se calibro nada.", file=sys.stderr)
        return 1

    tabla = {
        "generado": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "metodo": (
            f"SCF PBE (ecut={ECUT} eV, kpts={KPTS}, gamma-centrada) sobre "
            f"{A_REF}B{X_REF}3 cubica; SOC perturbativo post-SCF."
        ),
        "nota": (
            "chi_SOC es la correccion a sumar al Eg de PBE del cribado. Es "
            "negativa: el SOC hunde el minimo de la banda de conduccion y "
            "cierra el gap. Depende del elemento B porque es un efecto "
            "relativista que crece con el numero atomico."
        ),
        "chi_soc_eV": {r["B"]: r["chi_soc_eV"] for r in resultados},
        "detalle": resultados,
    }

    destino = Path(args.out)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(tabla, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print(f"\nEscrito {destino}")
    for r in resultados:
        print(f"  chi_SOC({r['B']}) = {r['chi_soc_eV']:+.4f} eV")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
