"""System configuration schema.

Three shapes share one vocabulary:

* ``SystemConfig``        – what we persist. Secrets are Fernet ciphertext (``*_enc``).
* ``SystemConfigView``    – what the panel receives. Secrets are masked / boolean flags.
* ``SystemConfigUpdate``  – what the panel sends. Secrets are optional write-only fields;
                            omitted or masked values keep the stored ciphertext.

All money is integer 分 (100 = 1.00 积分). Never floats.
"""

from __future__ import annotations

import re
import secrets
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.arp.models import ARP_MAX_USES_CAP
from app.core.crypto import FieldCipher

TokenRotation = Literal["random", "round_robin", "least_used"]
StorageBackend = Literal["r2", "s3", "minio"]
GeminiImageFormat = Literal["url", "inline"]
ProxyScheme = Literal["http", "socks5"]

_MASK = "••••"
# Full sticky username: `{user}-region-{CC}-sid-{SID}-t-{N}`. Must never be stored as the
# supplier prefix or `build_session` would double-expand and mint on a different egress.
_EXPANDED_USERNAME = re.compile(
    r"^.+-region-[A-Za-z]{2,3}-sid-[A-Za-z0-9]+-t-\d+$", re.IGNORECASE
)


def reject_expanded_username(username: str) -> str:
    """Supplier prefix only. An already-expanded sticky session is rejected."""
    value = username.strip()
    if value and _EXPANDED_USERNAME.match(value):
        raise ValueError("代理账号必须是供应商前缀，不能是已展开的 sticky 会话")
    return value


