"""Admin: users, manual recharge/adjust, global money records."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import AdminDep, SessionDep, SettingsDep, load_user
from app.core.errors import AppError
from app.core.security import hash_password
from app.models import BalanceLedger, ConsumeRecord, GenerationJob, RechargeRecord, User
from app.schemas.panel import (
    AdjustRequest,
    AdminUserOut,
    ConsumeOut,
    CreateUserRequest,
    CreateUserResponse,
    LedgerOut,
    Page,
    PatchUserRequest,
    RechargeOut,
    RechargeRequest,
    admin_user_of,
    consume_of,
    key_of,
    ledger_of,
    recharge_of,
)
from app.services import billing
from app.services import users as users_service

router = APIRouter(prefix="/api/admin", tags=["admin-users"])

PageQ = Query(default=1, ge=1)
SizeQ = Query(default=10, ge=1, le=100)


async def _stats(session: SessionDep, user_ids: list[int]) -> dict[int, tuple[int, int]]:
    if not user_ids:
        return {}
    jobs = await session.execute(
        select(GenerationJob.user_id, func.count())
        .where(GenerationJob.user_id.in_(user_ids))
        .group_by(GenerationJob.user_id)
    )
    spent = await session.execute(
        select(ConsumeRecord.user_id, func.coalesce(func.sum(ConsumeRecord.amount), 0))
        .where(ConsumeRecord.user_id.in_(user_ids), ConsumeRecord.status == "settled")
        .group_by(ConsumeRecord.user_id)
    )
    job_map = {int(u): int(c) for u, c in jobs}
    spent_map = {int(u): int(s) for u, s in spent}
    return {uid: (job_map.get(uid, 0), spent_map.get(uid, 0)) for uid in user_ids}


async def _usernames(session: SessionDep, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {int(i): str(n) for i, n in rows}


# --------------------------------------------------------------------------- users
@router.get("/users", response_model=Page[AdminUserOut])
async def list_users(
    _admin: AdminDep,
    session: SessionDep,
    page: int = PageQ,
    page_size: int = SizeQ,
    q: str | None = Query(default=None, max_length=64),
) -> Page[AdminUserOut]:
    base = select(User)
    if q:
        like = f"%{q}%"
        base = base.where(User.username.ilike(like) | User.email.ilike(like))
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = list(
        await session.scalars(
            base.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    stats = await _stats(session, [u.id for u in rows])
    return Page(
        items=[
            admin_user_of(u, job_count=stats[u.id][0], total_consumed=stats[u.id][1]) for u in rows
        ],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=CreateUserResponse, status_code=201)
async def create_user(
    payload: CreateUserRequest, admin: AdminDep, session: SessionDep, settings: SettingsDep
) -> CreateUserResponse:
    created = await users_service.create_user(
        session,
        username=payload.username,
        email=payload.email,
        password=payload.password,
        pepper=settings.app_secret_key,
        role=payload.role,
        initial_balance=payload.initial_balance,
    )
    if payload.initial_balance:
        # Attribute the opening balance to the operator for the audit trail.
        record = await session.scalar(
            select(RechargeRecord)
            .where(RechargeRecord.user_id == created.user.id)
            .order_by(RechargeRecord.id.desc())
        )
        if record is not None:
            record.operator_id = admin.id
    return CreateUserResponse(
        user=admin_user_of(created.user),
        initial_key=key_of(created.initial_key, created.initial_key_plain),
    )


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def patch_user(
    user_id: int, payload: PatchUserRequest, admin: AdminDep, session: SessionDep
) -> AdminUserOut:
    user = await load_user(session, user_id)
    if user.id == admin.id and payload.status == "disabled":
        raise AppError(code="self_disable", message="不能禁用自己", http_status=422)
    if user.id == admin.id and payload.role == "user":
        raise AppError(code="self_demote", message="不能降级自己", http_status=422)
    if payload.status is not None:
        user.status = payload.status
    if payload.role is not None:
        user.role = payload.role
    if payload.rate_limit is not None:
        user.rate_limit = payload.rate_limit
    if payload.concurrency_limit is not None:
        user.concurrency_limit = payload.concurrency_limit
    if payload.password:
        user.password_hash = hash_password(payload.password)
    await session.flush()
    stats = await _stats(session, [user.id])
    return admin_user_of(user, job_count=stats[user.id][0], total_consumed=stats[user.id][1])


@router.post("/users/{user_id}/recharge", response_model=AdminUserOut)
async def recharge_user(
    user_id: int, payload: RechargeRequest, admin: AdminDep, session: SessionDep
) -> AdminUserOut:
    user = await load_user(session, user_id)
    await billing.recharge(
        session,
        user_id=user.id,
        amount=payload.amount,
        operator_id=admin.id,
        method="manual",
        remark=payload.remark,
    )
    await session.refresh(user)
    return admin_user_of(user)


@router.post("/users/{user_id}/adjust", response_model=AdminUserOut)
async def adjust_user(
    user_id: int, payload: AdjustRequest, admin: AdminDep, session: SessionDep
) -> AdminUserOut:
    user = await load_user(session, user_id)
    await billing.adjust(
        session, user_id=user.id, delta=payload.delta, operator_id=admin.id, remark=payload.remark
    )
    await session.refresh(user)
    return admin_user_of(user)


@router.get("/users/{user_id}/ledger", response_model=Page[LedgerOut])
async def user_ledger(
    user_id: int, _admin: AdminDep, session: SessionDep, page: int = PageQ, page_size: int = SizeQ
) -> Page[LedgerOut]:
    await load_user(session, user_id)
    base = select(BalanceLedger).where(BalanceLedger.user_id == user_id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(BalanceLedger.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(
        items=[ledger_of(r) for r in rows], total=int(total or 0), page=page, page_size=page_size
    )


@router.get("/users/{user_id}/reconcile")
async def reconcile_user(
    user_id: int, _admin: AdminDep, session: SessionDep
) -> dict[str, int | bool]:
    await load_user(session, user_id)
    balance, ledger_sum = await billing.reconcile(session, user_id)
    return {"balance": balance, "ledger_sum": ledger_sum, "consistent": balance == ledger_sum}


# --------------------------------------------------------------------------- records
@router.get("/records/recharge", response_model=Page[RechargeOut])
async def all_recharges(
    _admin: AdminDep, session: SessionDep, page: int = PageQ, page_size: int = SizeQ
) -> Page[RechargeOut]:
    total = await session.scalar(select(func.count()).select_from(RechargeRecord))
    rows = list(
        await session.scalars(
            select(RechargeRecord)
            .order_by(RechargeRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    names = await _usernames(
        session,
        {r.user_id for r in rows} | {r.operator_id for r in rows if r.operator_id is not None},
    )
    return Page(
        items=[
            recharge_of(
                r,
                username=names.get(r.user_id, "?"),
                operator=names.get(r.operator_id) if r.operator_id is not None else None,
            )
            for r in rows
        ],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get("/records/consume", response_model=Page[ConsumeOut])
async def all_consumes(
    _admin: AdminDep, session: SessionDep, page: int = PageQ, page_size: int = SizeQ
) -> Page[ConsumeOut]:
    total = await session.scalar(select(func.count()).select_from(ConsumeRecord))
    rows = list(
        await session.scalars(
            select(ConsumeRecord)
            .order_by(ConsumeRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    names = await _usernames(session, {r.user_id for r in rows})
    return Page(
        items=[consume_of(r, username=names.get(r.user_id, "?")) for r in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )
