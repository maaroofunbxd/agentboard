"""Optional scripts in <agents dir>/hooks/on_KIND: run after a line is appended to the board. Never raises."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from agentboard import config

HOOK_KINDS = ("post", "reply", "done", "claim", "handoff")


def hooks_dir() -> Path:
    return config.settings.agents_dir() / "hooks"


def bundled_scripts() -> Path:
    return Path(__file__).resolve().parent / "hook_scripts"


def _hook_argv(script: Path) -> list[str]:
    """Run Python hook scripts with the same interpreter as `agents` (venv), not /usr/bin/env python3."""
    try:
        first = script.read_text(encoding="utf-8").split("\n", 1)[0]
    except OSError:
        return [str(script)]
    if first.startswith("#!") and "python" in first.lower():
        return [sys.executable, str(script)]
    return [str(script)]


def run(kind: str, entry: dict) -> None:
    """Run hooks/on_{kind} with the new line as JSON on stdin. AGENTS_HOOKS=off skips."""
    if os.environ.get(config.settings.env("HOOKS"), "").strip().lower() in ("off", "0", "no"):
        return
    if kind not in HOOK_KINDS:
        return
    script = hooks_dir() / f"on_{kind}"
    if not script.is_file():
        return
    if not os.access(script, os.X_OK):
        return
    try:
        subprocess.run(
            _hook_argv(script),
            input=json.dumps(entry, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=int(os.environ.get(config.settings.env("HOOK_TIMEOUT"), "120")),
            check=False,
            env=os.environ,
        )
    except (OSError, subprocess.SubprocessError):
        return


def install_examples(*, force: bool = False) -> list[str]:
    """Copy bundled hook_scripts into hooks_dir(); returns paths installed."""
    dest = hooks_dir()
    dest.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for src in sorted(bundled_scripts().glob("*")):
        if not src.is_file() or src.name.startswith("."):
            continue
        out = dest / src.name
        if out.exists() and not force:
            continue
        out.write_bytes(src.read_bytes())
        out.chmod(out.stat().st_mode | 0o111)
        installed.append(str(out))
    return installed
