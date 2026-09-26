"""User & API-key management."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import (
    api_key_prefix,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.models import ApiKey, User

logger = logging.getLogger(__name__)

DEFAULT_KEY_NAME = "default"


@dataclass(frozen=True, slots=True)
class CreatedUser:
    user: User
    initial_key: ApiKey
    initial_key_plain: str  # returned exactly once


async def create_api_key(
    session: AsyncSession, *, user_id: int, name: str, pepper: str, rate_limit: int | None = None
) -> tuple[ApiKey, str]:
    plain = generate_api_key()
    key = ApiKey(
        user_id=user_id,
        name=name.strip() or "key",
        key_prefix=api_key_prefix(plain),
        key_hash=hash_api_key(plain, pepper),
        rate_limit=rate_limit,
    )
    session.add(key)
    await session.flush()
    return key, plain


async def create_user(
    session: AsyncSession,
    *,
    username: str,
    email: str,
    password: str,
    pepper: str,
    role: str = "user",
    initial_balance: int = 0,
) -> CreatedUser:
    """Create a user and its default API key in one transaction (key plaintext returned once)."""
    if role not in ("user", "admin"):
        raise AppError(code="invalid_role", message="角色无效", http_status=422)
    if initial_balance < 0:
        raise AppError(code="invalid_amount", message="初始余额不能为负", http_status=422)
    user = User(
        username=username.strip(),
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role=role,
        status="active",
        balance=0,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise AppError(code="user_exists", message="用户名或邮箱已存在", http_status=409) from exc
    key, plain = await create_api_key(
        session, user_id=user.id, name=DEFAULT_KEY_NAME, pepper=pepper
    )
    if initial_balance:
        # Route through billing so the ledger stays the source of truth.
        from app.services import billing

        await billing.recharge(
            session,
            user_id=user.id,
            amount=initial_balance,
            operator_id=None,
            method="manual",
            remark="开户初始余额",
        )
        await session.refresh(user)
    return CreatedUser(user=user, initial_key=key, initial_key_plain=plain)


async def authenticate(session: AsyncSession, *, username: str, password: str) -> User:
    user = await session.scalar(
        select(User).where((User.username == username) | (User.email == username.lower()))
    )
    # Always run the hash to keep timing flat between "no such user" and "bad password".
    ok = verify_password(password, user.password_hash if user else hash_password("x"))
    if user is None or not ok:
        raise AppError(code="bad_credentials", message="用户名或密码错误", http_status=401)
    if user.status != "active":
        raise AppError(code="user_disabled", message="账号已禁用", http_status=403)
    user.last_login_at = datetime.now(UTC)
    return user


async def resolve_api_key(session: AsyncSession, *, plain: str, pepper: str) -> tuple[ApiKey, User]:
    key = await session.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(plain, pepper)))
    if key is None or key.status != "active":
        raise AppError(code="invalid_api_key", message="API KEY 无效或已吊销", http_status=401)
    user = await session.get(User, key.user_id)
    if user is None or user.status != "active":
        raise AppError(code="user_disabled", message="账号已禁用", http_status=403)
    key.last_used_at = datetime.now(UTC)
    return key, user


async def revoke_api_key(session: AsyncSession, *, user_id: int, key_id: int) -> ApiKey:
    key = await session.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
    if key is None:
        raise AppError(code="key_not_found", message="KEY 不存在", http_status=404)
    if key.status == "active":
        key.status = "revoked"
        key.revoked_at = datetime.now(UTC)
    return key


async def ensure_bootstrap_admin(
    session: AsyncSession, *, username: str, password: str, pepper: str
) -> User | None:
    """First boot only: if the users table is empty, seed the admin from env."""
    count = await session.scalar(select(func.count()).select_from(User))
    if count:
        return None
    created = await create_user(
        session,
        username=username,
        email=f"{username}@local",
        password=password,
        pepper=pepper,
        role="admin",
    )
    logger.warning("bootstrap admin '%s' created from env; change the password", username)
    return created.user
