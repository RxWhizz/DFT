#!/usr/bin/env python3
"""Monitor: espera a que termine el benchmark del MLIP y notifica a Telegram.

Detecta el fin observando el marcador "=== ÓPTIMO ===" en el log del benchmark (o la
aparición de bench_results.json). Al terminar, arma un resumen (tabla s/época + pico RAM
por config, óptimo elegido, speedup vs 16 threads) y lo envía al chat de Telegram
configurado en configs/monitor.local.yaml.

Uso (background):
  PYTHONPATH=src .venv/bin/python3 scripts/notify_bench_done.py \
      --watch-log data/mlip_datasets/bench/focused.log
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "data" / "mlip_datasets" / "bench"
RESULTS = BENCH / "bench_results.json"
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) INFO: Epoch (\d+):")


def load_telegram() -> tuple[str, str]:
    cfg = yaml.safe_load((ROOT / "configs" / "monitor.local.yaml").read_text()) or {}
    tg = cfg.get("telegram", {})
    return tg.get("bot_token", ""), str(tg.get("chat_id", ""))


def send(token: str, chat_id: str, text: str) -> bool:
    if not token or not chat_id:
        print("Sin credenciales Telegram — no se envía.", flush=True)
        return False
    try:
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                       timeout=20.0)
        ok = r.json().get("ok", False)
        print(f"Telegram enviado: {ok}", flush=True)
        return ok
    except Exception as exc:
        print(f"Error enviando Telegram: {exc}", flush=True)
        return False


def sec_per_epoch(run_dir: str) -> float | None:
    logs = glob.glob(f"{run_dir}/logs/*.log")
    if not logs:
        return None
    ts: dict[int, float] = {}
    for line in Path(logs[0]).read_text(errors="replace").splitlines():
        m = TS_RE.search(line)
        if m and int(m.group(2)) not in ts:
            ts[int(m.group(2))] = datetime.strptime(
                m.group(1), "%Y-%m-%d %H:%M:%S.%f").timestamp()
    eps = sorted(ts)
    deltas = [ts[b] - ts[a] for a, b in zip(eps[:-1], eps[1:])]
    return round(statistics.median(deltas), 1) if deltas else None


def build_report() -> str:
    full_frames = 7137          # set completo de entrenamiento (train, 3 cabezas)
    lines = ["🏁 <b>Benchmark MLIP terminado</b>", ""]
    results = []
    if RESULTS.exists():
        data = json.loads(RESULTS.read_text())
        results = data.get("results", [])
        best = data.get("best")
    else:
        best = None

    # timing por dir (incluye configs previas como t16) + RAM de results
    ram_by_tag = {r["tag"]: r.get("peak_ram_gb") for r in results}
    rows = []
    for d in sorted(glob.glob(str(BENCH / "run_*"))):
        tag = Path(d).name.replace("run_", "")
        spe = sec_per_epoch(d)
        if spe:
            rows.append((tag, spe, ram_by_tag.get(tag)))
    rows.sort(key=lambda r: r[1])

    lines.append("<pre>config        s/época  RAM_GB</pre>")
    for tag, spe, ram in rows:
        ram_s = f"{ram:.1f}" if ram else "—"
        lines.append(f"<code>{tag:13s} {spe:>7.0f}  {ram_s:>6}</code>")
    lines.append("")

    if best:
        spe_b = best.get("sec_per_epoch")
        full_min = round(spe_b * full_frames / 400 / 3 / 60, 1) if spe_b else None
        # ref 16 threads
        ref = next((r[1] for r in rows if r[0].startswith("t16")), None)
        speedup = round(ref / spe_b, 2) if (ref and spe_b) else None
        lines.append(f"⭐ <b>ÓPTIMO: {best['tag']}</b>")
        lines.append(f"   {spe_b} s/época (bench) · pico {best.get('peak_ram_gb')} GB")
        if speedup:
            lines.append(f"   speedup ×{speedup} vs 16 threads")
        if full_min:
            lines.append(f"   ≈ {full_min} min/época en set completo (7137 frames)")
            lines.append(f"   → 50 épocas ≈ {round(full_min*50/60,1)} h")
    else:
        lines.append("⚠️ No se encontró bench_results.json — revisa el log.")
    lines.append("")
    lines.append(f"<i>{datetime.now():%Y-%m-%d %H:%M}</i>")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch-log", default=str(BENCH / "focused.log"))
    ap.add_argument("--marker", default="=== ÓPTIMO ===")
    ap.add_argument("--poll", type=int, default=30)
    ap.add_argument("--timeout-h", type=float, default=8.0)
    args = ap.parse_args()

    token, chat_id = load_telegram()
    log = Path(args.watch_log)
    print(f"Vigilando {log} por '{args.marker}' (poll {args.poll}s)…", flush=True)
    t0 = time.time()
    while True:
        done = log.exists() and args.marker in log.read_text(errors="replace")
        if done:
            time.sleep(3)            # deja que escriba bench_results.json
            break
        if time.time() - t0 > args.timeout_h * 3600:
            send(token, chat_id, "⚠️ Monitor del benchmark MLIP: timeout sin detectar fin.")
            return
        time.sleep(args.poll)

    report = build_report()
    print(report, flush=True)
    send(token, chat_id, report)


if __name__ == "__main__":
    main()
