"""Authenticated download of locally stored generation results."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select

from app.api.deps import SessionDep, UserDep
from app.core.errors import AppError
from app.models import GenerationJob

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("/{job_id}/{index}")
async def get_media(
    job_id: str, index: int, user: UserDep, session: SessionDep, request: Request
) -> Response:
    query = select(GenerationJob).where(GenerationJob.id == job_id)
    if user.role != "admin":
        query = query.where(GenerationJob.user_id == user.id)
    job = await session.scalar(query)
    if job is None:
        raise AppError(code="job_not_found", message="任务不存在", http_status=404)
    if not 0 <= index < max(len(job.result_urls), 1):
        raise AppError(code="media_not_found", message="结果不存在", http_status=404)
    if job.result_urls and (
        job.result_urls[index].startswith("http://")
        or job.result_urls[index].startswith("https://")
    ):
        return RedirectResponse(job.result_urls[index], status_code=302)
    folder = Path(request.app.state.settings.media_dir) / job_id
    for suffix in ("png", "jpg", "webp", "mp4"):
        path = folder / f"{index}.{suffix}"
        if path.is_file():
            ctype = "image/png"
            meta = folder / f"{index}.ctype"
            if meta.is_file():
                ctype = meta.read_text(encoding="utf-8").strip() or ctype
            return FileResponse(path, media_type=ctype)
    raise AppError(code="media_not_found", message="结果文件不存在", http_status=404)
