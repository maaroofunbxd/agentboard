"""`agents` (or a wrapper's subcommand, config.Settings.command): the board between AI agent sessions, so they don't start the same work
twice, can pick up where another stopped, and can ask the sessions of another repo something. The board is the
record: a session reads it when it starts; a question and its answer are a thread on a post
(`reply`, `wait ID`, `done`). Plain files and one command: any agent tool, or a person, can use it. Every session on
this machine, in every repo, shares it (agents.jsonl in the board folder, config.py). Not a record of changes.

  agents whoami                                    # this session's name (say it first), actor, repo, branch
  agents status                                    # what's for the repo you're in: posts, open claims, hand-offs
  agents status --all                              # every repo's
  agents post --to api "document the port the service listens on in its README"
  agents post --to all "staging is pinned to a PR build until PROJ-123 is done"
  agents post --to api-fd00 "your claim 664b1a overlaps mine; which file is yours?"   # one session of api
  agents claim "retry on timeouts, branch retry" -p src/app/client.py
  agents handoff "done: …; left: …; next: <the command to run>"
  agents pickup 7c21e0                             # take over a hand-off: it becomes your claim
  agents done 3fa9c1 "merged 81480d2"              # on a post: the answer its sender sees
  agents reply 3fa9c1 "which region?"              # keep talking on a post's (or claim's, hand-off's) thread, without closing it
  agents sessions                                  # the sessions of this repo: live or ended, last seen, what they hold open
  agents wait                                      # in the background: ends when a request or reply arrives
  agents wait 3fa9c1 --timeout 600                 # ends when post 3fa9c1 gets a reply or its answer

After a session has read the board, a program that calls board.nudge after each run (a wrapper's own command) prints one
`[board]` line on stderr when something new arrives for its repo (a post, a claim or hand-off from its other
sessions, a reply). `agents wait`, run in the background, tells a session that runs no such command, in a tool that
wakes the agent when a background command ends.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from agentboard import board, config, identity
from agentboard import tools as agent_tools

console = Console()

agents_app = typer.Typer(
    help="The board between AI agent sessions, any repo: whoami, status (what's for this repo), post --to REPO|REPO-SESSION, reply, claim, handoff, pickup, done, wait, sessions.",
    no_args_is_help=True,
)


def _need_board() -> None:
    if board.store() is None:
        raise typer.BadParameter(config.settings.off_reason)


def _post(kind: str, text: str, ticket: Optional[str], to: Optional[str] = None, **fields) -> dict:
    _need_board()
    try:
        entry = board.post(kind, text, ticket=ticket, to=to, **fields)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--to") from exc
    console.print(f"[green]{kind.capitalize()} {entry['id']}[/green] (from {sender(entry) or identity.actor()}); "
                  f"close it with: {_cmd()} done {entry['id']}")
    return entry


TicketOpt = typer.Option(None, "--ticket", "-t", help="Jira ticket, e.g. CW-3220.")


def sender(r: dict) -> str:
    """Who posted: the session's name (repo-id) when it had one, else the actor, plus the branch."""
    repo, sid, branch = r.get("repo"), r.get("session"), r.get("branch")
    name = f"{repo}-{sid}" if repo and sid else sid or repo or ""
    return " ".join(x for x in (name or str(r.get("actor", "")), f"({branch})" if branch else "") if x)


_live_cache: dict = {}  # session id -> live?, once per run: status asks about many lines of one session


def _live(r: dict) -> str:
    """" (live)" when the session that wrote `r` still runs (board.session_live), else ""."""
    sid = r.get("session")
    if not sid:
        return ""
    if sid not in _live_cache:
        _live_cache[sid] = board.session_live(r)
    return " (live)" if _live_cache[sid] else ""


def addressee(r: dict) -> str:
    """A post's `to`: the repo, or `<repo>-<session>` when it is for one session of it."""
    return f"{r['to']}-{r['to_session']}" if r.get("to") and r.get("to_session") else r.get("to", "")


LOCAL = "AGENTS.local.md"  # in a repo's root: the user's own file for that repo (a symlink into <agents dir>/)
MARK = "<!-- made by `"  # a file a command here made starts with MARK + "<command> link`" (or setup)


def _mark(what: str) -> str:
    return f"{MARK}{_cmd()} {what}`"


def _made_by(text: str, what: str) -> bool:
    """`text` starts with the mark of `link` or `setup`, under any name of the command (agents, or a wrapper's)."""
    first = text.split("\n", 1)[0]
    return first.startswith(MARK) and f"agents {what}`" in first


def tool_local_text(tool: agent_tools.Tool, root: Path) -> str:
    """The tool's own per-clone file for `root`, importing AGENTS.local.md (and AGENTS.md when the repo has no file
    of the tool's: having a local one can stop a tool from reading AGENTS.md by itself)."""
    lines = [f"{_mark('link')}: {tool.name} loads this file by itself; it pulls in your AGENTS.local.md -->"]
    if (root / "AGENTS.md").is_file() and not (tool.repo_file and (root / tool.repo_file).is_file()):
        lines.append(tool.import_line.format("AGENTS.md"))
    lines.append(tool.import_line.format(LOCAL))
    return "\n".join(lines) + "\n"


