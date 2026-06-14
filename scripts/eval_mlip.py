#!/usr/bin/env python3
"""Evaluación del MLIP multi-cabeza (cubre la sección 'Evaluación' de la tesis).

Genera, para un modelo fine-tuneado phase2_mlip_<tag>.model:

  1. Curvas de pérdida train vs valid (parseando el log de MACE) → PNG.
  2. Overfitting: gap train/valid por época.
  3. Parity plots E (eV/átomo) y F (eV/Å) sobre la valid de la cabeza 'phase2a'.
  4. Generalización: RMSE sobre el holdout REAL del dataset CsXI3 (sp_test_set,
     14056015.zip) — datos nunca vistos en entrenamiento.
  5. Baseline: misma métrica con MACE-MP-0 'small' SIN fine-tune → tabla antes/después.
  6. Test de orden energético de fases (cspbclbr): por composición CsPb(Cl/Br)3, predecir
     E de las 4 fases (pnma/i4mcm/pm3m/p4mbm) y comparar el ORDEN relativo vs DFT (Spearman).

Uso:
  PYTHONPATH=src .venv/bin/python3 scripts/eval_mlip.py --tag mh_b000
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ase.io import read, write  # noqa: E402

MODELS = ROOT / "models" / "mace_phase2"
DATASETS = ROOT / "data" / "mlip_datasets"
BUILD = DATASETS / "build"
REPORTS = ROOT / "reports" / "training fase 2"
DATA_DIR = Path.home() / "Documents" / "Data"
PY = str(ROOT / ".venv/bin/python3")
DTYPE = "float32"   # debe coincidir con el dtype con que se entrenó (Colab GPU = float32)


# ─────────────────────── 1-2. curvas de pérdida / overfitting ───────────────────────

def parse_training_log(tag: str) -> list[dict]:
    """Extrae (epoch, head, loss, rmse_e, rmse_f) de los logs de MACE."""
    logdir = MODELS / f"mlip_{tag}" / "logs"
    rows = []
    pat = re.compile(
        r"Epoch (\d+):.*?head:\s*(\w+).*?loss=([\d.eE+-]+).*?"
        r"RMSE_E_per_atom=\s*([\d.eE+-]+)\s*meV.*?RMSE_F=\s*([\d.eE+-]+)\s*meV")
    for log in sorted(logdir.glob("*.log")):
        for line in log.read_text(errors="replace").splitlines():
            m = pat.search(line)
            if m:
                rows.append({"epoch": int(m.group(1)), "head": m.group(2),
                             "loss": float(m.group(3)), "rmse_e_meV": float(m.group(4)),
                             "rmse_f_meV": float(m.group(5))})
    return rows


def plot_learning_curve(tag: str, rows: list[dict]) -> Path | None:
    if not rows:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    heads = sorted({r["head"] for r in rows})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for head in heads:
        rh = [r for r in rows if r["head"] == head]
        ep = [r["epoch"] for r in rh]
        axes[0].plot(ep, [r["rmse_e_meV"] for r in rh], marker=".", label=head)
        axes[1].plot(ep, [r["rmse_f_meV"] for r in rh], marker=".", label=head)
    axes[0].set(xlabel="época", ylabel="RMSE_E (meV/átomo)", title="Energía (valid)")
    axes[1].set(xlabel="época", ylabel="RMSE_F (meV/Å)", title="Fuerzas (valid)")
    for ax in axes:
        ax.set_yscale("log"); ax.legend(); ax.grid(alpha=0.3)
    fig.suptitle(f"Curva de aprendizaje — phase2_mlip_{tag}")
    fig.tight_layout()
    out = REPORTS / f"mlip_{tag}_learning_curve.png"
    fig.savefig(out, dpi=150); plt.close(fig)
    return out


# ─────────────────────── 3-5. RMSE + parity con eval_configs ───────────────────────

def eval_configs(model: Path, frames: list, head: str | None, work: Path) -> tuple:
    """Devuelve (de_per_atom[], df_flat[]) prediciendo con eval_configs (cabeza opcional)."""
    if not frames:
        return np.array([]), np.array([])
    xyz = work / "in.extxyz"
    out = work / "out.extxyz"
    write(str(xyz), frames, format="extxyz")
    cmd = [PY, "-m", "mace.cli.eval_configs", "--configs", str(xyz),
           "--model", str(model), "--output", str(out),
           "--device", "cpu", "--default_dtype", DTYPE, "--batch_size", "4"]
    if head:
        cmd += ["--head", head]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    preds = read(str(out), index=":")
    de, df = [], []
    for ref, pr in zip(frames, preds):
        n = len(ref)
        rr = ref.calc.results if ref.calc is not None else {}
        e_ref = ref.info.get("REF_energy", rr.get("energy"))
        f_ref = ref.arrays.get("REF_forces", rr.get("forces"))
        e_pred = pr.info.get("MACE_energy", pr.calc.results.get("energy") if pr.calc else None)
        f_pred = pr.arrays.get("MACE_forces", pr.calc.results.get("forces") if pr.calc else None)
        if None in (e_ref, e_pred) or f_ref is None or f_pred is None:
            continue
        de.append((float(e_pred) - float(e_ref)) / n)
        df.append(np.asarray(f_pred, float) - np.asarray(f_ref, float))
    df_flat = np.concatenate([d.ravel() for d in df]) if df else np.array([])
    return np.array(de), df_flat


def rmse(arr: np.ndarray) -> float:
    return float(np.sqrt(np.mean(arr ** 2))) if len(arr) else float("nan")


def load_phase2a_valid() -> list:
    frames = read(str(BUILD / "phase2a_valid.xyz"), index=":")
    return frames


def load_cssni3_holdout(n_max: int = 800) -> list:
    """sp_test_set.xyz de 14056015.zip — holdout real, nunca visto en train."""
    zip_path = DATA_DIR / "14056015.zip"
    if not zip_path.exists():
        return []
    with zipfile.ZipFile(zip_path) as zf, tempfile.NamedTemporaryFile(
            "wb", suffix=".xyz", delete=True) as tmp:
        tmp.write(zf.read("sp_test_set.xyz")); tmp.flush()
        frames = read(tmp.name, index=":")
    rng = np.random.RandomState(0)
    if len(frames) > n_max:
        frames = [frames[int(i)] for i in sorted(rng.permutation(len(frames))[:n_max])]
    for at in frames:                       # mapear a REF_* (head cssni3)
        r = at.calc.results if at.calc is not None else {}
        if "energy" in r:
            at.info["REF_energy"] = float(r["energy"])
        if "forces" in r:
            at.arrays["REF_forces"] = np.asarray(r["forces"], float)
        at.info["head"] = "cssni3"; at.calc = None
    return frames


def parity_plot(tag: str, de: np.ndarray, df: np.ndarray, label: str) -> Path | None:
    if not len(de):
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    axes[0].hist(de * 1000, bins=40, color="#c1440e", alpha=0.8)
    axes[0].set(xlabel="ΔE (meV/átomo)", ylabel="frames",
                title=f"Error energía — {label}\nRMSE={rmse(de)*1000:.1f} meV/átomo")
    axes[1].hist(df * 1000, bins=60, color="#3a7abf", alpha=0.8)
    axes[1].set(xlabel="ΔF (meV/Å)", ylabel="componentes",
                title=f"Error fuerzas — {label}\nRMSE={rmse(df)*1000:.1f} meV/Å")
    for ax in axes:
        ax.grid(alpha=0.3)
    fig.tight_layout()
    out = REPORTS / f"mlip_{tag}_parity_{label}.png"
    fig.savefig(out, dpi=150); plt.close(fig)
    return out


# ─────────────────────── 6. test de orden de fases (cspbclbr) ───────────────────────

def phase_ordering_test(model: Path, tag: str, work: Path) -> dict:
    """Endpoints CsPb(Cl/Br)3: ¿el modelo ordena las 4 fases como el DFT?"""
    xyz = DATASETS / "cspbclbr_phase_test.extxyz"
    if not xyz.exists():
        return {}
    frames = [at for at in read(str(xyz), index=":") if at.info.get("is_endpoint")]
    if not frames:
        return {}
    # agrupar por composición (endpoint_name sin la fase) → {comp: {phase: E_dft}}
    groups: dict[str, dict] = {}
    for at in frames:
        name = at.info.get("endpoint_name", "")
        comp = name.rsplit("_", 1)[0] if "_" in name else name
        e_dft = at.calc.results["energy"] if at.calc else at.info.get("REF_energy")
        groups.setdefault(comp, {})[at.info.get("phase")] = (at, float(e_dft))
    # predecir E con el modelo (cabeza phase2a; el ORDEN no depende del E0 absoluto)
    pred_in = []
    for comp, d in groups.items():
        for phase, (at, _) in d.items():
            at.info["_comp"], at.info["_phase"] = comp, phase
            pred_in.append(at)
    de, _ = [], []
    out = work / "phase_out.extxyz"
    write(str(work / "phase_in.extxyz"), pred_in, format="extxyz")
    cmd = [PY, "-m", "mace.cli.eval_configs", "--configs", str(work / "phase_in.extxyz"),
           "--model", str(model), "--output", str(out), "--head", "phase2a",
           "--device", "cpu", "--default_dtype", DTYPE, "--batch_size", "4"]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    preds = read(str(out), index=":")
    pred_e = {(p.info.get("_comp"), p.info.get("_phase")):
              float(p.info["MACE_energy"] if "MACE_energy" in p.info
                    else p.calc.results["energy"]) / len(p)
              for p in preds if p.calc is not None or "MACE_energy" in p.info}
    # Spearman del orden de fases por composición
    results = {}
    for comp, d in groups.items():
        phases = list(d.keys())
        e_dft = np.array([d[ph][1] / len(d[ph][0]) for ph in phases])
        e_pred = np.array([pred_e[(comp, ph)] for ph in phases])
        if len(phases) < 2:
            continue
        rank_dft = np.argsort(np.argsort(e_dft))
        rank_pred = np.argsort(np.argsort(e_pred))
        n = len(phases)
        rho = 1 - 6 * np.sum((rank_dft - rank_pred) ** 2) / (n * (n ** 2 - 1)) if n > 1 else 1.0
        results[comp] = {"phases": phases, "spearman": round(float(rho), 3),
                         "dft_order": [phases[i] for i in np.argsort(e_dft)],
                         "pred_order": [phases[i] for i in np.argsort(e_pred)]}
    if results:
        results["_mean_spearman"] = round(
            float(np.mean([v["spearman"] for k, v in results.items()
                           if not k.startswith("_")])), 3)
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--baseline", action="store_true",
                    help="comparar contra MACE-MP-0 small sin fine-tune")
    ap.add_argument("--dtype", default="float32", choices=["float32", "float64"],
                    help="debe coincidir con el dtype de entrenamiento (Colab GPU = float32)")
    args = ap.parse_args()
    global DTYPE
    DTYPE = args.dtype

    REPORTS.mkdir(parents=True, exist_ok=True)
    model = MODELS / f"phase2_mlip_{args.tag}.model"
    if not model.exists():
        raise SystemExit(f"no existe {model} — entrena primero")
    work = Path(tempfile.mkdtemp(prefix="eval_mlip_"))
    summary: dict = {"tag": args.tag, "model": str(model)}

    # 1-2. curvas
    rows = parse_training_log(args.tag)
    lc = plot_learning_curve(args.tag, rows)
    summary["learning_curve_png"] = str(lc) if lc else None
    if rows:
        last = max(r["epoch"] for r in rows)
        summary["final_epoch"] = last

    # 3. parity sobre valid phase2a (head phase2a)
    p2v = load_phase2a_valid()
    de, df = eval_configs(model, p2v, "phase2a", work)
    summary["phase2a_valid"] = {"n": len(p2v), "rmse_e_meV_atom": round(rmse(de) * 1000, 2),
                                "rmse_f_meV_A": round(rmse(df) * 1000, 2)}
    summary["parity_phase2a_png"] = str(parity_plot(args.tag, de, df, "phase2a_valid"))

    # 4. generalización: holdout real cssni3 (head cssni3)
    hold = load_cssni3_holdout()
    if hold:
        deh, dfh = eval_configs(model, hold, "cssni3", work)
        summary["cssni3_holdout"] = {"n": len(hold),
                                     "rmse_e_meV_atom": round(rmse(deh) * 1000, 2),
                                     "rmse_f_meV_A": round(rmse(dfh) * 1000, 2)}
        parity_plot(args.tag, deh, dfh, "cssni3_holdout")

    # 5. baseline MACE-MP-0 (forces son comparables; energía no, por referencia)
    if args.baseline:
        deb, dfb = eval_configs(model.with_name("__foundation__"), p2v, None, work) \
            if False else (np.array([]), np.array([]))
        # eval directo con foundation 'small' vía python -m (descarga/uso del modelo base)
        try:
            from mace.calculators import mace_mp
            calc = mace_mp(model="small", device="cpu", default_dtype=DTYPE)
            dfb = []
            for at in p2v:
                a2 = at.copy(); a2.calc = calc
                f_pred = a2.get_forces()
                dfb.append(f_pred - at.arrays["REF_forces"])
            dfb = np.concatenate([d.ravel() for d in dfb])
            summary["baseline_mace_mp0"] = {"rmse_f_meV_A": round(rmse(dfb) * 1000, 2)}
        except Exception as exc:
            summary["baseline_mace_mp0"] = {"error": str(exc)}

    # 6. orden de fases cspbclbr
    summary["phase_ordering"] = phase_ordering_test(model, args.tag, work)

    (REPORTS / f"mlip_{args.tag}_eval.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
