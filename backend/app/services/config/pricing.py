"""Billing lookups against the hot pricing tables. All amounts are integer 分.

Resolution tiers are matched by label (``1K`` / ``2K`` / ``4K``); an unknown label falls
back to the *highest* tier so a mis-tagged request can never be under-billed.
Video: ``per_second`` models multiply by duration, ``per_call`` ignore it.
"""

from __future__ import annotations

from app.core.errors import AppError
from app.services.config.schema import ImagePricingTier, SystemConfig, VideoPricingTier

_TIER_ALIASES = {
    "1k": "1K",
    "1024": "1K",
    "1024px": "1K",
    "hd": "1K",
    "2k": "2K",
    "2048": "2K",
    "2048px": "2K",
    "4k": "4K",
    "4096": "4K",
    "4096px": "4K",
    "uhd": "4K",
}


def normalize_resolution(value: str) -> str:
    key = value.strip().lower()
    return _TIER_ALIASES.get(key, value.strip().upper())


def _norm_model(model_id: str) -> str:
    return model_id.strip().lower()


def find_image_pricing(cfg: SystemConfig, model_id: str) -> ImagePricingTier | None:
    wanted = _norm_model(model_id)
    for tier in cfg.image_pricing:
        if _norm_model(tier.model_id) == wanted:
            return tier
    # Family fallback by longest matching prefix: ``nano-banana-2`` → ``nano-banana``.
    for tier in sorted(cfg.image_pricing, key=lambda t: -len(t.model_id)):
        if wanted.startswith(_norm_model(tier.model_id)):
            return tier
    return None


def find_video_pricing(cfg: SystemConfig, model_id: str) -> VideoPricingTier | None:
    wanted = _norm_model(model_id)
    for tier in cfg.video_pricing:
        if _norm_model(tier.model_id) == wanted:
            return tier
    for tier in sorted(cfg.video_pricing, key=lambda t: -len(t.model_id)):
        if wanted.startswith(_norm_model(tier.model_id)):
            return tier
    return None


def image_cost(cfg: SystemConfig, model_id: str, resolution: str) -> int:
    tier = find_image_pricing(cfg, model_id)
    if tier is None or not tier.tiers:
        raise AppError(
            code="pricing_missing", message=f"模型 {model_id} 未配置计费", http_status=422
        )
    label = normalize_resolution(resolution)
    for t in tier.tiers:
        if normalize_resolution(t.resolution) == label:
            return t.price
    return max(t.price for t in tier.tiers)


def video_cost(cfg: SystemConfig, model_id: str, duration_seconds: int = 0) -> int:
    tier = find_video_pricing(cfg, model_id)
    if tier is None:
        raise AppError(
            code="pricing_missing", message=f"模型 {model_id} 未配置计费", http_status=422
        )
    if tier.billing == "per_second":
        if duration_seconds <= 0:
            raise AppError(
                code="duration_required", message="按秒计费模型必须提供时长", http_status=422
            )
        return tier.price * duration_seconds
    return tier.price


def format_credits(fen: int) -> str:
    sign = "-" if fen < 0 else ""
    fen = abs(fen)
    return f"{sign}{fen // 100}.{fen % 100:02d}"
