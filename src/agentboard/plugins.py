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

ATTACH_MODES = ("cursor", "antigravity", "interpreter")
_ON = frozenset({"on", "1", "true", "yes", "interpreter"})  # interpreter = legacy alias for on
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
    """cursor/antigravity: open IDE (no agent starts). interpreter: interactive Open Interpreter in repo."""
    load_headless_env_defaults()
    raw = os.environ.get("AGENTS_ATTACH", "").strip().lower() or _legacy_attach() or "cursor"
    if raw in ("macos-cursor", "open"):
        raw = "cursor"
    elif raw == "agy":
        raw = "antigravity"
    if raw not in ATTACH_MODES:
        raise ValueError(f"AGENTS_ATTACH={raw!r} unknown (use: {', '.join(ATTACH_MODES)})")
    if raw == "interpreter" and not shutil.which("interpreter"):
        raise ValueError("AGENTS_ATTACH=interpreter but interpreter not on PATH")
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
    """Run background auto on post: only when wanted and AGENTS_ATTACH=interpreter."""
    if not headless_auto_wanted():
        return False
    mode = attach_mode()
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
    if shutil.which("agy"):
        return ["agy", root]
    if sys.platform != "darwin":
        raise ValueError("AGENTS_ATTACH=antigravity needs agy on PATH, macOS, or set AGENTS_ATTACH_OPEN_CMD")
    return ["open", "-a", "Antigravity", root]


def interpreter_exec_argv(prompt: str) -> list[str]:
    custom = (
        os.environ.get("AGENTS_INTERPRETER_CMD", "").strip()
        or os.environ.get("AGENTS_HEADLESS_LLM_CMD", "").strip()
        or os.environ.get("AGENTS_ATTACH_SHELL_CMD", "").strip()
    )
    if custom:
        return [*custom.split(), prompt]
    return ["interpreter", "exec", "--", prompt]
