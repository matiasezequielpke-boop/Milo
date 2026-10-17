# Warden (formerly Milo)

**Your agent handles the money. You approve what can't be undone.**

Warden helps families protect an older parent's money. It watches the parent's bank accounts for scams and odd charges, keeps bills and subscriptions in view, and can pay a bill or prepare a cancellation — but only after a family approver says yes. Milo is the conversational front end; Warden is the part that can move money, and never alone.

## Warden MVP — what's in this branch

| Piece | Where | State |
|---|---|---|
| Households: account owner (elder) + family approvers, invites, revocable consent | `apps/api/app/households.py`, `routers/households.py` | Built, tested |
| Bank data via Plaid (link, exchange, transactions sync, sandbox helpers) | `apps/api/app/plaid_service.py`, `routers/banking.py` | Built; tested against fakes. Needs `PLAID_*` keys for live calls |
| Scam / odd-charge detector + recurring-charge detection | `apps/api/app/detection.py`, `monitoring.py` | Built, tested (pure functions) |
| One gate for money: propose → human approval → executor | `apps/api/app/warden.py`, `executor.py`, `routers/approvals.py` | Built, tested |
| Payments via Stripe (test mode, idempotent, live keys refused by default) | `apps/api/app/executor.py` | Built; tested against a fake. Needs `STRIPE_SECRET_KEY=sk_test_…` |
| Live Milo/Warden agent on Claude (tool use, streaming, append-only history) | `apps/api/app/agent/` | Built; loop tested with a scripted model. Needs `ANTHROPIC_API_KEY` |
| Web console: chat, approvals, alerts, money, family/consent, activity | `apps/web` | Built; walked through in Chromium as both roles |
| Shared, append-only audit log | `audit_log`, `GET /households/{id}/audit` | Built, tested |

Nothing answers with scripted text and nothing fakes a provider: with a key missing, the feature says exactly which key is missing. Fakes exist only inside `apps/api/tests/`. How money moves, and what must change before real money: [`docs/money-plan.md`](docs/money-plan.md).

### Run it locally

```bash
docker compose up -d                       # postgres (pgvector) + redis
cd apps/api
cp ../../.env.example .env                 # Supabase keys for real accounts, or DEMO_MODE=true for the demo family
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
pytest                                     # uses the milo_test database

cd ../web && npm install && npm run dev    # NEXT_PUBLIC_API_URL defaults to http://localhost:8000 in dev only
```

**Accounts.** Sign up with email + password (18+, Terms and Privacy accepted) and you're in. Logging in takes the password and then a code Supabase emails you. The API runs both flows in front of Supabase and refuses any session that skipped a step. Setup steps, including the Supabase email template and SMTP: [`docs/auth-setup.md`](docs/auth-setup.md). With `DEMO_MODE=true` the login page also offers a ready-made demo family (Rosa, the account owner, and Ana, Rosa's approver); demo mode refuses to start with live payments, live Stripe keys or Plaid production. A production web build with no `NEXT_PUBLIC_API_URL` shows an honest "API not connected" state and never calls localhost.

**Privacy and compliance.** Privacy, Terms, Cookies, Refunds and Licenses pages; data export and account deletion in Settings; unsubscribe links in every notification email; and the rest of the checklist in [`docs/compliance.md`](docs/compliance.md). Third-party licenses: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

### The end-to-end demo (needs Plaid sandbox, Stripe test, and Anthropic keys)

1. Viewing as Rosa, Family shows what Ana may do; Rosa can change it with one switch per permission.
2. Money → "Use Plaid's test bank" connects a real Plaid sandbox Item and syncs it.
3. Money → "Simulate a charge" adds `GIFT CARD MALL #3 — $500` at Plaid's sandbox bank; the sync raises a high-severity alert (and emails Ana when email is configured).
4. Rosa asks Milo in chat: "please pay my ConEd bill, $88.20". Milo records it and Warden sends Ana an approval request.
5. Switch to Ana (sidebar, or "View as Ana" on the request) and approve; Stripe (test mode) settles the payment; the result appears in Rosa's chat and in the shared Activity log.

---

## Earlier status notes (Milo)

This repo is the **real backend and production frontend**, being built from scratch. The previous work — a fully interactive frontend prototype with a simulated (client-side, scripted) agent engine — lives outside this repo as a published prototype and is being ported here incrementally.

Before the Warden MVP, nothing here talked to a live model (that needed API budget — see Fase 0 below); the Warden agent above now does as soon as `ANTHROPIC_API_KEY` is set. What was already real and tested against a live Postgres+pgvector and Redis: auth, persistence, the SSE streaming contract, the HITL approval gate, the encrypted credential vault, and Celery/Redis wiring. See "What's actually real" below for the honest breakdown.

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
