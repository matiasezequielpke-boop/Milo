"""Plaid: read-only bank data for Warden.

Plaid only ever *reads* (accounts, balances, transactions). Warden never
uses Plaid to move money in the MVP — payments go through Stripe after a
human approval (app/executor.py).

Every call is a real Plaid API call, gated on PLAID_CLIENT_ID /
PLAID_SECRET. With no keys, `PlaidNotConfiguredError` is raised before any
network call — never fake data. PLAID_ENV=sandbox points at Plaid's own
test institutions ("First Platypus Bank"), which return real API
responses with test data; the sandbox-only helpers at the bottom
(`sandbox_public_token`, `sandbox_add_transactions`) are Plaid endpoints
too, and refuse to run against production.

The plaid-python SDK is synchronous, so calls run in a worker thread.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.custom_sandbox_transaction import CustomSandboxTransaction
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_transactions import LinkTokenTransactions
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.sandbox_public_token_create_request_options import SandboxPublicTokenCreateRequestOptions
from plaid.model.sandbox_transactions_create_request import SandboxTransactionsCreateRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, vault
from app.config import get_settings
from app.models import BankAccount, BankConnection, BankTransaction, Credential, HouseholdMember, User

# Plaid's sandbox institution and the test user whose transactions can be
# added on demand with /sandbox/transactions/create.
SANDBOX_INSTITUTION_ID = "ins_109508"
SANDBOX_DYNAMIC_USER = "user_transactions_dynamic"


class PlaidNotConfiguredError(RuntimeError):
    """PLAID_CLIENT_ID / PLAID_SECRET not set."""


class PlaidSandboxOnlyError(RuntimeError):
    """A sandbox helper was called with PLAID_ENV != sandbox."""


class PlaidApiError(RuntimeError):
    """Plaid rejected a call. `code` is Plaid's error_code when present."""

    def __init__(self, message: str, code: str | None = None):
        self.code = code
        super().__init__(message)


