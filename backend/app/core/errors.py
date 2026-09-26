from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_SECRET_LOCS = frozenset(
    {"t", "token", "password", "proxy_url", "cookie", "authorization", "cookie_enc"}
)


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    http_status: int = 400
    detail: Any | None = None


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "请求参数无效"
    raw = str(errors[0].get("msg") or "请求参数无效")
    prefix = "Value error, "
    return raw[len(prefix) :] if raw.startswith(prefix) else raw


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, BaseException):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _safe_validation_detail(exc: RequestValidationError) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = tuple(err.get("loc") or ())
        secret = bool(loc) and str(loc[-1]).lower() in _SECRET_LOCS
        item: dict[str, Any] = {
            "type": err.get("type"),
            "loc": _jsonable(loc),
            "msg": err.get("msg"),
        }
        if secret:
            item["input"] = "[REDACTED]"
        elif "input" in err:
            item["input"] = _jsonable(err.get("input"))
        if "ctx" in err:
            item["ctx"] = _jsonable(err.get("ctx"))
        rows.append(item)
    return rows


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": _validation_message(exc),
                "detail": _safe_validation_detail(exc),
            },
        )
