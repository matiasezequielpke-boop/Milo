"""Central app configuration, loaded from environment variables.

Model API keys are intentionally allowed to be empty — see Fase 0 in the
README. The gateway checks at call time whether a given provider is
configured and returns a clear error instead of failing silently. The
same rule applies to every Warden integration below (Plaid, Stripe,
email): no key means a clear, typed error, never a fake result.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:3000"
    # Public URL of the web app — used to build invite links in emails.
    web_app_url: str = "http://localhost:3000"

    database_url: str = "postgresql://milo:milo@localhost:5432/milo"
    redis_url: str = "redis://localhost:6379/0"

    # Identity now lives in Supabase Auth, not this app — see
    # app/supabase_auth.py. supabase_url + supabase_anon_key are enough to
    # verify a user's access token; nothing here can mint one.
    supabase_url: str | None = None
    supabase_anon_key: str | None = None

    # Local-only escape hatch so the full flow can be exercised without a
    # reachable Supabase project: accepts `Authorization: Bearer dev:<email>`.
    # Refused at startup unless app_env == "development" (see app/main.py).
    dev_auth_enabled: bool = False

    # Demo mode: the app runs without sign-in. Requests act as one of two
    # fixed demo people (`Authorization: Bearer demo:<email>`) — the account
    # owner and her family approver — so the whole family flow can be shown
    # from one browser. Never combined with anything that can move real
    # money: app/main.py refuses to start if it is.
    demo_mode: bool = False
    demo_owner_email: str = "rosa@demo.warden.app"
    demo_approver_email: str = "ana@demo.warden.app"

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    deepseek_api_key: str | None = None

    # --- Warden agent (app/agent/) ---
    warden_model: str = "claude-opus-5-5"
    # Explicit so the SDK never picks up an unrelated ANTHROPIC_BASE_URL
    # from the environment (dev containers often set one for tooling).
    warden_api_base_url: str = "https://api.anthropic.com"
    warden_effort: str = "medium"
    warden_max_tool_rounds: int = 8

    # --- Plaid (read-only bank data) ---
    plaid_client_id: str | None = None
    plaid_secret: str | None = None
    plaid_env: str = "sandbox"  # "sandbox" | "production"
    plaid_webhook_url: str | None = None

    # --- Stripe (settles approved payments) ---
    stripe_secret_key: str | None = None
    # Test-mode payment method used as the paying instrument until the
    # elder's own bank account is linked as a Stripe payment method
    # (Plaid processor token -> ACH). Only honored with an sk_test_ key.
    stripe_test_payment_method: str = "pm_card_visa"
    # Hard stop on real money movement: a live key is refused unless this
    # is explicitly turned on after legal review (see docs/money-plan).
    payments_live_enabled: bool = False

    # --- Email (approval requests, invites) ---
    resend_api_key: str | None = None
    email_from: str = "Warden <warden@example.com>"

    # Fase 2/3 tool providers — same "empty until funded" rule as the model
    # keys above. tavily for Scout's web_search, e2b for Ledger's sandbox.
    tavily_api_key: str | None = None
    e2b_api_key: str | None = None

    # Fase 5 — vault. Production should set this explicitly (a real
    # Fernet.generate_key() value); dev derives one from app_secret_key
    # if unset. See app/vault.py.
    vault_encryption_key: str | None = None

    ntfy_topic: str | None = None

    @property
    def demo_people(self) -> dict[str, tuple[str, str]]:
        """email -> (display name, role) for the demo identities."""
        return {
            self.demo_owner_email.lower(): ("Rosa", "elder"),
            self.demo_approver_email.lower(): ("Ana", "approver"),
        }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
