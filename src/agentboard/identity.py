"""Who is running: the actor (user, runner, agent:<tool>), the agent session's id and name, and the repo it is in.

The same for every command of one session; another copy of the session (resumed, forked) gets another id. The
variables are named by config.Settings.env_prefix: $<prefix>_ACTOR, $<prefix>_SESSION, $<prefix>_AGENT_PID.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from agentboard import config, tools

SHELLS = {"sh", "bash", "zsh", "dash", "fish", "ksh", "csh", "tcsh", "env", "uv", "uvx", "timeout", "sudo", "login"}
_session: list = []  # [(the environment it was worked out from, the answer)]: once per process


def actor() -> str:
    explicit = os.environ.get(config.settings.env("ACTOR"), "").strip()
    if explicit:
        return explicit
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "runner"
    for var, name in tools.detect_env():
        if os.environ.get(var):
            return name
    return "user"


def agent_pid() -> Optional[int]:
    """The agent's own process (the tool running this session): $<prefix>_AGENT_PID, else the one its tool exports
    (if it does), else the nearest ancestor that isn't a shell, uv or python. The same for every command of one
    session; another copy of the session differs."""
    given = os.environ.get(config.settings.env("AGENT_PID"), "").strip() or tools.env(tools.named(actor()), "pid_env")
    if given.isdigit():
        return int(given)
    skip = SHELLS | set(config.settings.shells)
    pid = os.getppid()
    for _ in range(8):
        try:
            out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
        if not out or len(out.split(None, 1)) < 2:
            return None
        ppid, comm = out.split(None, 1)
        name = Path(comm.strip()).name.lstrip("-").lower()
        if name not in skip and not name.startswith("python"):
            return pid
        if not ppid.isdigit() or int(ppid) <= 1:
            return None
        pid = int(ppid)
    return None


def session_id() -> Optional[str]:
    """This agent session's id, short and unique per running copy: $<prefix>_SESSION (any tool can set it), else
    `<first 4 of the session id its tool exports>.<agent process>` (a resumed or forked copy of a conversation keeps
    the tool's id, not its process), else `p<agent process>` for any agent. None for a person at a terminal."""
    s = config.settings
    key = tuple(os.environ.get(v, "") for v in (s.env("SESSION"), s.env("AGENT_PID"), s.env("ACTOR"), *tools.every_env()))
    if _session and _session[0][0] == key:
        return _session[0][1]
    explicit = os.environ.get(s.env("SESSION"), "").strip()
    if explicit:
        value: Optional[str] = re.sub(r"[^A-Za-z0-9._-]", "-", explicit)[:40]
    else:
        tool_id = tools.env(tools.named(actor()), "session_env").replace("-", "")[:4]
        pid = agent_pid() if (tool_id or actor().startswith("agent:")) else None
        value = f"{tool_id}.{pid}" if tool_id and pid else tool_id or (f"p{pid}" if pid else None)
    _session[:] = [(key, value)]
    return value


def session_name(repo: Optional[str] = None) -> Optional[str]:
    """`<repo>-<id>`, e.g. api-734b.4506: what a session calls itself on the board and in its first message."""
    sid = session_id()
    if not sid:
        return None
    return f"{repo}-{sid}" if repo else sid


def git_here(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def here() -> Optional[str]:
    """The repo the current directory is in, by its main checkout's folder name (api, web), the same in every
    worktree of it (~/api-fix, a tool's own worktree folder). None outside git."""
    common = git_here("rev-parse", "--path-format=absolute", "--git-common-dir")
    if common:
        path = Path(common)
        return (path.parent if path.name == ".git" else path).name.removesuffix(".git")
    top = git_here("rev-parse", "--show-toplevel")
    return Path(top).name if top else None
