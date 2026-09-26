from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from app.adobe.client import GeneratedImage
from app.core.crypto import FieldCipher
from app.services.config.r2 import R2Usage, lifecycle_configuration
from app.services.config.schema import R2Account, default_config
from app.services.storage import object_key, ready_accounts, round_robin_order, store_image


def test_object_key_joins_prefix() -> None:
    assert object_key("generated/", job_id="abc", suffix="png") == "generated/jobs/abc/0.png"
    assert object_key("", job_id="abc", suffix="jpg") == "jobs/abc/0.jpg"
    assert object_key(" /media/ ", job_id="x", suffix="webp") == "media/jobs/x/0.webp"


def test_lifecycle_expires_after_one_day() -> None:
    cfg = lifecycle_configuration()
    rule = cfg["Rules"][0]
    assert rule["ID"] == "firefly-gen-expire-1d"
    assert rule["Status"] == "Enabled"
    assert rule["Expiration"]["Days"] == 1
    assert rule["AbortIncompleteMultipartUpload"]["DaysAfterInitiation"] == 1


def _account(account_id: str, *, enabled: bool = True, secret: str | None = "enc") -> R2Account:
    return R2Account(
        id=account_id,
        name=account_id,
        endpoint="https://a.r2.cloudflarestorage.com",
        bucket="firefly-media",
        public_base_url=f"https://pub-{account_id}.r2.dev",
        enabled=enabled,
        access_key_id="akid" if secret else "",
        secret_key_enc=secret,
    )


def test_ready_accounts_skip_disabled_and_empty_keys() -> None:
    cfg = default_config()
    cfg.r2_accounts = [
        _account("a"),
        _account("b", enabled=False),
        _account("c", secret=None),
        _account("d"),
    ]
    assert [a.id for a in ready_accounts(cfg)] == ["a", "d"]


def test_round_robin_order_rotates_from_start() -> None:
    accounts = [_account("a"), _account("b"), _account("c")]
    assert [a.id for a in round_robin_order(accounts, 0)] == ["a", "b", "c"]
    assert [a.id for a in round_robin_order(accounts, 1)] == ["b", "c", "a"]
    assert [a.id for a in round_robin_order(accounts, 5)] == ["c", "a", "b"]
    assert round_robin_order([], 0) == []


class _IncrRedis:
    def __init__(self, start: int = 0) -> None:
        self.n = start

    async def incr(self, _key: str) -> int:
        self.n += 1
        return self.n


@pytest.mark.asyncio
async def test_store_image_round_robin_and_skip_over_quota(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cipher = FieldCipher(Fernet.generate_key())
    secret = cipher.encrypt("plain-secret")
    cfg = default_config()
    cfg.r2_accounts = [
        _account("full", secret=secret),
        _account("ok", secret=secret),
        _account("later", secret=secret),
    ]
    uploaded: list[str] = []

    async def fake_upload(account: R2Account, _secret: str, **_kw: object) -> str:
        uploaded.append(account.id)
        return f"{account.public_base_url}/jobs/j/0.png"

    class FakeUsage:
        def __init__(self, _redis: object, **_kw: object) -> None:
            pass

        async def usage(self, account: R2Account, _secret: str | None, **_kw: object) -> R2Usage:
            return R2Usage(id=account.id, over_quota=account.id == "full", used_bytes=1)

    monkeypatch.setattr("app.services.storage.upload_object", fake_upload)
    monkeypatch.setattr("app.services.storage.R2UsageService", FakeUsage)

    image = GeneratedImage(content=b"png", content_type="image/png", source_url="", metadata={})
    redis = _IncrRedis(start=0)  # first incr → 1 → start index 0
    url = await store_image(
        job_id="j1",
        image=image,
        cfg=cfg,
        cipher=cipher,
        media_dir=tmp_path,
        redis=redis,  # type: ignore[arg-type]
    )
    assert uploaded == ["ok"]
    assert url.startswith("https://pub-ok.r2.dev/")

    uploaded.clear()
    url = await store_image(
        job_id="j2",
        image=image,
        cfg=cfg,
        cipher=cipher,
        media_dir=tmp_path,
        redis=redis,  # type: ignore[arg-type]
    )
    assert uploaded == ["ok"]
    assert "pub-ok" in url

    uploaded.clear()
    url = await store_image(
        job_id="j3",
        image=image,
        cfg=cfg,
        cipher=cipher,
        media_dir=tmp_path,
        redis=redis,  # type: ignore[arg-type]
    )
    assert uploaded == ["later"]
    assert "pub-later" in url


@pytest.mark.asyncio
async def test_store_image_falls_back_local_when_all_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cipher = FieldCipher(Fernet.generate_key())
    secret = cipher.encrypt("plain-secret")
    cfg = default_config()
    cfg.r2_accounts = [_account("a", secret=secret)]

    async def boom(*_a: object, **_k: object) -> str:
        raise RuntimeError("r2 down")

    monkeypatch.setattr("app.services.storage.upload_object", boom)
    monkeypatch.setattr(
        "app.services.storage.R2UsageService",
        lambda *_a, **_k: MagicMock(usage=AsyncMock(return_value=R2Usage(id="a"))),
    )
    image = GeneratedImage(content=b"png", content_type="image/png", source_url="", metadata={})
    url = await store_image(
        job_id="local1",
        image=image,
        cfg=cfg,
        cipher=cipher,
        media_dir=tmp_path,
        redis=_IncrRedis(),  # type: ignore[arg-type]
    )
    assert url == "/api/media/local1/0"
    assert (tmp_path / "local1" / "0.png").read_bytes() == b"png"
