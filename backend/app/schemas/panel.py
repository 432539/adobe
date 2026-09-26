from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import (
    ApiKey,
    BalanceLedger,
    ConsumeRecord,
    GenerationJob,
    RechargeRecord,
    User,
)
from app.services.generation.errors import public_fail_message

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------------------- auth / users
class Profile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: str
    balance: int
    created_at: datetime
    last_login_at: datetime | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    token: str
    role: str
    profile: Profile


class AnnouncementOut(BaseModel):
    announcement: str


class AdminUserOut(Profile):
    status: str
    rate_limit: int | None = None
    concurrency_limit: int | None = None
    job_count: int = 0
    total_consumed: int = 0


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["user", "admin"] = "user"
    initial_balance: int = Field(default=0, ge=0, description="分")


class CreateUserResponse(BaseModel):
    user: AdminUserOut
    initial_key: ApiKeyOut


class PatchUserRequest(BaseModel):
    status: Literal["active", "disabled"] | None = None
    role: Literal["user", "admin"] | None = None
    rate_limit: int | None = Field(default=None, ge=1, le=100_000)
    concurrency_limit: int | None = Field(default=None, ge=1, le=256)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class RechargeRequest(BaseModel):
    amount: int = Field(gt=0, description="分")
    remark: str = Field(default="", max_length=255)


class AdjustRequest(BaseModel):
    delta: int = Field(description="分，可负；不能使余额为负")
    remark: str = Field(min_length=1, max_length=255)


# --------------------------------------------------------------------------- keys
class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    key_prefix: str
    status: str
    rate_limit: int | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    plain: str | None = None  # only on creation


class CreateKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    rate_limit: int | None = Field(default=None, ge=1, le=100_000)


# --------------------------------------------------------------------------- jobs
class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    model: str
    prompt: str
    status: str
    progress: int
    cost: int
    result_urls: list[str]
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    params: dict[str, Any]


class CreateImageRequest(BaseModel):
    model: str = Field(min_length=1, max_length=64)
    prompt: str = Field(default="", max_length=4000)
    aspect_ratio: str = Field(default="1:1", max_length=8)
    resolution: str = Field(default="1K", max_length=8)
    reference_blob_ids: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="URL / data URI / base64，或面板落盘后的 file: 令牌",
    )
    idempotency_key: str = Field(min_length=8, max_length=128)


class CreateVideoRequest(BaseModel):
    model: str = Field(min_length=1, max_length=64)
    prompt: str = Field(default="", max_length=4000)
    aspect_ratio: str = Field(default="16:9", max_length=8)
    resolution: str = Field(default="720p", max_length=8)
    duration: int = Field(ge=1, le=60)
    reference_blob_ids: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="URL / data URI / base64，或面板落盘后的 file: 令牌",
    )
    idempotency_key: str = Field(min_length=8, max_length=128)


class ModelOut(BaseModel):
    id: str
    name: str
    kind: Literal["image", "video"]
    price: int
    billing: Literal["per_call", "per_second", "per_tier"]
    tiers: list[dict[str, Any]] = Field(default_factory=list)
    note: str = ""
    enabled: bool = True
    aspect_ratios: list[str] = Field(default_factory=list)
    resolutions: list[str] = Field(default_factory=list)
    durations: list[int] | None = None
    supports_edit: bool = False
    modes: list[str] = Field(default_factory=list)
    max_reference_images: int = 0
    submit_ready: bool = False


# --------------------------------------------------------------------------- money
class LedgerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    delta: int
    balance_after: int
    type: str
    job_id: str | None = None
    ref_id: str | None = None
    remark: str
    created_at: datetime


class RechargeOut(BaseModel):
    id: int
    user_id: int
    username: str
    amount: int
    method: str
    operator: str | None = None
    remark: str
    status: str
    created_at: datetime


class ConsumeOut(BaseModel):
    id: int
    user_id: int
    username: str
    job_id: str
    model: str
    amount: int
    status: str
    created_at: datetime


# --------------------------------------------------------------------------- mappers
def profile_of(user: User) -> Profile:
    return Profile.model_validate(user)


def admin_user_of(user: User, *, job_count: int = 0, total_consumed: int = 0) -> AdminUserOut:
    return AdminUserOut(
        **profile_of(user).model_dump(),
        status=user.status,
        rate_limit=user.rate_limit,
        concurrency_limit=user.concurrency_limit,
        job_count=job_count,
        total_consumed=total_consumed,
    )


def key_of(key: ApiKey, plain: str | None = None) -> ApiKeyOut:
    out = ApiKeyOut.model_validate(key)
    out.plain = plain
    return out


def job_of(job: GenerationJob) -> JobOut:
    out = JobOut.model_validate(job)
    if out.error_message or out.error_code:
        out.error_message = public_fail_message(out.error_code or "", 0, out.error_message or "")
    return out


def ledger_of(row: BalanceLedger) -> LedgerOut:
    return LedgerOut.model_validate(row)


def recharge_of(row: RechargeRecord, *, username: str, operator: str | None) -> RechargeOut:
    return RechargeOut(
        id=row.id,
        user_id=row.user_id,
        username=username,
        amount=row.amount,
        method=row.method,
        operator=operator,
        remark=row.remark,
        status=row.status,
        created_at=row.created_at,
    )


def consume_of(row: ConsumeRecord, *, username: str) -> ConsumeOut:
    return ConsumeOut(
        id=row.id,
        user_id=row.user_id,
        username=username,
        job_id=row.job_id,
        model=row.model,
        amount=row.amount,
        status=row.status,
        created_at=row.created_at,
    )
