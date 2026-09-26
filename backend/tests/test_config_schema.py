import pytest
from cryptography.fernet import Fernet

from app.core.crypto import FieldCipher
from app.core.errors import AppError
from app.services.config import pricing
from app.services.config.proxy import build_session, masked_url, parse_proxy_line, random_sid
from app.services.config.schema import (
    ProxyConfig,
    ProxyConfigUpdate,
    R2AccountUpdate,
    SystemConfig,
    SystemConfigUpdate,
    apply_update,
    default_config,
    ensure_pricing_catalog,
    hydrate_stored_config,
    mask_endpoint,
    reject_short_sticky,
    to_view,
)


@pytest.fixture
def cipher() -> FieldCipher:
    return FieldCipher(Fernet.generate_key())


def _update(**overrides: object) -> SystemConfigUpdate:
    base = default_config().model_dump(
        exclude={"proxy", "cloakbrowser_license_key_enc", "r2_accounts"}
    )
    base.update(overrides)
    return SystemConfigUpdate.model_validate(base)


# --------------------------------------------------------------------------- secrets
def test_apply_update_encrypts_and_masks_secrets(cipher: FieldCipher) -> None:
    update = _update(
        proxy=ProxyConfigUpdate(
            host="us.arxlabs.io", port=3010, username="p9mx", password="s3cret", country="sg"
        ),
        cloakbrowser_license_key="cb_cb1c8e11b3044208963dbe919132f2f5",
        r2_accounts=[
            R2AccountUpdate(
                name="cf1",
                endpoint="https://ffa7964b824a013739abcdef.r2.cloudflarestorage.com",
                bucket="media",
                access_key_id="AKIA1234567890ee82",
                secret_access_key="verysecret",
            )
        ],
    )
    stored = apply_update(default_config(), update, cipher)

    assert stored.proxy.password_enc and stored.proxy.password_enc.startswith("enc:v1:")
    assert "s3cret" not in stored.model_dump_json()
    assert "verysecret" not in stored.model_dump_json()
    assert "cb_cb1c8e11" not in stored.model_dump_json()
    assert stored.proxy.country == "SG"
    assert cipher.decrypt(stored.proxy.password_enc) == "s3cret"

    view = to_view(stored, cipher)
    assert view.proxy.password_set is True
    assert "s3cret" not in view.model_dump_json()
    assert (
        view.cloakbrowser_license_key_masked.startswith("cb_")
        and "••••" in view.cloakbrowser_license_key_masked
    )
    assert view.r2_accounts[0].key_suffix == "ee82"
    assert view.r2_accounts[0].endpoint_masked == mask_endpoint(stored.r2_accounts[0].endpoint)
    assert view.r2_accounts[0].prefix == stored.r2_accounts[0].prefix
    assert (
        "cloudflarestorage" not in view.r2_accounts[0].endpoint_masked
        or "…" in view.r2_accounts[0].endpoint_masked
    )


def test_apply_update_keeps_secrets_when_omitted_or_masked(cipher: FieldCipher) -> None:
    first = apply_update(
        default_config(),
        _update(
            proxy=ProxyConfigUpdate(host="h", username="u", password="pw1"),
            cloakbrowser_license_key="lic-1",
            r2_accounts=[
                R2AccountUpdate(
                    name="cf1",
                    endpoint="https://a.r2.cloudflarestorage.com",
                    bucket="b",
                    access_key_id="AK1",
                    secret_access_key="SK1",
                )
            ],
        ),
        cipher,
    )
    account_id = first.r2_accounts[0].id
    view = to_view(first, cipher)

    # Panel echoes the masked view back with no plaintext secrets.
    second = apply_update(
        first,
        _update(
            proxy=ProxyConfigUpdate(**view.proxy.model_dump()),
            cloakbrowser_license_key_masked=view.cloakbrowser_license_key_masked,
            r2_accounts=[
                R2AccountUpdate(**{**view.r2_accounts[0].model_dump(), "name": "cf1-renamed"})
            ],
        ),
        cipher,
    )
    assert second.proxy.password_enc == first.proxy.password_enc
    assert second.cloakbrowser_license_key_enc == first.cloakbrowser_license_key_enc
    assert second.r2_accounts[0].id == account_id
    assert second.r2_accounts[0].name == "cf1-renamed"
    assert second.r2_accounts[0].endpoint == "https://a.r2.cloudflarestorage.com"
    assert second.r2_accounts[0].secret_key_enc == first.r2_accounts[0].secret_key_enc


