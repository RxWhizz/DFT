"""Envía notificaciones push via Telegram Bot API."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_EMOJI = {
    "CONVERGED":   "✅",
    "FAILED":      "🔴",
    "STOPPED":     "🔴",
    "STALLED":     "⏸️",
    "OSCILLATING": "⚠️",
    "STARTED":     "🚀",
    "PING":        "📡",
}


def _build_message(event: str, job_id: str, data: dict) -> str:
    emoji = _EMOJI.get(event, "ℹ️")
    lines = [f"{emoji} <b>{event}</b>: <code>{job_id}</code>"]

    formula = data.get("formula")
    if formula:
        lines.append(f"Fórmula: {formula}")

    if event in ("CONVERGED", "FAILED", "STOPPED"):
        elapsed = data.get("elapsed_min")
        if elapsed is not None:
            lines.append(f"Tiempo: {elapsed:.1f} min")
        energy = data.get("energy_ev") or data.get("final_energy_ev")
        if energy is not None:
            lines.append(f"Energía final: {energy:.4f} eV")

    if event == "OSCILLATING":
        energies = data.get("energy_history", [])
        if energies:
            snippet = "  ".join(f"{e:.3f}" for e in energies[-5:])
            lines.append(f"Últimas E: <code>{snippet}</code> eV")
        std = data.get("energy_std")
        if std is not None:
            lines.append(f"std(E) = {std:.4f} eV")

    if event == "STALLED":
        stall_min = data.get("stall_minutes")
        if stall_min is not None:
            lines.append(f"Sin actividad: {stall_min:.0f} min")

    if event == "STARTED":
        cores = data.get("mpi_cores")
        if cores:
            lines.append(f"Cores MPI: {cores}")

    step = data.get("current_step") or data.get("n_fire_steps") or data.get("n_scf_iters")
    if step and event not in ("CONVERGED", "FAILED", "STOPPED"):
        step_type = data.get("step_type", "paso")
        lines.append(f"{step_type}: {step}")

    return "\n".join(lines)


async def send_telegram(
    bot_token: str,
    chat_id: str,
    event: str,
    job_id: str,
    data: dict | None = None,
) -> bool:
    """Envía mensaje a Telegram. Retorna True si fue exitoso.

    Si data contiene la clave '_raw', se envía ese texto directamente
    en lugar de construir el mensaje automáticamente.
    """
    if not bot_token or not chat_id:
        log.warning("Telegram no configurado (bot_token o chat_id vacíos)")
        return False

    d = data or {}
    text = d.get("_raw") or _build_message(event, job_id, d)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            })
        if resp.status_code == 200:
            return True
        log.warning("Telegram respondió %s: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        log.error("Error enviando Telegram: %s", exc)
        return False


async def send_test(bot_token: str, chat_id: str) -> bool:
    return await send_telegram(
        bot_token, chat_id,
        event="PING",
        job_id="test",
        data={"formula": "CsPbI3", "message": "Monitor DFT conectado ✓"},
    )
