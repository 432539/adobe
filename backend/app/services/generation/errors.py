"""User-facing generation errors. Never mention Adobe / Firefly / upstream hosts."""

from __future__ import annotations

import re

_UPSTREAM_WORDS = re.compile(
    r"(adobe|firefly|ims|gemini-flash|firefly-3p|bks-epo)",
    re.IGNORECASE,
)

_BY_CODE: dict[str, str] = {
    "content_rejected": "451 违禁词",
    "arp_rejected": "408 异常",
    "rate_limited": "429 频繁",
    "no_account": "暂无可用账号",
    "arp_empty": "票据不足，请稍后重试",
    "auth_failed": "账号鉴权失败",
    "identity_rejected": "账号被拒绝",
    "bad_request": "请求参数无效",
    "resolution_unsupported": "该分辨率不受支持",
    "proxy_tls": "连接异常",
    "poll_timeout": "生成超时",
    "job_failed": "生成失败",
    "download_failed": "结果下载失败",
    "upstream_error": "生成失败",
}


def public_fail_message(code: str, status_code: int = 0, raw: str = "") -> str:
    if code == "content_rejected" or status_code == 451:
        return "451 违禁词"
    if code == "arp_rejected" or status_code == 408:
        return "408 异常"
    if code == "rate_limited" or status_code == 429:
        return "429 频繁"
    mapped = _BY_CODE.get(code)
    if mapped:
        if code == "bad_request":
            cleaned = _strip_upstream(raw)
            if cleaned and not _UPSTREAM_WORDS.search(cleaned):
                return cleaned[:200]
        return mapped
    cleaned = _strip_upstream(raw)
    return cleaned[:200] if cleaned else "生成失败"


def _strip_upstream(raw: str) -> str:
    text = _UPSTREAM_WORDS.sub("", raw or "")
    return re.sub(r"\s{2,}", " ", text).strip(" -:|")
