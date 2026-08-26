"""Propuestas generadas por el agente.

V1 no ejecuta escrituras como tool calls. Si el modelo sugiere una acción, se
guarda como propuesta visible para aprobación/rechazo y queda auditada.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentProposal:
    id: str
    title: str
    created_at: float = field(default_factory=time.time)
    status: str = "pending"
    command: str | None = None
    diff: str | None = None
    rationale: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "status": self.status,
            "command": self.command,
            "diff": self.diff,
            "rationale": self.rationale,
            "metadata": self.metadata,
        }


_STORE: dict[str, AgentProposal] = {}


def create_proposal(
    *,
    title: str,
    command: str | None = None,
    diff: str | None = None,
    rationale: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AgentProposal:
    proposal = AgentProposal(
        id=f"prop_{secrets.token_urlsafe(9)}",
        title=title[:200] or "Propuesta del agente",
        command=command,
        diff=diff,
        rationale=rationale,
        metadata=metadata or {},
    )
    _STORE[proposal.id] = proposal
    return proposal


def get_proposal(proposal_id: str) -> AgentProposal | None:
    return _STORE.get(proposal_id)


def mark_proposal(proposal_id: str, status: str) -> AgentProposal | None:
    proposal = get_proposal(proposal_id)
    if proposal is None:
        return None
    proposal.status = status
    return proposal


def reset_proposals() -> None:
    _STORE.clear()
