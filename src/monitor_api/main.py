"""FastAPI app — DFT Simulation Monitor."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI

from .poller import DFTPoller
from .router import router
from .telegram_bot import run_listener

log = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    cfg: dict = {}
    if config_path.exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
    # Merge local overrides si existe
    local = config_path.with_suffix(".local.yaml")
    if local.exists():
        with open(local) as f:
            local_cfg = yaml.safe_load(f) or {}
        # deep merge a un nivel
        for k, v in local_cfg.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


@asynccontextmanager
async def lifespan(app: FastAPI):
    config_path = Path(__file__).resolve().parents[2] / "configs" / "monitor.yaml"
    cfg = load_config(config_path)
    app.state.config = cfg

    monitor_cfg = cfg.get("monitor", {})
    telegram_cfg = cfg.get("telegram", {})

    # Resolver runs_dir relativo al root del proyecto
    runs_rel = monitor_cfg.get("runs_dir", "runs/relax_basic")
    runs_dir = (Path(__file__).resolve().parents[2] / runs_rel).resolve()

    poller = DFTPoller(
        runs_dir=runs_dir,
        cfg=monitor_cfg,
        telegram_cfg=telegram_cfg,
    )
    app.state.poller = poller

    interval = monitor_cfg.get("poll_interval_sec", 30)
    poller_task = asyncio.create_task(poller.run_forever(interval))

    token   = telegram_cfg.get("bot_token", "")
    chat_id = telegram_cfg.get("chat_id", "")
    bot_task = asyncio.create_task(run_listener(token, chat_id, poller))

    log.info("Monitor DFT iniciado — runs_dir=%s", runs_dir)

    yield

    poller_task.cancel()
    bot_task.cancel()
    for t in (poller_task, bot_task):
        try:
            await t
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    app = FastAPI(
        title="DFT Simulation Monitor",
        description="Monitor en tiempo real de simulaciones GPAW/BUHO con push via Telegram",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
