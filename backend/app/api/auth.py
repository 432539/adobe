"""Panel login against the users table."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, Role, SessionDep, SettingsDep, UserDep, issue_token, load_user
from app.schemas.panel import LoginRequest, LoginResponse, Profile, profile_of
from app.services import users as users_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, session: SessionDep, settings: SettingsDep) -> LoginResponse:
    user = await users_service.authenticate(
        session, username=payload.username, password=payload.password
    )
    role: Role = "admin" if user.role == "admin" else "user"
    principal = CurrentUser(id=user.id, username=user.username, role=role)
    return LoginResponse(
        token=issue_token(settings, principal), role=role, profile=profile_of(user)
    )


@router.get("/me", response_model=Profile)
async def me(user: UserDep, session: SessionDep) -> Profile:
    return profile_of(await load_user(session, user.id))
