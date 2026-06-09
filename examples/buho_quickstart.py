#!/usr/bin/env python3
"""BUHO Quickstart — flujo completo con 20 candidatos sin DFT real.

Demuestra:
  1. Generación de candidatos ABX3 (puros y mixtos)
  2. Filtrado físico (Goldschmidt, octaédrico, carga)
  3. Scoring pre-DFT y selección de top-20
  4. Construcción de estructuras (CIF/POSCAR/traj)
  5. Preparación de directorios de job DFT

Ejecutar:
    python examples/buho_quickstart.py
    python examples/buho_quickstart.py --out /tmp/buho_example

No ejecuta DFT real — solo prepara los archivos de entrada.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CONFIG = ROOT / "config" / "generator.yaml"


def main():
    ap = argparse.ArgumentParser(description="BUHO Quickstart — 20 candidatos sin DFT")
    ap.add_argument("--out", default=None, help="Directorio de salida (default: /tmp/buho_quickstart)")
    ap.add_argument("--n", type=int, default=20, help="Número de candidatos a mostrar")
    args = ap.parse_args()

    out_dir = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="buho_quickstart_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*60}")
    print(f"BUHO Quickstart — {args.n} candidatos")
    print(f"Salida: {out_dir}")
    print(f"{'='*60}\n")

    # ── 1. Generación ─────────────────────────────────────────────────────────
    from buho.generator.heuristic_generator import HeuristicGenerator

    print("1. Generando candidatos ABX3...")
    gen = HeuristicGenerator(CONFIG)
    all_candidates = gen.generate()
    print(f"   Generados: {len(all_candidates)} candidatos brutos")

    from collections import Counter
    mode_counts = Counter(c.generation_mode for c in all_candidates)
    for mode, n in sorted(mode_counts.items()):
        print(f"   {mode:15s}: {n}")

    # ── 2. Filtrado físico ─────────────────────────────────────────────────────
    import yaml
    with open(CONFIG) as f:
        cfg = yaml.safe_load(f)

    from buho.filters.physical_filters import PhysicalFilter

    print("\n2. Aplicando filtros físicos...")
    filt = PhysicalFilter(cfg)
    result = filt.apply(all_candidates)
    print(f"   Pasan: {result.n_passed}  |  Rechazados: {result.n_rejected}")
    for reason, count in sorted(result.stats.items()):
        if count > 0 and reason not in ("total_in", "total_passed"):
            print(f"   Rechazados por {reason}: {count}")

    # ── 3. Scoring y selección ─────────────────────────────────────────────────
    from buho.scoring.pre_dft_score import PreDFTScorer

    print(f"\n3. Scoring y selección de top-{args.n}...")
    scorer = PreDFTScorer(cfg)
    top_scored = scorer.select_top(result.passed, n=args.n)
    df = PreDFTScorer.to_dataframe(top_scored)

    print(f"\n{'Fórmula':<25} {'t':>6} {'μ':>6} {'a₀(Å)':>7} {'Score':>7} {'Modo'}")
    print("-" * 65)
    for s in top_scored:
        c = s.candidate
        print(f"{c.formula:<25} {c.tolerance_t:6.3f} {c.oct_factor:6.3f} "
              f"{c.a0_est_A:7.3f} {s.pre_dft_score:7.4f} {c.generation_mode}")

    # ── 4. Construcción de estructuras ─────────────────────────────────────────
    from buho.structure.build_abx3 import ABX3StructureBuilder

    struct_dir = out_dir / "structures"
    print(f"\n4. Construyendo {len(top_scored)} estructuras en {struct_dir}/...")
    builder = ABX3StructureBuilder(cfg, random_seed=cfg.get("random_seed", 42))
    built = 0
    for s in top_scored:
        c = s.candidate
        job_dir = struct_dir / c.candidate_id
        try:
            atoms, meta = builder.build(c, out_dir=job_dir, export=True)
            built += 1
        except Exception as e:
            print(f"   ✗ {c.formula}: {e}")

    print(f"   Construidas: {built}/{len(top_scored)}")

    # ── 5. Preparación de jobs DFT ────────────────────────────────────────────
    from buho.dft_jobs.prepare_relaxation_jobs import RelaxationJobPreparer

    jobs_dir = out_dir / "relax_basic"
    print(f"\n5. Preparando jobs DFT en {jobs_dir}/...")
    cfg_for_prep = dict(cfg)
    cfg_for_prep["paths"] = {**cfg.get("paths", {}), "relax_dir": str(jobs_dir)}

    prep = RelaxationJobPreparer(cfg_for_prep, project_root=ROOT, n_cores=1, python=sys.executable)
    prepared = prep.prepare(
        top_scored,
        out_root=jobs_dir,
        config_src=CONFIG,
    )
    print(f"   Jobs preparados: {len(prepared)}")

    # ── Resumen ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Resumen:")
    print(f"  Candidatos brutos:   {len(all_candidates)}")
    print(f"  Tras filtros:        {result.n_passed}")
    print(f"  Seleccionados:       {len(top_scored)}")
    print(f"  Estructuras creadas: {built}")
    print(f"  Jobs DFT listos:     {len(prepared)}")
    print(f"\nPara ejecutar DFT en un job:")
    print(f"  cd {jobs_dir}/<candidate_id>")
    print(f"  python input.py")
    print(f"\nPara recolectar resultados después:")
    print(f"  python -m buho.dft collect-results --relax-dir {jobs_dir}")
    print(f"{'='*60}\n")

    # Guardar CSV de selección
    csv_out = out_dir / "top_candidates.csv"
    df.to_csv(csv_out, index=False)
    print(f"CSV guardado: {csv_out}")


if __name__ == "__main__":
    main()
