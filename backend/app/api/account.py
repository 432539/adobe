"""Panel views: platform announcement plus self-service ledger / consume / recharge."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import ConfigStoreDep, SessionDep, UserDep
from app.models import BalanceLedger, ConsumeRecord, RechargeRecord
from app.schemas.panel import (
    AnnouncementOut,
    ConsumeOut,
    LedgerOut,
    Page,
    RechargeOut,
    consume_of,
    ledger_of,
    recharge_of,
)

router = APIRouter(prefix="/api", tags=["account"])

PageQ = Query(default=1, ge=1)
SizeQ = Query(default=10, ge=1, le=100)


@router.get("/announcement", response_model=AnnouncementOut)
async def announcement(_user: UserDep, store: ConfigStoreDep) -> AnnouncementOut:
    cfg = await store.load()
    return AnnouncementOut(announcement=cfg.announcement.strip())


@router.get("/ledger", response_model=Page[LedgerOut])
async def ledger(
    user: UserDep, session: SessionDep, page: int = PageQ, page_size: int = SizeQ
) -> Page[LedgerOut]:
    base = select(BalanceLedger).where(BalanceLedger.user_id == user.id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(BalanceLedger.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(
        items=[ledger_of(r) for r in rows], total=int(total or 0), page=page, page_size=page_size
    )


@router.get("/records/consume", response_model=Page[ConsumeOut])
async def consume_records(
    user: UserDep, session: SessionDep, page: int = PageQ, page_size: int = SizeQ
) -> Page[ConsumeOut]:
    base = select(ConsumeRecord).where(ConsumeRecord.user_id == user.id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(ConsumeRecord.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(
        items=[consume_of(r, username=user.username) for r in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get("/records/recharge", response_model=Page[RechargeOut])
async def recharge_records(
    user: UserDep, session: SessionDep, page: int = PageQ, page_size: int = SizeQ
) -> Page[RechargeOut]:
    base = select(RechargeRecord).where(RechargeRecord.user_id == user.id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(RechargeRecord.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(
        items=[recharge_of(r, username=user.username, operator=None) for r in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )
