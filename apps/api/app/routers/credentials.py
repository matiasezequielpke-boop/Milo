"""Vault-backed credential storage. Plaintext is encrypted on the way in
(app/vault.py) and never returned on the way out — see CredentialResponse.
Retrieving a credential for actual use by Warden is a separate,
approval-gated code path, not a GET endpoint; this router only manages
existence (create/list/delete), never reveals the secret.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, vault
from app.db import get_db
from app.deps import get_current_user
from app.models import Credential, User
from app.schemas import CredentialCreateRequest, CredentialResponse

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Credential]:
    result = await db.execute(select(Credential).where(Credential.user_id == current_user.id))
    return list(result.scalars().all())


@router.post("", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credential(
    body: CredentialCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Credential:
    credential = Credential(
        user_id=current_user.id,
        name=body.name,
        encrypted_value=vault.encrypt(body.value),
    )
    db.add(credential)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"A credential named {body.name!r} already exists."
        ) from exc
    await db.refresh(credential)
    await audit.record(db, event_type="vault.credential_created", user_id=current_user.id, detail={"name": body.name})
    await db.commit()
    return credential


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_credential(
    credential_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    result = await db.execute(
        select(Credential).where(Credential.id == credential_id, Credential.user_id == current_user.id)
    )
    credential = result.scalar_one_or_none()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    await db.delete(credential)
    await audit.record(
        db, event_type="vault.credential_deleted", user_id=current_user.id, detail={"name": credential.name}
    )
    await db.commit()
