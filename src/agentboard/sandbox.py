"""Per-post sandbox metadata for `agents attach`."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from agentboard import config

_PATH_BACKTICK = re.compile(r"`([^`\n]+)`")
_PATH_TOKEN = re.compile(
    r"(?<![/\w])((?:src|docs|libs|tests|templates)/[\w./-]+\.[A-Za-z0-9]{2,8}|"
    r"[\w.-]+/[\w./-]+\.[A-Za-z0-9]{2,8})(?![/\w])"
)


def sessions_dir() -> Path:
    return config.settings.agents_dir() / "headless-sessions"


def load(post_id: str) -> dict:
    path = sessions_dir() / f"{post_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise FileNotFoundError(post_id) from exc


def note_attach(post_id: str, mode: str, *, exec_once: bool = False) -> None:
    path = sessions_dir() / f"{post_id}.json"
    if not path.is_file():
        return
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(meta, dict):
        return
    meta["last_attach"] = {
        "mode": mode,
        "exec": exec_once,
        "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")


def list_open() -> list[dict]:
    folder = sessions_dir()
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def paths_mentioned_in_text(text: str) -> list[str]:
    """Repo-relative file paths mentioned in post text (backticks and path-like tokens)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in _PATH_BACKTICK.findall(text):
        cand = raw.strip().split()[0] if raw.strip() else ""
        if cand and _looks_like_repo_path(cand):
            _add_path(cand, seen, out)
    for m in _PATH_TOKEN.finditer(text):
        _add_path(m.group(1), seen, out)
    return out


def _looks_like_repo_path(s: str) -> bool:
    if "://" in s or s.startswith("..") or s.startswith("/"):
        return False
    if "/" not in s and not s.endswith((".py", ".md", ".yml", ".yaml", ".toml", ".sh", ".rs", ".go")):
        return False
    return bool(re.search(r"\.[A-Za-z0-9]{2,8}$", s))


def _add_path(raw: str, seen: set[str], out: list[str]) -> None:
    p = raw.strip().strip("'\"")
    if not p or p in seen:
        return
    seen.add(p)
    out.append(p)


def _under_root(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def file_excerpt(root: Path, rel: str, *, max_lines: int = 150) -> str | None:
    path = (root / rel).expanduser()
    if not path.is_file() or not _under_root(root, path):
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:max_lines]
    except OSError:
        return None
    return f"=== {rel} (first {len(lines)} lines) ===\n" + "\n".join(lines)


def path_context_block(root: Path, text: str, *, max_lines: int = 150, max_files: int = 8) -> str:
    """Head files referenced in post text (repo root only)."""
    root = root.expanduser().resolve()
    parts: list[str] = []
    for rel in paths_mentioned_in_text(text):
        if len(parts) >= max_files:
            break
        bit = file_excerpt(root, rel, max_lines=max_lines)
        if bit:
            parts.append(bit)
    return "\n\n".join(parts)


def build_attach_prompt(
    post_id: str,
    root: Path,
    post_text: str,
    *,
    max_file_lines: int = 150,
    max_files: int = 8,
) -> str:
    root = root.expanduser()
    extra = path_context_block(root, post_text, max_lines=max_file_lines, max_files=max_files)
    body = post_text
    if extra:
        body = f"{post_text}\n\n## Files mentioned in the post\n\n{extra}"
    return (
        f"Board post {post_id} for this repo only. Root: {root}\n\n"
        f"{body}\n\n"
        f"Do the work in this repository. Use shell for `agents status` and "
        f"`agents done {post_id} \"summary\"` when finished. Follow AGENTS.md if present."
    )
