"""The agent tools recognised by name (Claude Code, Codex, Gemini CLI, Cursor), and the only place that names them.

Nothing on the board needs any of them. With none, a person at a terminal, or any agent tool that sets
<PREFIX>_ACTOR=agent:<name> and <PREFIX>_SESSION=<id> on its commands (config.Settings.env_prefix: AGENTS_, or a wrapper's),
gets every command. A row here only adds what a tool offers by itself: recognising it from the variables it sets in
its shells (so it needn't set the actor), its session id and process (so it needn't set the session), the command
that starts a session with a prompt, a file it loads by itself that can pull in a repo's AGENTS.local.md (`agents
link --for TOOL`), and where it keeps its global instructions and its prompt hook, which `agents setup` copies in
from <agents dir>/global.md. A new tool is a new row; a tool that goes away is a deleted row, and nothing else changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Tool:
    name: str  # as in actor `agent:<name>` and prompts.jsonl's `tool`
    detect: tuple[str, ...]  # a variable the tool sets in the shells it runs
    session_env: str = ""  # a variable holding its session id, if it sets one
    pid_env: str = ""  # a variable holding its own process id, if it sets one
    command: str = ""  # starts a session with a prompt: `<command> "PROMPT"`
    local_file: str = ""  # a per-clone file it loads by itself, which can import AGENTS.local.md
    repo_file: str = ""  # its committed instructions file; when missing, local_file imports AGENTS.md too
    import_line: str = "{}"  # how local_file pulls in another file
    global_file: str = ""  # its global instructions file (~ allowed): `agents setup` writes a copy of global.md there
    settings_file: str = ""  # its JSON settings file holding hooks, when it runs a command on each prompt
    prompt_hook_event: str = ""  # the hook event in settings_file that fires on each prompt

    @property
    def actor(self) -> str:
        return f"agent:{self.name}"


TOOLS = (
    Tool("claude-code", ("CLAUDECODE",), session_env="CLAUDE_CODE_SESSION_ID", pid_env="CLAUDE_PID", command="claude",
         local_file="CLAUDE.local.md", repo_file="CLAUDE.md", import_line="@{}", global_file="~/.claude/CLAUDE.md",
         settings_file="~/.claude/settings.json", prompt_hook_event="UserPromptSubmit"),
    Tool("codex", ("CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED"), command="codex"),
    Tool("gemini-cli", ("GEMINI_CLI",), command="gemini"),
    Tool("cursor", ("CURSOR_AGENT",), command="cursor-agent"),
)


def detect_env() -> tuple[tuple[str, str], ...]:
    """(variable, actor) pairs, checked in order: the first one set says which tool runs this shell."""
    return tuple((var, tool.actor) for tool in TOOLS for var in tool.detect)


def every_env() -> tuple[str, ...]:
    """Every variable a row reads: what a test clears, and what the session id is worked out from."""
    return tuple(dict.fromkeys(v for t in TOOLS for v in (*t.detect, t.session_env, t.pid_env) if v))


def named(name: Optional[str]) -> Optional[Tool]:
    """The row for `claude-code` or `agent:claude-code`; None for any other."""
    name = (name or "").removeprefix("agent:")
    return next((t for t in TOOLS if t.name == name), None)


def env(tool: Optional[Tool], which: str) -> str:
    """The value of the tool's `session_env` or `pid_env` in this environment, '' when it has none."""
    var = getattr(tool, which, "") if tool else ""
    return os.environ.get(var, "").strip() if var else ""


def with_prompt_hook(tool: Tool, settings: dict, command: str, timeout: int = 5) -> dict:
    """`settings` (the tool's settings_file, parsed) with `command` run on each prompt; unchanged when already there."""
    if not tool.prompt_hook_event:
        return settings
    groups = settings.get("hooks", {}).get(tool.prompt_hook_event, [])
    if any(h.get("command") == command for g in groups for h in g.get("hooks", [])):
        return settings
    hook = {"type": "command", "command": command, "timeout": timeout}
    hooks = {**settings.get("hooks", {}), tool.prompt_hook_event: [*groups, {"hooks": [hook]}]}
    return {**settings, "hooks": hooks}
