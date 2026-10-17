"""FastAPI entrypoint.

Wires the routers built out across Fase 1 (auth, chat/SSE), the "Ahora"
persisted waitlist + suggestions, Fase 5 (approvals, credentials/vault),
the Fase 6 monitor scaffold, and the Warden MVP (households + consent,
banking via Plaid, the family approval gate, and the live agent in chat).
Every integration stays inert — with a clear error, never a fake result —
until its key is configured.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.definitions import AGENTS
from app.config import get_settings
from app.routers import (
    approvals,
    auth,
    banking,
    chat,
    credentials,
    demo,
    households,
    monitors,
    suggestions,
    waitlist,
)

settings = get_settings()

if settings.dev_auth_enabled and settings.app_env != "development":
    # Dev auth accepts `Bearer dev:<email>` with no proof of identity. It
    # must never be reachable outside a laptop/CI; refuse to boot instead.
    raise RuntimeError("DEV_AUTH_ENABLED is set outside APP_ENV=development. Refusing to start.")

if settings.demo_mode and (
    settings.payments_live_enabled
    or settings.plaid_env == "production"
    or (settings.stripe_secret_key or "").startswith(("sk_live_", "rk_live_"))
):
    # Demo mode has no sign-in: anyone can act as the demo family. That's
    # only acceptable while nothing can touch real accounts or real money.
    raise RuntimeError("DEMO_MODE can't run with live payments, live Stripe keys, or Plaid production.")

app = FastAPI(title="Warden API", version="0.3.0")

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
app.include_router(households.router)
app.include_router(banking.router)
app.include_router(demo.router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/integrations")
async def integrations():
    """Which real integrations are switched on in this deployment — the
    frontend shows setup hints instead of failing silently."""
    return {
        "model": bool(settings.anthropic_api_key),
        "model_id": settings.warden_model,
        "plaid": bool(settings.plaid_client_id and settings.plaid_secret),
        "plaid_env": settings.plaid_env,
        "stripe": bool(settings.stripe_secret_key),
        "stripe_mode": (
            "live" if (settings.stripe_secret_key or "").startswith(("sk_live_", "rk_live_")) else "test"
        )
        if settings.stripe_secret_key
        else None,
        "email": bool(settings.resend_api_key),
        "push": bool(settings.ntfy_topic),
        "dev_auth": settings.dev_auth_enabled and settings.app_env == "development",
        "demo_mode": settings.demo_mode,
    }


@app.get("/agents")
async def list_agents():
    return [
        {"id": a.id, "name": a.name, "role": a.role, "tools": a.tools}
        for a in AGENTS.values()
    ]
