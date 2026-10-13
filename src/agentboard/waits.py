"""Open items: what a piece of work still waits on, who must act, and what it unblocks. Stdlib only: the caller
passes in where the work items are (branch names and their checkouts), how to read the agents board, and where to keep
local state, and names its own commands with configure() (the texts say `waits add` / `waits` / `waits done` until then).

Each work item (a ticket branch, say) keeps its open items in a plain file next to its record, on its branch:
`records/<record>.waits.jsonl`, one JSON object per line (id, text, on, who, unblocks, added, by, done, done_note).
The wrapper's commands write it and commit it; any agent or person reads it with them (or the file itself). No agent
tool is involved.

What an item waits on (`--on`) is something checked automatically:

  gh:OWNER/REPO#N   a PR (reviewed, approved, merged) or an issue (closed), through the gh login
  board:ID          a post, hand-off or claim on the agents board (replied, answered / closed)
  date:ISO          a deadline (due within 48h, passed); no timezone = local time
  user              a decision of the user's: the text is the question
  manual            nothing checks it; it stays until it is closed by hand (`waits done ID`)

Checks fail soft: no network or no gh login shows the item as unchecked, the rest still shows.

What the checks last saw is local to this machine, not to a branch (a state file the caller names), per item its
state, when that state last changed, and the state the last change DM told you about (the DM is only about the items
whose state moved since then).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

Board = Callable[[], list]  # returns the board's rows (dicts with kind, id, ref, to, repo, text)

SUFFIX = ".waits.jsonl"
KINDS = ("gh", "board", "date", "user", "manual")
GH = re.compile(r"^gh:([\w.-]+/[\w.-]+)#(\d+)$")
BOARD = re.compile(r"^board:([0-9a-f]{6})$")
SOON = datetime.timedelta(hours=48)
STORED = ("id", "text", "on", "who", "unblocks", "added", "by", "done", "done_note")

# How the texts name the caller's commands: configure(add=..., list=..., done=...).
COMMANDS = {"add": "waits add", "list": "waits", "done": "waits done"}


def configure(**names: str) -> None:
    """Name the commands that add, list and close items (e.g. `mytool work wait add`) in the texts."""
    unknown = set(names) - set(COMMANDS)
    if unknown:
        raise ValueError(f"unknown command name(s): {', '.join(sorted(unknown))} (known: {', '.join(COMMANDS)})")
    COMMANDS.update(names)


# States that put the next move with the user: merge / reply / read the answer / decide / meet the deadline.
NEEDS_YOU = {"approved", "changes", "merged", "closed", "answered", "replied", "soon", "passed", "you"}
LABELS = {"review": "waiting for review", "approved": "approved, not merged", "changes": "changes requested",
          "merged": "merged", "closed": "closed", "draft": "draft", "open": "open", "replied": "a reply came",
          "answered": "answered", "later": "deadline later", "soon": "due within 48h", "passed": "deadline passed",
          "you": "your decision", "manual": "not checked automatically", "unchecked": "not checked"}


@dataclass
class Item:
    id: str
    text: str
    on: str
    who: str = ""
    unblocks: str = ""
    added: str = ""
    by: str = ""
    done: str = ""
    done_note: str = ""
    # not stored: where it is, and what the check saw
    ticket: str = ""
    file: str = ""
    state: str = ""
    detail: str = ""
    url: str = ""
    changed: str = ""  # when its state last changed (ISO, UTC), from the local state file
    was: str = ""      # the state before that change
    seen: str = ""     # the last state a check saw (shown when this one couldn't check)

    @property
    def kind(self) -> str:
        return self.on.split(":", 1)[0]

    @property
    def needs_you(self) -> bool:
        return not self.done and self.state in NEEDS_YOU

    def stored(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k in STORED and v}

    def as_dict(self) -> dict:
        return {**asdict(self), "kind": self.kind, "needs_you": self.needs_you}


# ---- the file ---------------------------------------------------------------------------------------


def waits_path(record: Path) -> Path:
    """records/2026-10-12-AI-1115-x.md -> records/2026-10-12-AI-1115-x.waits.jsonl"""
    return record.with_name(record.stem + SUFFIX)


def parse(text: str, ticket: str = "", file: str = "") -> list[Item]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a hand edit gone wrong: skip the line rather than lose the rest
        if isinstance(row, dict) and row.get("id") and row.get("on"):
            items.append(Item(**{k: str(row.get(k) or "") for k in STORED}, ticket=ticket, file=file))
    return items


def load(path: Path, ticket: str = "") -> list[Item]:
    try:
        return parse(path.read_text(encoding="utf-8"), ticket, str(path))
    except OSError:
        return []


def save(path: Path, items: list[Item]) -> None:
    path.write_text("".join(json.dumps(i.stored(), ensure_ascii=False) + "\n" for i in items), encoding="utf-8")


def new_id(taken: set[str]) -> str:
    while True:
        id_ = uuid.uuid4().hex[:6]
        if id_ not in taken:
            return id_


def parse_on(on: str, now: Optional[datetime.datetime] = None) -> str:
    """The --on value, checked and normalised (a date gets its timezone); ValueError says what's accepted."""
    on = on.strip()
    if on in ("user", "manual") or GH.match(on) or BOARD.match(on):
        return on
    if on.startswith("date:"):
        t = parse_date(on[5:])
        if t is None:
            raise ValueError(f"not a date: {on[5:]!r}; give an ISO time like date:2026-10-18T05:30+05:30 or date:2026-10-18")
        return "date:" + t.isoformat(timespec="minutes")
    raise ValueError(f"--on {on!r}: one of gh:OWNER/REPO#N, board:ID (6 hex), date:ISO, user, manual")


