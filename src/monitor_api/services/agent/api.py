"""Endpoints REST del agente local."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...security import audit
from .config import load_agent_config
from .ollama import OllamaError
from .proposals import get_proposal, mark_proposal
from .service import AgentDisabled, AgentService

router = APIRouter(tags=["agent"])


class AgentHealthResponse(BaseModel):
    enabled: bool
    provider: str
    ok: bool
    base_url: str
    model: str
    model_present: bool = False
    manage_service: bool
    allow_writes: bool = False
    models_dir: str
    revive_repo: str | None = None
    version: str | None = None
    error: str | None = None


class AgentMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: list[AgentMessage] = []
    job_id: str | None = None
    structured: bool = False


class AgentToolResult(BaseModel):
    name: str
    arguments: dict[str, Any] = {}
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    status_code: int | None = None


class AgentChatResponse(BaseModel):
    ok: bool
    model: str
    message: str
    structured: dict[str, Any] | None = None
    tool_rounds: int
    tool_results: list[AgentToolResult]
    proposal_ids: list[str] = []


class AgentProposalResponse(BaseModel):
    id: str
    title: str
    created_at: float
    status: str
    command: str | None = None
    diff: str | None = None
    rationale: str | None = None
    metadata: dict[str, Any] = {}
    executed: bool = False


@router.get("/api/agent/health", response_model=AgentHealthResponse)
async def agent_health(request: Request) -> AgentHealthResponse:
    cfg = load_agent_config(request.app.state.config)
    return AgentHealthResponse(**await AgentService(cfg).health())


@router.post("/api/agent/chat", response_model=AgentChatResponse)
async def agent_chat(request: Request, body: AgentChatRequest) -> AgentChatResponse:
    cfg = load_agent_config(request.app.state.config)
    client = request.client.host if request.client else None
    audit(
        request.app.state,
        "agent_chat",
        client=client,
        job_id=body.job_id,
        message_chars=len(body.message),
        structured=body.structured,
    )

    try:
        response = await AgentService(cfg).chat(
            request.app,
            message=body.message,
            history=[m.model_dump() for m in body.history],
            job_id=body.job_id,
            structured=body.structured,
        )
    except AgentDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OllamaError as exc:
        detail = str(exc)
        status = 504 if "timeout" in detail.lower() else 502
        raise HTTPException(status_code=status, detail=f"Ollama no completo el chat: {detail}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ollama/agente no disponible: {exc}") from exc

    for proposal_id in response.get("proposal_ids") or []:
        audit(request.app.state, "agent_proposal_created", client=client, proposal_id=proposal_id)
    return AgentChatResponse(**response)


@router.post("/api/agent/proposals/{proposal_id}/approve", response_model=AgentProposalResponse)
async def approve_proposal(request: Request, proposal_id: str) -> AgentProposalResponse:
    proposal = mark_proposal(proposal_id, "approved")
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Propuesta '{proposal_id}' no encontrada")
    audit(
        request.app.state,
        "agent_proposal_approved",
        client=request.client.host if request.client else None,
        proposal_id=proposal_id,
    )
    return AgentProposalResponse(**proposal.as_dict(), executed=False)


@router.post("/api/agent/proposals/{proposal_id}/reject", response_model=AgentProposalResponse)
async def reject_proposal(request: Request, proposal_id: str) -> AgentProposalResponse:
    proposal = mark_proposal(proposal_id, "rejected")
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Propuesta '{proposal_id}' no encontrada")
    audit(
        request.app.state,
        "agent_proposal_rejected",
        client=request.client.host if request.client else None,
        proposal_id=proposal_id,
    )
    return AgentProposalResponse(**proposal.as_dict(), executed=False)
