"""FastAPI entrypoint.

Wires the routers built out across Fase 1 (auth, chat/SSE), the "Ahora"
persisted waitlist + suggestions, Fase 5 (approvals, credentials/vault),
and the Fase 6 monitor scaffold. None of this makes a live model call
work without real API keys — see README's Fase 0 — it just means the
plumbing is no longer the missing piece once keys exist.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.definitions import AGENTS
from app.config import get_settings
from app.routers import approvals, auth, chat, credentials, monitors, suggestions, waitlist

settings = get_settings()

app = FastAPI(title="Milo API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(waitlist.router)
app.include_router(suggestions.router)
app.include_router(approvals.router)
app.include_router(credentials.router)
app.include_router(monitors.router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/agents")
async def list_agents():
    return [
        {"id": a.id, "name": a.name, "role": a.role, "tools": a.tools}
        for a in AGENTS.values()
    ]
