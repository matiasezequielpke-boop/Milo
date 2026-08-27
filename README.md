# Milo

High-autonomy AI agent — a JARVIS-style assistant that executes multi-step work across research, communication, files, and transactions, with human approval built into anything irreversible.

Milo starts as a general-purpose AI assistant and grows toward full autonomous capability across domains (including, but not limited to, the real-estate wholesaling workflow that originally motivated it). Users choose which model powers their agent — Claude, Gemini, GPT, or DeepSeek.

## Status

This repo is the **real backend and production frontend**, being built from scratch. The previous work — a fully interactive frontend prototype with a simulated (client-side, scripted) agent engine — lives outside this repo as a published prototype and is being ported here incrementally. Nothing in this repo talks to a live model yet; that requires API budget (see Roadmap).

## Architecture

Four horizontal layers, plus a security spine that crosses all four (never a fifth step):

- **L1 — Frontend** (`apps/web`): Next.js App Router, React, TypeScript, Zustand, SSE streaming. *(not yet scaffolded — coming next)*
- **L2 — Gateway & orchestration** (`apps/api`): FastAPI, LiteLLM multi-model gateway, LangGraph coordinator, Celery/Redis for long-running work.
- **L3 — Runtime & tools**: web search, RAG, E2B code sandbox, Anthropic Computer Use + Playwright, email/messages, ntfy push. *(not yet scaffolded)*
- **L4 — Data & infra**: PostgreSQL, pgvector, object storage (R2/S3), Redis.
- **L5 — Security & Vault** (the spine): human-in-the-loop approval gate on every irreversible action, encrypted credential vault (HashiCorp Vault / AWS KMS), append-only audit log, sandbox network isolation.

Full technical blueprint: see `docs/architecture.md`.

## Build order (one blast radius at a time)

1. **Fase 0** — model API budget (blocks everything below)
2. **Fase 1 — V1 launchable**: FastAPI + LiteLLM gateway, SSE streaming, PostgreSQL, auth, the 8 agents with real prompts, ntfy push *(this commit starts here)*
3. **Fase 2** — web search + RAG
4. **Fase 3** — E2B sandbox (isolated)
5. **Fase 4** — Computer Use (only where no real API exists)
6. **Fase 5** — vault + structural HITL
7. **Fase 6** — background monitoring + dynamic subagents

## Local development

```bash
cp .env.example .env   # fill in what you have; model keys can stay empty for now
docker compose up -d   # postgres + redis
cd apps/api && pip install -r requirements.txt && uvicorn app.main:app --reload
```

Frontend setup will be added once `apps/web` is scaffolded.

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