def parse_date(text: str) -> Optional[datetime.datetime]:
    try:
        t = datetime.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.astimezone()  # no zone: the local time it names


def default_who(on: str, board: Optional[Board] = None) -> str:
    if on in ("user",) or on.startswith("date:"):
        return "you"
    if on.startswith("gh:"):
        return "reviewer"
    if on.startswith("board:"):
        row = next((r for r in (board() if board else []) if r.get("id") == on[6:]), None)
        target = (row or {}).get("to") or (row or {}).get("repo")
        return f"{target} sessions" if target else "another session"
    return ""


# ---- every work item's items ---------------------------------------------------------------------------


def _git(work: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(work), *args], capture_output=True, text=True).stdout


def collect(work: Path, branches: Iterable[str], trees: dict[str, Path]) -> list[Item]:
    """Every item of every work item named in `branches` (its records/<date>-<KEY>….waits.jsonl): from its checkout
    in `trees` when it has one (what `wait add` wrote there), else from the branch in the git repo at `work`."""
    items: list[Item] = []
    for key in sorted(branches):
        tree = trees.get(key)
        if tree is not None:
            for path in sorted((tree / "records").glob(f"*-{key}*{SUFFIX}")):
                if re.match(rf"\d{{4}}-\d{{2}}-\d{{2}}-{re.escape(key)}(-|\.)", path.name):
                    items += load(path, key)
            continue
        for name in _git(work, "ls-tree", "--name-only", key, "records/").split():
            base = Path(name).name
            if base.endswith(SUFFIX) and re.match(rf"\d{{4}}-\d{{2}}-\d{{2}}-{re.escape(key)}(-|\.)", base):
                items += parse(_git(work, "show", f"{key}:{name}"), key, f"{key}:{name}")
    return items


# ---- checks -------------------------------------------------------------------------------------------


def _gh(*args: str) -> dict:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:200] or "gh failed (gh auth status?)")
    return json.loads(proc.stdout)


def check_gh(item: Item) -> None:
    repo, number = GH.match(item.on).groups()
    try:
        pr = _gh("pr", "view", number, "-R", repo, "--json", "state,reviewDecision,isDraft,url,title,reviewRequests")
    except RuntimeError as exc:
        if "no pull requests found" not in str(exc).lower() and "could not resolve to a pullrequest" not in str(exc).lower():
            raise
        issue = _gh("issue", "view", number, "-R", repo, "--json", "state,url,title")
        item.state = "closed" if issue.get("state") == "CLOSED" else "open"
        item.url, item.detail = issue.get("url", ""), f"issue: {issue.get('title', '')[:70]}"
        return
    reviewers = [r.get("login") or r.get("name") or r.get("slug") or "" for r in pr.get("reviewRequests") or []]
    if pr.get("state") == "MERGED":
        item.state = "merged"
    elif pr.get("state") == "CLOSED":
        item.state = "closed"
    elif pr.get("isDraft"):
        item.state = "draft"
    elif pr.get("reviewDecision") == "APPROVED":
        item.state = "approved"
    elif pr.get("reviewDecision") == "CHANGES_REQUESTED":
        item.state = "changes"
    else:
        item.state = "review"
    item.url = pr.get("url", "")
    who = f" (asked: {', '.join(r for r in reviewers if r)})" if item.state == "review" and any(reviewers) else ""
    item.detail = f"PR: {pr.get('title', '')[:70]}{who}"


