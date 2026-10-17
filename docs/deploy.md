# Deployment

| Piece | Where | Deploys |
|---|---|---|
| Web (`apps/web`) | Vercel project `milo` → https://milo-lilac.vercel.app | Every push to `main` |
| API (`apps/api`) | Vercel project `warden-api` (FastAPI) | Every push to `main` |
| Database + sign-in | Supabase project `warden` (ref `qtlnrxfbdtckruwtekhb`, us-east-1) | Migrations: see below |

Both Vercel projects build from `matiasezequielpke-boop/Milo` with root directories `apps/web` and `apps/api`.

## API on Vercel

- Entrypoint: `app/main.py` (detected by Vercel's FastAPI preset). Dependencies: `requirements.txt` only; `requirements-extras.txt` (LiteLLM, Celery, Redis, Tavily, E2B) stays out of the function.
- Database: Supabase's transaction pooler. `app/db.py` turns off prepared statements for it and uses a connection per request on Vercel.
- Scheduled custom agents: Vercel Cron calls `GET /internal/cron/agents` daily at 13:05 UTC (`apps/api/vercel.json`), authorized with `CRON_SECRET`. On the Hobby plan a cron runs once a day, which covers the Monday and 1st-of-the-month runs. Runs stop starting new agents after ~200 seconds; the rest stay due for the next day.
- Deployment protection: Vercel Authentication covers preview URLs only, so the production URL is reachable by the web app and the cron.

### Environment variables (`warden-api`)

| Variable | Set by | Notes |
|---|---|---|
| `APP_ENV=production`, `WEB_APP_URL`, `CORS_ORIGINS`, `PUBLIC_API_URL` | deploy | Plain values |
| `WARDEN_SUPABASE_URL`, `WARDEN_SUPABASE_ANON_KEY` | deploy | Project URL and publishable key (public by design). Named so they don't collide with the integration's `SUPABASE_*` |
| `APP_SECRET_KEY`, `VAULT_ENCRYPTION_KEY`, `CRON_SECRET` | deploy (generated) | Sensitive. Rotating `VAULT_ENCRYPTION_KEY` makes stored bank links unreadable; reconnect banks after |
| `DATABASE_URL` (or `POSTGRES_URL`) | **owner** | Supabase → Connect → Transaction pooler, with the database password |
| `SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_SECRET_KEY`) | **owner** | Supabase → Project Settings → API keys. Server only |
| `ANTHROPIC_API_KEY` | **owner** | The agent's model |
| `PLAID_CLIENT_ID`, `PLAID_SECRET` | **owner** | Sandbox keys; `PLAID_ENV=sandbox` is the default |
| `STRIPE_SECRET_KEY` | **owner** | `sk_test_…` only. Live keys are refused unless `PAYMENTS_LIVE_ENABLED` is set after legal review |
| `RESEND_API_KEY`, `EMAIL_FROM` | owner, optional | Approval and alert emails |

Connecting Supabase's Vercel integration to `warden-api` (Vercel → Storage) provides `POSTGRES_URL` and `SUPABASE_SERVICE_ROLE_KEY` without copying them by hand. A change to environment variables applies from the next deployment.

### Migrations

The schema in Supabase was applied from `alembic upgrade head --sql` (Supabase migration `warden_schema_f4d1a9c3e822`), so `alembic_version` is current. For a new migration, either run `alembic upgrade head` with `DATABASE_URL` pointing at the pooler from a machine that can reach Supabase, or apply the output of `alembic upgrade <current>:head --sql` in the Supabase SQL editor. Every new table needs row level security (`tests/test_schema.py` fails otherwise).

## Web on Vercel

`NEXT_PUBLIC_API_URL` on the `milo` project points at the API's production URL. It's read at build time, so the web is redeployed after it changes.
