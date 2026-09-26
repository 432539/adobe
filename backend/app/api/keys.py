"""User API-key management. Plaintext is returned once, on creation."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import SessionDep, SettingsDep, UserDep
from app.core.errors import AppError
from app.models import ApiKey
from app.schemas.panel import ApiKeyOut, CreateKeyRequest, key_of
from app.services import users as users_service

router = APIRouter(prefix="/api/keys", tags=["keys"])

MAX_KEYS_PER_USER = 20


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(user: UserDep, session: SessionDep) -> list[ApiKeyOut]:
    rows = await session.scalars(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return [key_of(k) for k in rows]


@router.post("", response_model=ApiKeyOut, status_code=201)
async def create_key(
    payload: CreateKeyRequest, user: UserDep, session: SessionDep, settings: SettingsDep
) -> ApiKeyOut:
    active = await session.scalar(
        select(func.count())
        .select_from(ApiKey)
        .where(ApiKey.user_id == user.id, ApiKey.status == "active")
    )
    if int(active or 0) >= MAX_KEYS_PER_USER:
        raise AppError(
            code="too_many_keys", message=f"最多 {MAX_KEYS_PER_USER} 把有效 KEY", http_status=422
        )
    key, plain = await users_service.create_api_key(
        session,
        user_id=user.id,
        name=payload.name,
        pepper=settings.app_secret_key,
        rate_limit=payload.rate_limit,
    )
    return key_of(key, plain)


@router.delete("/{key_id}", response_model=ApiKeyOut)
async def revoke_key(key_id: int, user: UserDep, session: SessionDep) -> ApiKeyOut:
    return key_of(await users_service.revoke_api_key(session, user_id=user.id, key_id=key_id))
