from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.admin_api.auth import require_internal_token
from app.admin_api.store import arp_store_for, arp_store_from, pulse_harvester
from app.api.deps import get_config_store
from app.arp.models import ArpInvalidateRequest, ArpPublishRequest

router = APIRouter(prefix="/admin-api/adobe/arp", tags=["internal-arp"])


@router.post("")
async def publish(
    payload: ArpPublishRequest,
    request: Request,
    _auth: Annotated[None, Depends(require_internal_token)],
) -> dict[str, object]:
    ids = await (await arp_store_for(request)).publish(payload.tokens)
    return {"ok": True, "published": len(ids), "ids": ids}


@router.get("")
async def health(
    request: Request,
    _auth: Annotated[None, Depends(require_internal_token)],
) -> dict[str, object]:
    cfg = await get_config_store(request).load()
    store = arp_store_from(request, cfg)
    await pulse_harvester(store, cfg.mint_interval_seconds)
    result = await store.health()
    return {"ok": True, **result}


@router.post("/invalidate")
async def invalidate(
    payload: ArpInvalidateRequest,
    request: Request,
    _auth: Annotated[None, Depends(require_internal_token)],
) -> dict[str, object]:
    removed = await (await arp_store_for(request)).invalidate(payload.id)
    return {"ok": True, "removed": removed}
