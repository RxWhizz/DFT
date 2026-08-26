"""Herramientas locales de sólo lectura para el agente."""
from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from ... import router as monitor_router
from ...security import audit

READ_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("get", "/api/health"),
        ("get", "/api/jobs"),
        ("get", "/api/jobs/converged"),
        ("get", "/api/jobs/{job_id}"),
        ("get", "/api/jobs/{job_id}/log"),
        ("get", "/api/jobs/{job_id}/traces"),
        ("get", "/api/jobs/{job_id}/metadata"),
        ("get", "/api/summary"),
        ("get", "/api/statusfull"),
        ("get", "/api/status/report"),
        ("get", "/api/batches"),
        ("get", "/api/screening/config"),
        ("get", "/api/screening/runs"),
        ("get", "/api/screening/runs/{run_id}"),
        ("get", "/api/models"),
        ("get", "/api/ml/top8"),
        ("get", "/api/candidates"),
    }
)


@dataclass(frozen=True)
class ReadTool:
    name: str
    method: str
    path: str
    description: str
    parameters: dict[str, Any]

    def as_ollama_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def tool_name(method: str, path: str) -> str:
    name = f"{method.lower()}_{path.strip('/')}"
    name = name.replace("{", "by_").replace("}", "")
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    return re.sub(r"_+", "_", name).strip("_")


def generate_read_tools(openapi: dict[str, Any]) -> list[ReadTool]:
    """Genera definiciones Ollama desde OpenAPI, filtradas por whitelist."""
    tools: list[ReadTool] = []
    for path, methods in sorted((openapi.get("paths") or {}).items()):
        for method, op in sorted(methods.items()):
            key = (method.lower(), path)
            if key not in READ_ALLOWLIST:
                continue
            properties: dict[str, Any] = {}
            required: list[str] = []
            for param in op.get("parameters") or []:
                pname = param.get("name")
                if not pname:
                    continue
                schema = dict(param.get("schema") or {"type": "string"})
                schema.pop("title", None)
                if param.get("description"):
                    schema.setdefault("description", param["description"])
                properties[pname] = schema
                if param.get("required"):
                    required.append(pname)

            tools.append(
                ReadTool(
                    name=tool_name(method, path),
                    method=method.lower(),
                    path=path,
                    description=_tool_description(method, path, op),
                    parameters={
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                )
            )
    return tools


def _tool_description(method: str, path: str, op: dict[str, Any]) -> str:
    description = op.get("summary") or op.get("description") or f"{method.upper()} {path}"
    if "{job_id}" in path:
        description += (
            " Requiere un job_id exacto. No la uses si el usuario solo dijo "
            "'este job' o 'job seleccionado' sin contexto; primero llama get_api_jobs."
        )
    return description


class ReadOnlyToolCatalog:
    def __init__(self, app):
        self.app = app
        self.tools = generate_read_tools(app.openapi())
        self._by_name = {tool.name: tool for tool in self.tools}

    def as_ollama_tools(self) -> list[dict[str, Any]]:
        return [tool.as_ollama_tool() for tool in self.tools]

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self._by_name.get(name)
        if tool is None:
            return {"ok": False, "error": f"Herramienta no permitida: {name}"}

        request = SimpleNamespace(app=self.app, client=SimpleNamespace(host="agent"))
        try:
            data = await self._dispatch(tool.path, request, arguments)
        except HTTPException as exc:
            return {"ok": False, "status_code": exc.status_code, "error": str(exc.detail)}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        payload = jsonable_encoder(data)
        if not isinstance(payload, dict):
            payload = {"value": payload}
        audit(self.app.state, "agent_tool_read", client="agent", tool=name, path=tool.path)
        return {"ok": True, "data": payload}

    async def _dispatch(self, path: str, request, args: dict[str, Any]) -> Any:
        r = monitor_router
        match path:
            case "/api/health":
                return await r.health(request)
            case "/api/jobs":
                return await r.list_jobs(
                    request,
                    status=_str_or_none(args.get("status")),
                    q=_str_or_none(args.get("q")),
                    sort=str(args.get("sort") or "formula"),
                    desc=bool(args.get("desc", False)),
                    limit=_int(args.get("limit"), 100),
                    offset=_int(args.get("offset"), 0),
                )
            case "/api/jobs/converged":
                return await r.list_converged(request, limit=_int(args.get("limit"), 50))
            case "/api/jobs/{job_id}":
                return await r.get_job(_required(args, "job_id"), request)
            case "/api/jobs/{job_id}/log":
                return await r.job_log(
                    request,
                    _required(args, "job_id"),
                    label=_str_or_none(args.get("label")),
                    tail=_int(args.get("tail"), 200),
                )
            case "/api/jobs/{job_id}/traces":
                return await r.job_traces_endpoint(request, _required(args, "job_id"))
            case "/api/jobs/{job_id}/metadata":
                return await r.job_metadata_endpoint(request, _required(args, "job_id"))
            case "/api/summary":
                return await r.summary(request)
            case "/api/statusfull":
                return await r.statusfull_report(request)
            case "/api/status/report":
                return await r.status_report(request)
            case "/api/batches":
                return await r.list_batches_endpoint(request)
            case "/api/screening/config":
                return await r.screening_config()
            case "/api/screening/runs":
                return await r.screening_runs()
            case "/api/screening/runs/{run_id}":
                return await r.screening_run_detail(_required(args, "run_id"))
            case "/api/models":
                maybe = r.list_models()
                return await maybe if inspect.isawaitable(maybe) else maybe
            case "/api/ml/top8":
                maybe = r.ml_top8()
                return await maybe if inspect.isawaitable(maybe) else maybe
            case "/api/candidates":
                return await r.list_candidates(
                    request,
                    q=_str_or_none(args.get("q")),
                    generation_mode=_str_or_none(args.get("generation_mode")),
                    b_family=_str_or_none(args.get("b_family")),
                    halide=_str_or_none(args.get("halide")),
                    sort=str(args.get("sort") or "score"),
                    desc=bool(args.get("desc", True)),
                    limit=_int(args.get("limit"), 500),
                    offset=_int(args.get("offset"), 0),
                )
        raise ValueError(f"Ruta no implementada para el agente: {path}")


def _required(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if value is None or value == "":
        raise HTTPException(status_code=422, detail=f"Falta argumento requerido: {key}")
    return str(value)


def _str_or_none(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def result_as_tool_message(name: str, result: dict[str, Any]) -> dict[str, str]:
    return {
        "role": "tool",
        "tool_name": name,
        "name": name,
        "content": json.dumps(result, ensure_ascii=False, default=str)[:120_000],
    }
