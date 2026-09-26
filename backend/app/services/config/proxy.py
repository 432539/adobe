"""Residential sticky proxy helpers.

Supplier template (ArxLabs style)::

    {username}-region-{COUNTRY}-sid-{SID}-t-{MINUTES}:{password}@{host}:{port}

Every ARP mint gets a fresh ``sid`` so different browsers never share an egress IP, and
the same expanded URL is handed to the submit path so *mint egress == submit egress*.
Credentials never reach logs: use :func:`masked_url` or ``egress_id`` for diagnostics.
"""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from dataclasses import dataclass
from urllib.parse import quote

from pydantic import BaseModel

from app.services.config.schema import (
    ProxyConfig,
    ProxyConfigUpdate,
    reject_expanded_username,
    reject_short_sticky,
)

# Unambiguous alphabet (no 0/O/1/I/l) – matches what the reference harvester used.
_SID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
_USER_TEMPLATE = re.compile(
    r"^(?P<user>.+?)-region-(?P<country>[A-Za-z]{2,3})-sid-(?P<sid>[A-Za-z0-9]+)-t-(?P<minutes>\d+)$"
)
_SCHEME = re.compile(r"^(?P<scheme>https?|socks5h?)://", re.IGNORECASE)


def random_sid(length: int = 8) -> str:
    return "".join(secrets.choice(_SID_ALPHABET) for _ in range(max(4, length)))


def wire_scheme(scheme: str) -> str:
    """DNS must go through the proxy or the sticky egress is a lie. ``socks5`` → ``socks5h``."""
    return "socks5h" if scheme == "socks5" else scheme


def session_username(cfg: ProxyConfig | ProxyConfigUpdate, sid: str) -> str:
    return f"{cfg.username}-region-{cfg.country.upper()}-sid-{sid}-t-{cfg.sticky_minutes}"


@dataclass(frozen=True, slots=True)
class ProxySession:
    """One expanded sticky session. ``url`` carries credentials – never log it."""

    url: str
    sid: str
    masked: str

    @property
    def egress_id(self) -> str:
        return f"sid-{self.sid}"


def build_session(
    cfg: ProxyConfig | ProxyConfigUpdate,
    password: str,
    sid: str | None = None,
    *,
    arp_ttl_seconds: int | None = None,
) -> ProxySession:
    if not cfg.host or not cfg.username:
        raise ValueError("proxy host and username are required")
    reject_expanded_username(cfg.username)
    if arp_ttl_seconds is not None:
        reject_short_sticky(cfg.sticky_minutes, arp_ttl_seconds, configured=True)
    sid = sid or random_sid(cfg.sid_length)
    user = session_username(cfg, sid)
    scheme = wire_scheme(cfg.scheme)
    url = f"{scheme}://{quote(user, safe='')}:{quote(password, safe='')}@{cfg.host}:{cfg.port}"
    masked = f"{scheme}://{user}:••••@{cfg.host}:{cfg.port}"
    return ProxySession(url=url, sid=sid, masked=masked)


def masked_url(url: str) -> str:
    """Strip credentials from any proxy URL for logging."""
    if "@" not in url:
        return url
    head, tail = url.rsplit("@", 1)
    scheme = head.split("://", 1)[0] + "://" if "://" in head else ""
    return f"{scheme}••••@{tail}"


class ParsedProxy(BaseModel):
    scheme: str = "http"
    host: str
    port: int
    username: str
    password: str | None = None
    country: str | None = None
    sticky_minutes: int | None = None
    sid_length: int | None = None


def parse_proxy_line(raw: str) -> ParsedProxy | None:
    """Mirror of the panel-side parser so imports / CLI get identical results."""
    value = raw.strip()
    if not value:
        return None
    scheme = "http"
    if m := _SCHEME.match(value):
        scheme = "socks5" if m.group("scheme").lower().startswith("socks") else "http"
        value = value[m.end() :]

    if "@" in value:
        cred, addr = value.rsplit("@", 1)
        if ":" not in cred:
            return None
        username, password = cred.split(":", 1)
        if ":" not in addr:
            return None
        host, port_text = addr.rsplit(":", 1)
    else:
        parts = value.split(":")
        if len(parts) < 4:
            return None
        host, port_text, username = parts[0], parts[1], parts[2]
        password = ":".join(parts[3:])

    if not host or not username or not port_text.isdigit():
        return None
    port = int(port_text)
    if not 1 <= port <= 65535:
        return None

    parsed = ParsedProxy(
        scheme=scheme, host=host, port=port, username=username, password=password or None
    )
    if m := _USER_TEMPLATE.match(username):
        parsed.username = m.group("user")
        parsed.country = m.group("country").upper()
        parsed.sid_length = len(m.group("sid"))
        parsed.sticky_minutes = int(m.group("minutes"))
    return parsed


# --------------------------------------------------------------------------- probe
class ProxyTestResult(BaseModel):
    ok: bool
    proxy_masked: str
    egress_ip: str | None = None
    country: str | None = None
    latency_ms: int | None = None
    error: str | None = None


def _probe_sync(
    session: ProxySession, probe_url: str, timeout: float, impersonate: str
) -> ProxyTestResult:
    # curl_cffi is blocking; callers run this in a worker thread.
    from curl_cffi import requests as cffi_requests

    started = time.perf_counter()
    try:
        response = cffi_requests.get(
            probe_url,
            proxies={"http": session.url, "https": session.url},
            timeout=timeout,
            impersonate=impersonate,
        )
        latency = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            return ProxyTestResult(
                ok=False,
                proxy_masked=session.masked,
                latency_ms=latency,
                error=f"probe returned HTTP {response.status_code}",
            )
        body = json.loads(response.content or b"{}")
        ip = body.get("ip") or body.get("query") or body.get("origin")
        country = body.get("country") or body.get("countryCode") or body.get("country_code")
        return ProxyTestResult(
            ok=True,
            proxy_masked=session.masked,
            egress_ip=str(ip) if ip else None,
            country=str(country).upper() if country else None,
            latency_ms=latency,
        )
    except Exception as exc:  # noqa: BLE001 - surface any transport error to the panel
        latency = int((time.perf_counter() - started) * 1000)
        # Never echo the exception verbatim: curl may embed the proxy URL (with creds).
        reason = type(exc).__name__
        detail = str(exc)
        if "@" in detail:
            detail = masked_url(detail)
        return ProxyTestResult(
            ok=False,
            proxy_masked=session.masked,
            latency_ms=latency,
            error=f"{reason}: {detail[:160]}",
        )


async def test_proxy(
    cfg: ProxyConfig | ProxyConfigUpdate,
    password: str,
    *,
    probe_url: str,
    timeout_seconds: float,
    impersonate: str = "chrome146",
    sid: str | None = None,
) -> ProxyTestResult:
    session = build_session(cfg, password, sid=sid)
    return await asyncio.to_thread(_probe_sync, session, probe_url, timeout_seconds, impersonate)