STARTER = """# How I work with agents in {repo}

My own file for this repo, not committed here: `AGENTS.local.md` is a symlink to `{target}`
(in my agent folder), and git ignores it in this clone only (`.git/info/exclude`).

## How I want answers

(Mine. Agents: propose a change here, with the reason; don't make it without my OK.)

## What agents need from me

(The agents'. Per kind of task in this repo, what you need before starting: fill in what you can find yourself,
then ask me only for the blanks, all at once. When you keep missing something, add it here and say so.)
"""


def _cmd() -> str:
    """How messages name this command: `agents`, or a wrapper's (config.Settings.command)."""
    return config.settings.command


def print_json(data) -> None:
    """Plain JSON on stdout (pretty-coloured only for a real terminal), safe to pipe to jq."""
    text = json.dumps(data, indent=2, default=str)
    if sys.stdout.isatty():
        Console(file=sys.stdout).print_json(text)
    else:
        print(text)


def agents_dir() -> Path:
    """The user's agent folder: <repo>.md for `link`, global.md for `setup` (config.Settings.agents_dir)."""
    return config.settings.agents_dir()


def repo_root() -> Optional[Path]:
    top = identity.git_here("rev-parse", "--show-toplevel")
    return Path(top) if top else None


def local_file(repo: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """The user's file for `repo`: AGENTS.local.md in this checkout, else <agents dir>/<repo>.md. (text, path)."""
    root = repo_root()
    for path in ([root / LOCAL] if root else []) + ([agents_dir() / f"{repo}.md"] if repo else []):
        if path.is_file():
            return path.read_text(encoding="utf-8"), str(path.resolve())
    return None, None



@agents_app.command("whoami")
def cmd_whoami(json_output: bool = typer.Option(False, "--json")) -> None:
    """This session's name (say it at the start): `<repo>-<id>`; then the user's own file for this repo, if any.

    The id is $AGENTS_SESSION ($<prefix>_SESSION under a wrapper, config.py) when set (any tool can set it for its
    commands), else the session id its tool exports (tools.py), else `p<the agent's process>`. The file
    is AGENTS.local.md in the repo (`agents link`), else <agents dir>/<repo>.md."""
    repo = identity.here()
    where = board.store()
    info = {"name": identity.session_name(repo), "session": identity.session_id(), "actor": identity.actor(), "repo": repo,
            "branch": identity.git_here("branch", "--show-current") or None, "pid": identity.pid_of(identity.session_id()),
            "tool_session": identity.tool_session() or None,
            "board": str(where.path(board.AGENTS)) if hasattr(where, "path") else type(where).__name__ if where else None}
    text, source = local_file(repo)
    if json_output:
        print_json({**info, "local": text, "local_from": source})
        return
    if not info["name"]:
        console.print(f"No session id ({info['actor']}): an agent sets {config.settings.env('SESSION')}=<name> on its commands to get one.")
    else:
        process = f", process {info['pid']}" if info["pid"] else ""
        console.print(f"{info['name']}  ({info['actor']}, {'/'.join(x for x in (repo, info['branch']) if x)}{process})", highlight=False)
    # which board this copy of the command reads: two installs (one with a wrapper, one without) can read different ones
    console.print(f"board: {info['board'] or config.settings.off_reason}", highlight=False)
    if text:
        print(f"\nThe user's own file for this repo ({source}): follow 'How I want answers'; ask in the shape of "
              "'What agents need from me', only for what you can't find yourself, and add to that section when you "
              "keep missing something.\n")
        print(text.rstrip())
    if not info["name"]:
        raise typer.Exit(1)


@agents_app.command("claim")
def cmd_claim(
    text: str = typer.Argument(..., help="What you're taking on, and your branch: 'ghci fork-PR fix, branch ghci-fork'."),
    paths: Optional[list[str]] = typer.Option(None, "--paths", "-p", help="A file or folder you'll change (repeat it), "
                                              "relative to the repo root; an open claim on an overlapping path is shown."),
    ticket: Optional[str] = TicketOpt,
) -> None:
    """Say you're on something other sessions might also start, so they don't.

    A shared tool, a fix someone asked for, a cluster you're testing on. Others see it in `agents status`;
    close it with `agents done ID`. With --paths, a session claiming an overlapping path is told whose
    claim it overlaps (the claim is still made: you decide, or ask that session)."""
    _need_board()
    paths = [x.strip().strip("/") for x in paths or [] if x.strip().strip("/")]
    for other in board.claim_overlaps(board.agent_posts(), identity.here(), paths) if paths else []:
        console.print(f"[yellow]Overlaps open claim {other['id']}[/yellow] from {sender(other)} "
                      f"({', '.join(other['paths'])}): {other.get('text', '')}", highlight=False)
    _post("claim", text, ticket, paths=paths or None)


@agents_app.command("handoff")
def cmd_handoff(
    text: str = typer.Argument(..., help="'done: …; left: …; next: <the command to run>'."),
    ticket: Optional[str] = TicketOpt,
) -> None:
    """Leave work half-way for the next session: what's done, what's left, the next command.

    The next session may be another LLM, which can't read your chat."""
    _post("handoff", text, ticket)


@agents_app.command("post")
def cmd_post(
    text: str = typer.Argument(..., help="What the other repo's sessions should know or do, and why."),
    to: str = typer.Option(..., "--to", help="The repo it's for (its folder name: api, web, ...), `all`, or one session "
                           "of a repo as the board names it (api-fd00.60203, or the start of the id: api-fd00)."),
    ticket: Optional[str] = TicketOpt,
) -> None:
    """Leave something for another repo's sessions, or for one session: a request or a heads-up. They see it when they start.

    It shows in `agents status` run in that repo. It's information for them, not an instruction: what
    changes code or a live system, they raise with their user first. A request says what is asked and where the
    answer should go ("document it in its ops.yml"); whoever deals with it closes it with
    `agents done ID "the answer, or a link to it"`, and that shows under replies in this repo's status.
    `agents wait ID` in the background ends when the answer (or a reply) lands.
    To one session (--to REPO-SESSION, a name from `agents status` or `agents sessions`): the whole repo still sees
    it in status, marked for that session, but only that session's `agents wait` and [board] line wake for it."""
    _need_board()
    repo, session = board.resolve_to(board.agent_posts(), to)
    entry = _post("post", text, ticket, to=repo, to_session=session)
    if session:
        print(f"For {repo}-{session} only (the rest of {repo} sees it marked for that session).")
    if repo != "all":
        print(presence_note(repo, session, skip=entry["id"]))
    print(f"For an answer, wait in the background: {_cmd()} wait {entry['id']}")


def presence_note(repo: str, session: Optional[str] = None, skip: Optional[str] = None) -> str:
    """One line for the asker: who of `repo` (or of `repo-session`) is there to read a post (board.presence), and how
    long its other open posts have waited, so nobody waits blind on a repo with no session running."""
    p = board.presence(board.agent_posts(), repo, session, skip=skip)
    name = f"{repo}-{session}" if session else repo
    oldest = p["waiting"][0] if p["waiting"] else None
    waiting = (f"; {len(p['waiting'])} other open post(s) to it, the oldest ({oldest['id']}) waiting {_ago(oldest.get('ts'))}"
               if oldest else "")
    if p["live"]:
        return f"Live: {', '.join(p['live'])}{waiting}."
    if p["unknown"]:
        return f"Maybe there (no process to check): {', '.join(p['unknown'])}{waiting}."
    last = f"its last line {_ago(p['last'])} ago" if p["last"] else "it has never written to the board"
    return (f"No session of {name} is live ({last}){waiting}. An answer waits until someone starts a session there: "
            "tell the user now, not after waiting. (A session that never wrote to the board isn't seen.)")


@agents_app.command("done")
def cmd_done(
    ref: str = typer.Argument(..., help="The claim, hand-off or post id (from `agents status`)."),
    text: str = typer.Argument("", help="What came of it: 'merged 81480d2', 'dropped: not needed'."),
) -> None:
    """Close a claim, a hand-off or a post. On a post, the text is the answer: the sender's repo sees it in its
    status and `agents wait ID`, and its running sessions get a [board] line."""
    _need_board()
    posts = board.agent_posts()
    closed = {r.get("ref") for r in posts if r.get("kind") == "done"}
    if ref not in {r.get("id") for r in posts if r.get("kind") in ("claim", "handoff", "post")} - closed:  # any age
        raise typer.BadParameter(f"nothing open on the board is {ref!r}; `{_cmd()} status --all` lists them", param_hint="REF")
    board.post("done", text or "done", ref=ref)
    console.print(f"[green]Closed[/green] {ref}")



@agents_app.command("reply")
def cmd_reply(
    ref: str = typer.Argument(..., help="The post, claim or hand-off id (from `agents status`), open or closed."),
    text: str = typer.Argument(..., help="The follow-up: a question back, more detail, a correction."),
) -> None:
    """Say more on a thread without closing it: a question back to the asker, the asker's follow-up, a word to the
    session holding a claim or the one that left a hand-off.

    The other side sees it in its status and `agents wait ID`. Close the thread with `agents done ID`."""
    _need_board()
    posts = board.agent_posts()
    lines = board.thread(posts, ref)
    if not lines:
        raise typer.BadParameter(f"no post, claim or hand-off is {ref!r}; `{_cmd()} status --all` lists them", param_hint="REF")
    board.post("reply", text, ref=ref)
    console.print(f"[green]Reply[/green] on {ref}; the other side's answer: {_cmd()} wait {ref}")


@agents_app.command("pickup")
def cmd_pickup(ref: str = typer.Argument(..., help="The hand-off id (from `agents status`).")) -> None:
    """Take over a hand-off: it's closed as picked up by you and becomes your claim, so no other session resumes it.

    Close the claim with `agents done ID` when you finish."""
    _need_board()
    posts = board.agent_posts()
    closed = {r.get("ref") for r in posts if r.get("kind") == "done"}
    handoff = next((r for r in posts if r.get("kind") == "handoff" and r.get("id") == ref and ref not in closed), None)
    if handoff is None:
        raise typer.BadParameter(f"no open hand-off is {ref!r}; `{_cmd()} status` lists them", param_hint="REF")
    me = identity.session_name(identity.here()) or identity.actor()
    board.post("done", f"picked up by {me}", ref=ref)
    _post("claim", f"continuing hand-off {ref} from {sender(handoff)}: {handoff.get('text', '')}", handoff.get("ticket"),
          paths=handoff.get("paths"))


def _sections(where: str, view: dict) -> list[tuple[str, str, list[dict]]]:
    """(title, kind, rows) for status, in the order they're printed."""
    return [(f"Posts {where}", "post", view["posts"]), ("Claims (open)", "claim", view["claims"]),
            ("Hand-offs (open, last 7 days)", "handoff", view["handoffs"]),
            ("Replies to this repo's posts (last 7 days)", "reply", view.get("replies", []))]


def _what(r: dict) -> str:
    """A row's text for status: a claim's paths, a reply's answer."""
    if "reply" in r:
        return f"{r.get('text', '')}  -> {sender(r['replied'])}: {r['reply']}"
    paths = f" [paths: {', '.join(r['paths'])}]" if r.get("paths") else ""
    return r.get("text", "") + paths


def _worktrees() -> list[str]:
    """`branch  path` for each worktree of the repo you're in: which branch each session works on."""
    out, path = [], None
    for line in identity.git_here("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = line.split(" ", 1)[1]
        elif line.startswith("branch ") and path:
            out.append(f"{line.split(' ', 1)[1].removeprefix('refs/heads/')}  {path}")
    return out


def _this_session(r: dict) -> str:
    """ " (this session)" for an item the running session posted (its session id is on the line), else ""."""
    sid = identity.session_id()
    return " (this session)" if sid and r.get("session") == sid else ""


def _print_plain(where: str, view: dict, sections) -> None:
    counts = ", ".join(f"{len(rows)} {name}" for name, rows in (("post(s)", view["posts"]), ("open claim(s)", view["claims"]),
                                                                  ("open hand-off(s)", view["handoffs"])))
    replies = f", {len(view['replies'])} reply(ies)" if view.get("replies") else ""
    print(f"Board {where}: {counts}{replies}" + (f"; {view['elsewhere']} post(s) for other repos (--all)" if view["elsewhere"] else ""))
    for _title, kind, rows in sections:
        for r in rows:
            to = f" to {addressee(r)}" if r.get("to") else ""
            stale = " (stale?)" if r.get("stale") else ""
            print(f"[{kind} {r['id']}] {r.get('ts', '')} from {sender(r)}{_live(r)}{to}{stale}{_this_session(r)}: {_what(r)}")
    for tree in view.get("worktrees", []):
        print(f"[worktree] {tree}")
    print(f"Close one: {_cmd()} done ID 'what came of it'; take over a hand-off: {_cmd()} pickup ID")


@agents_app.command("link")
def cmd_link(
    for_tools: Optional[list[str]] = typer.Option(None, "--for", help="Also write this agent tool's own per-clone file, "
                                                  "importing it, for a tool that doesn't read AGENTS.local.md by itself "
                                                  "(the tools that have one: agentboard/tools.py). Repeat it."),
    remove: bool = typer.Option(False, "--remove", help="Remove the symlink, the files this made and the exclude lines; the file in <agents dir>/ stays."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Say what it would do; change nothing."),
) -> None:
    """Give this repo your own AGENTS.local.md: a symlink to <agents dir>/<repo>.md, ignored by git in this clone only.

    An agent finds it through `agents whoami`, which prints it (AGENTS.md's first step), whatever the tool. With
    --for TOOL, also writes that tool's own per-clone file (one it loads by itself) importing it.

    Creates <agents dir>/<repo>.md if missing (two empty sections), the symlink in the repo's root, and an
    AGENTS.local.md line in the clone's .git/info/exclude (never committed). Nothing is added to the repo itself. Edit
    the file from the repo; it lives in your agent folder (config.Settings.agents_dir). Running it again changes
    nothing."""
    repo, root = identity.here(), repo_root()
    if not repo or not root:
        raise typer.BadParameter("not inside a git repo: cd into the repo first")
    tools = []
    for name in for_tools or []:
        tool = agent_tools.named(name)
        if not tool or not tool.local_file:
            have = ", ".join(t.name for t in agent_tools.TOOLS if t.local_file) or "none"
            raise typer.BadParameter(f"{name!r} has no per-clone file of its own (tools that do: {have})", param_hint="--for")
        tools.append(tool)
    target, link = agents_dir() / f"{repo}.md", root / LOCAL
    exclude = Path(identity.git_here("rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
    listed = exclude.read_text(encoding="utf-8").split() if exclude.is_file() else []
    def made(path: Path) -> bool:
        return path.is_file() and _made_by(path.read_text(encoding="utf-8"), "link")

    if remove:
        names = [LOCAL] + [t.local_file for t in agent_tools.TOOLS if t.local_file]
        ours = [root / t.local_file for t in agent_tools.TOOLS if t.local_file and made(root / t.local_file)]
        drop = [x for x in names if x in listed]
        steps = ([f"remove the symlink {link}"] if link.is_symlink() else []) + [f"remove {p}" for p in ours] + \
            ([f"remove {', '.join(drop)} from {exclude}"] if drop else [])
        for step in steps or ["nothing to remove"]:
            console.print(f"  - {step}", highlight=False)
        if dry_run or not steps:
            return
        if link.is_symlink():
            link.unlink()
        for path in ours:
            path.unlink()
        if drop:
            exclude.write_text("".join(x for x in exclude.read_text(encoding="utf-8").splitlines(keepends=True)
                                       if x.strip() not in drop), encoding="utf-8")
        console.print(f"[green]Unlinked[/green]; {target} is kept")
        return
    if link.exists() and not link.is_symlink():
        raise typer.BadParameter(f"{link} is a real file, not a link: move its text into {target}, delete it, then run this again")
    if link.is_symlink() and link.resolve() != target.resolve():
        raise typer.BadParameter(f"{link} already points at {link.resolve()}: {_cmd()} link --remove first")
    extras = [(t, root / t.local_file) for t in tools]
    for _tool, path in extras:
        if path.exists() and not made(path):
            raise typer.BadParameter(f"{path} exists and isn't one this command made: import {LOCAL} in it yourself, then run this again")
    missing = [x for x in [LOCAL] + [t.local_file for t in tools] if x not in listed]
    steps = []
    if not target.exists():
        sample = root / f"{LOCAL}.example"
        steps.append(f"create {target} (from {sample.name})" if sample.is_file() else f"create {target} (two empty sections)")
    if not link.is_symlink():
        steps.append(f"link {link} -> {target}")
    steps += [f"write {path} ({tool.name} loads it by itself; it imports {LOCAL})" for tool, path in extras if not path.exists()]
    if missing:
        steps.append(f"add {', '.join(missing)} to {exclude} (this clone only, never committed)")
    if not steps:
        console.print(f"Already linked: {link} -> {target}")
        return
    for step in steps:
        console.print(f"  - {step}", highlight=False)
    if dry_run:
        return
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        sample = root / f"{LOCAL}.example"  # a repo may commit a sample; else the built-in starter
        target.write_text(sample.read_text(encoding="utf-8") if sample.is_file() else STARTER.format(repo=repo, target=target),
                          encoding="utf-8")
    if not link.is_symlink():
        link.symlink_to(target)
    for tool, path in extras:
        if not path.exists():
            path.write_text(tool_local_text(tool, root), encoding="utf-8")
    if missing:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        if not exclude.exists():
            exclude.write_text("", encoding="utf-8")
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write(("" if not exclude.stat().st_size or exclude.read_text().endswith("\n") else "\n") + "".join(f"{x}\n" for x in missing))
    console.print(f"[green]Linked[/green] {link} -> {target}. Edit it from here; `{_cmd()} whoami` prints it.")


GLOBAL = "global.md"  # in <agents dir>/: the user's instructions for every repo and tool; the origin of the copies
STARTER_GLOBAL = "# My instructions for every agent, in every repo\n"


@agents_app.command("setup")
def cmd_setup(
    for_tools: Optional[list[str]] = typer.Option(None, "--for", help="Only this agent tool (repeat it). Default: every "
                                                  "tool in agentboard/tools.py that keeps global files and is installed."),
    force: bool = typer.Option(False, "--force", help="Replace a global file this command didn't make (kept as <file>.bak)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Say what it would do; change nothing."),
) -> None:
    """Copy your global agent setup from <agents dir>/global.md into each agent tool's own files.

    The origin is <agents dir>/global.md (your agent folder; created from the wrapper's template, if any, when missing);
    edit it there, never in a tool's file, then run this again. For each tool that keeps them (tools.py),
    writes a marked copy to its global instructions file and adds the prompt hook (config.Settings.prompt_hook, if any) to its settings,
    leaving the rest of its settings alone. Without any agent tool nothing is needed: the file is plain markdown.
    Running it again changes nothing when all is in place."""
    if for_tools:
        tools = []
        for name in for_tools:
            tool = agent_tools.named(name)
            if not tool or not (tool.global_file or tool.settings_file):
                have = ", ".join(t.name for t in agent_tools.TOOLS if t.global_file or t.settings_file) or "none"
                raise typer.BadParameter(f"{name!r} has no global files in agentboard/tools.py (tools that do: {have})", param_hint="--for")
            tools.append(tool)
    else:
        tools = [t for t in agent_tools.TOOLS if (t.global_file or t.settings_file)
                 and Path(t.global_file or t.settings_file).expanduser().parent.is_dir()]
    source = agents_dir() / GLOBAL
    template = config.settings.global_template
    text = source.read_text(encoding="utf-8") if source.is_file() else \
        template.read_text(encoding="utf-8") if template else STARTER_GLOBAL
    copy = f"{_mark('setup')} from {source}: edit that file, then run `{_cmd()} setup` -->\n{text}"
    steps, writes = [], []
    if not source.is_file():
        steps.append(f"create {source} (from {template})" if template else f"create {source} (a heading only)")
        writes.append((source, text))
    for tool in tools:
        if tool.global_file:
            path = Path(tool.global_file).expanduser()
            old = path.read_text(encoding="utf-8") if path.is_file() else None
            if old != copy:
                if old is not None and not _made_by(old, "setup") and old.strip() != text.strip():
                    if not force:
                        raise typer.BadParameter(f"{path} isn't one this command made: move what you want to keep into "
                                                 f"{source}, then run this again with --force (the old file is kept as .bak)")
                    steps.append(f"keep {path} as {path.name}.bak")
                    writes.append((path.with_name(path.name + ".bak"), old))
                steps.append(f"write {path} ({tool.name}: a copy of {source.name})")
                writes.append((path, copy))
        if tool.settings_file and tool.prompt_hook_event and config.settings.prompt_hook:
            path = Path(tool.settings_file).expanduser()
            settings = json.loads(path.read_text(encoding="utf-8") or "{}") if path.is_file() else {}
            new = agent_tools.with_prompt_hook(tool, settings, config.settings.prompt_hook)
            if new != settings:
                steps.append(f"add the `{config.settings.prompt_hook}` hook ({tool.prompt_hook_event}) to {path}")
                writes.append((path, json.dumps(new, indent=2) + "\n"))
    if not steps:
        console.print(f"Already set up from {source}" + (f" for {', '.join(t.name for t in tools)}" if tools else
                                                           " (no agent tool installed: nothing to copy)"))
        return
    for step in steps:
        console.print(f"  - {step}", highlight=False)
    if dry_run:
        return
    for path, content in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    console.print(f"[green]Set up[/green] from {source}. Edit it there, then run `{_cmd()} setup` again.")


def _wait_advice(asks: list[dict], repo: str) -> list[str]:
    """What a woken session does with what `agents wait` found: the user decides who takes it."""
    if not any(r.get("kind") in ("post", "handoff") for r in asks):
        return [f"Tell the user about the replies when you next write to them. Then run `{_cmd()} wait` in the background again."]
    first = next(r for r in asks if r.get("kind") in ("post", "handoff"))
    tool = getattr(agent_tools.named(identity.actor()), "command", "") or "<your agent tool>"
    root = identity.git_here("rev-parse", "--path-format=absolute", "--git-common-dir").removesuffix("/.git") or "."
    return [
        "Don't drop the work you're on, and don't start this one yourself. At the next natural break, tell the user what "
        "arrived and offer them three choices:",
        f"  1. A new session for it, in a new terminal: cd {root} && {tool} \"Take {first['kind']} {first['id']} "
        f"on the {repo} board ({_cmd()} status)\"",
        "  2. A sub-agent of this session, if your tool has them: kept apart from your own work, in its own worktree, with "
        f"its own `{_cmd()} claim` (or `pickup {first['id']}` for a hand-off).",
        "  3. Leave it on the board: the next session started in this repo sees it.",
        f"Then run `{_cmd()} wait` in the background again.",
    ]


@agents_app.command("wait")
def cmd_wait(
    ref: Optional[str] = typer.Argument(None, help="A post, claim or hand-off id: wait only for a reply or the answer on that thread."),
    timeout: float = typer.Option(0, "--timeout", help="Give up after this many seconds (exit 124). 0 = wait until something arrives."),
    every: float = typer.Option(10, "--every", help="Seconds between looks at the board."),
) -> None:
    """Wait until the board gets something for the repo you're in, then print it and what to do, and exit.

    It wakes for a post to this repo (or all), a hand-off from its other sessions, or a reply to its posts, made after
    this session last read the board. Run it in the background at the start of a session, in a tool that wakes the
    agent when a background command ends. Start it again each time it ends.

    With a post id: ends when another session replies on that post or closes it, after this session's last line on
    it (so an answer that came before you started waiting counts). For a question you asked and need answered."""
    import datetime
    import time

    if ref:
        _wait_thread(ref, timeout, every)
        return

    repo = identity.here()
    if not repo:
        raise typer.BadParameter("run it inside a git repo: it waits for that repo's board")
    sid = identity.session_id() or ""  # since this session last read the board; a session that never did: from now
    since = (board._seen().get(sid) if sid else None) or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    start, seen_mtime = time.monotonic(), -1.0
    while True:
        mtime = board.board_mtime()
        if mtime != seen_mtime:
            seen_mtime = mtime
            asks = board.board_asks(board.agent_posts(), repo, sid, since)
            if asks:
                break
        if timeout and time.monotonic() - start >= timeout:
            print(f"Nothing new on the board for {repo} in {timeout:g}s.")
            raise typer.Exit(124)
        time.sleep(every)
    from collections import Counter

    counts = Counter("reply" if r.get("kind") in ("done", "reply") else r.get("kind") for r in asks)
    print(f"[board] new for {repo}: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
    for r in asks:
        if r.get("kind") in ("done", "reply"):
            print(f"[reply {r.get('ref', '')}] {r.get('ts', '')} from {sender(r)}: {r.get('text', '')}")
        else:
            to = f" to {addressee(r)}" if r.get("to") else ""
            print(f"[{r['kind']} {r['id']}] {r.get('ts', '')} from {sender(r)}{to}: {_what(r)}")
    for line in _wait_advice(asks, repo):
        print(line)
    board.mark_seen(sid, asks[-1].get("ts"))


def _wait_thread(ref: str, timeout: float, every: float) -> None:
    """`agents wait ID`: the lines from other sessions on `ref`'s thread (a post, claim or hand-off) after this
    session's last one."""
    import time

    me = identity.session_id()
    lines = board.thread(board.agent_posts(), ref)
    if not lines:
        raise typer.BadParameter(f"no post, claim or hand-off is {ref!r}; `{_cmd()} status --all` lists them", param_hint="REF")
    head = lines[0]
    if head.get("kind") == "post" and head.get("to") not in (None, "all", identity.here()):
        print(presence_note(head["to"], head.get("to_session"), skip=ref))  # the asker's side: is anyone there?
    mine = [i for i, r in enumerate(lines) if me and r.get("session") == me]
    after = mine[-1] + 1 if mine else 1  # by position: the board's times are to the second
    start, seen_mtime = time.monotonic(), -1.0
    while True:
        mtime = board.board_mtime()
        if mtime != seen_mtime:
            seen_mtime = mtime
            new = [r for r in board.thread(board.agent_posts(), ref)[after:] if not (me and r.get("session") == me)]
            if new:
                break
        if timeout and time.monotonic() - start >= timeout:
            print(f"No reply on {ref} in {timeout:g}s.")
            raise typer.Exit(124)
        time.sleep(every)
    for r in new:
        print(f"[{'answer' if r.get('kind') == 'done' else 'reply'} {ref}] {r.get('ts', '')} from {sender(r)}: {r.get('text', '')}")
    if new[-1].get("kind") == "done":
        print(f"The thread is closed. Tell the user the answer; a follow-up still works: {_cmd()} reply {ref} \"...\".")
    else:
        print(f"Answer with: {_cmd()} reply {ref} \"...\", then {_cmd()} wait {ref} again (in the background).")
    board.mark_seen(me, new[-1].get("ts"))


@agents_app.command("status")
def cmd_status(
    all_repos: bool = typer.Option(False, "--all", help="Posts for every repo, not only the one you're in."),
    this_session: bool = typer.Option(False, "--this-session", help="Only what this session posted and hasn't closed (any repo): "
                                      "what to close or hand off before it ends."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """What's on the board for the repo you're in: posts for it, open claims, open hand-offs.

    Posts addressed to this repo or to `all`; agents read it when a session starts. A claim with no `done` for a
    day is marked stale; a post nobody closed drops off after two weeks."""
    sid = identity.session_id()
    if this_session and not sid:
        raise typer.BadParameter(f"no session id: set {config.settings.env('SESSION')}=<name> on the commands (a tool in agentboard/tools.py gets one by itself)",
                                 param_hint="--this-session")
    repo = None if all_repos or this_session else identity.here()
    view = board.agents_view(board.agent_posts(), repo=repo)
    if this_session:
        for key in ("posts", "claims", "handoffs", "replies"):
            if isinstance(view.get(key), list):
                view[key] = [r for r in view[key] if r.get("session") == sid]
        view["elsewhere"] = 0
    if repo:
        view["worktrees"] = _worktrees()
    if not this_session:  # --this-session hides others' posts, so it mustn't swallow the [board] nudge for them
        board.mark_seen(identity.session_id())  # the nudge only tells this session about what comes after
    if json_output:
        print_json(view)
        return
    where = "of this session" if this_session else f"for {repo}" if repo else "every repo"
    if not any(view.get(k) for k in ("posts", "claims", "handoffs", "replies")):
        console.print(f"[dim]Nothing on the board {where}." + (f" {view['elsewhere']} post(s) for other repos: --all." if view["elsewhere"] else "") + "[/dim]")
        return
    sections = _sections(where, view)
    if not console.is_terminal:  # an agent's shell: one line each, full text, counts first (survives `| head`)
        _print_plain(where, view, sections)
        return
    for title, _kind, rows in sections:
        if not rows:
            continue
        table = Table(title=title, title_justify="left", show_lines=False)
        for col in ("id", "when (UTC)", "from", "to", "what"):
            table.add_column(col, overflow="fold")
        for r in rows:
            stale = " [yellow](stale?)[/yellow]" if r.get("stale") else ""
            table.add_row(r["id"], r.get("ts", ""), sender(r) + _live(r) + _this_session(r), addressee(r), _what(r) + stale)
        console.print(table)
    if view.get("worktrees"):
        console.print("[dim]Worktrees: " + "; ".join(view["worktrees"]) + "[/dim]", highlight=False)
    tail = f"{view['elsewhere']} post(s) for other repos: --all. " if view["elsewhere"] else ""
    console.print(f"[dim]{tail}close one: {_cmd()} done ID 'what came of it'; take over a hand-off: {_cmd()} pickup ID[/dim]")


def _ago(ts: Optional[str], now: Optional[float] = None) -> str:
    """'2h10m' / '3d' since a board time; '' when unknown."""
    import datetime
    import time

    if not ts:
        return ""
    try:
        then = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return ""
    seconds = max(0, int((now or time.time()) - then))
    if seconds >= 86400:
        return f"{seconds // 86400}d{(seconds % 86400) // 3600}h"
    if seconds >= 3600:
        return f"{seconds // 3600}h{(seconds % 3600) // 60}m"
    return f"{seconds // 60}m"


@agents_app.command("sessions")
def cmd_sessions(
    all_repos: bool = typer.Option(False, "--all", help="Every repo's sessions, not only the one you're in."),
    days: int = typer.Option(7, "--days", help="Also list sessions with nothing open whose last line is this recent."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """The sessions on the board: which still run, when each last wrote, what each holds open, and where its tool
    keeps the conversation.

    A session is live when its agent process (the number at the end of its id) still runs and is older than the
    session's first line. `--to REPO-SESSION` on a post reaches one of them. A tool's row in agentboard/tools.py
    (`address`, `resume`) says where that tool keeps the conversation and how to reopen it; without one, the name
    and what it holds open is all there is."""
    repo = None if all_repos else identity.here()
    if not repo and not all_repos:
        raise typer.BadParameter("run it inside a git repo, or pass --all")
    rows = board.sessions(board.agent_posts(), repo=repo, days=days)
    me = identity.session_id()
    for e in rows:
        tool = agent_tools.named(e.get("actor"))
        e["address"] = tool.address.format(session=e["tool_session"]) if tool and tool.address and e.get("tool_session") else None
        e["resume"] = tool.resume.format(session=e["tool_session"]) if tool and tool.resume and e.get("tool_session") else None
        e["this_session"] = bool(me and e["session"] == me)
    if json_output:
        print_json(rows)
        return
    if not rows:
        console.print(f"[dim]No session of {repo or 'any repo'} wrote to the board in the last {days} days.[/dim]")
        return
    for e in rows:
        state = "live" if e["live"] else "ended" if e["live"] is False else "unknown"
        held = "; ".join(f"{o['kind']} {o['id']}" for o in e["open"]) or "nothing open"
        where = f"  {e['resume']}" if e.get("resume") else f"  {e['address']}" if e.get("address") else ""
        mine = " (this session)" if e["this_session"] else ""
        branch = f" ({e['branch']})" if e.get("branch") else ""
        print(f"{e['name']}{branch}{mine}: {state}, last {_ago(e['last'])} ago, {held}{where}")


SETTINGS_GROUP = "agentboard.settings"  # entry points: modules that call config.configure() when imported


def load_wrappers() -> None:
    """Import every module named in the entry-point group `agentboard.settings` (a wrapper's configure() call), so
    `agents` shows the same board as the wrapper. $AGENTS_WRAPPERS=off skips them. A wrapper that fails to load is
    skipped with a warning."""
    import os

    if os.environ.get("AGENTS_WRAPPERS", "").strip().lower() in ("off", "0", "no"):
        return
    from importlib import metadata

    eps = metadata.entry_points()
    group = eps.select(group=SETTINGS_GROUP) if hasattr(eps, "select") else eps.get(SETTINGS_GROUP, [])
    for ep in group:
        try:
            ep.load()
        except Exception as exc:  # noqa: BLE001 - a broken wrapper must not stop the board
            print(f"WARNING: agentboard wrapper {ep.name} ({ep.value}) didn't load: {exc}", file=sys.stderr)


def main() -> None:
    """`agents`: the board with this module's settings (config.py: the defaults, or what a wrapper configured)."""
    load_wrappers()
    agents_app(prog_name="agents")
