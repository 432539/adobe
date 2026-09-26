from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SystemSetting(TimestampMixin, Base):
    """Key → JSON document. Hot config lives here so it can change without redeploy.

    Secrets inside the document are already Fernet-encrypted by the service layer;
    this table never sees plaintext credentials.
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
