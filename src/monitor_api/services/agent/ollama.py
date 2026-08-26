"""Cliente mínimo para la API HTTP de Ollama."""
from __future__ import annotations

from typing import Any

import httpx


class OllamaError(RuntimeError):
    """Ollama no respondió o devolvió un error."""


class OllamaClient:
    def __init__(self, base_url: str, *, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def version(self) -> dict[str, Any]:
        return await self._request("GET", "/api/version")

    async def tags(self) -> dict[str, Any]:
        return await self._request("GET", "/api/tags")

    async def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/api/chat", json=payload)

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise OllamaError(
                f"timeout tras {self.timeout:.0f}s esperando {path}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500].strip()
            raise OllamaError(
                f"Ollama devolvio HTTP {exc.response.status_code}"
                + (f": {detail}" if detail else "")
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(str(exc)) from exc


def model_present(tags_response: dict[str, Any], model: str) -> bool:
    """Comprueba si `model` aparece en `/api/tags`."""
    for entry in tags_response.get("models") or []:
        if entry.get("name") == model or entry.get("model") == model:
            return True
    return False
