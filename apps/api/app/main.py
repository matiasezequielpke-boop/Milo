"""FastAPI entrypoint.

Today: health check + agent roster only. The streaming endpoint (the one
seam between this and the Next.js frontend) lands with Fase 1 once the
coordinator and gateway are wired to a real model.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.definitions import AGENTS
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Milo API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/agents")
async def list_agents():
    return [
        {"id": a.id, "name": a.name, "role": a.role, "tools": a.tools}
        for a in AGENTS.values()
    ]
