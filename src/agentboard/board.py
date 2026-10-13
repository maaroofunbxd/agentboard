"""The board between agent sessions: the `agents` stream of the store (store.py; the plain file: agents.jsonl in
the board folder, config.Settings.board_dir).

Not a record of changes, coordination: claims (I'm on X), hand-offs, posts to another repo's sessions (`to`), a
`reply` on a post's thread (`ref`), and the `done` that closes one. board.jsonl, its old name, is still read. Every
line says when, who (`by`, the OS / GitHub user), `actor` and `session` (identity.py), the repo and branch it was
posted from. Writing never fails the command it is part of.
"""
from __future__ import annotations

import datetime
import getpass
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from agentboard import config, identity
from agentboard.store import FileStore, Store

AGENTS = "agents"
KINDS = ("claim", "handoff", "post", "done", "reply")
POST_TTL = datetime.timedelta(days=14)  # a post nobody closed drops off the board after this
STALE_AFTER = datetime.timedelta(hours=24)


def board_dir() -> Optional[Path]:
    return config.settings.board_dir()


def who() -> dict:
    """The fields a board line starts with, when the program gives none (config.Settings.line_fields)."""
    out: dict[str, Any] = {
        "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by": os.environ.get("GITHUB_ACTOR") or getpass.getuser(),
        "actor": identity.actor(),
    }
    sid = identity.session_id()
    if sid:
        out["session"] = sid
    return out


def store() -> Optional[Store]:
    """Where the lines are kept (store.py): the configured store, else the plain file in board_dir(); None = off."""
    if config.settings.store is not None:
        return config.settings.store()
    folder = board_dir()
    return FileStore(folder) if folder is not None else None


def _append(entry: dict) -> None:
    where = store()
    if where is None:
        return
    fields = config.settings.line_fields
    where.append(AGENTS, {**(fields() if fields else who()), **entry})


def read(stream: str = AGENTS) -> list[dict]:
    where = store()
    return [{**row, "_stream": stream} for row in where.lines(stream)] if where else []


def post(kind: str, text: str, ref: Optional[str] = None, commands: list[str] | None = None, to: Optional[str] = None,
         **fields: Any) -> dict:
    """One line in agents.jsonl, with the repo and branch it was posted from (which session is on what).
    A `post` is addressed: `to` is a repo name (api, web, ...) or `all`."""
    if kind not in KINDS:
        raise ValueError(f"kind is one of {', '.join(KINDS)}, not {kind!r}")
    if kind == "post" and not to:
        raise ValueError("a post is for a repo's sessions: --to REPO (api, web, ...) or --to all")
    entry = {"kind": kind, "id": uuid.uuid4().hex[:6], "text": text, "repo": identity.here(), "session": identity.session_id(), "to": to,
             "branch": identity.git_here("branch", "--show-current") or None, "ref": ref, "commands": commands or None, **fields}
    entry = {k: v for k, v in entry.items() if v}
    _append(entry)
    return entry


def agent_posts() -> list[dict]:
    """agents.jsonl, plus board.jsonl from before the rename, oldest first."""
    return sorted(read("board") + read(AGENTS), key=lambda r: r.get("ts", ""))


def agents_view(rows: list[dict], now: Optional[datetime.datetime] = None, repo: Optional[str] = None) -> dict:
    """Open claims (stale after STALE_AFTER without a done), open hand-offs of the last week, and open posts of
    the last POST_TTL. With `repo`, only the posts addressed to it (or to `all`); `elsewhere` counts the rest."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    stale_ts = (now - STALE_AFTER).strftime("%Y-%m-%dT%H:%M:%SZ")
    week_ts = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ttl_ts = (now - POST_TTL).strftime("%Y-%m-%dT%H:%M:%SZ")
    closed = {r.get("ref") for r in rows if r.get("kind") == "done"}
    claims = [{**r, "stale": r.get("ts", "") < stale_ts} for r in rows
              if r.get("kind") == "claim" and r.get("id") not in closed]
    handoffs = [r for r in rows if r.get("kind") == "handoff" and r.get("id") not in closed and r.get("ts", "") >= week_ts]
    every = [r for r in rows if r.get("kind") == "post" and r.get("id") not in closed and r.get("ts", "") >= ttl_ts]
    posts = [r for r in every if repo is None or r.get("to") in (repo, "all")]
    view = {"repo": repo, "claims": claims, "handoffs": handoffs, "posts": posts, "elsewhere": len(every) - len(posts)}
    if repo:
        view["replies"] = replies(rows, repo, since=week_ts)
    return view


def replies(rows: list[dict], repo: str, since: str = "") -> list[dict]:
    """Answers on the threads this repo is part of, since `since`: on this repo's posts, a `done` or `reply` from
    another session; on a post to this repo, a `reply` from the session that asked (a follow-up). Each is the post,
    with the line's text as `reply` and the line as `replied`. How each side of a conversation sees the other."""
    posts = {r["id"]: r for r in rows if r.get("kind") == "post" and r.get("id")}
    out = []
    for d in rows:
        asked = posts.get(d.get("ref")) if d.get("kind") in ("done", "reply") else None
        if not asked or d.get("ts", "") <= since:
            continue
        by_asker = (d.get("session"), d.get("repo")) == (asked.get("session"), asked.get("repo"))
        if (asked.get("repo") == repo and not by_asker) or (d.get("kind") == "reply" and by_asker and asked.get("to") == repo):
            out.append({**asked, "reply": d.get("text", ""), "replied": d})
    return out