def check_board(item: Item, rows: list[dict]) -> None:
    id_ = item.on[6:]
    head = next((r for r in rows if r.get("id") == id_ and r.get("kind") in ("post", "handoff", "claim")), None)
    if head is None:
        raise RuntimeError(f"no post, hand-off or claim {id_} on the board (this machine's)")
    done = [r for r in rows if r.get("ref") == id_ and r.get("kind") == "done"]
    replies = [r for r in rows if r.get("ref") == id_ and r.get("kind") == "reply"]
    if done:
        item.state, item.detail = "answered", f"{head['kind']} closed: {done[-1].get('text', '')[:120]}"
    elif replies:
        item.state = "replied"
        item.detail = f"{len(replies)} repl{'y' if len(replies) == 1 else 'ies'}, latest: {replies[-1].get('text', '')[:120]}"
    else:
        item.state, item.detail = "open", f"{head['kind']} to {head.get('to') or head.get('repo') or '?'}: {head.get('text', '')[:90]}"


def _in(delta: datetime.timedelta) -> str:
    secs = int(abs(delta.total_seconds()))
    days, hours, mins = secs // 86400, secs % 86400 // 3600, secs % 3600 // 60
    span = f"{days}d {hours}h" if days else f"{hours}h {mins}m" if hours else f"{mins}m"
    return f"in {span}" if delta.total_seconds() >= 0 else f"{span} ago"


def check_date(item: Item, now: datetime.datetime) -> None:
    t = parse_date(item.on[5:])
    if t is None:
        raise RuntimeError(f"bad date in {item.on}")
    left = t - now
    item.state = "passed" if left.total_seconds() <= 0 else "soon" if left <= SOON else "later"
    item.detail = f"{t.astimezone():%a %d %b %H:%M} ({_in(left)})"


