"""Watch public repo stars and invite new stargazers to the private full-source repo.

Anyone who stars 432539/adobe is treated as authorized and invited to
432539/ad-xiaoguai. Personal private repos only allow write collaborators,
so the default permission is push.

  set STAR_GRANT_TOKEN=<github pat with repo admin on ad-xiaoguai>
  python scripts/star_grant.py --once
  python scripts/star_grant.py --watch

Token needs: read stargazers on the public repo, and invite collaborators on
the private repo. Classic PAT: `repo`. Fine-grained: adobe Metadata +
ad-xiaoguai Administration (invite collaborators).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PUBLIC_REPO = os.environ.get("STAR_GRANT_PUBLIC", "432539/adobe")
PRIVATE_REPO = os.environ.get("STAR_GRANT_PRIVATE", "432539/ad-xiaoguai")
PERMISSION = os.environ.get("STAR_GRANT_PERMISSION", "push")
API = "https://api.github.com"
STATE_PATH = Path(os.environ.get("STAR_GRANT_STATE", "secrets/star-grant-state.json"))


def token() -> str:
    value = os.environ.get("STAR_GRANT_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not value:
        raise SystemExit("缺少 STAR_GRANT_TOKEN（或 GITHUB_TOKEN）。不要写进仓库。")
    return value


def request(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ad-xiaoguai-star-grant",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        payload: object
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = raw.decode("utf-8", errors="replace")
        return exc.code, payload


def paginate(path: str) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        status, payload = request("GET", f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        if status != 200 or not isinstance(payload, list):
            raise SystemExit(f"GET {path} 失败 HTTP {status}: {payload}")
        if not payload:
            break
        items.extend(payload)
        if len(payload) < 100:
            break
        page += 1
    return items


def load_state() -> set[str]:
    if not STATE_PATH.is_file():
        return set()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return set(data.get("invited") or [])


def save_state(invited: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"invited": sorted(invited)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def already_on_private() -> set[str]:
    names: set[str] = set()
    for row in paginate(f"/repos/{PRIVATE_REPO}/collaborators"):
        login = row.get("login")
        if isinstance(login, str):
            names.add(login.lower())
    status, invitations = request("GET", f"/repos/{PRIVATE_REPO}/invitations")
    if status == 200 and isinstance(invitations, list):
        for row in invitations:
            invitee = row.get("invitee") or {}
            login = invitee.get("login")
            if isinstance(login, str):
                names.add(login.lower())
    return names


def grant_once() -> int:
    stargazers = paginate(f"/repos/{PUBLIC_REPO}/stargazers")
    stars = [row["login"] for row in stargazers if isinstance(row.get("login"), str)]
    owner = PRIVATE_REPO.split("/", 1)[0].lower()
    skip = already_on_private() | load_state() | {owner}
    invited = load_state()
    granted = 0
    print(f"公开仓库 Star {len(stars)} 人，私有仓已有/待接受 {len(skip)} 人")
    for login in stars:
        key = login.lower()
        if key in skip:
            continue
        status, payload = request(
            "PUT",
            f"/repos/{PRIVATE_REPO}/collaborators/{login}",
            {"permission": PERMISSION},
        )
        # User-owned private repos reject pull/read; retry as push.
        if status == 422 and "permission of read" in str(payload):
            status, payload = request(
                "PUT",
                f"/repos/{PRIVATE_REPO}/collaborators/{login}",
                {"permission": "push"},
            )
        if status in {201, 204}:
            invited.add(key)
            skip.add(key)
            granted += 1
            action = "已是协作者" if status == 204 else "已发邀请"
            print(f"  + {login}  {action}（{PERMISSION}）")
        else:
            print(f"  ! {login}  失败 HTTP {status}: {payload}")
    save_state(invited)
    print(f"本轮新增 {granted} 人")
    return granted


def main() -> None:
    parser = argparse.ArgumentParser(description="Star 公开仓 → 邀请进完整版私有仓")
    parser.add_argument("--once", action="store_true", help="只跑一轮")
    parser.add_argument("--watch", action="store_true", help="循环监视")
    parser.add_argument("--interval", type=int, default=120, help="监视间隔秒，默认 120")
    args = parser.parse_args()
    if not args.once and not args.watch:
        args.once = True
    if args.watch:
        print(f"监视 {PUBLIC_REPO} → {PRIVATE_REPO}，每 {args.interval}s")
        while True:
            try:
                grant_once()
            except SystemExit as exc:
                print(exc, file=sys.stderr)
            time.sleep(max(30, args.interval))
    else:
        grant_once()


if __name__ == "__main__":
    main()
