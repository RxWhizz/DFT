"""Listener de comandos Telegram via long-polling (getUpdates).

Comandos soportados:
  /status   — reporte completo con métricas de sistema
  /converged [N]  — primeros N convergidos (default 50)
  /ping <job_id>  — lectura instantánea de un job
  /help     — lista de comandos
"""
from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

_HELP = (
    "🤖 <b>DFT Monitor — comandos</b>\n\n"
    "/status — reporte completo (sistema + jobs)\n"
    "/converged [N] — lista convergidos (default 50)\n"
    "/ping &lt;job_id&gt; — ping instantáneo a un job\n"
    "/search &lt;query&gt; — busca jobs por fórmula\n"
    "/help — esta ayuda"
)


async def _tg_post(token: str, method: str, payload: dict, timeout: float = 15.0) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)
    return r.json()


async def _send(token: str, chat_id: str | int, text: str) -> None:
    await _tg_post(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    })


async def _handle(token: str, chat_id: str | int, text: str, poller) -> None:
    """Despacha un mensaje de texto al handler correcto."""
    text = text.strip()
    cmd = text.split()[0].lower().lstrip("/").split("@")[0]  # quita @BotName si lo hay
    args = text.split()[1:]

    if cmd in ("status", "s"):
        from .router import _build_status_report
        from .sysmetrics import collect
        report = _build_status_report(poller, collect())
        await _send(token, chat_id, report)

    elif cmd in ("converged", "c"):
        from .router import _build_converged_text
        limit = int(args[0]) if args and args[0].isdigit() else 50
        text_out = _build_converged_text(poller, limit)
        await _send(token, chat_id, text_out)

    elif cmd in ("ping", "p"):
        if not args:
            await _send(token, chat_id, "⚠️ Uso: /ping &lt;job_id&gt;")
            return
        job_id = args[0]
        from .poller import ping_job
        job_dir = poller.runs_dir / job_id
        if not job_dir.is_dir():
            # Buscar por fórmula parcial
            matches = [
                s for s in poller.snapshots.values()
                if job_id.lower() in s.formula.lower()
            ]
            if not matches:
                await _send(token, chat_id, f"❓ Job <code>{job_id}</code> no encontrado")
                return
            snap = matches[0]
            job_dir = poller.runs_dir / snap.job_id

        from .utils import fmt_formula
        data = ping_job(job_dir)
        st   = poller.snapshots.get(job_dir.name)
        formula = fmt_formula(st.formula if st else job_dir.name)
        alive  = "✅ vivo" if data["alive"] else "💀 muerto"
        step   = f"{data['step_type']} {data['current_step']}" if data.get("current_step") else "—"
        energy = f"{data['energy_ev']:.3f} eV" if data.get("energy_ev") else "—"
        fmax   = f"{data['fmax_ev_ang']:.4f}" if data.get("fmax_ev_ang") else "—"
        rss    = f"{data['memory_rss_mb']} MB" if data.get("memory_rss_mb") else "—"
        last   = data.get("log_last_line") or "—"
        msg = (
            f"📡 <b>Ping</b>: <code>{formula}</code>\n"
            f"PID: {alive}   RAM: {rss}\n"
            f"Paso: {step}   E: {energy}   fmax: {fmax}\n"
            f"<code>{last[:120]}</code>"
        )
        await _send(token, chat_id, msg)

    elif cmd in ("search", "buscar"):
        if not args:
            await _send(token, chat_id, "⚠️ Uso: /search &lt;query&gt;")
            return
        from .utils import fmt_formula
        query = " ".join(args).lower()
        matches = [
            s for s in poller.snapshots.values()
            if query in (s.formula or s.job_id).lower()
        ]
        if not matches:
            await _send(token, chat_id, f"❓ Sin resultados para <code>{query}</code>")
            return
        _ICON = {
            "running": "🔄", "converged": "✅", "failed": "❌",
            "stopped": "🔴", "stalled": "⏸️", "oscillating": "⚠️",
            "pending": "⏳", "unknown": "❓",
        }
        # Ordenar: running/stalled/oscillating primero, luego resto
        _ORDER = {"running": 0, "stalled": 1, "oscillating": 2, "pending": 3,
                  "converged": 4, "failed": 5, "stopped": 6, "unknown": 7}
        matches.sort(key=lambda s: (_ORDER.get(s.status, 9), s.formula))
        lines = [f"🔍 <b>Resultados para</b> <code>{query}</code> ({len(matches)} jobs)\n"]
        for s in matches[:20]:
            icon = _ICON.get(s.status, "❓")
            name = fmt_formula(s.formula or s.job_id)
            detail = ""
            if s.status in ("running", "stalled", "oscillating"):
                if s.n_fire_steps:
                    detail = f"  FIRE {s.n_fire_steps}"
                    if s.fmax_history:
                        detail += f"  fmax={s.fmax_history[-1]:.3f}"
                elif s.n_scf_iters:
                    detail = f"  SCF {s.n_scf_iters}"
                if s.energy_history:
                    detail += f"  E={s.energy_history[-1]:.3f} eV"
            elif s.status == "converged" and s.final_energy_ev:
                detail = f"  E={s.final_energy_ev:.3f} eV"
            lines.append(f"{icon} <code>{name}</code>{detail}")
        if len(matches) > 20:
            lines.append(f"…(+{len(matches)-20} más, refina la búsqueda)")
        await _send(token, chat_id, "\n".join(lines))

    elif cmd in ("help", "h", "start"):
        await _send(token, chat_id, _HELP)

    else:
        await _send(token, chat_id, f"❓ Comando desconocido: <code>{cmd}</code>\n\n{_HELP}")


async def run_listener(token: str, chat_id: str, poller) -> None:
    """Long-polling loop — corre como asyncio task en background."""
    if not token or not chat_id:
        log.warning("Telegram bot_token o chat_id vacíos — listener desactivado")
        return

    log.info("Telegram listener iniciado (long-polling)")
    offset = 0

    while True:
        try:
            resp = await _tg_post(token, "getUpdates", {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["message"],
            }, timeout=40.0)

            if not resp.get("ok"):
                log.warning("getUpdates error: %s", resp)
                await asyncio.sleep(5)
                continue

            for update in resp.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                from_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "")

                if from_id != chat_id:
                    continue

                if text.startswith("/"):
                    log.info("Comando recibido: %s", text)
                    try:
                        await _handle(token, chat_id, text, poller)
                    except Exception as exc:
                        log.error("Error manejando '%s': %s", text, exc)
                        await _send(token, chat_id, f"❌ Error interno: <code>{exc}</code>")

        except asyncio.CancelledError:
            log.info("Telegram listener detenido")
            return
        except Exception as exc:
            log.error("Error en listener: %s", exc)
            await asyncio.sleep(10)
