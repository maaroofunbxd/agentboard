"""Where the board lives and what it calls itself: the settings a program using kit.agents gives it.

Defaults, for the board on its own: the board in $AGENTS_BOARD_DIR (else ~/.agents/board), the user's agent folder
in $AGENTS_DIR (else ~/.agents), the session read from $AGENTS_SESSION / $AGENTS_ACTOR / $AGENTS_AGENT_PID. A
program wraps it by calling `configure(...)` once at import, before any board or identity call (for example to keep
the board in its own data folder and name the variables <ITS PREFIX>_*). So that the `agents` command shows the same
board as the wrapper, the wrapper names that module as an entry point in the group `agentboard.settings`
(README.md, "Wrapping the board"); `agents` imports it before it starts.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from agentboard.store import Store


def _env_path(var: str, default: str) -> Path:
    return Path(os.environ.get(var, "").strip() or default).expanduser()


@dataclass(frozen=True)
class Settings:
    # where the lines are kept (store.py); None = the plain file in board_dir()
    store: Optional[Callable[[], Optional["Store"]]] = None
    # the folder holding agents.jsonl; None = the board is off
    board_dir: Callable[[], Optional[Path]] = lambda: _env_path("AGENTS_BOARD_DIR", "~/.agents/board")
    # the user's agent folder: <repo>.md (`agents link`) and global.md (`agents setup`)
    agents_dir: Callable[[], Path] = lambda: _env_path("AGENTS_DIR", "~/.agents")
    # which session has read the board up to when (the [board] nudge)
    seen_file: Callable[[], Path] = lambda: _env_path("AGENTS_DIR", "~/.agents") / "seen.json"
    command: str = "agents"  # how messages name the command: `<command> status`
    env_prefix: str = "AGENTS"  # $<prefix>_SESSION, $<prefix>_ACTOR, $<prefix>_AGENT_PID
    # the fields a board line starts with; None = ts, by, actor, session (board.who)
    line_fields: Optional[Callable[[], dict]] = None
    prompt_hook: str = ""  # the command `agents setup` adds to a tool's prompt hook; "" = none
    global_template: Optional[Path] = None  # what `agents setup` starts <agents dir>/global.md from
    off_reason: str = "the board is off (no board folder)"  # said when board_dir() is None
    shells: frozenset = field(default_factory=lambda: frozenset())  # more process names to skip looking for the agent

    def env(self, name: str) -> str:
        """The variable `<prefix>_<name>`: SESSION, ACTOR, AGENT_PID."""
        return f"{self.env_prefix}_{name}"


settings = Settings()


def configure(**changes) -> Settings:
    """Replace some settings (the rest stay); returns the new ones."""
    global settings
    settings = replace(settings, **changes)
    return settings
