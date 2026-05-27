"""CLI inference: GNN property prediction for top-8 or arbitrary ABX3 materials.

Usage
-----
    # All top-8, ranked
    .venv/bin/python3 -m ml_surrogate.inference --mat all

    # Single material
    .venv/bin/python3 -m ml_surrogate.inference --mat CsPbI3

    # Arbitrary composition
    .venv/bin/python3 -m ml_surrogate.inference --A Rb --B Sn --X Br

    # JSON output (schema compatible with ai_predictions.json)
    .venv/bin/python3 -m ml_surrogate.inference --mat all --out gnn_predictions.json

    # Tune UCB exploration
    .venv/bin/python3 -m ml_surrogate.inference --mat all --beta 2.0
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ml_surrogate.gnn_predictor import GNNPredictor, GNNResult
from ml_surrogate.structure_builder import PerovskiteStructureBuilder
from ml_surrogate.bayes_optimizer import GNNAcquisition, AcquisitionScore

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────

TOP8_MATS: dict[str, dict] = {
    "CsSnI3":  {"A": "Cs", "B": "Sn", "X": "I"},
    "MASnI3":  {"A": "MA", "B": "Sn", "X": "I"},
    "FASnI3":  {"A": "FA", "B": "Sn", "X": "I"},
    "FASnBr3": {"A": "FA", "B": "Sn", "X": "Br"},
    "CsPbI3":  {"A": "Cs", "B": "Pb", "X": "I"},
    "MAPbI3":  {"A": "MA", "B": "Pb", "X": "I"},
    "FAPbI3":  {"A": "FA", "B": "Pb", "X": "I"},
    "FAPbBr3": {"A": "FA", "B": "Pb", "X": "Br"},
}

DFT_REF: dict[str, dict] = {
    "CsSnI3":  {"Eg_dft_eV": 1.359, "Eg_exp_eV": 1.30,  "dft_method": "r²SCAN+U+SOC"},
    "MASnI3":  {"Eg_dft_eV": 1.584, "Eg_exp_eV": None,   "dft_method": "r²SCAN+U+SOC"},
    "FASnI3":  {"Eg_dft_eV": 0.771, "Eg_exp_eV": None,   "dft_method": "r²SCAN+U+SOC"},
    "FASnBr3": {"Eg_dft_eV": 1.115, "Eg_exp_eV": None,   "dft_method": "r²SCAN+U+SOC"},
    "CsPbI3":  {"Eg_dft_eV": 1.483, "Eg_exp_eV": 1.73,   "dft_method": "PBE+scissor"},
    "MAPbI3":  {"Eg_dft_eV": 2.054, "Eg_exp_eV": 1.55,   "dft_method": "PBE+scissor"},
    "FAPbI3":  {"Eg_dft_eV": 0.982, "Eg_exp_eV": 1.48,   "dft_method": "PBE+scissor"},
    "FAPbBr3": {"Eg_dft_eV": 1.079, "Eg_exp_eV": 2.23,   "dft_method": "PBE+scissor"},
}

# ──────────────────────────────────────────────────────────────────────────────


def _run_all(
    mats: dict[str, dict],
    predictor: GNNPredictor,
    builder: PerovskiteStructureBuilder,
) -> dict[str, dict]:
    out: dict[str, dict] = {}

    for mat, cfg in mats.items():
        A, B, X = cfg["A"], cfg["B"], cfg["X"]
        print(f"\n  {mat}  (A={A} B={B} X={X})")
        t0 = time.time()

        try:
            struct, source = builder.build(A, B, X, mat=mat)
        except Exception as exc:
            print(f"  ERROR structure: {exc}")
            out[mat] = {"error": f"structure: {exc}"}
            continue

        try:
            res = predictor.predict(struct, source)
        except Exception as exc:
            print(f"  ERROR GNN: {exc}")
            out[mat] = {"error": f"gnn: {exc}"}
            continue

        elapsed = time.time() - t0
        ef_str = f"{res.Eform_eV_atom:.4f}" if res.Eform_eV_atom is not None else "N/A"
        ef_std = (f" ± {res.Eform_std_eV_atom:.4f}" if res.Eform_std_eV_atom else "")
        print(f"  Eg_GNN  = {res.Eg_eV:.4f} eV  [{source}]")
        print(f"  Eform   = {ef_str}{ef_std} eV/atom  [MEGNet+M3GNet]")

        ref = DFT_REF.get(mat, {})
        if ref.get("Eg_dft_eV"):
            print(f"  Eg_DFT  = {ref['Eg_dft_eV']:.4f} eV  "
                  f"error = {res.Eg_eV - ref['Eg_dft_eV']:+.4f} eV")
        if ref.get("Eg_exp_eV"):
            print(f"  Eg_exp  = {ref['Eg_exp_eV']:.4f} eV  "
                  f"error = {res.Eg_eV - ref['Eg_exp_eV']:+.4f} eV")
        for w in res.model_warnings:
            print(f"  WARN: {w}")
        print(f"  [{elapsed:.1f} s]")

        record: dict = {
            "A": A, "B": B, "X": X,
            "Eg_gnn_eV": round(res.Eg_eV, 4),
            "Eform_gnn_eV_atom": (
                round(res.Eform_eV_atom, 4) if res.Eform_eV_atom is not None else None
            ),
            "Eform_gnn_std_eV_atom": (
                round(res.Eform_std_eV_atom, 4) if res.Eform_std_eV_atom is not None else None
            ),
            "gnn_struct_source": source,
            "in_pv_window": res.in_pv_window,
            "is_stable_heuristic": res.is_stable,
            "model_warnings": res.model_warnings,
        }
        record.update(ref)
        out[mat] = record

    return out


def _print_ranking(results: dict, acquisition: GNNAcquisition) -> None:
    gnn_pairs: list[tuple[str, GNNResult]] = []
    for mat, r in results.items():
        if "error" in r:
            continue
        gnn_pairs.append((mat, GNNResult(
            Eg_eV=r["Eg_gnn_eV"],
            Eform_megnet_eV_atom=None,
            Eform_m3gnet_eV_atom=None,
            Eform_eV_atom=r.get("Eform_gnn_eV_atom"),
            Eform_std_eV_atom=r.get("Eform_gnn_std_eV_atom"),
            structure_source=r.get("gnn_struct_source", ""),
        )))

    if not gnn_pairs:
        return

    ranked = acquisition.rank([m for m, _ in gnn_pairs], [r for _, r in gnn_pairs])

    print("\n" + "=" * 78)
    print("  GNN ACQUISITION RANKING  — replaces heuristic AINAGENT AI-03 score")
    print("=" * 78)
    hdr = f"  {'#':<3} {'Material':<11} {'Eg_GNN':>8} {'Eform':>9} {'±':>7} {'band':>7} {'stab':>7} {'ucb':>7} {'total':>7}"
    print(hdr)
    print("  " + "─" * 74)
    for i, s in enumerate(ranked, 1):
        ef  = f"{s.Eform_gnn:.4f}"  if s.Eform_gnn  is not None else "    N/A"
        std = f"{s.Eform_std:.4f}"  if s.Eform_std   is not None else "    N/A"
        pv  = "✓" if s.in_pv_window else " "
        print(
            f"  {i:<3} {s.material:<11} {s.Eg_gnn:>8.4f} {ef:>9} {std:>7} "
            f"{s.band_score:>7.4f} {s.stab_score:>7.4f} {s.ucb_bonus:>7.4f} "
            f"{s.total_score:>7.4f} {pv}"
        )


def main() -> None:
    pa = argparse.ArgumentParser(
        description="GNN property prediction for ABX3 perovskites (MATGL, zero heuristics)"
    )
    pa.add_argument("--mat", default="all",
                    help="Material name or 'all' for top-8 (default: all)")
    pa.add_argument("--A", help="A-site element (with --B and --X)")
    pa.add_argument("--B", help="B-site element")
    pa.add_argument("--X", help="X-site element")
    pa.add_argument("--out", type=Path,
                    help="Write JSON to file (default: print only)")
    pa.add_argument("--beta", type=float, default=1.0,
                    help="UCB exploration coefficient (default 1.0)")
    pa.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    pa.add_argument("--verbose", action="store_true")
    args = pa.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    if args.A and args.B and args.X:
        mats = {f"{args.A}{args.B}{args.X}3": {"A": args.A, "B": args.B, "X": args.X}}
    elif args.mat == "all":
        mats = TOP8_MATS
    elif args.mat in TOP8_MATS:
        mats = {args.mat: TOP8_MATS[args.mat]}
    else:
        pa.error(f"Unknown material '{args.mat}'. Use --mat all or --A/--B/--X.")

    print("=" * 78)
    print("  GNN SURROGATE  MEGNet-BandGap + MEGNet/M3GNet-Eform  (MATGL 3.0.1)")
    print("  No heuristics. No B_BASE. No Goldschmidt t-factor in acquisition.")
    print("=" * 78)

    predictor = GNNPredictor(device=args.device)
    builder = PerovskiteStructureBuilder()
    acquisition = GNNAcquisition(beta=args.beta)

    results = _run_all(mats, predictor, builder)
    _print_ranking(results, acquisition)

    if args.out:
        args.out.write_text(json.dumps(results, indent=2))
        print(f"\nJSON → {args.out}")

    print()


if __name__ == "__main__":
    main()
