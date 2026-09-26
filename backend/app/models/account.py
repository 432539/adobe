from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, utcnow


class UpstreamAccount(TimestampMixin, Base):
    """Upstream identity. Cookie is encrypted at rest; access tokens are minted per request."""

    __tablename__ = "upstream_accounts"
    __table_args__ = (Index("ix_upstream_status", "status", "plan_cap"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    email_masked: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    cookie_enc: Mapped[str] = mapped_column(Text, nullable=False)
    # Legacy column. New code never writes an AT; kept so existing rows still load.
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    plan_cap: Mapped[str] = mapped_column(String(8), nullable=False, default="UNKNOWN")
    group: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    # Long-lived FF-iOS grant. Both values are encrypted; short access tokens are never stored.
    ios_device_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    ios_device_id_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unverified"
    )
    credential_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    parked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credits_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_reset_on: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)


class RequestLog(Base):
    """Desensitized upstream audit. Never store cookies, tokens, or proxy passwords."""

    __tablename__ = "request_logs"
    __table_args__ = (Index("ix_request_logs_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    account_hash: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    egress_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False, default="generate")
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    arp_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    # Per-step Adobe responses (sanitized). Empty on older rows.
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
