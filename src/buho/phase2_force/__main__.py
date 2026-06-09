"""CLI Fase 2A."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from buho.phase2_force.collect import collect_labels
from buho.phase2_force.common import OUT_DIR, REPORT_DIR, RUNS_DIR
from buho.phase2_force.prepare import prepare_all, prepare_batch
from buho.phase2_force.runner import run_batch
from buho.phase2_force.selection import BATCH_SIZE, TARGET_N, select_phase2_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="BUHO Fase 2A DFT E+F para MACE.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_select = sub.add_parser("select")
    p_select.add_argument("--n", type=int, default=TARGET_N)
    p_select.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p_select.add_argument("--dry-run", action="store_true")

    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("--batch-id", type=int)
    p_prepare.add_argument("--all", action="store_true")
    p_prepare.add_argument("--config", default="config/generator.yaml")
    p_prepare.add_argument("--runs-dir", default=str(RUNS_DIR))
    p_prepare.add_argument("--cores", type=int, default=8)
    p_prepare.add_argument("--limit", type=int)
    p_prepare.add_argument("--dry-run", action="store_true")

    p_run = sub.add_parser("run")
    p_run.add_argument("--batch-id", type=int, required=True)
    p_run.add_argument("--slots", type=int, default=5)
    p_run.add_argument("--cores", type=int, default=8)
    p_run.add_argument("--poll", type=int, default=30)
    p_run.add_argument("--stagger", type=int, default=8)
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--start-real", action="store_true")
    p_run.add_argument("--resume", action="store_true")
    p_run.add_argument("--override-active", action="store_true")
    p_run.add_argument("--runs-dir", default=str(RUNS_DIR))
    p_run.add_argument("--limit", type=int, default=None)

    p_collect = sub.add_parser("collect")
    p_collect.add_argument("--runs-dir", default=str(RUNS_DIR))
    p_collect.add_argument("--out-dir", default=str(OUT_DIR))
    p_collect.add_argument("--report-dir", default=str(REPORT_DIR))

    args = parser.parse_args()
    if args.cmd == "select":
        result = select_phase2_candidates(args.n, args.batch_size, dry_run=args.dry_run)
    elif args.cmd == "prepare":
        if args.all:
            result = prepare_all(Path(args.config), Path(args.runs_dir), args.cores, dry_run=args.dry_run)
        elif args.batch_id is not None:
            result = prepare_batch(args.batch_id, Path(args.config), Path(args.runs_dir),
                                   args.cores, args.limit, dry_run=args.dry_run)
        else:
            raise SystemExit("Usa --batch-id N o --all")
    elif args.cmd == "run":
        result = run_batch(args.batch_id, args.slots, args.cores, args.poll, args.stagger,
                           args.dry_run, args.resume, args.override_active, Path(args.runs_dir),
                           start_real=args.start_real, limit=args.limit)
    elif args.cmd == "collect":
        result = collect_labels(Path(args.runs_dir), Path(args.out_dir), Path(args.report_dir))
    else:
        raise SystemExit(f"Comando desconocido: {args.cmd}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
