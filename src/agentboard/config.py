"""Where the board lives and what it calls itself: the settings a program using kit.agents gives it.

Defaults, for the board on its own: the board in $AGENTS_BOARD_DIR, else `board_dir` in the config file (below), else
~/.agents/board; the user's agent folder in $AGENTS_DIR, else `agents_dir` there, else ~/.agents; the seen file
`seen_file` there, else <agents dir>/seen.json; the session read from $AGENTS_SESSION / $AGENTS_ACTOR /
$AGENTS_AGENT_PID. The config file ($AGENTS_CONFIG, else $XDG_CONFIG_HOME or ~/.config, then agentboard/config.toml)
is how every copy of `agents` finds one board: the first run of `agents` with a wrapper writes the wrapper's
locations there (cli.main), and `agents where --save` writes them by hand. A wrapper's configure() always wins over
it, so a wrapper's own runs (its tests on a temporary board, say) never read or write elsewhere. A
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


KEYS = ("board_dir", "agents_dir", "seen_file")  # what the config file can hold


def config_file() -> Path:
    """$AGENTS_CONFIG, else <$XDG_CONFIG_HOME or ~/.config>/agentboard/config.toml."""
    base = os.environ.get("XDG_CONFIG_HOME", "").strip() or "~/.config"
    return _env_path("AGENTS_CONFIG", f"{base}/agentboard/config.toml")


def read_config() -> dict:
    """The config file's `key = "value"` lines (KEYS only; a TOML subset, so Python 3.9 needs no parser); {} when
    there is none."""
    try:
        text = config_file().read_text(encoding="utf-8")
    except OSError:
        return {}
    out = {}
    for line in text.splitlines():
        key, eq, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if eq and key in KEYS and len(value) >= 2 and value[0] == value[-1] == '"':
            out[key] = value[1:-1]
    return out


def write_config(values: dict) -> Path:
    """Write KEYS from `values` to the config file; returns its path. A path with a quote or backslash in it is
    refused: the reader takes the text between the quotes as it is."""
    bad = [str(v) for v in values.values() if v and any(c in str(v) for c in '"\\')]
    if bad:
        raise ValueError(f"a path with a quote or backslash can't go in {config_file()}: {bad[0]}")
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f'{k} = "{values[k]}"\n' for k in KEYS if values.get(k))
    path.write_text("# Where every copy of `agents` finds the board (agentboard/config.py).\n" + body, encoding="utf-8")
    return path


def _located(var: str, key: str, default: str) -> Path:
    """$var, else `key` in the config file, else `default`."""
    return _env_path(var, read_config().get(key) or default)


def _default_seen() -> Path:
    found = read_config().get("seen_file")
    return Path(found).expanduser() if found else _located("AGENTS_DIR", "agents_dir", "~/.agents") / "seen.json"


@dataclass(frozen=True)
class Settings:
    # where the lines are kept (store.py); None = the plain file in board_dir()
    store: Optional[Callable[[], Optional["Store"]]] = None
    # the folder holding agents.jsonl; None = the board is off
    board_dir: Callable[[], Optional[Path]] = lambda: _located("AGENTS_BOARD_DIR", "board_dir", "~/.agents/board")
    # the user's agent folder: <repo>.md (`agents link`) and global.md (`agents setup`)
    agents_dir: Callable[[], Path] = lambda: _located("AGENTS_DIR", "agents_dir", "~/.agents")
    # which session has read the board up to when (the [board] nudge)
    seen_file: Callable[[], Path] = _default_seen
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
DEFAULTS = settings  # the settings no wrapper changed: wrapped() compares against them


def wrapped() -> bool:
    """Whether a wrapper's configure() moved the board (its board_dir isn't the default)."""
    return settings.board_dir is not DEFAULTS.board_dir


def fallback_board() -> Path:
    """Where a copy of `agents` with no wrapper, no $AGENTS_BOARD_DIR and no config file keeps the board."""
    return Path("~/.agents/board").expanduser()


def configure(**changes) -> Settings:
    """Replace some settings (the rest stay); returns the new ones."""
    global settings
    settings = replace(settings, **changes)
    return settings
