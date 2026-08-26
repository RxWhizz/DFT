"""Configuración del agente local."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ... import paths

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "dft-agent:14b-q4"

# Sin default: es un repositorio de terceros y no hay ruta que valga en otra
# máquina. Una absoluta incrustada aquí viajaría dentro del binario y filtraría
# la disposición local. Quien use `manage_service` define monitor.agent.revive_repo.
DEFAULT_REVIVE_REPO: Path | None = None


@dataclass(frozen=True)
class AgentConfig:
    enabled: bool = False
    provider: str = "ollama"
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    manage_service: bool = False
    revive_repo: Path | None = DEFAULT_REVIVE_REPO
    allow_writes: bool = False
    # default_factory y no un valor: un default de dataclass se evalúa al crear
    # la clase, o sea al importar, y congelaría la raíz de datos que hubiera en
    # ese momento — `--data-root` no la movería después.
    models_dir: Path = field(default_factory=lambda: paths.resolve_data("models/ollama"))
    max_tool_rounds: int = 4
    request_timeout_sec: float = 180.0
    num_predict_tool: int = 192
    num_predict_final: int = 384
    temperature: float = 0.2
    think: bool = False


def load_agent_config(cfg: dict) -> AgentConfig:
    """Extrae `monitor.agent` con defaults conservadores."""
    raw = ((cfg.get("monitor") or {}).get("agent") or {}) if cfg else {}
    models_dir = raw.get("models_dir", "models/ollama")
    revive_repo = raw.get("revive_repo")

    return AgentConfig(
        enabled=bool(raw.get("enabled", False)),
        provider=str(raw.get("provider", "ollama")),
        base_url=str(raw.get("base_url", DEFAULT_BASE_URL)).rstrip("/"),
        model=str(raw.get("model", DEFAULT_MODEL)),
        manage_service=bool(raw.get("manage_service", False)),
        revive_repo=Path(str(revive_repo)).expanduser() if revive_repo else None,
        allow_writes=bool(raw.get("allow_writes", False)),
        models_dir=paths.resolve_data(str(models_dir)),
        max_tool_rounds=max(1, min(8, int(raw.get("max_tool_rounds", 4)))),
        request_timeout_sec=max(30.0, min(600.0, float(raw.get("request_timeout_sec", 180)))),
        num_predict_tool=max(32, min(1024, int(raw.get("num_predict_tool", 192)))),
        num_predict_final=max(64, min(2048, int(raw.get("num_predict_final", 384)))),
        temperature=max(0.0, min(2.0, float(raw.get("temperature", 0.2)))),
        think=bool(raw.get("think", False)),
    )