def check(items: list[Item], now: Optional[datetime.datetime] = None, offline: bool = False,
          board: Optional[Board] = None) -> list[str]:
    """Fill each open item's state; returns one error line per check that failed (that item: `unchecked`).
    `board` reads the agents board, for board: items (none: they stay unchecked)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    errors: list[str] = []
    rows: Optional[list[dict]] = None
    for item in items:
        if item.done:
            item.state = "done"
            continue
        try:
            if item.on == "user":
                item.state, item.detail = "you", "your decision"
            elif item.on == "manual":
                item.state = "manual"
            elif item.kind == "date":
                check_date(item, now)
            elif offline:
                item.state, item.detail = "unchecked", "--no-check"
            elif item.kind == "gh":
                check_gh(item)
            elif item.kind == "board":
                if board is None:
                    raise RuntimeError("no board to read")
                if rows is None:
                    rows = board()
                check_board(item, rows)
            else:
                item.state, item.detail = "unchecked", f"unknown kind {item.kind!r}"
        except Exception as exc:  # noqa: BLE001  (offline, gh logged out, a typo: show the item anyway)
            item.state, item.detail = "unchecked", f"check failed: {exc}"
            errors.append(f"{item.ticket} {item.id} ({item.on}): {exc}")
    return errors


# ---- what the checks last saw (local), and the change-only DM -----------------------------------------------


def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def track(items: list[Item], now: Optional[datetime.datetime], state: dict) -> dict:
    """Remember each open item's checked state; when it differs from the last one seen, note when (`changed`)
    and what it was (`was`). A first sighting isn't a change, and sets the DM baseline (`wait add` sends its own
    "added" DM). An unchecked item keeps what was seen before. Items no longer open are forgotten."""
    now_s = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    open_ids = set()
    for item in items:
        if item.done:
            continue
        open_ids.add(item.id)
        seen = state.get(item.id)
        if item.state != "unchecked":
            if seen is None:
                seen = state[item.id] = {"state": item.state, "notified": item.state}
            elif seen.get("state") != item.state:
                seen.update({"was": seen.get("state", ""), "state": item.state, "changed": now_s})
        if seen:
            item.changed, item.was, item.seen = seen.get("changed", ""), seen.get("was", ""), seen.get("state", "")
    for id_ in [i for i in state if i not in open_ids]:
        del state[id_]
    return state


def unnotified(items: list[Item], state: dict) -> list[Item]:
    """Open, checked items whose state moved since the last change DM (the ones the next DM is about)."""
    return [i for i in items if not i.done and i.state != "unchecked" and i.id in state
            and state[i.id].get("notified") != i.state]


def mark_notified(items: list[Item], state: dict) -> None:
    for item in items:
        if item.id in state:
            state[item.id]["notified"] = item.state


# ---- rendering ----------------------------------------------------------------------------------------


def ordered(items: list[Item]) -> list[Item]:
    """What needs you first (deadline passed, then due soon, then the rest), then by ticket."""
    rank = {"passed": 0, "soon": 1}
    return sorted(items, key=lambda i: (not i.needs_you, bool(i.done), rank.get(i.state, 2), i.ticket, i.added))


def line(item: Item, with_ticket: bool = True) -> str:
    """One line, plain text: `[ID] TEXT — STATE (detail) · who: … · unblocks: … · on: …`."""
    state = LABELS.get(item.state, item.state) if not item.done else f"done {item.done}"
    if item.state == "unchecked" and item.seen:
        state = f"{state} now, last seen: {LABELS.get(item.seen, item.seen)}"
    elif item.was and item.changed and not item.done:
        state = f"{LABELS.get(item.was, item.was)} → {state}"
    bits = [f"{item.ticket} " if with_ticket else "", f"[{item.id}] {item.text} — {state}"]
    if item.detail and item.state not in ("you", "manual") and not item.done:
        bits.append(f" ({item.detail})")
    extras = [f"who: {item.who}" if item.who else "", f"unblocks: {item.unblocks}" if item.unblocks else "",
              f"on: {item.on}", item.url]
    if item.done and item.done_note:
        extras.insert(0, item.done_note)
    return "".join(bits) + "".join(f" · {e}" for e in extras if e)


def to_text(items: list[Item]) -> str:
    """Needs you (across every ticket) first, then the rest grouped by ticket."""
    items = ordered(items)
    first = [i for i in items if i.needs_you]
    rest = [i for i in items if not i.needs_you]
    out: list[str] = []
    if first:
        out.append(f"Needs you ({len(first)})")
        out += [f"  • {line(i)}" for i in first]
    tickets: dict[str, list[Item]] = {}
    for i in rest:
        tickets.setdefault(i.ticket, []).append(i)
    for ticket in sorted(tickets):
        out.append(("\n" if out else "") + f"{ticket} ({len(tickets[ticket])})")
        out += [f"  • {line(i, with_ticket=False)}" for i in tickets[ticket]]
    return "\n".join(out) if out else f"No open items. Add one: {COMMANDS['add']} \"what\" --on gh:OWNER/REPO#N -t KEY"


def dm(changed: list[Item], items: list[Item], added: list[Item] | tuple = ()) -> tuple[str, list[dict]]:
    """The DM: (notification text, Block Kit blocks): what was added and what moved, then how many need you in all."""
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    need = sum(1 for i in items if i.needs_you)
    what = ", ".join(x for x in (f"{len(added)} added" if added else "", f"{len(changed)} changed" if changed else "") if x)
    text = f"Open items: {what}" + (f", {need} need you" if need else "")
    lines = []
    for i in ordered(list(added)) + ordered(changed):
        new = any(i is a for a in added)
        state = LABELS.get(i.state, i.state)
        moved = f"new, *{esc(state)}*" if new else f"{esc(LABELS.get(i.was, i.was) if i.was else '?')} → *{esc(state)}*"
        link = f" <{i.url}|{esc(i.on)}>" if i.url else f" `{esc(i.on)}`"
        extra = (f" · who: {esc(i.who)}" if new and i.who else "") + (f" · unblocks: {esc(i.unblocks)}" if i.unblocks else "")
        lines.append(f"• *{esc(i.ticket)}* [{i.id}] {esc(i.text)} — {moved}{link}{extra}")
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"🧷 *{esc(text)}*\n" + "\n".join(lines)[:2900]}},
              {"type": "context", "elements": [{"type": "mrkdwn", "text": f"All of them: `{COMMANDS['list']}` · close one: "
                                                f"`{COMMANDS['done']} ID`"}]}]
    return text, blocks

