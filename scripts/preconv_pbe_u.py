#!/usr/bin/env python3
"""Pre-converge PBEsol+U density to seed r²SCAN+U warm start.

PBEsol+U uses the same PAW setups as r²SCAN+U (setups={'Sn': ':s,3.5'}),
so GPAW can reuse the wavefunctions in the subsequent r²SCAN restart.

Usage:
    cd dft/
    mpirun -n 7 .venv/bin/python3 scripts/preconv_pbe_u.py --mat MASnI3
    mpirun -n 7 .venv/bin/python3 scripts/preconv_pbe_u.py --mat FASnI3
    mpirun -n 7 .venv/bin/python3 scripts/preconv_pbe_u.py --mat FASnBr3
    mpirun -n 7 .venv/bin/python3 scripts/preconv_pbe_u.py --mat CsSnI3
"""
import argparse
import pathlib
import yaml
from ase.io import read
from gpaw import GPAW, PW
from gpaw.eigensolvers import Davidson


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mat", required=True, help="Material name, e.g. MASnI3")
    parser.add_argument("--workdir", default="calculations/top8_r2scan")
    parser.add_argument("--config", default="configs/default_params.yaml")
    args = parser.parse_args()

    dft_root = pathlib.Path(__file__).parent.parent
    work_mat = dft_root / args.workdir / args.mat
    config = yaml.safe_load((dft_root / args.config).read_text())
    r2cfg = config["r2scan"]
    dft_u_cfg = config.get("dft_u", {})

    # Build setups identical to r²SCAN+U run (Sn ':s,3.5')
    setups: dict[str, str] = {}
    for elem, ucfg in dft_u_cfg.items():
        orbital = ucfg.get("orbital", "d")
        u_ev = float(ucfg.get("u_ev", 0.0))
        if u_ev > 0:
            setups[elem] = f":{orbital},{u_ev}"

    # Source structure: prefer relax_sym (FA materials), fallback to relax
    relax_sym = work_mat / "01_relax_sym" / "relax_sym.gpw"
    relax = work_mat / "01_relax" / "relax.gpw"
    src = relax_sym if relax_sym.exists() else relax
    if not src.exists():
        raise FileNotFoundError(f"No source GPW found for {args.mat}: tried {relax_sym} and {relax}")

    out_dir = work_mat / "06_r2scan"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_gpw = out_dir / "pre_r2scan.gpw"
    out_txt = out_dir / "pre_r2scan.txt"

    print(f"[preconv] {args.mat}: PBEsol+U from {src.name} → {out_gpw.name}")
    print(f"[preconv] setups={setups}  kpts={r2cfg.get('kpts',[6,6,6])}  ecut={r2cfg.get('ecut',450)}")

    atoms = read(str(src))

    calc = GPAW(
        mode=PW(r2cfg.get("ecut", 450)),
        xc="PBE",
        kpts={"size": r2cfg.get("kpts", [6, 6, 6]), "gamma": True},
        setups=setups,
        occupations={
            "name": r2cfg.get("occupations", {}).get("name", "fermi-dirac"),
            "width": 0.5,
        },
        convergence={"density": 0.01, "energy": 1e-3, "eigenstates": 1e-5},
        mixer={"backend": "msr1", "beta": 0.02, "nmaxold": 10},
        eigensolver=Davidson(niter=4),
        parallel={"domain": 1},
        txt=str(out_txt),
    )
    atoms.calc = calc
    atoms.get_potential_energy()
    calc.write(str(out_gpw))
    print(f"[preconv] Done: {out_gpw}")


if __name__ == "__main__":
    main()
