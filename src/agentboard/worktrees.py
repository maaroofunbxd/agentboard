"""The worktrees of every repo the board knows, and which of them can go: `agents worktrees [--prune]`.

A repo's main checkout is found from the `root` its board lines carry (board.post adds it), else ~/<repo>. A
worktree can be removed only when its branch is merged into the repo's primary branch (git, or a merged PR by
`gh`), it has no uncommitted changes and no commits that are on no remote, no open claim or hand-off names its
branch or path, and no live session of the repo is on its branch. Everything else is kept, with the reasons.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from agentboard import identity


def git(root: Path | str, *args: str, timeout: int = 10) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return p.returncode, p.stdout.strip()


def main_checkout() -> Optional[str]:
    """The main checkout of the repo you're in (the folder of its git common dir), the same from every worktree."""
    common = identity.git_here("rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return None
    path = Path(common)
    return str(path.parent if path.name == ".git" else path)


def repo_roots(rows: list[dict]) -> dict[str, Path]:
    """repo name -> main checkout, for every repo on the board that has one on this machine."""
    out: dict[str, Path] = {}
    for r in rows:
        repo, root = r.get("repo"), r.get("root")
        if repo and root and Path(root).is_dir():
            out[repo] = Path(root)
    for repo in {r.get("repo") for r in rows if r.get("repo")} - set(out):
        guess = Path.home() / repo
        if (guess / ".git").exists():
            out[repo] = guess
    return out


def primary(root: Path) -> str:
    code, ref = git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if code == 0 and "/" in ref:
        return ref.split("/", 1)[1]
    for name in ("main", "master"):
        if git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}")[0] == 0:
            return name
    return "main"


def listing(root: Path) -> list[dict]:
    """`git worktree list` of `root`, without the main checkout: path, branch (None when detached), missing."""
    out: list[dict] = []
    for line in git(root, "worktree", "list", "--porcelain")[1].splitlines():
        if line.startswith("worktree "):
            out.append({"path": line.split(" ", 1)[1], "branch": None})
        elif line.startswith("branch ") and out:
            out[-1]["branch"] = line.split(" ", 1)[1].removeprefix("refs/heads/")
        elif line.startswith("prunable") and out:
            out[-1]["missing"] = True
    return [w for w in out if Path(w["path"]).resolve() != root.resolve()]


def size_mb(path: Path) -> Optional[int]:
    if not path.is_dir():
        return None
    try:
        out = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True, timeout=120).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return int(out[0]) // 1024 if out and out[0].isdigit() else None


def pr_merged(root: Path, branch: str) -> bool:
    """A merged pull request from `branch` (`gh`), for squash and rebase merges git can't see."""
    if not shutil.which("gh"):
        return False
    try:
        p = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "merged", "--json", "number", "-q", "length"],
                           cwd=root, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0 and p.stdout.strip() not in ("", "0")


def holders(w: dict, repo: str, open_items: list[dict], sessions: list[dict]) -> list[str]:
    """Open claims and hand-offs of `repo` naming the worktree's branch or path, and live sessions on its branch."""
    branch, path = w.get("branch"), w["path"]
    word = re.compile(rf"(?<![\w/.-]){re.escape(branch)}(?![\w/-])") if branch else None
    out = []
    for r in open_items:
        if r.get("repo") != repo:
            continue
        text = " ".join([r.get("text", ""), *(r.get("paths") or [])])
        if path in text or Path(path).name in text.split() or (word and word.search(text)):
            out.append(f"{r['kind']} {r['id']}")
    out += [f"live session {s['name']}" for s in sessions
            if s["repo"] == repo and s.get("live") and branch and s.get("branch") == branch]
    return out


def inspect(repo: str, root: Path, open_items: list[dict], sessions: list[dict], sizes: bool = True, use_gh: bool = True) -> list[dict]:
    """Each worktree of `repo`: branch, merged, dirty, unpushed, age_days, size_mb, venv_mb, held_by, removable and
    why (the reasons it is kept)."""
    main = primary(root)
    merged = set(git(root, "branch", "--format=%(refname:short)", "--merged", main)[1].splitlines())
    out = []
    for w in listing(root):
        path, branch = Path(w["path"]), w["branch"]
        missing = bool(w.get("missing")) or not path.is_dir()
        e = {"repo": repo, "root": str(root), "path": str(path), "branch": branch, "primary": main, "missing": missing}
        e["merged"] = bool(branch) and branch != main and (branch in merged or (use_gh and pr_merged(root, branch)))
        e["dirty"] = not missing and bool(git(path, "status", "--porcelain")[1])
        count = git(root, "rev-list", "--count", branch, "--not", "--remotes", f"refs/heads/{main}")[1] if branch else ""
        e["unpushed"] = int(count) if count.isdigit() else 0
        stamp = git(root, "log", "-1", "--format=%ct", branch)[1] if branch else ""
        e["age_days"] = int((time.time() - int(stamp)) // 86400) if stamp.isdigit() else None
        e["size_mb"] = size_mb(path) if sizes else None
        e["venv_mb"] = size_mb(path / ".venv") if sizes else None
        e["held_by"] = holders(w, repo, open_items, sessions)
        why = []
        if not branch:
            why.append("detached HEAD")
        elif branch == main:
            why.append(f"on {main}")
        elif not e["merged"]:
            why.append(f"not merged into {main}")
        if e["dirty"]:
            why.append("uncommitted changes")
        if e["unpushed"]:
            why.append(f"{e['unpushed']} commit(s) on no remote")
        why += [f"held by {h}" for h in e["held_by"]]
        e["why"], e["removable"] = why, not why
        out.append(e)
    return out


def remove(e: dict) -> list[str]:
    """Remove a removable worktree, its local branch, and its branch on origin when there. What was done."""
    root, branch, done = e["root"], e["branch"], []
    if e["missing"]:
        git(root, "worktree", "prune")
    elif git(root, "worktree", "remove", e["path"])[0] != 0:
        return [f"git worktree remove {e['path']} failed; kept"]
    done.append(f"removed {e['path']}")
    if git(root, "branch", "-D", branch)[0] == 0:
        done.append(f"deleted branch {branch}")
    if git(root, "ls-remote", "--exit-code", "--heads", "origin", branch, timeout=30)[0] == 0:
        ok = git(root, "push", "origin", "--delete", branch, timeout=60)[0] == 0
        done.append(f"deleted origin/{branch}" if ok else f"could not delete origin/{branch}")
    return done
