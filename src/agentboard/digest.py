"""Open posts on repos with no live session; optional pending log for the next session."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from agentboard import board, config, worktrees

PENDING = "pending"
STATE = "digest-state.json"


def agents_dir() -> Path:
    return config.settings.agents_dir()


def state_path() -> Path:
    return agents_dir() / STATE


def load_state() -> dict:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(data: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def pending_dir() -> Path:
    return agents_dir() / PENDING


def open_posts(rows: list[dict]) -> list[dict]:
    closed = {r.get("ref") for r in rows if r.get("kind") == "done"}
    now = datetime.datetime.now(datetime.timezone.utc)
    ttl = (now - board.POST_TTL).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for r in rows:
        if r.get("kind") != "post" or r.get("id") in closed:
            continue
        if r.get("ts", "") < ttl:
            continue
        out.append(r)
    return sorted(out, key=lambda r: r.get("ts", ""))


def offline_inbox(rows: list[dict]) -> dict[str, list[dict]]:
    """Posts to each repo that has no live session."""
    by_repo: dict[str, list[dict]] = {}
    for r in open_posts(rows):
        to = r.get("to")
        if not to or to == "all":
            continue
        by_repo.setdefault(to, []).append(r)
    roots = worktrees.repo_roots(rows)
    offline: dict[str, list[dict]] = {}
    for repo, posts in sorted(by_repo.items()):
        if repo not in roots:
            continue
        if board.presence(rows, repo)["live"]:
            continue
        offline[repo] = posts
    return offline


def write_pending(rows: list[dict], since: str) -> list[dict]:
    """Append new post ids for offline repos to ~/.agents/pending/<repo>.jsonl."""
    pending = pending_dir()
    pending.mkdir(parents=True, exist_ok=True)
    written: list[dict] = []
    for repo, posts in offline_inbox(rows).items():
        path = pending / f"{repo}.jsonl"
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        seen = {line.split('"id": "', 1)[1][:6] for line in existing.splitlines() if '"id": "' in line}
        chunk = existing
        for r in posts:
            if since and r.get("ts", "") <= since:
                continue
            pid = r.get("id")
            if not pid or pid in seen:
                continue
            chunk += json.dumps(r, ensure_ascii=False) + "\n"
            seen.add(pid)
            written.append(r)
        if chunk != existing:
            path.write_text(chunk, encoding="utf-8")
    return written


def run(*, record_pending: bool = False) -> dict:
    rows = board.agent_posts()
    offline = offline_inbox(rows)
    state = load_state()
    since = state.get("last_run") or ""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pending_n = 0
    if record_pending:
        pending_n = len(write_pending(rows, since))
    save_state({**state, "last_run": now})
    return {
        "at": now,
        "offline": {
            repo: [{"id": r["id"], "ts": r.get("ts"), "from": r.get("repo"), "text": (r.get("text") or "")[:240]} for r in posts]
            for repo, posts in offline.items()
        },
        "pending_written": pending_n,
    }