def _client() -> plaid_api.PlaidApi:
    settings = get_settings()
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise PlaidNotConfiguredError(
            "PLAID_CLIENT_ID / PLAID_SECRET are not set — bank connections can't work until they are "
            "(free sandbox keys: dashboard.plaid.com)."
        )
    host = plaid.Environment.Production if settings.plaid_env == "production" else plaid.Environment.Sandbox
    configuration = plaid.Configuration(
        host=host,
        api_key={"clientId": settings.plaid_client_id, "secret": settings.plaid_secret},
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def _require_sandbox() -> None:
    if get_settings().plaid_env != "sandbox":
        raise PlaidSandboxOnlyError("This helper only runs against Plaid's sandbox.")


async def _call(fn, request):
    try:
        response = await asyncio.to_thread(fn, request)
    except plaid.ApiException as exc:
        code = None
        message = str(exc)
        try:
            body = json.loads(exc.body or "{}")
            code = body.get("error_code")
            message = body.get("display_message") or body.get("error_message") or message
        except (TypeError, ValueError):
            pass
        raise PlaidApiError(f"Plaid: {message}", code=code) from exc
    return response.to_dict()


async def create_link_token(*, client_user_id: str) -> dict:
    client = _client()
    settings = get_settings()
    kwargs = {}
    if settings.plaid_webhook_url:
        kwargs["webhook"] = settings.plaid_webhook_url
    request = LinkTokenCreateRequest(
        client_name="Warden",
        language="en",
        country_codes=[CountryCode("US")],
        user=LinkTokenCreateRequestUser(client_user_id=client_user_id),
        products=[Products("transactions")],
        # Two years of history: enough to tell a new subscription from an
        # old one and to know what "normal" looks like for this person.
        transactions=LinkTokenTransactions(days_requested=730),
        **kwargs,
    )
    return await _call(client.link_token_create, request)


async def exchange_public_token(public_token: str) -> tuple[str, str]:
    client = _client()
    data = await _call(client.item_public_token_exchange, ItemPublicTokenExchangeRequest(public_token=public_token))
    return data["access_token"], data["item_id"]


async def sandbox_public_token() -> str:
    """Creates a sandbox Item without the Link UI (Plaid's documented way
    to test server-side flows)."""
    _require_sandbox()
    client = _client()
    request = SandboxPublicTokenCreateRequest(
        institution_id=SANDBOX_INSTITUTION_ID,
        initial_products=[Products("transactions")],
        options=SandboxPublicTokenCreateRequestOptions(
            override_username=SANDBOX_DYNAMIC_USER, override_password="pass_good"
        ),
    )
    data = await _call(client.sandbox_public_token_create, request)
    return data["public_token"]


async def sandbox_add_transactions(access_token: str, transactions: list[dict]) -> None:
    """Adds transactions to a sandbox Item (dynamic test user only).
    Each dict: description, amount (positive = money out), date."""
    _require_sandbox()
    client = _client()
    request = SandboxTransactionsCreateRequest(
        access_token=access_token,
        transactions=[
            CustomSandboxTransaction(
                date_transacted=t["date"],
                date_posted=t["date"],
                amount=float(t["amount"]),
                description=t["description"],
                iso_currency_code="USD",
            )
            for t in transactions
        ],
    )
    await _call(client.sandbox_transactions_create, request)


@dataclass
class SyncPage:
    accounts: list[dict]
    added: list[dict]
    modified: list[dict]
    removed: list[str]
    cursor: str


async def fetch_changes(access_token: str, cursor: str | None) -> SyncPage:
    client = _client()
    accounts = (await _call(client.accounts_get, AccountsGetRequest(access_token=access_token)))["accounts"]
    added: list[dict] = []
    modified: list[dict] = []
    removed: list[str] = []
    next_cursor = cursor or ""
    while True:
        kwargs = {"cursor": next_cursor} if next_cursor else {}
        page = await _call(
            client.transactions_sync, TransactionsSyncRequest(access_token=access_token, count=500, **kwargs)
        )
        added.extend(page.get("added", []))
        modified.extend(page.get("modified", []))
        removed.extend(r["transaction_id"] for r in page.get("removed", []))
        next_cursor = page["next_cursor"]
        if not page.get("has_more"):
            break
    return SyncPage(accounts=accounts, added=added, modified=modified, removed=removed, cursor=next_cursor)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _decimal(value) -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(Decimal("0.01"))


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _category(t: dict) -> str | None:
    pfc = t.get("personal_finance_category") or {}
    if pfc.get("primary"):
        return str(pfc["primary"])
    legacy = t.get("category") or []
    return legacy[0] if legacy else None


async def connect_item(
    db: AsyncSession,
    *,
    household_id: uuid.UUID,
    owner: HouseholdMember,
    linked_by: User,
    public_token: str,
    institution_name: str | None,
) -> BankConnection:
    access_token, item_id = await exchange_public_token(public_token)
    credential = Credential(
        user_id=linked_by.id,
        name=f"plaid:{item_id}",
        encrypted_value=vault.encrypt(access_token),
    )
    db.add(credential)
    await db.flush()
    connection = BankConnection(
        household_id=household_id,
        owner_member_id=owner.id,
        provider="plaid",
        provider_item_id=item_id,
        credential_id=credential.id,
        institution_name=institution_name,
        status="active",
    )
    db.add(connection)
    await db.flush()
    await audit.record(
        db,
        event_type="bank.connected",
        user_id=linked_by.id,
        household_id=household_id,
        detail={"institution": institution_name, "owner": owner.display_name},
    )
    return connection


async def remove_item(access_token: str) -> None:
    """Ends Warden's access to that bank login at Plaid (/item/remove), so
    the access token stops working everywhere — used when an account owner
    deletes their account."""
    await _call(_client().item_remove, ItemRemoveRequest(access_token=access_token))


async def access_token_for(db: AsyncSession, connection: BankConnection) -> str:
    credential = await db.get(Credential, connection.credential_id)
    if credential is None:
        raise PlaidApiError("Bank connection has no stored credential; reconnect it.")
    credential.last_used_at = datetime.now(timezone.utc)
    return vault.decrypt(credential.encrypted_value)


@dataclass
class ConnectionSync:
    accounts: int
    added: int
    modified: int
    removed: int


async def sync_connection(db: AsyncSession, connection: BankConnection) -> ConnectionSync:
    access_token = await access_token_for(db, connection)
    page = await fetch_changes(access_token, connection.sync_cursor)

    account_ids: dict[str, uuid.UUID] = {}
    for a in page.accounts:
        balances = a.get("balances") or {}
        stmt = pg_insert(BankAccount).values(
            id=uuid.uuid4(),
            household_id=connection.household_id,
            connection_id=connection.id,
            provider_account_id=a["account_id"],
            name=a.get("official_name") or a.get("name") or "Account",
            mask=a.get("mask"),
            type=str(a.get("type")) if a.get("type") is not None else None,
            subtype=str(a.get("subtype")) if a.get("subtype") is not None else None,
            current_balance=_decimal(balances.get("current")),
            available_balance=_decimal(balances.get("available")),
            currency=balances.get("iso_currency_code") or "USD",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[BankAccount.provider_account_id],
            set_={
                "name": stmt.excluded.name,
                "mask": stmt.excluded.mask,
                "current_balance": stmt.excluded.current_balance,
                "available_balance": stmt.excluded.available_balance,
                "updated_at": datetime.now(timezone.utc),
            },
        ).returning(BankAccount.id)
        account_ids[a["account_id"]] = (await db.execute(stmt)).scalar_one()

    for t in page.added + page.modified:
        account_id = account_ids.get(t["account_id"])
        if account_id is None:
            continue
        values = {
            "amount": _decimal(t["amount"]),
            "currency": t.get("iso_currency_code") or "USD",
            "date": _as_date(t.get("authorized_date") or t["date"]),
            "name": (t.get("name") or t.get("original_description") or "Transaction")[:300],
            "merchant_name": (t.get("merchant_name") or None),
            "category": _category(t),
            "payment_channel": str(t.get("payment_channel")) if t.get("payment_channel") else None,
            "pending": bool(t.get("pending")),
            "removed": False,
        }
        stmt = pg_insert(BankTransaction).values(
            id=uuid.uuid4(),
            household_id=connection.household_id,
            account_id=account_id,
            provider_transaction_id=t["transaction_id"],
            **values,
        )
        await db.execute(
            stmt.on_conflict_do_update(index_elements=[BankTransaction.provider_transaction_id], set_=values)
        )

    if page.removed:
        result = await db.execute(
            select(BankTransaction).where(BankTransaction.provider_transaction_id.in_(page.removed))
        )
        for row in result.scalars():
            row.removed = True

    connection.sync_cursor = page.cursor
    connection.last_synced_at = datetime.now(timezone.utc)
    return ConnectionSync(
        accounts=len(page.accounts), added=len(page.added), modified=len(page.modified), removed=len(page.removed)
    )
