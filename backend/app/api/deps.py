"""Shared FastAPI dependencies for panel routes: current user, admin guard, services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.resources import Resources
from app.core.security import looks_like_api_key
from app.models import ApiKey, User
from app.services import users as users_service
from app.services.config.store import ConfigStore

Role = Literal["admin", "user"]


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: int
    username: str
    role: Role

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def issue_token(settings: Settings, user: CurrentUser) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(settings: Settings, token: str) -> CurrentUser:
    try:
        data = jwt.decode(token, settings.app_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AppError(code="token_expired", message="登录已过期", http_status=401) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(code="token_invalid", message="无效的登录凭证", http_status=401) from exc
    role = data.get("role")
    if role not in ("admin", "user"):
        raise AppError(code="token_invalid", message="无效的登录凭证", http_status=401)
    return CurrentUser(id=int(data["sub"]), username=str(data.get("username", "")), role=role)


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_resources(request: Request) -> Resources:
    resources: Resources = request.app.state.resources
    return resources


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Request-scoped session: commit on success, roll back on any exception."""
    resources: Resources = request.app.state.resources
    async with resources.request_sessions() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(code="unauthorized", message="未登录", http_status=401)
    return authorization[7:].strip()


async def current_user(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Panel JWT → live DB user. Disabled users are cut off even with a valid token."""
    claims = decode_token(request.app.state.settings, _bearer(authorization))
    user = await session.get(User, claims.id)
    if user is None or user.status != "active":
        raise AppError(code="user_disabled", message="账号不可用", http_status=403)
    role: Role = "admin" if user.role == "admin" else "user"
    return CurrentUser(id=user.id, username=user.username, role=role)


async def require_admin(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    if not user.is_admin:
        raise AppError(code="forbidden", message="需要管理员权限", http_status=403)
    return user


@dataclass(frozen=True, slots=True)
class ApiPrincipal:
    """Caller of the public ``/v1`` / ``/v1beta`` surface: a user acting through a key."""

    user_id: int
    api_key_id: int
    rate_limit: int | None


async def require_api_key(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    x_goog_api_key: Annotated[str | None, Header(alias="x-goog-api-key")] = None,
) -> ApiPrincipal:
    """``Authorization: Bearer sk-…`` (OpenAI style) or ``x-goog-api-key`` (Gemini style)."""
    plain = x_goog_api_key.strip() if x_goog_api_key else _bearer(authorization)
    if not looks_like_api_key(plain):
        raise AppError(code="invalid_api_key", message="API KEY 无效", http_status=401)
    settings: Settings = request.app.state.settings
    key, user = await users_service.resolve_api_key(
        session, plain=plain, pepper=settings.app_secret_key
    )
    return ApiPrincipal(
        user_id=user.id, api_key_id=key.id, rate_limit=key.rate_limit or user.rate_limit
    )


async def load_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise AppError(code="user_not_found", message="用户不存在", http_status=404)
    return user


async def load_key(session: AsyncSession, key_id: int) -> ApiKey:
    key = await session.get(ApiKey, key_id)
    if key is None:
        raise AppError(code="key_not_found", message="KEY 不存在", http_status=404)
    return key


def get_config_store(request: Request) -> ConfigStore:
    """One store per app; created lazily so tests can inject resources."""
    store: ConfigStore | None = getattr(request.app.state, "config_store", None)
    if store is None:
        settings: Settings = request.app.state.settings
        resources: Resources = request.app.state.resources
        store = ConfigStore(
            resources.sessions,
            resources.redis,
            resources.cipher,
            cache_seconds=settings.config_cache_seconds,
            channel=settings.config_channel,
        )
        request.app.state.config_store = store
    return store


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ResourcesDep = Annotated[Resources, Depends(get_resources)]
AdminDep = Annotated[CurrentUser, Depends(require_admin)]
UserDep = Annotated[CurrentUser, Depends(current_user)]
ApiKeyDep = Annotated[ApiPrincipal, Depends(require_api_key)]
ConfigStoreDep = Annotated[ConfigStore, Depends(get_config_store)]