def test_removed_r2_account_is_dropped(cipher: FieldCipher) -> None:
    first = apply_update(
        default_config(),
        _update(
            r2_accounts=[R2AccountUpdate(name="cf1", endpoint="https://a.example", bucket="b")]
        ),
        cipher,
    )
    second = apply_update(first, _update(r2_accounts=[]), cipher)
    assert second.r2_accounts == []


def test_invalid_status_codes_rejected() -> None:
    with pytest.raises(ValueError):
        _update(retryable_status_codes="429,abc")


# --------------------------------------------------------------------------- proxy
def test_parse_supplier_line_extracts_template_parts() -> None:
    parsed = parse_proxy_line(
        "p9mx1124350-region-SG-sid-2fyNrACK-t-10:iw843jdsnb82@us.arxlabs.io:3010"
    )
    assert parsed is not None
    assert (parsed.host, parsed.port, parsed.username) == ("us.arxlabs.io", 3010, "p9mx1124350")
    assert parsed.password == "iw843jdsnb82"
    assert (parsed.country, parsed.sticky_minutes, parsed.sid_length) == ("SG", 10, 8)


def test_parse_variants() -> None:
    socks = parse_proxy_line("socks5://user:p@ss:w0rd@1.2.3.4:1080")
    assert socks is not None and socks.scheme == "socks5" and socks.password == "p@ss:w0rd"
    colon = parse_proxy_line("host.example:8080:user:pw")
    assert colon is not None and colon.username == "user" and colon.port == 8080
    assert parse_proxy_line("garbage") is None
    assert parse_proxy_line("user:pw@host:99999") is None


def test_build_session_uses_template_and_masks() -> None:
    cfg = ProxyConfigUpdate(
        host="us.arxlabs.io",
        port=3010,
        username="p9mx",
        country="JP",
        sticky_minutes=30,
        sid_length=8,
    )
    session = build_session(cfg, "pw:with@chars", sid="AbCdEfGh")
    assert (
        session.url
        == "http://p9mx-region-JP-sid-AbCdEfGh-t-30:pw%3Awith%40chars@us.arxlabs.io:3010"
    )
    assert session.masked == "http://p9mx-region-JP-sid-AbCdEfGh-t-30:••••@us.arxlabs.io:3010"
    assert session.egress_id == "sid-AbCdEfGh"
    assert "pw" not in masked_url(session.url)


def test_build_session_maps_socks5_to_socks5h() -> None:
    cfg = ProxyConfigUpdate(scheme="socks5", host="p.example", username="u", country="SG")
    session = build_session(cfg, "secret", sid="AbCdEfGh")
    assert session.url.startswith("socks5h://")
    assert session.masked.startswith("socks5h://")
    assert "secret" not in session.masked


def test_build_session_rejects_expanded_username() -> None:
    cfg = ProxyConfig(host="h", username="p9mx-region-SG-sid-AbCdEfGh-t-10")
    with pytest.raises(ValueError, match="供应商前缀"):
        build_session(cfg, "pw")


def test_two_sessions_get_distinct_sids() -> None:
    cfg = ProxyConfigUpdate(host="h", username="u", country="SG")
    a = build_session(cfg, "pw")
    b = build_session(cfg, "pw")
    assert a.sid != b.sid
    assert a.url != b.url


def test_expanded_username_rejected_on_update() -> None:
    with pytest.raises(ValueError, match="供应商前缀"):
        ProxyConfigUpdate(host="h", username="p9mx-region-SG-sid-AbCdEfGh-t-10")


def test_short_sticky_is_lifted_to_cover_ttl() -> None:
    update = _update(
        arp_ttl_seconds=300,
        proxy=ProxyConfigUpdate(
            host="us.arxlabs.io", username="p9mx", sticky_minutes=5, country="SG"
        ),
    )
    assert update.arp_ttl_seconds == 300
    assert update.proxy.sticky_minutes == 6


def test_reject_short_sticky_still_blocks_lease() -> None:
    with pytest.raises(ValueError, match="粘性会话必须长过票 TTL"):
        reject_short_sticky(5, 300, configured=True)


