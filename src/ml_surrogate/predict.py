"""CLI predictor for the ABX3 perovskite surrogate.

Usage
-----
    # Single composition
    python -m src.ml_surrogate.predict --A Cs --B Pb --X I

    # Batch from CSV
    python -m src.ml_surrogate.predict --input candidates.csv --output predictions.csv

    # With optional geometry data (from MACE relaxation)
    python -m src.ml_surrogate.predict --A MA --B Sn --X I --a_lat 6.32 --E_mace -50.9

    # Predict all top-8 materials
    python -m src.ml_surrogate.predict --mat all

Input CSV must have columns: A, B, X (plus optionally a_lat_mp_A, E_mace_eV_atom, etc.)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ml_surrogate.config import SurrogateConfig
from ml_surrogate.features import BASE_FEATURES, OPTIONAL_FEATURES, build_X, extract
from ml_surrogate.model import SurrogateEnsemble, make_prediction_record

TOP8_MATS = {
    "CsSnI3":  {"A": "Cs", "B": "Sn", "X": "I"},
    "MASnI3":  {"A": "MA", "B": "Sn", "X": "I"},
    "FASnI3":  {"A": "FA", "B": "Sn", "X": "I"},
    "FASnBr3": {"A": "FA", "B": "Sn", "X": "Br"},
    "CsPbI3":  {"A": "Cs", "B": "Pb", "X": "I"},
    "MAPbI3":  {"A": "MA", "B": "Pb", "X": "I"},
    "FAPbI3":  {"A": "FA", "B": "Pb", "X": "I"},
    "FAPbBr3": {"A": "FA", "B": "Pb", "X": "Br"},
}

DFT_REF = {
    "CsSnI3":  {"Eg_dft_eV": 1.359, "Eg_exp_eV": 1.30},
    "MASnI3":  {"Eg_dft_eV": 1.584, "Eg_exp_eV": 1.20},
    "FASnI3":  {"Eg_dft_eV": 0.771, "Eg_exp_eV": 1.41},
    "FASnBr3": {"Eg_dft_eV": 1.115, "Eg_exp_eV": 2.00},
    "CsPbI3":  {"Eg_dft_eV": 1.483, "Eg_exp_eV": 1.73},
    "MAPbI3":  {"Eg_dft_eV": 2.054, "Eg_exp_eV": 1.55},
    "FAPbI3":  {"Eg_dft_eV": 0.982, "Eg_exp_eV": 1.48},
    "FAPbBr3": {"Eg_dft_eV": 1.079, "Eg_exp_eV": 2.23},
}


def load_model(cfg: SurrogateConfig) -> SurrogateEnsemble:
    model_path = cfg.model_path
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model not found: {model_path}\n"
            f"Train first: python -m src.ml_surrogate.train --config configs/surrogate.yaml"
        )
    return SurrogateEnsemble.load(model_path)


def predict_one(
    model: SurrogateEnsemble,
    A: str,
    B: str,
    X: str,
    a_lat: float | None = None,
    E_mace_eV_atom: float | None = None,
    band_gap_gga: float | None = None,
    Eform_eV_atom: float | None = None,
    mat: str | None = None,
) -> dict:
    """Predict bandgap and uncertainty for one composition."""
    feats = extract(A, B, X, a_lat=a_lat, E_mace_eV_atom=E_mace_eV_atom,
                    band_gap_gga=band_gap_gga, Eform_eV_atom=Eform_eV_atom)
    df_row = pd.DataFrame([feats])
    X_arr = build_X(df_row, model.feature_cols)
    mean_pred, std = model.predict_single(X_arr[0])
    mat_label = mat or f"{A}{B}{X}3"
    return make_prediction_record(mat_label, A, B, X, mean_pred, std,
                                  Eform_eV_atom, model.feature_cols)


def predict_csv(
    model: SurrogateEnsemble,
    input_csv: Path,
    output_csv: Path,
) -> pd.DataFrame:
    """Batch prediction from CSV. Returns predictions DataFrame."""
    df_in = pd.read_csv(input_csv)
    if not {"A", "B", "X"}.issubset(df_in.columns):
        raise ValueError("Input CSV must have columns A, B, X")

    results = []
    for _, row in df_in.iterrows():
        a_lat = row.get("a_lat_mp_A") or row.get("a_mace_A")
        E_mace = row.get("E_mace_eV_atom")
        if E_mace is None and "E_mace_eV" in row and "nsites" in row:
            E_mace = row["E_mace_eV"] / row["nsites"]
        gga = row.get("band_gap_gga_eV") or row.get("Eg_megnet_eV")
        eform = row.get("Eform_eV_atom")
        mat = row.get("material") or f"{row.A}{row.B}{row.X}3"

        try:
            rec = predict_one(model, row.A, row.B, row.X,
                              a_lat=a_lat, E_mace_eV_atom=E_mace,
                              band_gap_gga=gga, Eform_eV_atom=eform, mat=mat)
            rec["source_row"] = _
        except Exception as e:
            rec = {"material": mat, "error": str(e), "source_row": _}
        results.append(rec)

    df_out = pd.DataFrame(results)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_csv, index=False)
    return df_out


def _print_ranking(results: list[dict]) -> None:
    print("\n" + "=" * 76)
    print("  SURROGATE RANKING  — experimental-trained, zero GNN dependency")
    print("=" * 76)
    ranked = sorted(results, key=lambda r: r.get("solar_score", 0) + r.get("stability_score", 0),
                    reverse=True)
    hdr = f"  {'#':<3} {'Material':<11} {'Eg_pred':>8} {'±':>6} {'solar':>7} {'stab':>7} {'PV':>4}"
    print(hdr)
    print("  " + "─" * 58)
    for i, r in enumerate(ranked, 1):
        if "error" in r:
            print(f"  {i:<3} {r['material']:<11}  ERROR: {r['error']}")
            continue
        pv = "✓" if r.get("in_pv_window") else " "
        dft_ref = DFT_REF.get(r.get("material", ""), {})
        eg_dft = dft_ref.get("Eg_dft_eV")
        eg_exp = dft_ref.get("Eg_exp_eV")
        line = (f"  {i:<3} {r['material']:<11} "
                f"{r['bandgap_pred']:>8.4f} {r['bandgap_uncertainty']:>6.4f} "
                f"{r['solar_score']:>7.4f} {r['stability_score']:>7.4f} {pv:>4}")
        if eg_exp is not None:
            line += f"  (exp={eg_exp:.2f}, err={r['bandgap_pred']-eg_exp:+.3f})"
        print(line)


def main() -> None:
    pa = argparse.ArgumentParser(description="ABX3 surrogate bandgap predictor")
    pa.add_argument("--config", type=Path, default="configs/surrogate.yaml")
    pa.add_argument("--mat", default=None, help="Material name or 'all' for top-8")
    pa.add_argument("--A", help="A-site element")
    pa.add_argument("--B", help="B-site element")
    pa.add_argument("--X", help="X-site element")
    pa.add_argument("--a_lat", type=float, help="Lattice constant (Å) from MACE or MP")
    pa.add_argument("--E_mace", type=float, help="MACE energy/atom (eV)")
    pa.add_argument("--input", type=Path, help="Batch prediction: input CSV")
    pa.add_argument("--output", type=Path, default=Path("predictions.csv"),
                    help="Batch prediction: output CSV")
    pa.add_argument("--out-json", type=Path, help="Write JSON output")
    args = pa.parse_args()

    cfg_path = ROOT / args.config if not Path(args.config).is_absolute() else args.config
    cfg = SurrogateConfig.from_yaml(cfg_path) if cfg_path.exists() else SurrogateConfig()

    model = load_model(cfg)

    # Batch mode
    if args.input:
        df_out = predict_csv(model, args.input, args.output)
        print(f"Predictions saved: {args.output}")
        print(df_out[["material", "bandgap_pred", "bandgap_uncertainty",
                       "solar_score", "stability_score"]].to_string(index=False))
        return

    # Single or top-8 mode
    if args.A and args.B and args.X:
        mats = {f"{args.A}{args.B}{args.X}3": {"A": args.A, "B": args.B, "X": args.X}}
    elif args.mat == "all":
        mats = TOP8_MATS
    elif args.mat and args.mat in TOP8_MATS:
        mats = {args.mat: TOP8_MATS[args.mat]}
    else:
        pa.error("Specify --A/--B/--X, --mat <name>, or --mat all")

    results = []
    for mat, cfg_mat in mats.items():
        E_mace = args.E_mace
        rec = predict_one(model, cfg_mat["A"], cfg_mat["B"], cfg_mat["X"],
                          a_lat=args.a_lat, E_mace_eV_atom=E_mace, mat=mat)
        rec["material"] = mat
        results.append(rec)
        print(f"  {mat:12} Eg={rec['bandgap_pred']:.4f} ± {rec['bandgap_uncertainty']:.4f} eV  "
              f"solar={rec['solar_score']:.4f}  stab={rec['stability_score']:.4f}")

    _print_ranking(results)

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(results, indent=2))
        print(f"\nJSON → {args.out_json}")


if __name__ == "__main__":
    main()
