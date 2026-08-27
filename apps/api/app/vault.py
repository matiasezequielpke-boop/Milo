"""Encrypted credential vault — the L5 vault half of Fase 5.

Symmetric encryption (Fernet) rather than HashiCorp Vault / AWS KMS for
now: those are correct for the architecture blueprint's long-term
picture, but they're infrastructure a one-founder team without a CTO
yet shouldn't be standing up and operating solo (see build-backlog.md,
bloqueante #3). This module keeps the *interface* — encrypt/decrypt by
name, never expose plaintext outside this module — identical to what a
Vault-backed implementation would need, so swapping the backend later
is a implementation-only change, not an API change.

Plaintext secrets are never logged, never written to the audit log
(only the *fact* that a credential was used is), and never returned by
any API response — only Warden, gated by an approved ApprovalRequest,
calls `decrypt()`.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class VaultError(RuntimeError):
    """Raised on encrypt/decrypt failure — e.g. ciphertext doesn't match the key."""


def _derive_dev_key(app_secret_key: str) -> bytes:
    """Deterministic fallback so local dev works with zero extra setup.

    Production MUST set VAULT_ENCRYPTION_KEY explicitly (a real
    `Fernet.generate_key()` value) — deriving it from app_secret_key means
    rotating one silently rotates the other, which is fine for a laptop
    and wrong for anything with real credentials in it.
    """
    digest = hashlib.sha256(app_secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.vault_encryption_key or _derive_dev_key(settings.app_secret_key)
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise VaultError("Could not decrypt credential — wrong key or corrupted value.") from exc
