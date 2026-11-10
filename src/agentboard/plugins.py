"""Attach tool and optional auto on offline post.

AGENTS_ATTACH=cursor|interpreter — `agents attach POST_ID` (and which LLM when auto runs).
AGENTS_HEADLESS_AUTO=on|off     — on post: background read-only auto-done (interpreter only; ignored with cursor).

Shell exports beat `headless.env.sh` (load_headless_env_defaults).
"""
from __future__ import annotations

import os
import re
import shutil
import sys

from agentboard import config

ATTACH_MODES = ("cursor", "antigravity", "agy", "interpreter")
_ON = frozenset({"on", "1", "true", "yes", "interpreter", "antigravity", "agy"})  # tool names = legacy/convenience alias for on
_OFF = frozenset({"off", "0", "no", "false", ""})

_EXPORT_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def load_headless_env_defaults() -> None:
    """Apply `<agents dir>/headless.env.sh` without overriding variables already set in the environment."""
    path = config.settings.agents_dir() / "headless.env.sh"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = _EXPORT_RE.match(line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if not key.startswith("AGENTS_"):
            continue
        if os.environ.get(key, "").strip():
            continue
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1]
        os.environ[key] = os.path.expandvars(raw)


def _legacy_attach() -> str | None:
    if os.environ.get("AGENTS_ATTACH", "").strip():
        return None
    open_p = os.environ.get("AGENTS_ATTACH_OPEN_PLUGIN", "").strip().lower()
    if open_p in ("macos-cursor", "cursor", ""):
        return "cursor"
    return None


def attach_mode() -> str:
    """cursor/antigravity: open IDE (no agent starts). agy: Antigravity CLI in repo. interpreter: Open Interpreter in repo."""
    load_headless_env_defaults()
    raw = os.environ.get("AGENTS_ATTACH", "").strip().lower() or _legacy_attach() or "cursor"
    if raw in ("macos-cursor", "open"):
        raw = "cursor"
    if raw not in ATTACH_MODES:
        raise ValueError(f"AGENTS_ATTACH={raw!r} unknown (use: {', '.join(ATTACH_MODES)})")
    if raw == "interpreter" and not shutil.which("interpreter"):
        raise ValueError("AGENTS_ATTACH=interpreter but interpreter not on PATH")
    if raw == "agy" and not shutil.which("agy"):
        raise ValueError("AGENTS_ATTACH=agy but agy not on PATH")
    return raw


def _raw_headless_auto_flag() -> str:
    load_headless_env_defaults()
    raw = os.environ.get("AGENTS_HEADLESS_AUTO", "").strip().lower()
    if not raw:
        if os.environ.get("AGENTS_HEADLESS_LLM", "").strip() in ("1", "true", "yes"):
            return "on"
        if os.environ.get("AGENTS_HEADLESS_WORK", "1") == "0":
            return "off"
        leg = os.environ.get("AGENTS_HEADLESS_LLM_PLUGIN", "off").strip().lower()
        if leg == "interpreter" and os.environ.get("AGENTS_HEADLESS_LLM"):
            return "on"
        return "off"
    return raw


def headless_auto_wanted() -> bool:
    """User set AGENTS_HEADLESS_AUTO=on (or legacy interpreter / AGENTS_HEADLESS_LLM)."""
    return _raw_headless_auto_flag() in _ON


def headless_auto_on() -> bool:
    """Run background auto on post: when wanted and either agy (antigravity/agy) or interpreter is selected."""
    if not headless_auto_wanted():
        return False
    mode = attach_mode()
    if mode in ("antigravity", "agy"):
        if not shutil.which("agy"):
            raise ValueError("AGENTS_HEADLESS_AUTO=on with antigravity/agy needs agy on PATH")
        return True
    if mode != "interpreter":
        return False
    if not shutil.which("interpreter"):
        raise ValueError("AGENTS_HEADLESS_AUTO=on needs interpreter on PATH (set AGENTS_ATTACH=interpreter)")
    return True


def headless_auto() -> str:
    raw = _raw_headless_auto_flag()
    if raw not in _ON | _OFF:
        raise ValueError(f"AGENTS_HEADLESS_AUTO={raw!r} unknown (use: on, off)")
    return "on" if headless_auto_on() else "off"


def cursor_open_argv(root: str) -> list[str]:
    custom = os.environ.get("AGENTS_ATTACH_OPEN_CMD", "").strip()
    if custom:
        return [*custom.split(), root]
    if sys.platform != "darwin":
        raise ValueError("AGENTS_ATTACH=cursor needs macOS or set AGENTS_ATTACH_OPEN_CMD")
    return ["open", "-a", "Cursor", root]


def antigravity_open_argv(root: str) -> list[str]:
    custom = os.environ.get("AGENTS_ATTACH_OPEN_CMD", "").strip()
    if custom:
        return [*custom.split(), root]
    if sys.platform != "darwin":
        if shutil.which("agy"):
            return ["agy", root]
        raise ValueError("AGENTS_ATTACH=antigravity needs macOS or set AGENTS_ATTACH_OPEN_CMD")
    return ["open", "-a", "Antigravity", root]


def agy_exec_argv(prompt: str) -> list[str]:
    custom = os.environ.get("AGENTS_AGY_CMD", "").strip()
    if custom:
        return [*custom.split(), prompt]
    return ["agy", "-p", prompt]


def headless_exec_argv(prompt: str) -> list[str]:
    """CLI argv for non-interactive headless LLM execution (agy if attach is antigravity/agy, else interpreter)."""
    try:
        mode = attach_mode()
    except ValueError:
        mode = "antigravity" if shutil.which("agy") else "interpreter"
    if mode in ("antigravity", "agy") or (shutil.which("agy") and not shutil.which("interpreter")):
        return agy_exec_argv(prompt)
    return interpreter_exec_argv(prompt)


def interpreter_exec_argv(prompt: str) -> list[str]:
    custom = (
        os.environ.get("AGENTS_INTERPRETER_CMD", "").strip()
        or os.environ.get("AGENTS_HEADLESS_LLM_CMD", "").strip()
        or os.environ.get("AGENTS_ATTACH_SHELL_CMD", "").strip()
    )
    if custom:
        return [*custom.split(), prompt]
    return ["interpreter", "exec", "--", prompt]
