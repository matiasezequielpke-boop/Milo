# Milo

High-autonomy AI agent — a JARVIS-style assistant that executes multi-step work across research, communication, files, and transactions, with human approval built into anything irreversible.

Milo starts as a general-purpose AI assistant and grows toward full autonomous capability across domains (including, but not limited to, the real-estate wholesaling workflow that originally motivated it). Users choose which model powers their agent — Claude, Gemini, GPT, or DeepSeek.

## Status

This repo is the **real backend and production frontend**, being built from scratch. The previous work — a fully interactive frontend prototype with a simulated (client-side, scripted) agent engine — lives outside this repo as a published prototype and is being ported here incrementally.

Nothing in this repo talks to a live model yet; that requires API budget (see Fase 0 below). What *is* real and tested against a live Postgres+pgvector and Redis: auth, persistence, the SSE streaming contract, the HITL approval gate, the encrypted credential vault, and Celery/Redis wiring. See "What's actually real" below for the honest breakdown.

## Architecture

Four horizontal layers, plus a security spine that crosses all four (never a fifth step):

- **L1 — Frontend** (`apps/web`): Next.js App Router, React, TypeScript, Tailwind. Landing shell scaffolded; the full interactive console (chat, sidebar, agent details, pricing/suggestions/waitlist) is still being ported from the prototype.
- **L2 — Gateway & orchestration** (`apps/api`): FastAPI, LiteLLM multi-model gateway, Celery/Redis for background work. A real LangGraph coordinator (routing a group chat across multiple agents by intent, the way the prototype's client-side engine did) hasn't been built yet — see "Known simplifications" below.
- **L3 — Runtime & tools**: web search (Tavily), RAG (pgvector + LiteLLM embeddings), E2B code sandbox, Anthropic Computer Use + Playwright, email/messages, ntfy push. Interfaces exist and are correctly gated on missing API keys; the underlying provider calls light up automatically once a key is set, except computer_use (see below).
- **L4 — Data & infra**: PostgreSQL + pgvector, Redis. Schema and migrations are real (12 tables, Alembic-managed).
- **L5 — Security & vault** (the spine): human-in-the-loop approval gate on every irreversible action, encrypted credential vault (Fernet today — see note below), append-only audit log.

Full technical blueprint: see the architecture doc in the Claude Project this repo was built alongside.

## What's actually real (read before assuming a feature works)

Real and tested against a live Supabase project (Postgres 17 + pgvector, schema + RLS applied) and Redis:
- Auth via Supabase (email OTP) — this backend verifies the resulting token against Supabase's `/auth/v1/user` and exposes `/auth/me`; it never sees a password or issues its own token. The code imports clean and the schema is live, but the *end-to-end* flow (a real browser getting a real OTP and reaching `/auth/me`) hasn't run yet — that needs the OTP email provider enabled in the Supabase dashboard first (a one-time, human step) and a deployed backend to point at. See `claude/ruta-a-produccion.md` for the full picture.
- Conversations + messages, persisted. `POST /conversations/{id}/messages` streams via SSE; with no model key configured it streams a clean `error` event, never a fake response.
- Waitlist and Suggestions board, persisted (previously client-only state in the prototype — this was the single highest-ROI fix in the backlog, since every real signup was being silently lost on page reload).
- HITL approval gate: `approval_requests` table + `/approvals` endpoints, enforcing each agent's `requires_approval_for` from `app/agents/definitions.py`.
- Encrypted credential vault: `/credentials` endpoints, Fernet encryption, plaintext never returned by any API response.
- Append-only audit log, written on every approval and vault event.
- Celery + Redis: a real worker consumes a real beat-scheduled heartbeat task through the broker.

Real interface, but inert until a key exists (raises a clear, typed error — never a fake result):
- The model gateway itself (LiteLLM `acompletion`/`aembedding` calls are real code, gated on `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / etc.).
- Scout's web_search (Tavily) and Ledger's code_sandbox (E2B) — real SDK calls, gated on their own keys.
- Scribe's RAG: the embedding step is gated (needs `OPENAI_API_KEY`); the retrieval half (pgvector cosine search) needs no key and is fully real today.

Not implemented yet, on purpose, in order:
- Scout's computer_use — the most fragile capability in the system, by design the last one built (Fase 4). The gating check is real; the actual Claude-computer-use + Playwright loop is not, and won't be stubbed with a fake browser result.
- Sentinel's actual per-monitor checkers (RSS diff, price watch, etc.) — `monitors` table and the Celery heartbeat are real; there's no real check logic behind any of it yet, since what "checking" means is different per monitor type.
- A real LangGraph coordinator. See below.

### Known simplifications

Which agent answers a message is currently simple, not smart: a 1:1 chat (`active_participants` has exactly one agent) always routes to that agent; anything else (free routing or a group chat) routes to Milo. The prototype's client-side intent router (`INTENTS`, picking a responder by keyword match across a group) hasn't been reimplemented server-side — that's real LangGraph coordinator work, not yet started. Whichever agent answers, the answer itself is either a real model completion or a clear "no model configured" error — never scripted content.

## Build order (one blast radius at a time)

1. **Fase 0** — model API budget (blocks live model calls; deferred until funding — see below)
2. **Fase 1 — V1 launchable**: FastAPI + LiteLLM gateway, SSE streaming, PostgreSQL, auth, the 8 agents with real prompts, ntfy push. *(done except the live model call itself, which needs Fase 0)*
3. **Fase 2** — web search + RAG *(interfaces built and gated; needs Fase 0-equivalent budget for Tavily/OpenAI)*
4. **Fase 3** — E2B sandbox, isolated *(interface built and gated; needs its own budget)*
5. **Fase 4** — Computer Use, only where no real API exists *(deliberately not started — see above)*
6. **Fase 5** — vault + structural HITL *(done — didn't need to wait on budget)*
7. **Fase 6** — background monitoring + dynamic subagents *(scaffolded: schema + Celery/Redis wiring real, per-monitor logic not started)*

Budget for Fase 0 is intentionally deferred until there's funding to cover it — nothing here should be "fixed" by quietly adding a real key. A CTO/technical cofounder hire is similarly deferred until acceptance into an accelerator (YC/a16z).

## Local development

```bash
cp .env.example .env    # fill in what you have; model + tool keys can stay empty for now
docker compose up -d    # postgres (with pgvector) + redis
cd apps/api
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Run the background worker (optional — only needed to exercise Fase 6's heartbeat):

```bash
celery -A app.celery_app worker --loglevel=info
celery -A app.celery_app beat --loglevel=info   # separate process, schedules the heartbeat
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

## Agent roster

| Agent | Role |
|---|---|
| Milo | Coordinator — orchestrates and delegates to the rest of the fleet |
| Scout | Research + browser / computer use |
| Herald | Email and messages — always gated by approval before sending |
| Ledger | Numbers, analysis, code sandbox |
| Scribe | Documents, RAG |
| Courier | Files |
| Warden | Approvals + encrypted credential vault + purchase gate |
| Sentinel | Background monitoring and alerts |

Users can also create custom agents; Milo can spin up ephemeral agents for a single job.
