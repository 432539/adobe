import logging
import re
from collections.abc import Mapping
from typing import Any

_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,]+"),
    re.compile(r"(?i)(cookie\s*[:=]\s*)[^\r\n]+"),
    re.compile(r"(?i)(x-internal-token\s*[:=]\s*)[^\s,]+"),
    re.compile(r"(?i)(https?://)[^/@:\s]+:[^/@\s]+@"),
    re.compile(r"(?i)(socks5h?://)[^/@:\s]+:[^/@\s]+@"),
)


def redact(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for pattern in _SENSITIVE_PATTERNS:
            if "://" in pattern.pattern:
                result = pattern.sub(r"\1[REDACTED]@", result)
            else:
                result = pattern.sub(r"\1[REDACTED]", result)
        return result
    if isinstance(value, Mapping):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.msg)
        record.args = redact(record.args)
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