def min_sticky_minutes(arp_ttl_seconds: int) -> int:
    """Sticky must cover TTL plus a 60s buffer so the mint egress does not drift."""
    return max(1, (arp_ttl_seconds + 60 + 59) // 60)


def reject_short_sticky(
    sticky_minutes: int, arp_ttl_seconds: int, *, configured: bool
) -> None:
    """Sticky must outlive the ticket, else the IP drifts while the ARP is still pooled."""
    if not configured:
        return
    need = min_sticky_minutes(arp_ttl_seconds)
    if sticky_minutes < need:
        raise ValueError(
            f"粘性会话必须长过票 TTL：需要 sticky_minutes ≥ {need} 分钟"
            f"（当前 {sticky_minutes} 分钟，TTL {arp_ttl_seconds}s）"
        )


def mask_tail(value: str | None, keep: int = 4) -> str:
    """``abcdef1234`` → ``1234`` (only the tail, for identification)."""
    if not value:
        return ""
    return value[-keep:] if len(value) > keep else value


def mask_endpoint(endpoint: str) -> str:
    """``https://ffa7964b824a013739abc.r2.cloudflarestorage.com`` → ``ffa7964b824a…storage.com``."""
    host = endpoint.split("://", 1)[-1].split("/", 1)[0]
    if len(host) <= 22:
        return host
    return f"{host[:10]}…{host[-11:]}"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------- proxy
class ProxyConfig(_Strict):
    scheme: ProxyScheme = "http"
    host: str = ""
    port: int = Field(default=3010, ge=1, le=65535)
    username: str = ""
    password_enc: str | None = None
    country: str = "SG"
    sticky_minutes: int = Field(default=10, ge=1, le=120)
    sid_length: int = Field(default=8, ge=4, le=32)
    upload_via_proxy: bool = False

    @field_validator("country")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class ProxyConfigView(_Strict):
    scheme: ProxyScheme
    host: str
    port: int
    username: str
    password_set: bool
    country: str
    sticky_minutes: int
    sid_length: int
    upload_via_proxy: bool


class ProxyConfigUpdate(_Strict):
    scheme: ProxyScheme = "http"
    host: str = ""
    port: int = Field(default=3010, ge=1, le=65535)
    username: str = ""
    password: str | None = None
    password_set: bool | None = None  # echoed back by the UI; ignored
    country: str = "SG"
    sticky_minutes: int = Field(default=10, ge=1, le=120)
    sid_length: int = Field(default=8, ge=4, le=32)
    upload_via_proxy: bool = False

    @field_validator("username")
    @classmethod
    def _supplier_prefix(cls, v: str) -> str:
        return reject_expanded_username(v)

    @field_validator("country")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


# --------------------------------------------------------------------------- storage
class R2Account(_Strict):
    id: str
    name: str
    endpoint: str
    bucket: str
    public_base_url: str = ""
    prefix: str = ""
    enabled: bool = True
    quota_bytes: int = Field(default=10 * 1024**3, ge=0)
    access_key_id: str = ""
    secret_key_enc: str | None = None


class R2AccountView(_Strict):
    id: str
    name: str
    endpoint_masked: str
    bucket: str
    public_base_url: str
    prefix: str = ""
    enabled: bool
    quota_bytes: int
    key_suffix: str
    used_bytes: int | None = None


class R2AccountUpdate(_Strict):
    id: str | None = None
    name: str
    endpoint: str | None = None  # full URL when (re)configuring; None keeps stored value
    endpoint_masked: str | None = None  # echoed by UI; ignored
    bucket: str
    public_base_url: str = ""
    prefix: str = ""
    enabled: bool = True
    quota_bytes: int = Field(default=10 * 1024**3, ge=0)
    access_key_id: str | None = None
    secret_access_key: str | None = None
    key_suffix: str | None = None  # echoed; ignored
    used_bytes: int | None = None  # echoed; ignored


# --------------------------------------------------------------------------- pricing
class ImageTier(_Strict):
    resolution: str
    pixels: str = ""
    price: int = Field(ge=0, description="分/次")


class ImagePricingTier(_Strict):
    model_id: str
    model_name: str
    model_note: str | None = None
    tiers: list[ImageTier]


class VideoPricingTier(_Strict):
    model_id: str
    model_name: str
    billing: Literal["per_second", "per_call"]
    note: str = ""
    price: int = Field(ge=0, description="分/秒 或 分/次")


# --------------------------------------------------------------------------- root
class _CommonFields(_Strict):
    announcement: str = Field(default="", max_length=160)
    # 同步接口最长等待；超时返回 504 + task_id，任务继续
    sync_timeout_seconds: int = Field(default=180, ge=10, le=600)
    # worker 侧单任务上限：轮询上游超过则判失败并进入容错重试
    generation_timeout_seconds: int = Field(default=300, ge=30, le=1800)
    # 用户默认限流（次/分钟）
    default_rate_limit: int = Field(default=60, ge=1, le=10_000)
    # 用户默认并发上限（同时 queued+running 任务数），超出排队。单号并发是另一维。
    user_concurrency_default: int = Field(default=2, ge=1, le=200)
    # 进程内 worker 同时处理的任务数。过小会把出图串行化。
    worker_concurrency: int = Field(default=32, ge=1, le=200)

    mint_browser_count: int = Field(default=2, ge=1, le=8)
    # Idle wait *after a BATCH finishes*. Must stay under TTL. ~10s keeps the standing pool fresh.
    mint_interval_seconds: int = Field(default=10, ge=1, le=300)
    arp_ttl_seconds: int = Field(default=120, ge=30, le=600)
    arp_max_uses: int = Field(default=ARP_MAX_USES_CAP, ge=1, le=ARP_MAX_USES_CAP)
    arp_min_ready: int = Field(default=3, ge=1, le=100)
    # Standing pool size. 20 concurrency needs a handful of fresh tickets, not 20 browsers.
    arp_pool_target: int = Field(default=8, ge=4, le=20)
    # Tickets one hot worker mints before idling. Spread across distinct egress leases.
    arp_mint_batch: int = Field(default=8, ge=1, le=20)

    retry_max_attempts: int = Field(default=10, ge=1, le=30)
    retry_backoff_base_seconds: float = Field(default=0.1, ge=0.05, le=10)
    adobe_dual_identity_enabled: bool = True
    normal_canary_account_id: int = Field(default=0, ge=0)
    alpha_canary_account_id: int = Field(default=0, ge=0)
    alpha_retry_max_attempts: int = Field(default=6, ge=1, le=6)
    alpha_retry_delay_seconds: float = Field(default=1.2, ge=0.2, le=10)
    account_park_seconds: int = Field(default=300, ge=30, le=3600)
    account_park_second_seconds: int = Field(default=600, ge=30, le=7200)
    account_park_disable_seconds: int = Field(default=1800, ge=120, le=86400)
    account_park_disable_after: int = Field(default=3, ge=2, le=10)
    # After 408 park, keep the account in observe (concurrency 1) for this many extra seconds.
    # 0 = off. Streak still blocks hot models until a success.
    account_408_observe_seconds: int = Field(default=1800, ge=0, le=86400)
    # Comma-separated model ids a still-risky account (streak >= block_after) cannot take.
    account_408_block_models: str = Field(
        default="gpt-image-2.5-flare,gpt-image-2.5-sunburst"
    )
    account_408_block_after: int = Field(default=1, ge=1, le=10)
    # Clustered 408s → pause account-swap retries so one bad minute cannot drain the pool.
    arp_bad_window_count: int = Field(default=3, ge=2, le=50)
    arp_bad_window_seconds: int = Field(default=60, ge=10, le=600)
    arp_bad_window_pause_seconds: int = Field(default=120, ge=0, le=3600)
    token_rotation: TokenRotation = "random"
    account_concurrency_normal: int = Field(default=1, ge=1, le=16)
    account_daily_image_limit: int = Field(default=5, ge=1, le=1000)
    account_concurrency_advanced: int = Field(default=1, ge=1, le=8)
    disabled_auto_enable_waterline: int = Field(default=2, ge=0, le=100)
    retryable_status_codes: str = "429,451,500,502,503,422"
    retryable_error_types: str = "UpstreamTemporaryError"

    storage_backend: StorageBackend = "r2"
    gemini_image_response_format: GeminiImageFormat = "url"

    image_pricing: list[ImagePricingTier] = Field(default_factory=list)
    video_pricing: list[VideoPricingTier] = Field(default_factory=list)

    @field_validator("retryable_status_codes")
    @classmethod
    def _codes(cls, v: str) -> str:
        parts = [p.strip() for p in v.split(",") if p.strip()]
        for p in parts:
            if not p.isdigit() or not 100 <= int(p) <= 599:
                raise ValueError(f"invalid status code: {p}")
        return ",".join(parts)

    @field_validator("account_408_block_models")
    @classmethod
    def _block_models(cls, v: str) -> str:
        parts = [p.strip().lower() for p in v.split(",") if p.strip()]
        for item in parts:
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", item):
                raise ValueError(f"invalid model id: {item}")
        return ",".join(parts)

    def blocked_408_models(self) -> set[str]:
        return {p.strip().lower() for p in self.account_408_block_models.split(",") if p.strip()}

    @field_validator("arp_max_uses", mode="before")
    @classmethod
    def _cap_max_uses(cls, v: object) -> object:
        if isinstance(v, bool):
            return v
        if isinstance(v, int) and v > ARP_MAX_USES_CAP:
            return ARP_MAX_USES_CAP
        if isinstance(v, str) and v.isdigit() and int(v) > ARP_MAX_USES_CAP:
            return ARP_MAX_USES_CAP
        return v

    @model_validator(mode="after")
    def _interval_under_ttl(self) -> Self:
        if self.mint_interval_seconds >= self.arp_ttl_seconds:
            raise ValueError(
                f"铸币间隔必须小于票据 TTL，否则池会空窗"
                f"（间隔 {self.mint_interval_seconds}s，TTL {self.arp_ttl_seconds}s）"
            )
        if self.arp_pool_target < self.arp_min_ready:
            raise ValueError(
                f"常备池目标必须 ≥ 最低水位"
                f"（目标 {self.arp_pool_target}，水位 {self.arp_min_ready}）"
            )
        return self

    def retryable_codes(self) -> set[int]:
        return {int(p) for p in self.retryable_status_codes.split(",") if p}


class SystemConfig(_CommonFields):
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    cloakbrowser_license_key_enc: str | None = None
    r2_accounts: list[R2Account] = Field(default_factory=list)


class SystemConfigView(_CommonFields):
    proxy: ProxyConfigView
    cloakbrowser_license_key_masked: str
    r2_accounts: list[R2AccountView]


class SystemConfigUpdate(_CommonFields):
    proxy: ProxyConfigUpdate = Field(default_factory=ProxyConfigUpdate)
    cloakbrowser_license_key: str | None = None
    cloakbrowser_license_key_masked: str | None = None  # echoed; ignored
    r2_accounts: list[R2AccountUpdate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sticky_outlives_ttl(self) -> Self:
        configured = bool(self.proxy.host and self.proxy.username)
        if not configured:
            return self
        need = min_sticky_minutes(self.arp_ttl_seconds)
        if self.proxy.sticky_minutes < need:
            self.proxy.sticky_minutes = need
        return self


# --------------------------------------------------------------------------- defaults
def hydrate_stored_config(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a DB document onto defaults.

    Rows from before ``arp_pool_target`` treated ``arp_min_ready`` as the standing
    pool. Default target is 8; a stored waterline of 10 must not 500 the panel —
    promote the target (capped 4–20) instead of rejecting the document.
    """
    raw = {**default_config().model_dump(), **(stored or {})}
    min_ready = int(raw.get("arp_min_ready") or 3)
    target = int(raw.get("arp_pool_target") or 8)
    if target < min_ready:
        target = min(max(min_ready, 4), 20)
        min_ready = min(min_ready, target)
        raw["arp_pool_target"] = target
        raw["arp_min_ready"] = min_ready
    return raw


def default_config() -> SystemConfig:
    return SystemConfig(
        announcement="",
        image_pricing=[
            ImagePricingTier(
                model_id="nano-banana",
                model_name="普通模型 Nano Banana / V2",
                tiers=[
                    ImageTier(resolution="1K", pixels="1024px", price=8),
                    ImageTier(resolution="2K", pixels="2048px", price=12),
                    ImageTier(resolution="4K", pixels="4096px", price=15),
                ],
            ),
            ImagePricingTier(
                model_id="nano-banana-pro",
                model_name="Pro 模型 Nano Banana Pro",
                tiers=[
                    ImageTier(resolution="1K", pixels="1024px", price=10),
                    ImageTier(resolution="2K", pixels="2048px", price=15),
                    ImageTier(resolution="4K", pixels="4096px", price=20),
                ],
            ),
            *[
                ImagePricingTier(
                    model_id=mid,
                    model_name=name,
                    model_note=mid,
                    tiers=[
                        ImageTier(resolution="1K", pixels="~1Mpx", price=8),
                        ImageTier(resolution="2K", pixels="~4Mpx", price=12),
                        ImageTier(resolution="4K", pixels="~8Mpx", price=20),
                    ],
                )
                for mid, name in (
                    ("gpt-image-2", "GPT IMAGE 2"),
                    ("gpt-image-2.5-flare", "GPT IMAGE 2.5 Flare"),
                    ("gpt-image-2.5-sunburst", "GPT IMAGE 2.5 Sunburst"),
                )
            ],
        ],
        video_pricing=[
            VideoPricingTier(
                model_id="gemini-omni-flash",
                model_name="Gemini Omni Flash",
                billing="per_second",
                note="按秒计费",
                price=10,
            ),
            VideoPricingTier(
                model_id="seedance-2.0",
                model_name="Seedance 2.0",
                billing="per_second",
                note="按秒计费，支持参考图",
                price=20,
            ),
            VideoPricingTier(
                model_id="seedance-2.0-fast",
                model_name="Seedance 2.0 Fast",
                billing="per_second",
                note="按秒计费，支持参考图",
                price=15,
            ),
        ],
    )


# --------------------------------------------------------------------------- transforms
def to_view(cfg: SystemConfig, cipher: FieldCipher) -> SystemConfigView:
    licence = ""
    if cfg.cloakbrowser_license_key_enc:
        try:
            plain = cipher.decrypt(cfg.cloakbrowser_license_key_enc)
            licence = f"{plain[:3]}{_MASK}{mask_tail(plain)}"
        except ValueError:
            licence = f"{_MASK}(无法解密)"
    return SystemConfigView(
        **cfg.model_dump(exclude={"proxy", "cloakbrowser_license_key_enc", "r2_accounts"}),
        proxy=ProxyConfigView(
            **cfg.proxy.model_dump(exclude={"password_enc"}),
            password_set=bool(cfg.proxy.password_enc),
        ),
        cloakbrowser_license_key_masked=licence,
        r2_accounts=[
            R2AccountView(
                id=a.id,
                name=a.name,
                endpoint_masked=mask_endpoint(a.endpoint),
                bucket=a.bucket,
                public_base_url=a.public_base_url,
                prefix=a.prefix,
                enabled=a.enabled,
                quota_bytes=a.quota_bytes,
                key_suffix=mask_tail(a.access_key_id),
            )
            for a in cfg.r2_accounts
        ],
    )


def _looks_masked(value: str | None) -> bool:
    return not value or _MASK in value or value.startswith("enc:")


def apply_update(
    current: SystemConfig, update: SystemConfigUpdate, cipher: FieldCipher
) -> SystemConfig:
    """Merge a panel submission into the stored config, preserving secrets that were not resent."""
    common = update.model_dump(
        exclude={
            "proxy",
            "cloakbrowser_license_key",
            "cloakbrowser_license_key_masked",
            "r2_accounts",
        }
    )

    proxy_data = update.proxy.model_dump(exclude={"password", "password_set"})
    password_enc = current.proxy.password_enc
    if update.proxy.password and not _looks_masked(update.proxy.password):
        password_enc = cipher.encrypt(update.proxy.password)
    proxy = ProxyConfig(**proxy_data, password_enc=password_enc)
    reject_expanded_username(proxy.username)
    reject_short_sticky(
        proxy.sticky_minutes,
        int(common["arp_ttl_seconds"]),
        configured=bool(proxy.host and proxy.username),
    )

    licence_enc = current.cloakbrowser_license_key_enc
    if update.cloakbrowser_license_key and not _looks_masked(update.cloakbrowser_license_key):
        licence_enc = cipher.encrypt(update.cloakbrowser_license_key)

    existing = {a.id: a for a in current.r2_accounts}
    accounts: list[R2Account] = []
    for item in update.r2_accounts:
        prev = existing.get(item.id or "")
        endpoint = (
            item.endpoint
            if item.endpoint and not _looks_masked(item.endpoint) and "…" not in item.endpoint
            else (prev.endpoint if prev else "")
        )
        access_key_id = (
            item.access_key_id
            if item.access_key_id and not _looks_masked(item.access_key_id)
            else (prev.access_key_id if prev else "")
        )
        secret_enc = prev.secret_key_enc if prev else None
        if item.secret_access_key and not _looks_masked(item.secret_access_key):
            secret_enc = cipher.encrypt(item.secret_access_key)
        if not endpoint:
            raise ValueError(f"R2 账号 {item.name}: endpoint 不能为空")
        accounts.append(
            R2Account(
                id=item.id or f"r2_{secrets.token_hex(4)}",
                name=item.name,
                endpoint=endpoint,
                bucket=item.bucket,
                public_base_url=item.public_base_url,
                prefix=item.prefix,
                enabled=item.enabled,
                quota_bytes=item.quota_bytes,
                access_key_id=access_key_id,
                secret_key_enc=secret_enc,
            )
        )

    return SystemConfig(
        **common, proxy=proxy, cloakbrowser_license_key_enc=licence_enc, r2_accounts=accounts
    )


def ensure_pricing_catalog(cfg: SystemConfig) -> SystemConfig:
    """Append any missing default models. Never overwrite an already-priced row."""
    defaults = default_config()
    have_image = {t.model_id.strip().lower() for t in cfg.image_pricing}
    have_video = {t.model_id.strip().lower() for t in cfg.video_pricing}
    images = list(cfg.image_pricing)
    videos = list(cfg.video_pricing)
    changed = False
    for image_tier in defaults.image_pricing:
        if image_tier.model_id.strip().lower() not in have_image:
            images.append(image_tier)
            changed = True
    for video_tier in defaults.video_pricing:
        if video_tier.model_id.strip().lower() not in have_video:
            videos.append(video_tier)
            changed = True
    if not changed:
        return cfg
    return cfg.model_copy(update={"image_pricing": images, "video_pricing": videos})
