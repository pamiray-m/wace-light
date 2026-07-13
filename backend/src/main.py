"""WACE Light — open-source individual edition. FastAPI entrypoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.wace import router as wace_router

app = FastAPI(title="WACE Light", version="0.1.0",
              description="The governed AI command environment — open-source individual edition.")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _init_db() -> None:
    # Create tables on first boot (SQLite by default — see .env.example).
    from src.aos.voundry.persistence import models  # noqa: F401 — register ORM tables
    from src.core.registry.database import init_db
    import os
    init_db(os.environ.get("AOS_DB_URL", "sqlite:///./wace_light.db"))


@app.get("/health")
def health() -> dict:
    from src.aos.voundry.byok import llm_config
    return {"status": "ok", "product": "wace-light", "byok": llm_config()}


app.include_router(wace_router)
