from __future__ import annotations

import base64
import binascii
import json
import time
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

REQUIRED_ARP_PARTS = frozenset({"sid", "ark", "bfp", "ftr"})
ARP_MAX_USES_CAP = 10


def cap_arp_max_uses(value: int) -> int:
    """Hard ceiling for a single ticket. Config may be lower (ge=1)."""
    return max(1, min(int(value), ARP_MAX_USES_CAP))


def decode_arp_token(token: str) -> dict[str, Any]:
    try:
        decoded = base64.b64decode(token, validate=True)
        payload = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("ARP token must be base64-encoded JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("ARP token payload must be an object")
    missing = REQUIRED_ARP_PARTS.difference(payload)
    if missing:
        raise ValueError(f"ARP token is missing required parts: {','.join(sorted(missing))}")
    if any(not isinstance(payload[name], str) or not payload[name] for name in REQUIRED_ARP_PARTS):
        raise ValueError("ARP token parts must be non-empty strings")
    if "v2_tt" not in payload["ftr"]:
        raise ValueError("ARP token ftr must be the full forter cookie with v2_tt")
    return payload


class ArpPublishItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    token: SecretStr = Field(alias="t")
    proxy_url: SecretStr
    egress_id: str = Field(min_length=1, max_length=128)
    ua: str = Field(min_length=1, max_length=1024)
    ch: dict[str, Any]
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: SecretStr) -> SecretStr:
        decode_arp_token(value.get_secret_value())
        return value

    @field_validator("proxy_url")
    @classmethod
    def require_proxy_url(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value().strip()
        if not raw or "://" not in raw:
            raise ValueError("ARP bundle requires proxy_url")
        return value

    @field_validator("ua")
    @classmethod
    def require_chrome_148(cls, value: str) -> str:
        if "Chrome/148." not in value:
            raise ValueError("minting browser must identify as Chrome 148")
        return value

    @model_validator(mode="after")
    def require_client_hints(self) -> ArpPublishItem:
        required = {"platform", "platformVersion", "fullVersionList", "architecture", "bitness"}
        missing = required.difference(self.ch)
        if missing:
            raise ValueError(f"missing client hints: {','.join(sorted(missing))}")
        return self


class ArpPublishRequest(BaseModel):
    tokens: list[ArpPublishItem] = Field(min_length=1, max_length=100)


class ArpInvalidateRequest(BaseModel):
    id: str = Field(min_length=1, max_length=128)


class ArpBundle(BaseModel):
    id: str
    token: SecretStr
    proxy_url: SecretStr
    egress_id: str
    ua: str
    ch: dict[str, Any]
    headers: dict[str, str]
    minted_at: int
    expires_at: int
    uses: int = 0
    max_uses: int

    @classmethod
    def from_publish_item(
        cls, item: ArpPublishItem, *, ttl_seconds: int, max_uses: int
    ) -> ArpBundle:
        now = int(time.time())
        return cls(
            id=f"arp_{uuid4().hex}",
            token=item.token,
            proxy_url=item.proxy_url,
            egress_id=item.egress_id,
            ua=item.ua,
            ch=item.ch,
            headers=item.headers,
            minted_at=now,
            expires_at=now + ttl_seconds,
            max_uses=max_uses,
        )

    def to_storage_json(self) -> str:
        data = self.model_dump(mode="json")
        data["token"] = self.token.get_secret_value()
        data["proxy_url"] = self.proxy_url.get_secret_value()
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_storage_json(cls, raw: str | bytes) -> ArpBundle:
        return cls.model_validate_json(raw)
