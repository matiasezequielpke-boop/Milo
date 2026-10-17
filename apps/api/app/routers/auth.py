"""Sign-up and two-step login, in front of Supabase Auth.

    sign up   email + password (+ terms, 18+)  ->  in
    log in    email + password  ->  Supabase emails a code  ->  code  ->  in

Supabase checks the password and sends the code; this router decides when
a session counts. Only sessions created here are recorded in
`auth_sessions`, and app/deps.py rejects any Supabase token whose session
isn't recorded — so skipping a step (a password-only session straight from
Supabase, or an emailed link on its own) gets nowhere.

Failure messages never say whether an email has an account (except at
sign-up, where "already registered" is unavoidable).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, supabase_auth
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import AuthSession, LoginChallenge, User
from app.schemas import (
    EmailOnlyRequest,
    LoginRequest,
    LoginStartResponse,
    LoginVerifyRequest,
    RefreshRequest,
    SessionResponse,
    SignupRequest,
    UserResponse,
)
from app.supabase_auth import SupabaseAuthError, SupabaseAuthNotConfiguredError

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

BAD_LOGIN = "That email and password don't match an account."
TIMED_OUT = "Your sign-in timed out. Enter your email and password again."
BAD_CODE = "That code isn't right, or it has expired."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _not_configured() -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sign-in isn't set up on this server yet.")


def _upstream(exc: SupabaseAuthError, fallback: str) -> HTTPException:
    if exc.status == 429:
        return HTTPException(status_code=429, detail="Too many attempts. Wait a minute and try again.")
    logger.warning("supabase auth error %s: %s", exc.status, exc)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=fallback)


async def _ensure_user(db: AsyncSession, user_id: uuid.UUID, email: str) -> User:
    """public.users mirrors auth.users (a Supabase trigger may already have
    made the row); make sure it exists either way."""
    user = await db.get(User, user_id)
    if user is not None:
        return user
    clash = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if clash is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is linked to a different account. Contact support.")
    user = User(id=user_id, email=email, display_name=email.split("@")[0])
    db.add(user)
    await db.flush()
    return user


async def _start_session(db: AsyncSession, session: dict, method: str, email: str) -> tuple[User, SessionResponse]:
    claims = supabase_auth.token_claims(session["access_token"])
    user = await _ensure_user(db, uuid.UUID(claims["sub"]), email)
    db.add(AuthSession(id=uuid.UUID(claims["session_id"]), user_id=user.id, method=method))
    expires_at = int(session.get("expires_at") or (_now().timestamp() + int(session.get("expires_in", 3600))))
    return user, SessionResponse(
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        expires_at=expires_at,
        user=UserResponse.model_validate(user, from_attributes=True),
    )


@router.post("/signup", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)) -> SessionResponse:
    if not body.accept_terms:
        raise HTTPException(status_code=422, detail="Please agree to the Terms and the Privacy Policy to create an account.")
    if not body.confirm_age:
        raise HTTPException(status_code=422, detail="Warden is only for people 18 or older.")
    email = body.email.strip().lower()
    if body.password.strip().lower() == email:
        raise HTTPException(status_code=422, detail="Choose a password that isn't your email address.")
    settings = get_settings()

    try:
        if settings.supabase_service_role_key:
            await supabase_auth.create_confirmed_user(email, body.password)
            session = await supabase_auth.password_grant(email, body.password)
        else:
            session = await supabase_auth.sign_up(email, body.password)
    except SupabaseAuthNotConfiguredError as exc:
        raise _not_configured() from exc
    except SupabaseAuthError as exc:
        text = str(exc).lower()
        if exc.status in (400, 409, 422) and ("already" in text or "registered" in text or "exists" in text):
            raise HTTPException(status_code=409, detail="There's already an account with this email. Log in instead.") from exc
        if exc.status in (400, 422) and "password" in text:
            raise HTTPException(status_code=422, detail=f"Supabase rejected that password: {exc}") from exc
        raise _upstream(exc, "Couldn't create the account right now. Try again in a minute.") from exc
    if not session.get("access_token"):
        # Public sign-up with "Confirm email" on: no session until the
        # person clicks the confirmation email. Configure the service role
        # key (or turn confirmation off) for the "in straight away" flow.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account created, but this server needs SUPABASE_SERVICE_ROLE_KEY to sign you in straight away.",
        )

    user, response = await _start_session(db, session, "signup", email)
    now = _now()
    user.terms_version = settings.legal_version
    user.terms_accepted_at = now
    user.age_confirmed_at = now
    await audit.record(db, event_type="account.created", user_id=user.id, detail={"terms_version": settings.legal_version})
    await db.commit()
    response.user = UserResponse.model_validate(user, from_attributes=True)
    return response


@router.post("/login", response_model=LoginStartResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginStartResponse:
    """Step 1: check the password, then have Supabase email a code. The
    session the password check produces is signed out at once — the
    browser never gets it."""
    settings = get_settings()
    email = body.email.strip().lower()
    window = _now() - timedelta(minutes=15)
    failures = await db.scalar(
        select(func.count()).select_from(LoginChallenge).where(
            LoginChallenge.email == email, LoginChallenge.password_ok.is_(False), LoginChallenge.created_at > window
        )
    )
    if (failures or 0) >= settings.login_max_failures:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes.")

    # Sign-in attempt records only exist for rate limiting and the code
    # window; nothing needs them after 30 days.
    await db.execute(delete(LoginChallenge).where(LoginChallenge.created_at < _now() - timedelta(days=30)))
    expires = _now() + timedelta(minutes=settings.login_challenge_minutes)
    try:
        session = await supabase_auth.password_grant(email, body.password)
    except SupabaseAuthNotConfiguredError as exc:
        raise _not_configured() from exc
    except SupabaseAuthError as exc:
        if exc.status in (400, 401):
            db.add(LoginChallenge(email=email, password_ok=False, codes_sent=0, code_attempts=0, expires_at=_now()))
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=BAD_LOGIN) from exc
        raise _upstream(exc, "Couldn't check your password right now. Try again in a minute.") from exc

    try:
        await supabase_auth.sign_out(session["access_token"])
    except (SupabaseAuthError, KeyError):
        # Not fatal: that session was never recorded, so this API rejects it anyway.
        logger.warning("could not sign out the password-check session")

    # Any earlier unfinished login for this email is superseded.
    pending = await db.execute(
        select(LoginChallenge).where(LoginChallenge.email == email, LoginChallenge.consumed_at.is_(None), LoginChallenge.password_ok.is_(True))
    )
    for old in pending.scalars():
        old.consumed_at = _now()
    db.add(LoginChallenge(email=email, password_ok=True, codes_sent=1, code_attempts=0, expires_at=expires))
    await db.commit()

    try:
        await supabase_auth.send_email_code(email)
    except SupabaseAuthError as exc:
        raise _upstream(exc, "Couldn't send the code right now. Try again in a minute.") from exc
    return LoginStartResponse(expires_in_seconds=settings.login_challenge_minutes * 60)


async def _open_challenge(db: AsyncSession, email: str) -> LoginChallenge:
    challenge = (
        await db.execute(
            select(LoginChallenge)
            .where(
                LoginChallenge.email == email,
                LoginChallenge.password_ok.is_(True),
                LoginChallenge.consumed_at.is_(None),
                LoginChallenge.expires_at > _now(),
            )
            .order_by(LoginChallenge.created_at.desc())
            .with_for_update()
        )
    ).scalars().first()
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=TIMED_OUT)
    return challenge


@router.post("/login/resend", response_model=LoginStartResponse)
async def resend_code(body: EmailOnlyRequest, db: AsyncSession = Depends(get_db)) -> LoginStartResponse:
    """Another code — only inside a password-checked window, and only a
    few times per window."""
    settings = get_settings()
    email = body.email.strip().lower()
    challenge = await _open_challenge(db, email)
    if challenge.codes_sent >= settings.login_max_codes:
        raise HTTPException(status_code=429, detail="That's the most codes we can send for now. Start again in a few minutes.")
    challenge.codes_sent += 1
    await db.commit()
    try:
        await supabase_auth.send_email_code(email)
    except SupabaseAuthNotConfiguredError as exc:
        raise _not_configured() from exc
    except SupabaseAuthError as exc:
        raise _upstream(exc, "Couldn't send the code right now. Try again in a minute.") from exc
    remaining = int((challenge.expires_at - _now()).total_seconds())
    return LoginStartResponse(expires_in_seconds=max(remaining, 0))


@router.post("/login/verify", response_model=SessionResponse)
async def verify_code(body: LoginVerifyRequest, db: AsyncSession = Depends(get_db)) -> SessionResponse:
    """Step 2: the emailed code. Only now does the browser get a session."""
    email = body.email.strip().lower()
    challenge = await _open_challenge(db, email)
    if challenge.code_attempts >= 5:
        challenge.consumed_at = _now()
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=TIMED_OUT)
    try:
        session = await supabase_auth.verify_email_code(email, body.code)
    except SupabaseAuthNotConfiguredError as exc:
        raise _not_configured() from exc
    except SupabaseAuthError as exc:
        if exc.status in (400, 401, 403, 422):
            challenge.code_attempts += 1
            await db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=BAD_CODE) from exc
        raise _upstream(exc, "Couldn't check the code right now. Try again in a minute.") from exc

    challenge.consumed_at = _now()
    user, response = await _start_session(db, session, "login", email)
    await audit.record(db, event_type="auth.login", user_id=user.id, detail={})
    await db.commit()
    return response


@router.post("/refresh", response_model=SessionResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> SessionResponse:
    try:
        session = await supabase_auth.refresh_session(body.refresh_token)
    except SupabaseAuthNotConfiguredError as exc:
        raise _not_configured() from exc
    except SupabaseAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in again.") from exc
    claims = supabase_auth.token_claims(session["access_token"])
    recorded = await db.get(AuthSession, uuid.UUID(claims["session_id"]))
    if recorded is None or recorded.revoked_at is not None or str(recorded.user_id) != claims["sub"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in again.")
    user = await db.get(User, recorded.user_id)
    return SessionResponse(
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        expires_at=int(session.get("expires_at") or (_now().timestamp() + int(session.get("expires_in", 3600)))),
        user=UserResponse.model_validate(user, from_attributes=True),
    )


_bearer = HTTPBearer(auto_error=False)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    token = credentials.credentials if credentials else ""
    if token.startswith(("dev:", "demo:")):
        return
    claims = supabase_auth.token_claims(token)
    recorded = await db.get(AuthSession, uuid.UUID(claims["session_id"]))
    if recorded is not None and recorded.revoked_at is None:
        recorded.revoked_at = _now()
        await db.commit()
    try:
        await supabase_auth.sign_out(token)
    except SupabaseAuthError:
        logger.warning("supabase sign-out failed; the session is revoked here regardless")


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