def test_short_sticky_allowed_when_proxy_empty() -> None:
    update = _update(arp_ttl_seconds=120, proxy=ProxyConfigUpdate(sticky_minutes=1))
    assert update.proxy.sticky_minutes == 1


def test_mint_interval_must_stay_under_ttl() -> None:
    with pytest.raises(ValueError, match="铸币间隔必须小于票据 TTL"):
        _update(mint_interval_seconds=120, arp_ttl_seconds=120)


def test_pool_target_must_cover_min_ready() -> None:
    with pytest.raises(ValueError, match="常备池目标必须"):
        _update(arp_min_ready=10, arp_pool_target=8)


def test_legacy_min_ready_hydrates_pool_target() -> None:
    cfg = SystemConfig.model_validate(hydrate_stored_config({"arp_min_ready": 10}))
    assert cfg.arp_min_ready == 10
    assert cfg.arp_pool_target == 10
    capped = SystemConfig.model_validate(hydrate_stored_config({"arp_min_ready": 99}))
    assert capped.arp_pool_target == 20
    assert capped.arp_min_ready == 20


def test_arp_max_uses_is_capped_at_ten() -> None:
    update = _update(arp_max_uses=20)
    assert update.arp_max_uses == 10
    loaded = SystemConfig.model_validate({**default_config().model_dump(), "arp_max_uses": 20})
    assert loaded.arp_max_uses == 10


def test_random_sid_shape() -> None:
    sid = random_sid(8)
    assert len(sid) == 8 and sid.isalnum()
    assert not set("0O1Il") & set(sid)
    assert random_sid(8) != sid


# --------------------------------------------------------------------------- pricing
def test_image_cost_by_tier_and_family() -> None:
    cfg = default_config()
    assert pricing.image_cost(cfg, "nano-banana-pro", "1K") == 10
    assert pricing.image_cost(cfg, "nano-banana-pro", "4k") == 20
    assert pricing.image_cost(cfg, "nano-banana-2", "2048px") == 12  # family fallback
    assert (
        pricing.image_cost(cfg, "gpt-image-2.5-sunburst", "weird") == 20
    )  # unknown → highest tier
    with pytest.raises(AppError):
        pricing.image_cost(cfg, "unknown-model", "1K")


def test_video_cost_per_second_vs_per_call() -> None:
    cfg = default_config()
    assert pricing.video_cost(cfg, "gemini-omni-flash", 8) == 80
    assert pricing.video_cost(cfg, "seedance-2.0", 8) == 160
    with pytest.raises(AppError):
        pricing.video_cost(cfg, "seedance-2.0", 0)
    assert pricing.format_credits(80) == "0.80"
    assert pricing.format_credits(-1205) == "-12.05"


def test_account_park_seconds_defaults_to_five_minutes() -> None:
    cfg = default_config()
    assert cfg.account_park_seconds == 300
    assert cfg.account_park_second_seconds == 600
    assert cfg.account_park_disable_seconds == 1800
    assert cfg.account_park_disable_after == 3
    assert cfg.account_408_observe_seconds == 1800
    assert cfg.account_408_block_after == 1
    assert cfg.blocked_408_models() == {"gpt-image-2.5-flare", "gpt-image-2.5-sunburst"}
    assert cfg.arp_bad_window_count == 3
    assert cfg.arp_bad_window_seconds == 60
    assert cfg.arp_bad_window_pause_seconds == 120
    assert cfg.user_concurrency_default == 2
    assert cfg.worker_concurrency == 32
    assert cfg.user_concurrency_default <= 200


def test_ensure_pricing_catalog_appends_missing_models() -> None:
    cfg = default_config()
    slim = cfg.model_copy(
        update={
            "image_pricing": cfg.image_pricing[:1],
            "video_pricing": [t for t in cfg.video_pricing if t.model_id == "gemini-omni-flash"],
        }
    )
    filled = ensure_pricing_catalog(slim)
    image_ids = [t.model_id for t in filled.image_pricing]
    video_ids = [t.model_id for t in filled.video_pricing]
    assert image_ids[0] == "nano-banana"
    assert "gpt-image-2.5-sunburst" in image_ids
    assert video_ids[0] == "gemini-omni-flash"
    assert "seedance-2.0-fast" in video_ids
    assert filled.image_pricing[0].tiers[0].price == slim.image_pricing[0].tiers[0].price
