"""Password hashing and API-key derivation. Pure functions, no IO."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_PREFIX = "sk-"
_KEY_RANDOM_BYTES = 30  # → 40 urlsafe chars


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    salt_b64 = base64.urlsafe_b64encode(salt).decode()
    digest_b64 = base64.urlsafe_b64encode(digest).decode()
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt_b64}${digest_b64}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, n, r, p, salt_b64, digest_b64 = encoded.split("$")
        if algo != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        expected = base64.urlsafe_b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def generate_api_key() -> str:
    return _KEY_PREFIX + base64.urlsafe_b64encode(
        secrets.token_bytes(_KEY_RANDOM_BYTES)
    ).decode().rstrip("=")


def api_key_prefix(key: str) -> str:
    """Display form ``sk-abcd…``: enough to recognise, useless to guess."""
    return key[:10]


def hash_api_key(key: str, pepper: str) -> str:
    """HMAC with the server secret: DB leak alone cannot recover or forge keys."""
    return hmac.new(pepper.encode(), key.encode(), hashlib.sha256).hexdigest()


def looks_like_api_key(value: str) -> bool:
    return value.startswith(_KEY_PREFIX) and len(value) >= 20
