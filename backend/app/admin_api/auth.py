"""Internal-token gate for harvester ↔ admin-api.

Never expose these routes on the public gateway.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Header, Request

from app.core.config import Settings
from app.core.errors import AppError


async def require_internal_token(
    request: Request,
    token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> None:
    settings: Settings = request.app.state.settings
    if token is None or not hmac.compare_digest(token, settings.arp_internal_token):
        raise AppError(
            code="internal_auth_failed",
            message="invalid internal credentials",
            http_status=401,
        )
