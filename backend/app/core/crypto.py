"""Field-level encryption for secrets that must never be stored in plaintext.

Sensitive columns (proxy passwords, R2 secret keys, CloakBrowser licence, upstream
cookies) are wrapped with Fernet before they reach the database. The key comes from
``FIELD_ENCRYPTION_KEY``; in ``dev`` we derive a stable key from ``APP_SECRET_KEY`` so
local setups work out of the box, but production must supply a real key.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings

logger = logging.getLogger(__name__)

_PREFIX = "enc:v1:"


class FieldCipher:
    """Encrypt/decrypt short secrets. Ciphertext is prefixed so plaintext leaks are obvious."""

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_settings(cls, settings: Settings) -> FieldCipher:
        raw = settings.field_encryption_key.strip()
        if raw and not raw.startswith("change-me"):
            try:
                return cls(raw.encode())
            except ValueError as exc:  # pragma: no cover - misconfiguration path
                raise RuntimeError(
                    "FIELD_ENCRYPTION_KEY must be a urlsafe base64 Fernet key"
                ) from exc
        if settings.app_env == "prod":
            raise RuntimeError("FIELD_ENCRYPTION_KEY is required in prod")
        logger.warning("FIELD_ENCRYPTION_KEY unset; deriving dev-only key from APP_SECRET_KEY")
        digest = hashlib.sha256(settings.app_secret_key.encode()).digest()
        return cls(base64.urlsafe_b64encode(digest))

    def encrypt(self, plaintext: str) -> str:
        return _PREFIX + self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        if not token.startswith(_PREFIX):
            raise ValueError("value is not an encrypted field")
        try:
            return self._fernet.decrypt(token[len(_PREFIX) :].encode()).decode()
        except InvalidToken as exc:
            raise ValueError("cannot decrypt field: key mismatch or corrupted data") from exc

    @staticmethod
    def is_encrypted(value: str | None) -> bool:
        return bool(value) and str(value).startswith(_PREFIX)


def generate_key() -> str:
    """Ops helper: ``python -c "from app.core.crypto import generate_key as g; print(g())"``."""
    return Fernet.generate_key().decode()
