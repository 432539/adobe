from pathlib import Path

import pytest

from app.accounts.cookie_loader import CookieFileError, load_cookie_file, parse_cookie_text


def test_load_cookie_file_returns_only_safe_metadata(tmp_path: Path) -> None:
    secret = "ims_sid=secret-value; aux_sid=another-secret; locale=en_US"
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(secret + "\n", encoding="utf-8")

    records = load_cookie_file(cookie_file)

    assert len(records) == 1
    assert records[0].value == secret
    assert records[0].identity is None
    assert records[0].has_ims_sid is True
    assert secret not in repr(records[0])
    assert "secret-value" not in str(records[0].safe_summary())
    assert records[0].safe_summary()["cookie_count"] == 3


def test_email_prefix_is_stripped_and_matches_bare_cookie() -> None:
    cookie = "ims_sid=secret-value; aux_sid=another-secret; locale=en_US"
    prefixed = f"ada@example.com----{cookie}"
    with_prefix = parse_cookie_text(prefixed)
    bare = parse_cookie_text(cookie)

    assert with_prefix[0].identity == "ada@example.com"
    assert with_prefix[0].value == cookie
    assert with_prefix[0].fingerprint == bare[0].fingerprint
    assert "ada@example.com" not in repr(with_prefix[0])
    assert "secret-value" not in repr(with_prefix[0])
    assert with_prefix[0].safe_summary()["has_identity"] is True


def test_load_cookie_file_rejects_invalid_line(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("not-a-cookie\n", encoding="utf-8")

    with pytest.raises(CookieFileError, match="invalid Cookie header"):
        load_cookie_file(cookie_file)


def test_parse_rejects_cookie_without_ims_sid() -> None:
    with pytest.raises(CookieFileError, match="missing ims_sid"):
        parse_cookie_text("locale=en_US; aux_sid=another-secret")


def test_load_cookie_file_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CookieFileError, match="cookie file not found"):
        load_cookie_file(tmp_path / "missing.txt")
