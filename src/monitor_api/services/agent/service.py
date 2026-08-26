"""Orquestación del agente local con tool loop."""
from __future__ import annotations

import json
from typing import Any

from .config import AgentConfig
from .ollama import OllamaClient, OllamaError, model_present
from .proposals import create_proposal
from .tools import ReadOnlyToolCatalog, result_as_tool_message

SYSTEM_PROMPT = """Eres el agente local del Monitor DFT.
Tu trabajo es diagnosticar y operar el pipeline leyendo datos del monitor.
No sustituyes cálculos DFT, MACE ni surrogates numéricos.
Usa herramientas sólo para leer estado, logs, trazas, metadata y reportes.
Si recomiendas una acción de escritura, descríbela como propuesta visible; no la ejecutes.
Responde en español claro y con pasos concretos."""

DIAGNOSTIC_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "status": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
        "proposal": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "command": {"type": "string"},
                "diff": {"type": "string"},
                "rationale": {"type": "string"},
            },
        },
    },
    "required": ["summary", "status", "evidence", "recommended_actions"],
}


class AgentDisabled(RuntimeError):
    """El agente no está habilitado en configuración."""


class AgentService:
    def __init__(self, cfg: AgentConfig, *, client: OllamaClient | None = None):
        self.cfg = cfg
        self.client = client or OllamaClient(cfg.base_url, timeout=cfg.request_timeout_sec)

    async def health(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            return self._health_base(ok=False, error="agent disabled")
        if self.cfg.provider != "ollama":
            return self._health_base(ok=False, error=f"provider no soportado: {self.cfg.provider}")

        try:
            version = await self.client.version()
            tags = await self.client.tags()
        except OllamaError as exc:
            return self._health_base(ok=False, error=str(exc))

        return self._health_base(
            ok=True,
            version=version.get("version"),
            model_present=model_present(tags, self.cfg.model),
        )

    async def chat(
        self,
        app,
        *,
        message: str,
        history: list[dict[str, str]] | None = None,
        job_id: str | None = None,
        structured: bool = False,
    ) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise AgentDisabled("monitor.agent.enabled está desactivado")
        if self.cfg.provider != "ollama":
            raise AgentDisabled(f"provider no soportado: {self.cfg.provider}")

        catalog = ReadOnlyToolCatalog(app)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if job_id:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"Contexto de UI: hay un job seleccionado. Usa exactamente "
                        f"este job_id para herramientas específicas de job: `{job_id}`."
                    ),
                }
            )
        else:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Contexto de UI: no hay job seleccionado en esta vista. "
                        "Si el usuario dice 'este job', 'job seleccionado' o algo similar, "
                        "no inventes un job_id ni llames herramientas que requieren job_id. "
                        "Primero usa get_api_jobs para listar candidatos o pide al usuario "
                        "un job_id exacto."
                    ),
                }
            )
        messages.extend(history or [])
        user_content = message
        if job_id:
            user_content = (
                f"Diagnostica el job `{job_id}` usando las herramientas disponibles. "
                f"Pregunta original: {message}"
            )
        if structured:
            user_content += (
                "\nDevuelve el diagnóstico final como JSON con summary, status, "
                "evidence y recommended_actions."
            )
        messages.append({"role": "user", "content": user_content})

        tool_results: list[dict[str, Any]] = []
        final_response: dict[str, Any] | None = None
        used_rounds = 0

        for round_index in range(self.cfg.max_tool_rounds):
            payload: dict[str, Any] = {
                "model": self.cfg.model,
                "messages": messages,
                "stream": False,
                "tools": catalog.as_ollama_tools(),
                "think": self.cfg.think,
                "options": {
                    "temperature": self.cfg.temperature,
                    "num_predict": self.cfg.num_predict_tool,
                },
            }
            if structured:
                payload["format"] = DIAGNOSTIC_SCHEMA
            final_response = await self.client.chat(payload)
            assistant = final_response.get("message") or {}
            calls = assistant.get("tool_calls") or []
            if not calls:
                break

            used_rounds = round_index + 1
            messages.append(assistant)
            for call in calls:
                fn = call.get("function") or {}
                name = str(fn.get("name") or "")
                arguments = fn.get("arguments") or {}
                if not isinstance(arguments, dict):
                    arguments = {}
                result = await catalog.execute(name, arguments)
                tool_results.append({"name": name, "arguments": arguments, **result})
                messages.append(result_as_tool_message(name, result))
        else:
            messages.append(
                {
                    "role": "user",
                    "content": "Alcanzaste el límite de herramientas. Resume con los datos leídos.",
                }
            )
            payload = {"model": self.cfg.model, "messages": messages, "stream": False}
            payload["think"] = self.cfg.think
            payload["options"] = {
                "temperature": self.cfg.temperature,
                "num_predict": self.cfg.num_predict_final,
            }
            if structured:
                payload["format"] = DIAGNOSTIC_SCHEMA
            final_response = await self.client.chat(payload)

        assistant = (final_response or {}).get("message") or {}
        content = str(assistant.get("content") or "")
        structured_payload = _parse_json_object(content) if structured else None
        proposal_ids = _create_proposals_from_payload(structured_payload)

        return {
            "ok": True,
            "model": (final_response or {}).get("model") or self.cfg.model,
            "message": content,
            "structured": structured_payload,
            "tool_rounds": used_rounds,
            "tool_results": tool_results,
            "proposal_ids": proposal_ids,
        }

    def _health_base(self, *, ok: bool, error: str | None = None, **extra) -> dict[str, Any]:
        return {
            "enabled": self.cfg.enabled,
            "provider": self.cfg.provider,
            "ok": ok,
            "base_url": self.cfg.base_url,
            "model": self.cfg.model,
            "model_present": False,
            "manage_service": self.cfg.manage_service,
            "allow_writes": self.cfg.allow_writes,
            "models_dir": str(self.cfg.models_dir),
            "revive_repo": str(self.cfg.revive_repo) if self.cfg.revive_repo else None,
            "version": None,
            "error": error,
            **extra,
        }


def _parse_json_object(content: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _create_proposals_from_payload(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    raw = payload.get("proposals")
    proposals = raw if isinstance(raw, list) else [payload.get("proposal")]
    ids: list[str] = []
    for item in proposals:
        if not isinstance(item, dict):
            continue
        if not any(item.get(k) for k in ("command", "diff", "title")):
            continue
        proposal = create_proposal(
            title=str(item.get("title") or "Propuesta del agente"),
            command=item.get("command"),
            diff=item.get("diff"),
            rationale=item.get("rationale"),
            metadata={"source": "agent"},
        )
        ids.append(proposal.id)
    return ids
