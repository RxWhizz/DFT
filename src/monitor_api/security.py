"""Autenticación del monitor y registro de auditoría.

El monitor expone endpoints que matan procesos y lanzan runners, y está pensado
para consultarse desde la LAN o por VPN. Este módulo aporta:

* un token compartido (config o `DFT_MONITOR_TOKEN`) que se canjea por una
  cookie de sesión firmada, `HttpOnly` y `SameSite`;
* una barrera ASGI que cubre **HTTP y WebSocket** — se usa cookie y no cabecera
  `Authorization` precisamente porque el navegador no permite cabeceras propias
  en el handshake de un WebSocket;
* limitación de intentos de login por IP;
* un log de auditoría en JSONL para las acciones destructivas.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse

from . import paths

log = logging.getLogger(__name__)

# Prefijos que exigen sesión.
PROTECTED_PREFIXES = ("/api", "/ws", "/docs", "/redoc", "/openapi.json")
# Rutas que quedan fuera: sin ellas no habría forma de autenticarse.
EXEMPT_PATHS = frozenset({"/auth/login", "/auth/logout", "/auth/me"})

# Limitación de intentos de login.
MAX_FAILED_ATTEMPTS = 8
LOCKOUT_SECONDS = 300.0


@dataclass
class AuthConfig:
    enabled: bool = True
    token: str = ""
    session_secret: str = ""
    session_max_age_sec: int = 7 * 24 * 3600
    https_only: bool = False
    same_site: str = "strict"
    audit_path: Path = field(default_factory=lambda: paths.audit_file())


def load_auth_config(cfg: dict) -> AuthConfig:
    """Construye la config de auth desde `monitor.auth`, con override por entorno."""
    raw = (cfg.get("monitor", {}) or {}).get("auth", {}) or {}

    token = os.environ.get("DFT_MONITOR_TOKEN", "") or str(raw.get("token", "") or "")
    secret = os.environ.get("DFT_MONITOR_SESSION_SECRET", "") or str(
        raw.get("session_secret", "") or ""
    )
    if not secret:
        # Efímero: al reiniciar caducan las sesiones. Es el default seguro.
        secret = secrets.token_urlsafe(32)
        log.info("session_secret no configurado — se genera uno efímero por arranque")

    audit_rel = raw.get("audit_path")
    # Por defecto, junto a la configuración: en un binario no hay repositorio
    # donde escribir un logs/.
    audit_path = paths.resolve_data(audit_rel) if audit_rel else paths.audit_file()

    # Por defecto la auth se activa si hay token. Activarla sin token dejaría el
    # monitor inservible (ningún login podría prosperar), así que se avisa
    # explícitamente en vez de fallar en silencio.
    declared = raw.get("enabled")
    enabled = bool(declared) if declared is not None else bool(token)
    if enabled and not token:
        raise ValueError(
            "monitor.auth.enabled está activo pero no hay token. Define "
            "monitor.auth.token en configs/monitor.yaml o la variable de "
            "entorno DFT_MONITOR_TOKEN."
        )

    return AuthConfig(
        enabled=enabled,
        token=token,
        session_secret=secret,
        session_max_age_sec=int(raw.get("session_max_age_sec", 7 * 24 * 3600)),
        https_only=bool(raw.get("https_only", False)),
        same_site=str(raw.get("same_site", "strict")),
        audit_path=audit_path,
    )


# ── Auditoría ────────────────────────────────────────────────────────────────

def audit(app_state, action: str, *, client: str | None = None, **fields) -> None:
    """Anota una acción en el log de auditoría. Nunca lanza."""
    cfg: AuthConfig | None = getattr(app_state, "auth", None)
    if cfg is None:
        return
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "action": action,
        "client": client or "?",
        **fields,
    }
    try:
        cfg.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with cfg.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        log.warning("No se pudo escribir la auditoría: %s", exc)


# ── Limitación de intentos ───────────────────────────────────────────────────

_failures: dict[str, list[float]] = {}


def _recent_failures(ip: str) -> int:
    now = time.time()
    hits = [t for t in _failures.get(ip, []) if now - t < LOCKOUT_SECONDS]
    if hits:
        _failures[ip] = hits
    else:
        _failures.pop(ip, None)
    return len(hits)


def _record_failure(ip: str) -> None:
    _failures.setdefault(ip, []).append(time.time())


def reset_rate_limit() -> None:
    """Limpia el estado de intentos (para tests)."""
    _failures.clear()


# ── Barrera ASGI ─────────────────────────────────────────────────────────────

class AuthGateMiddleware:
    """Exige sesión en las rutas protegidas, tanto HTTP como WebSocket.

    Debe montarse por DENTRO de SessionMiddleware para que `scope["session"]`
    ya esté resuelto cuando se ejecuta.
    """

    def __init__(self, app, *, enabled: bool = True):
        self.app = app
        self.enabled = enabled

    async def __call__(self, scope, receive, send):
        if not self.enabled or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        protected = path.startswith(PROTECTED_PREFIXES) and path not in EXEMPT_PATHS
        if not protected or (scope.get("session") or {}).get("auth"):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            # 1008 = policy violation; se cierra antes de aceptar el handshake.
            await send({"type": "websocket.close", "code": 1008})
        else:
            await JSONResponse(
                {"detail": "No autenticado"}, status_code=401
            )(scope, receive, send)


def install_auth(app, auth_cfg: AuthConfig) -> None:
    """Monta SessionMiddleware + la barrera. Sin efecto si auth está desactivada."""
    app.state.auth = auth_cfg
    if not auth_cfg.enabled:
        log.warning(
            "AUTENTICACIÓN DESACTIVADA (sin token configurado) — solo apto para "
            "127.0.0.1. Define monitor.auth.token para exponerlo en la red."
        )
        return
    log.info("Autenticación activa — sesión por cookie, %d días de validez",
             auth_cfg.session_max_age_sec // 86400)

    from starlette.middleware.sessions import SessionMiddleware

    # add_middleware antepone: el añadido en último lugar queda más externo, así
    # que SessionMiddleware envuelve a la barrera y le resuelve la sesión.
    app.add_middleware(AuthGateMiddleware, enabled=True)
    app.add_middleware(
        SessionMiddleware,
        secret_key=auth_cfg.session_secret,
        session_cookie="dft_monitor_session",
        max_age=auth_cfg.session_max_age_sec,
        same_site=auth_cfg.same_site,
        https_only=auth_cfg.https_only,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    token: str


class AuthState(BaseModel):
    authenticated: bool
    auth_enabled: bool


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.get("/auth/me", response_model=AuthState)
async def me(request: Request) -> AuthState:
    cfg: AuthConfig = request.app.state.auth
    if not cfg.enabled:
        return AuthState(authenticated=True, auth_enabled=False)
    return AuthState(
        authenticated=bool(request.session.get("auth")), auth_enabled=True
    )


@router.post("/auth/login", response_model=AuthState)
async def login(request: Request, body: LoginRequest) -> AuthState:
    cfg: AuthConfig = request.app.state.auth
    if not cfg.enabled:
        return AuthState(authenticated=True, auth_enabled=False)

    ip = _client_ip(request)
    if _recent_failures(ip) >= MAX_FAILED_ATTEMPTS:
        audit(request.app.state, "login_bloqueado", client=ip)
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos. Espera {int(LOCKOUT_SECONDS // 60)} min.",
        )

    if not cfg.token or not hmac.compare_digest(body.token.encode(), cfg.token.encode()):
        _record_failure(ip)
        audit(request.app.state, "login_fallido", client=ip)
        raise HTTPException(status_code=401, detail="Token inválido")

    _failures.pop(ip, None)
    request.session["auth"] = True
    audit(request.app.state, "login", client=ip)
    return AuthState(authenticated=True, auth_enabled=True)


@router.post("/auth/logout", response_model=AuthState)
async def logout(request: Request) -> AuthState:
    cfg: AuthConfig = request.app.state.auth
    request.session.clear()
    audit(request.app.state, "logout", client=_client_ip(request))
    return AuthState(authenticated=not cfg.enabled, auth_enabled=cfg.enabled)