def thread(rows: list[dict], ref: str) -> list[dict]:
    """A post and every `reply` and `done` on it, oldest first; [] when no post is `ref`."""
    head = [r for r in rows if r.get("kind") == "post" and r.get("id") == ref]
    return head + [r for r in rows if r.get("ref") == ref and r.get("kind") in ("reply", "done")] if head else []


def _paths_overlap(a: str, b: str) -> bool:
    a, b = a.strip("/"), b.strip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def claim_overlaps(rows: list[dict], repo: Optional[str], paths: list[str]) -> list[dict]:
    """Open claims in `repo` that name a path overlapping one of `paths` (a folder overlaps what's in it)."""
    closed = {r.get("ref") for r in rows if r.get("kind") == "done"}
    return [r for r in rows if r.get("kind") == "claim" and r.get("id") not in closed and r.get("repo") == repo
            and any(_paths_overlap(a, b) for a in r.get("paths") or [] for b in paths)]


# ---- the nudge: a line on stderr when the board has something new for a session that already read it -------------


def _seen() -> dict:
    try:
        data = json.loads(config.settings.seen_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def mark_seen(session: Optional[str], ts: Optional[str] = None) -> None:
    """Remember that `session` has seen the board up to `ts` (now): the nudge only tells it about newer lines.
    Entries older than 30 days are dropped. Never raises."""
    if not session:
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    old = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {k: v for k, v in _seen().items() if isinstance(v, str) and v >= old}
    data[session] = ts or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        path = config.settings.seen_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def board_news(rows: list[dict], repo: str, session: str, since: str) -> list[dict]:
    """What other sessions put on the board after `since` that the sessions of `repo` should know: posts to it (or
    to all), claims and hand-offs from its other sessions, and replies on its threads."""
    news = []
    for r in rows:
        if r.get("ts", "") <= since or (r.get("session") == session and r.get("repo") == repo):
            continue
        kind = r.get("kind")
        if (kind == "post" and r.get("to") in (repo, "all")) or (kind in ("claim", "handoff") and r.get("repo") == repo):
            news.append(r)
    news += [x["replied"] for x in replies(rows, repo, since=since)]
    return sorted(news, key=lambda r: r.get("ts", ""))


def board_asks(rows: list[dict], repo: str, session: str, since: str) -> list[dict]:
    """The part of board_news a session should stop and tell its user about (what `agents wait` wakes it for): posts
    to the repo still open, hand-offs still open, replies to its posts. Not others' claims: those matter only when
    you claim something yourself, and `claim -p` warns then."""
    closed = {r.get("ref") for r in rows if r.get("kind") == "done"}
    return [r for r in board_news(rows, repo, session, since)
            if r.get("kind") in ("done", "reply") or (r.get("kind") in ("post", "handoff") and r.get("id") not in closed)]


def board_mtime() -> float:
    """When the board last changed (0 when there is none yet): `agents wait` re-reads it only then."""
    where = store()
    return where.changed(AGENTS) if where else 0.0


def nudge(argv: list[str]) -> None:
    """After an agent session's run of the program: one line on stderr if the board got something for its repo since
    the session last looked (`agents status`, or the last nudge). A session that never read the board gets nothing
    here: reading it at the start is the rule. Never raises."""
    session = identity.session_id()
    if not session or (argv[:1] == ["agents"]):
        return
    try:
        since = _seen().get(session)
        repo = identity.here() if since else None
        if not repo:
            return
        news = board_news(agent_posts(), repo, session, since)
        if not news:
            return
        from collections import Counter

        counts = Counter("reply" if r.get("kind") in ("done", "reply") else r.get("kind") for r in news)
        kinds = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
        print(f"[board] new for {repo} since {since}: {kinds}. Read it: {config.settings.command} status", file=sys.stderr)
        mark_seen(session, news[-1].get("ts"))
    except Exception:  # noqa: BLE001 - a nudge must never break the command it follows
        return
