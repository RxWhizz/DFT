"""Background poller: escanea status.json + logs GPAW/FIRE, emite eventos."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import JobStatus, JobStatusLiteral, StatsResponse, WsEvent
from .notifier import send_telegram

log = logging.getLogger(__name__)

# Regexes reutilizadas de buho_monitor.py / gpaw_monitor.py
_OPTIMIZER_RE = re.compile(
    r"(?:FIRE|BFGS|LBFGS):\s+(\d+)\s+(\d{2}:\d{2}:\d{2})\s+([-\d.]+)\s+([\d.]+)"
)
_SCF_TS_RE = re.compile(
    r"\|iter:\s+(\d+)\|\s+(\d{2}):(\d{2}):(\d{2})\s*\|\s*([-\d.]+)"
)
_SCF_RE = re.compile(r"iter:\s+(\d+)\s+(\d{2}:\d{2}:\d{2})")
_ENERGY_RE = re.compile(r"Total:\s+([-\d.]+)")
_CONV_RE = re.compile(r"Converged after|scf cycle converged", re.I)
_ERROR_RE = re.compile(r"Traceback|MemoryError|Segfault|Killed", re.I)


# ── Helpers reutilizados ──────────────────────────────────────────────────────

def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _proc_rss_mb(pid: int) -> int | None:
    try:
        status = Path(f"/proc/{pid}/status").read_text().splitlines()
        for line in status:
            if line.startswith("VmRSS"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


def _fmt_elapsed(iso_start: str) -> float | None:
    try:
        start = datetime.fromisoformat(iso_start.replace("Z", "+00:00")).replace(tzinfo=None)
        return round((datetime.now() - start).total_seconds() / 60, 1)
    except Exception:
        return None


def _read_status(job_dir: Path) -> dict:
    import json
    p = job_dir / "status.json"
    try:
        data = json.loads(p.read_text())
    except Exception:
        data = {"status": "unknown", "candidate_id": job_dir.name}
    # Si no hay fórmula en status.json, buscarla en metadata.json
    if not data.get("formula"):
        meta = job_dir / "metadata.json"
        try:
            data["formula"] = json.loads(meta.read_text()).get("formula", job_dir.name)
        except Exception:
            data["formula"] = job_dir.name
    return data


# ── Log parsers ───────────────────────────────────────────────────────────────

def _parse_relax_log(job_dir: Path) -> dict:
    """Extrae historial FIRE/BFGS del relax.log."""
    log_file = job_dir / "relax.log"
    if not log_file.exists():
        return {}
    try:
        lines = log_file.read_text(errors="replace").splitlines()
        steps, energies, fmaxes = [], [], []
        for line in lines:
            m = _OPTIMIZER_RE.search(line)
            if m:
                steps.append(int(m.group(1)))
                energies.append(float(m.group(3)))
                fmaxes.append(float(m.group(4)))
        if not steps:
            return {}
        return {
            "step": steps[-1],
            "energy": energies[-1],
            "fmax": fmaxes[-1],
            "energy_history": energies,
            "fmax_history": fmaxes,
            "step_type": "FIRE",
        }
    except Exception:
        return {}


def _parse_scf_log(job_dir: Path) -> dict:
    """Extrae iteraciones SCF y energías del r2scan.txt / gpaw.txt."""
    for name in ("r2scan.txt", "gpaw.txt"):
        txt = job_dir / name
        if not txt.exists():
            continue
        try:
            content = txt.read_text(errors="replace")
            matches = _SCF_TS_RE.findall(content)
            if matches:
                iters   = [int(m[0]) for m in matches]
                energies = [float(m[4]) for m in matches]

                times = []
                for m in matches:
                    h, mn, s = int(m[1]), int(m[2]), int(m[3])
                    times.append(h * 3600 + mn * 60 + s)
                deltas = [(times[i] - times[i-1]) % 86400 for i in range(1, len(times))]
                t_iter = round(sum(deltas) / len(deltas), 1) if deltas else None
                eta_iters = max(0, 30 - iters[-1])
                eta_min = round(eta_iters * t_iter / 60, 1) if t_iter else None

                return {
                    "scf_iter": iters[-1],
                    "energy": energies[-1],
                    "energy_history": energies,
                    "scf_iter_history": iters,
                    "t_iter_s": t_iter,
                    "eta_min": eta_min,
                    "step_type": "SCF",
                }
            # Fallback sin timestamp
            scf_iters = _SCF_RE.findall(content)
            n_scf = int(scf_iters[-1][0]) if scf_iters else 0
            e_match = _ENERGY_RE.search(content)
            return {
                "scf_iter": n_scf,
                "energy": float(e_match.group(1)) if e_match else None,
                "step_type": "SCF",
            }
        except Exception:
            continue
    return {}


def _detect_oscillation(energies: list[float], window: int, threshold: float) -> bool:
    if len(energies) < window:
        return False
    recent = energies[-window:]
    try:
        return statistics.stdev(recent) > threshold
    except statistics.StatisticsError:
        return False


def _log_mtime_minutes_ago(job_dir: Path) -> float | None:
    """Minutos desde que el último log fue modificado."""
    for name in ("relax.log", "r2scan.txt", "gpaw.txt"):
        p = job_dir / name
        if p.exists():
            age = time.time() - p.stat().st_mtime
            return round(age / 60, 1)
    return None


# ── Job snapshot ─────────────────────────────────────────────────────────────

def snapshot_job(job_dir: Path, cfg: dict) -> StatsResponse:
    """Construye un StatsResponse completo para un job_dir."""
    st = _read_status(job_dir)
    raw_status: str = st.get("status", "unknown")
    pid: int | None = st.get("pid")
    formula: str = st.get("formula", job_dir.name)
    start_time: str | None = st.get("start_time")
    elapsed = _fmt_elapsed(start_time) if start_time else st.get("elapsed_min")

    relax  = _parse_relax_log(job_dir)
    scf    = _parse_scf_log(job_dir)

    energy_history = relax.get("energy_history") or scf.get("energy_history") or []
    fmax_history   = relax.get("fmax_history", [])
    scf_iters      = scf.get("scf_iter_history", [])

    is_oscillating = _detect_oscillation(
        energy_history,
        window=cfg.get("oscillation_window", 10),
        threshold=cfg.get("oscillation_energy_std_ev", 0.05),
    )

    # Determina status efectivo
    effective_status: JobStatusLiteral = raw_status  # type: ignore[assignment]
    stall_minutes: float | None = None

    if raw_status == "running" and pid:
        if not _is_pid_alive(pid):
            effective_status = "stopped"  # type: ignore[assignment]
        else:
            stall_min = _log_mtime_minutes_ago(job_dir)
            stall_threshold = cfg.get("stall_minutes", 10)
            if stall_min is not None and stall_min > stall_threshold:
                effective_status = "stalled"  # type: ignore[assignment]
                stall_minutes = stall_min
            elif is_oscillating:
                effective_status = "oscillating"  # type: ignore[assignment]

    return StatsResponse(
        job_id=job_dir.name,
        formula=formula,
        status=effective_status,
        pid=pid,
        start_time=start_time,
        elapsed_min=elapsed,
        mpi_cores=st.get("mpi_cores"),
        energy_history=energy_history,
        fmax_history=fmax_history,
        scf_iter_history=scf_iters,
        n_fire_steps=relax.get("step", 0),
        n_scf_iters=scf.get("scf_iter", 0),
        is_oscillating=is_oscillating,
        stall_minutes=stall_minutes,
        final_energy_ev=st.get("final_energy_eV"),
    )


def ping_job(job_dir: Path) -> dict:
    """Lectura instantánea (para el endpoint /ping)."""
    st = _read_status(job_dir)
    pid: int | None = st.get("pid")
    alive = _is_pid_alive(pid) if pid else False

    relax = _parse_relax_log(job_dir)
    scf   = _parse_scf_log(job_dir)

    current_step = relax.get("step") or scf.get("scf_iter")
    step_type    = relax.get("step_type") or scf.get("step_type") or "?"
    energy       = relax.get("energy") or scf.get("energy")
    fmax         = relax.get("fmax")
    rss          = _proc_rss_mb(pid) if pid and alive else None

    # Última línea del log más reciente
    last_line = None
    for name in ("relax.log", "r2scan.txt", "gpaw.txt"):
        p = job_dir / name
        if p.exists():
            try:
                lines = p.read_text(errors="replace").splitlines()
                last_line = next((l for l in reversed(lines) if l.strip()), None)
                break
            except Exception:
                pass

    return {
        "alive": alive,
        "current_step": current_step,
        "step_type": step_type,
        "energy_ev": energy,
        "fmax_ev_ang": fmax,
        "memory_rss_mb": rss,
        "t_iter_s": scf.get("t_iter_s"),
        "eta_min": scf.get("eta_min"),
        "log_last_line": last_line,
        "status": st.get("status", "unknown"),
    }


# ── Background poller ─────────────────────────────────────────────────────────

class DFTPoller:
    def __init__(self, runs_dir: Path, cfg: dict, telegram_cfg: dict):
        self.runs_dir    = runs_dir
        self.cfg         = cfg
        self.telegram    = telegram_cfg
        self._prev_states: dict[str, str] = {}
        self._event_queue: asyncio.Queue[WsEvent] = asyncio.Queue(maxsize=256)
        self._snapshots: dict[str, StatsResponse] = {}

    @property
    def event_queue(self) -> asyncio.Queue[WsEvent]:
        return self._event_queue

    @property
    def snapshots(self) -> dict[str, StatsResponse]:
        return self._snapshots

    def _runner_kind(self) -> str:
        return str(self.cfg.get("runner_kind", "relax"))

    @staticmethod
    def _batch_id_from_dir(batch_dir: Path) -> int:
        digits = "".join(filter(str.isdigit, batch_dir.name))
        return int(digits or "0")

    def _launch_runner(self, batch_dir: Path) -> None:
        """Lanza el runner configurado para el batch actual."""
        root = Path(__file__).resolve().parents[2]
        slots = self.cfg.get("runner_slots", 2)
        cores = self.cfg.get("runner_cores", 8)
        kind = self._runner_kind()
        if kind == "phase2_force":
            runner = root / "scripts" / "phase2_force_runner.py"
            batch_id = self._batch_id_from_dir(batch_dir)
            runs_dir = Path(self.cfg.get("phase2_runs_dir", batch_dir.parent))
            if not runs_dir.is_absolute():
                runs_dir = (root / runs_dir).resolve()
            env = os.environ.copy()
            env.setdefault("DFT_RUNS_ROOT", str(runs_dir.parent))
            env["PHASE2_FORCE_RUNS_DIR"] = str(runs_dir)
            subprocess.Popen(
                [
                    sys.executable,
                    str(runner),
                    "--batch-id",
                    str(batch_id),
                    "--slots",
                    str(slots),
                    "--cores",
                    str(cores),
                    "--resume",
                    "--start-real",
                    "--runs-dir",
                    str(runs_dir),
                ],
                cwd=str(root),
                env=env,
                start_new_session=True,
            )
            return

        runner = root / "scripts" / "buho_relax_runner.py"
        subprocess.Popen(
            [
                sys.executable,
                str(runner),
                "--relax-dir",
                str(batch_dir),
                "--slots",
                str(slots),
                "--cores",
                str(cores),
            ],
            cwd=str(root),
            start_new_session=True,
        )

    def _runner_running_for(self, batch_dir: Path) -> bool:
        target_dir = batch_dir.resolve()
        kind = self._runner_kind()
        batch_id = self._batch_id_from_dir(batch_dir)
        runs_dir = Path(self.cfg.get("phase2_runs_dir", batch_dir.parent)).resolve()

        def runner_matches(cmd: list[str]) -> bool:
            if kind == "phase2_force":
                if not any("phase2_force_runner.py" in part for part in cmd):
                    return False
                joined = " ".join(cmd)
                if str(target_dir) in joined:
                    return True
                if "--batch-id" in cmd:
                    try:
                        if int(cmd[cmd.index("--batch-id") + 1]) != batch_id:
                            return False
                    except (ValueError, IndexError):
                        return False
                else:
                    return False
                if "--runs-dir" in cmd:
                    try:
                        proc_runs = Path(cmd[cmd.index("--runs-dir") + 1]).resolve()
                    except (ValueError, IndexError):
                        return False
                    return proc_runs == runs_dir
                return str(runs_dir) in joined

            if not any("buho_relax_runner.py" in part for part in cmd):
                return False
            try:
                proc_dir = Path(cmd[cmd.index("--relax-dir") + 1]).resolve()
            except (ValueError, IndexError):
                return str(target_dir) in " ".join(cmd)
            return proc_dir == target_dir

        return any(
            runner_matches(p.info.get("cmdline") or [])
            for p in __import__("psutil").process_iter(["cmdline"])
        )

    async def poll_once(self) -> None:
        if not self.runs_dir.exists():
            return

        for job_dir in sorted(self.runs_dir.iterdir()):
            if not job_dir.is_dir():
                continue
            try:
                snap = snapshot_job(job_dir, self.cfg)
                self._snapshots[snap.job_id] = snap
                await self._check_transition(snap)
            except Exception as exc:
                log.debug("Error procesando %s: %s", job_dir.name, exc)

    async def _check_transition(self, snap: StatsResponse) -> None:
        prev = self._prev_states.get(snap.job_id)
        current = snap.status

        if prev == current:
            return

        self._prev_states[snap.job_id] = current

        # Solo eventos que requieren atención inmediata
        event_map = {
            "failed":      "FAILED",
            "stopped":     "STOPPED",
            "stalled":     "STALLED",
            "oscillating": "OSCILLATING",
        }
        event_name = event_map.get(current)

        # WebSocket siempre recibe todos los cambios de estado
        all_events = {
            "running": "STARTED", "converged": "CONVERGED",
            **event_map,
        }
        ws_event_name = all_events.get(current)
        if ws_event_name is None:
            return

        data: dict[str, Any] = {
            "formula":      snap.formula,
            "elapsed_min":  snap.elapsed_min,
            "energy_ev":    snap.energy_history[-1] if snap.energy_history else None,
            "n_fire_steps": snap.n_fire_steps,
            "n_scf_iters":  snap.n_scf_iters,
            "mpi_cores":    snap.mpi_cores,
        }
        if event_name == "OSCILLATING":
            data["energy_history"] = snap.energy_history[-10:]
            data["energy_std"] = (
                round(statistics.stdev(snap.energy_history[-10:]), 4)
                if len(snap.energy_history) >= 2 else None
            )
        if event_name == "STALLED":
            data["stall_minutes"] = snap.stall_minutes

        ws_event = WsEvent(
            job_id=snap.job_id,
            event=ws_event_name,  # type: ignore[arg-type]
            timestamp=datetime.now().isoformat(),
            data=data,
        )

        # WebSocket recibe todo
        try:
            self._event_queue.put_nowait(ws_event)
        except asyncio.QueueFull:
            pass

        # Telegram solo para problemas
        if event_name is not None:
            token   = self.telegram.get("bot_token", "")
            chat_id = self.telegram.get("chat_id", "")
            if token and chat_id:
                await send_telegram(token, chat_id, event_name, snap.job_id, data)

    def _find_next_batch(self) -> Path | None:
        """Busca en batches_dir el primer batch con jobs pendientes."""
        _ROOT = Path(__file__).resolve().parents[2]
        batches_dir = Path(self.cfg.get("batches_dir", "runs/batches"))
        if not batches_dir.is_absolute():
            batches_dir = (_ROOT / batches_dir).resolve()
        if not batches_dir.exists():
            return None
        # Ordenar batch_NNN numéricamente
        candidates = sorted(
            (d for d in batches_dir.iterdir() if d.is_dir()),
            key=lambda d: int("".join(filter(str.isdigit, d.name)) or "0"),
        )
        for batch_dir in candidates:
            # Saltar batches ya lanzados por el monitor
            if (batch_dir / ".runner_launched").exists():
                continue
            has_pending = any(
                json.loads((j / "status.json").read_text()).get("status") == "pending"
                for j in batch_dir.iterdir()
                if j.is_dir() and (j / "status.json").exists()
            )
            if has_pending:
                return batch_dir
        return None

    async def _check_batch_done(self) -> None:
        """Detecta fin de batch, notifica y lanza el siguiente si existe."""
        if not self._snapshots:
            return
        pending = sum(1 for s in self._snapshots.values() if s.status == "pending")
        running = sum(1 for s in self._snapshots.values()
                      if s.status in ("running", "stalled", "oscillating"))
        if pending + running > 0:
            self._batch_done_notified = False
            return
        if getattr(self, "_batch_done_notified", False):
            return

        self._batch_done_notified = True
        n_conv = sum(1 for s in self._snapshots.values() if s.status == "converged")
        n_fail = sum(1 for s in self._snapshots.values() if s.status in ("failed", "stopped"))
        token   = self.telegram.get("bot_token", "")
        chat_id = self.telegram.get("chat_id", "")

        next_batch = self._find_next_batch()

        if next_batch:
            slots = self.cfg.get("runner_slots", 2)
            cores = self.cfg.get("runner_cores", 22)
            self._launch_runner(next_batch)
            (next_batch / ".runner_launched").write_text(
                datetime.now().isoformat()
            )
            log.info("Nuevo batch lanzado: %s (%s slots × %s cores)", next_batch.name, slots, cores)
            # Cambiar el poller al nuevo directorio
            self.runs_dir = next_batch
            self._snapshots.clear()
            self._prev_states.clear()
            self._batch_done_notified = False
            self._orchestrator_running = False   # batch preparado consumido

            if token and chat_id:
                text = (
                    f"✅ <b>Batch completo</b> — {n_conv} conv / {n_fail} fallidos\n"
                    f"🚀 Lanzando <b>{next_batch.name}</b> ({slots} slots × {cores} cores)"
                )
                await send_telegram(token, chat_id, "PING", "batch-done", {"_raw": text})
        else:
            # No hay batch preparado en cola → disparar el orquestador de active
            # learning: finaliza el batch actual (acumula + reentrena + evalúa +
            # grafica) y genera+prepara el siguiente (sin lanzar). El monitor lo
            # lanzará en un poll posterior al detectar el batch preparado.
            _ROOT = Path(__file__).resolve().parents[2]
            al_state_f = _ROOT / "data" / "batches" / "orchestrator_state.json"
            try:
                al_state = json.loads(al_state_f.read_text()) if al_state_f.exists() else {}
            except Exception:
                al_state = {}

            if al_state.get("stopped"):
                log.info("Active learning terminado: %s", al_state.get("reason"))
                if token and chat_id and not getattr(self, "_al_done_notified", False):
                    self._al_done_notified = True
                    await send_telegram(token, chat_id, "PING", "al-done",
                        {"_raw": f"🏁 <b>Active learning terminado</b>\n{al_state.get('reason','')}"})
            elif not getattr(self, "_orchestrator_running", False):
                orch = _ROOT / "scripts" / "active_learning_orchestrator.py"
                subprocess.Popen([sys.executable, str(orch), "advance"], cwd=str(_ROOT))
                self._orchestrator_running = True
                self._batch_done_notified = False   # re-chequear hasta que aparezca el batch
                log.info("Orquestador disparado (retrain + preparar siguiente batch)")
                if token and chat_id:
                    await send_telegram(token, chat_id, "PING", "al-prep",
                        {"_raw": f"✅ <b>Batch completo</b> — {n_conv} conv / {n_fail} fallidos\n"
                                 f"🧠 Reentrenando surrogate + preparando siguiente batch…"})
            else:
                # orquestador trabajando; seguir re-chequeando sin re-spawn
                self._batch_done_notified = False

    async def _check_runner_alive(self) -> None:
        """Detecta runner muerto (pending>0, running==0) y lo relanza automáticamente."""
        if not self._snapshots:
            return
        pending = sum(1 for s in self._snapshots.values() if s.status == "pending")
        running = sum(1 for s in self._snapshots.values()
                      if s.status in ("running", "stalled", "oscillating"))
        if pending == 0 or running > 0:
            self._runner_dead_since = 0.0
            return

        # pending > 0 y running == 0 — ¿hace cuánto?
        now = time.time()
        if not getattr(self, "_runner_dead_since", 0.0):
            self._runner_dead_since = now
            return

        # Esperar 2 ciclos completos antes de actuar (evitar falsos positivos al arrancar)
        wait_sec = self.cfg.get("poll_interval_sec", 30) * 2
        if now - self._runner_dead_since < wait_sec:
            return

        if self._runner_running_for(self.runs_dir):
            self._runner_dead_since = 0.0
            return

        # Runner realmente muerto → relanzar
        self._runner_dead_since = 0.0
        slots = self.cfg.get("runner_slots", 2)
        cores = self.cfg.get("runner_cores", 8)
        self._launch_runner(self.runs_dir)
        log.warning("Runner muerto detectado — relanzando para %s", self.runs_dir.name)
        token   = self.telegram.get("bot_token", "")
        chat_id = self.telegram.get("chat_id", "")
        if token and chat_id:
            await send_telegram(token, chat_id, "PING", "runner-revived", {
                "_raw": (
                    f"⚠️ <b>Runner relanzado</b>\n"
                    f"Batch: <code>{self.runs_dir.name}</code>\n"
                    f"{pending} jobs pendientes  {slots} slots × {cores} cores"
                )
            })

    async def _check_surrogate(self) -> None:
        """Notifica cuando el surrogate se reentrenó (metrics.json más nuevo)."""
        _ROOT = Path(__file__).resolve().parents[2]
        rel = self.cfg.get("surrogate_metrics_path",
                           "models/surrogate_energy.pkl.metrics.json")
        metrics_path = Path(rel)
        if not metrics_path.is_absolute():
            metrics_path = (_ROOT / rel).resolve()
        if not metrics_path.exists():
            return
        mtime = metrics_path.stat().st_mtime
        if mtime <= getattr(self, "_last_surrogate_mtime", 0):
            return
        self._last_surrogate_mtime = mtime
        token   = self.telegram.get("bot_token", "")
        chat_id = self.telegram.get("chat_id", "")
        if not token or not chat_id:
            return
        try:
            m = json.loads(metrics_path.read_text())
            lines = ["🤖 <b>Surrogate entrenado</b>"]
            if "n_train" in m:
                lines.append(f"n_train: {m['n_train']}   n_features: {m.get('n_features','?')}")
            if "cv_mae" in m:
                lines.append(f"CV MAE: {m['cv_mae']:.4f} eV/átomo")
            if "train_mae" in m:
                lines.append(f"Train MAE: {m['train_mae']:.4f} eV/átomo")
            if "test_mae" in m:
                lines.append(f"Test MAE: {m['test_mae']:.4f} eV/átomo")
            if "overfit_ratio" in m:
                lines.append(f"Overfit ratio: {m['overfit_ratio']:.2f}")
            await send_telegram(token, chat_id, "PING", "surrogate", {"_raw": "\n".join(lines)})
        except Exception as exc:
            log.error("Error leyendo metrics surrogate: %s", exc)

    async def _check_temperatures(self) -> None:
        """Envía alerta si algún socket CPU supera el umbral configurado."""
        from .sysmetrics import collect as collect_metrics
        threshold = self.cfg.get("temp_alert_celsius", 85)
        token   = self.telegram.get("bot_token", "")
        chat_id = self.telegram.get("chat_id", "")
        if not token or not chat_id:
            return
        try:
            m = collect_metrics()
            hot = [(i, t) for i, t in enumerate(m.pkg_temps) if t >= threshold]
            if not hot:
                self._temp_alerted = False
                return
            if getattr(self, "_temp_alerted", False):
                return  # ya se notificó, no spam
            self._temp_alerted = True
            pkg_str = "  ".join(f"PKG{i}: {t}°C" for i, t in hot)
            text = (
                f"🌡️ <b>TEMPERATURA ALTA</b>\n"
                f"{pkg_str}\n"
                f"núcleo max: {m.core_temp_max}°C   CPU: {m.cpu_percent:.0f}%"
            )
            await send_telegram(token, chat_id, "PING", "temp-alert", {"_raw": text})
        except Exception as exc:
            log.error("Error en check_temperatures: %s", exc)

    def _find_active_batch(self) -> Path | None:
        """Al arrancar: encuentra el batch más reciente con centinela + jobs activos."""
        _ROOT = Path(__file__).resolve().parents[2]
        batches_dir = Path(self.cfg.get("batches_dir", "runs/batches"))
        if not batches_dir.is_absolute():
            batches_dir = (_ROOT / batches_dir).resolve()
        if not batches_dir.exists():
            return None
        candidates = sorted(
            (d for d in batches_dir.iterdir()
             if d.is_dir() and (d / ".runner_launched").exists()),
            key=lambda d: int("".join(filter(str.isdigit, d.name)) or "0"),
            reverse=True,
        )
        for batch_dir in candidates:
            has_active = any(
                json.loads((j / "status.json").read_text()).get("status")
                in ("pending", "running")
                for j in batch_dir.iterdir()
                if j.is_dir() and (j / "status.json").exists()
            )
            if has_active:
                return batch_dir
        return None

    async def run_forever(self, interval: int) -> None:
        log.info("Poller iniciado — directorio=%s  intervalo=%ss", self.runs_dir, interval)
        self._temp_alerted = False
        self._batch_done_notified = False
        self._last_surrogate_mtime = 0.0

        # Al arrancar: si runs_dir no tiene jobs activos, resumir el batch correcto
        def _has_active(d: Path) -> bool:
            return any(
                json.loads((j / "status.json").read_text()).get("status")
                in ("pending", "running")
                for j in d.iterdir()
                if j.is_dir() and (j / "status.json").exists()
            )
        try:
            if not _has_active(self.runs_dir):
                active = self._find_active_batch()
                if active:
                    log.info("Resumiendo batch activo: %s", active.name)
                    self.runs_dir = active
                    self._batch_done_notified = False
        except Exception:
            pass

        while True:
            try:
                await self.poll_once()
            except Exception as exc:
                log.error("Error en poll_once: %s", exc)

            await self._check_temperatures()
            try:
                await self._check_runner_alive()
            except Exception as exc:
                log.error("Error en _check_runner_alive: %s", exc)
            try:
                await self._check_batch_done()
            except Exception as exc:
                log.error("Error en _check_batch_done: %s", exc)
            try:
                await self._check_surrogate()
            except Exception as exc:
                log.error("Error en _check_surrogate: %s", exc)
            await asyncio.sleep(interval)
