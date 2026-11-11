"""The worktrees of every repo the board knows, and which of them can go: `agents worktrees [--prune]`.

A repo's main checkout is found from the `root` its board lines carry (board.post adds it), else ~/<repo>. A
worktree can be removed only when its branch is merged into the repo's primary branch (git, or a merged PR by
`gh`), it has no uncommitted changes and no commits that are on no remote, no open claim or hand-off names its
branch or path, and no live session of the repo is on its branch. Everything else is kept, with the reasons.
"""
from __future__ import annotations

import os
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


def upstream_base(root: Path) -> tuple[str, str]:
    """(remote, primary) for `root`: GIT_PRIMARY_REMOTE / upstream / origin, and GIT_PRIMARY_BRANCH / dev.local /
    main / master (matching gland's pre-push and git-sync). Base ref is `refs/remotes/{remote}/{primary}`."""
    remote = os.environ.get("GIT_PRIMARY_REMOTE", "").strip()
    if not remote:
        for r in ("upstream", "origin"):
            if git(root, "remote", "get-url", r)[0] == 0 or git(root, "for-each-ref", "--count=1", f"refs/remotes/{r}/")[1]:
                remote = r
                break
        else:
            remote = "origin"
    branch = os.environ.get("GIT_PRIMARY_BRANCH", "").strip()
    if not branch:
        for b in ("dev.local", "main", "master"):
            if (git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{b}")[0] == 0
                    or git(root, "show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{b}")[0] == 0):
                branch = b
                break
        else:
            branch = primary(root)
    return remote, branch


def _conflict_paths(out: str) -> list[str]:
    head, _, _ = out.partition("\n\n")
    paths: list[str] = []
    for line in head.splitlines()[1:]:
        if "\t" in line:
            paths.append(line.split("\t", 1)[1].strip())
        elif line.strip() and not line.startswith(("Auto-merging ", "CONFLICT ")):
            paths.append(line.strip())
    if not paths:
        paths = [m.strip() for m in re.findall(r"^CONFLICT [^:]*: .*? in (.+)$", out, re.M)]
    return list(dict.fromkeys(p for p in paths if p))


def divergence(root: Path, branch: str, base_ref: str) -> dict:
    """How `branch` compares to `base_ref` (e.g. refs/remotes/upstream/master): behind, ahead, rebase_clean,
    conflicts (file paths from `git merge-tree --write-tree`), and cherry_picked (`-` lines in `git cherry`)."""
    empty = {"behind": 0, "ahead": 0, "rebase_clean": True, "conflicts": [], "cherry_picked": 0}
    if not branch or git(root, "rev-parse", "--verify", "--quiet", base_ref)[0] != 0:
        return empty
    b_cnt = git(root, "rev-list", "--count", f"{branch}..{base_ref}")[1]
    a_cnt = git(root, "rev-list", "--count", f"{base_ref}..{branch}")[1]
    behind = int(b_cnt) if b_cnt.isdigit() else 0
    ahead = int(a_cnt) if a_cnt.isdigit() else 0
    rebase_clean, conflicts, cherry_picked = True, [], 0
    if behind > 0 and ahead > 0:
        code, mt_out = git(root, "merge-tree", "--write-tree", base_ref, branch)
        rebase_clean = code == 0
        if not rebase_clean:
            conflicts = _conflict_paths(mt_out)
        ch_code, ch_out = git(root, "cherry", base_ref, branch)
        if ch_code == 0:
            cherry_picked = sum(1 for ln in ch_out.splitlines() if ln.startswith("-"))
    return {"behind": behind, "ahead": ahead, "rebase_clean": rebase_clean, "conflicts": conflicts, "cherry_picked": cherry_picked}


def listing(root: Path, *, include_main: bool = False) -> list[dict]:
    """`git worktree list` of `root` (without the main checkout unless `include_main=True`): path, branch (None when detached), missing."""
    out: list[dict] = []
    for line in git(root, "worktree", "list", "--porcelain")[1].splitlines():
        if line.startswith("worktree "):
            out.append({"path": line.split(" ", 1)[1], "branch": None})
        elif line.startswith("branch ") and out:
            out[-1]["branch"] = line.split(" ", 1)[1].removeprefix("refs/heads/")
        elif line.startswith("prunable") and out:
            out[-1]["missing"] = True
    if include_main and not out and root.is_dir():
        out.append({"path": str(root), "branch": git(root, "branch", "--show-current")[1] or None})
    if include_main:
        return out
    return [w for w in out if Path(w["path"]).resolve() != root.resolve()]


def dirty_tracked_count(path: Path) -> int:
    """Count of uncommitted tracked changes in `path` (`git status --porcelain --untracked-files=no`)."""
    if not path.is_dir():
        return 0
    code, out = git(path, "status", "--porcelain", "--untracked-files=no")
    return len([ln for ln in out.splitlines() if ln.strip()]) if code == 0 and out else 0


def unpushed_count(root: Path, branch: Optional[str], main: str) -> int:
    """Commits on `branch` not on any remote (or ahead of `main` when the repo has no remote refs)."""
    if not branch:
        return 0
    has_remotes = bool(git(root, "for-each-ref", "--count=1", "refs/remotes/")[1])
    if has_remotes:
        count = git(root, "rev-list", "--count", branch, "--not", "--remotes")[1]
    elif branch != main:
        count = git(root, "rev-list", "--count", branch, "--not", f"refs/heads/{main}")[1]
    else:
        return 0
    return int(count) if count.isdigit() else 0


def checkout_last_ts(path: Path, branch: Optional[str] = None) -> Optional[int]:
    """Unix timestamp of latest commit on `branch` (or HEAD) or working-tree modified tracked file in `path`."""
    if not path.is_dir():
        return None
    stamp = git(path, "log", "-1", "--format=%ct", branch or "HEAD")[1]
    stamps: list[int] = [int(stamp)] if stamp.isdigit() else []
    code, out = git(path, "status", "--porcelain", "--untracked-files=no")
    if code == 0 and out:
        for ln in out.splitlines():
            parts = ln.strip().split(None, 1)
            if len(parts) < 2:
                continue
            rel = parts[1].split(" -> ")[-1].strip('"')
            try:
                stamps.append(int((path / rel).stat().st_mtime))
            except OSError:
                pass
    return max(stamps) if stamps else None


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


def inspect(repo: str, root: Path, open_items: list[dict], sessions: list[dict], sizes: bool = True, use_gh: bool = True,
            include_main: bool = False) -> list[dict]:
    """Each worktree of `repo`: branch, merged, dirty, unpushed, behind, ahead, rebase_clean, conflicts,
    cherry_picked, age_days, size_mb, venv_mb, held_by, removable and why (the reasons it is kept)."""
    main = primary(root)
    remote, up_main = upstream_base(root)
    base_ref = f"refs/remotes/{remote}/{up_main}"
    merged = set(git(root, "branch", "--format=%(refname:short)", "--merged", main)[1].splitlines())
    out = []
    for w in listing(root, include_main=include_main):
        path, branch = Path(w["path"]), w["branch"]
        missing = bool(w.get("missing")) or not path.is_dir()
        is_main = not missing and path.resolve() == root.resolve()
        e = {"repo": repo, "root": str(root), "path": str(path), "branch": branch, "primary": main,
             "upstream": f"{remote}/{up_main}", "missing": missing, "is_main": is_main}
        e["merged"] = bool(branch) and branch != main and (branch in merged or (use_gh and pr_merged(root, branch)))
        e["dirty"] = not missing and bool(git(path, "status", "--porcelain")[1])
        e["dirty_count"] = dirty_tracked_count(path) if not missing else 0
        e["unpushed"] = unpushed_count(root, branch, main)
        e.update(divergence(root, branch or "", base_ref) if branch and branch != up_main else
                 {"behind": 0, "ahead": 0, "rebase_clean": True, "conflicts": [], "cherry_picked": 0})
        stamp = git(root, "log", "-1", "--format=%ct", branch)[1] if branch else ""
        e["age_days"] = int((time.time() - int(stamp)) // 86400) if stamp.isdigit() else None
        e["last_ts"] = checkout_last_ts(path, branch) if not missing else None
        e["size_mb"] = size_mb(path) if sizes else None
        e["venv_mb"] = size_mb(path / ".venv") if sizes else None
        e["held_by"] = holders(w, repo, open_items, sessions)
        why = []
        if is_main:
            why.append("main checkout")
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


def inspect_checkouts(
    rows: Optional[list[dict]] = None,
    *,
    include_main: bool = True,
    skip_repos: tuple[str, ...] | set[str] | list[str] = ("work",),
) -> list[dict]:
    """Inspect every repo in `repo_roots(rows)` (main checkout + secondary worktrees by default).
    Returns entries with: repo, root, path, branch, primary, is_main, dirty (count of uncommitted tracked changes
    via `git status --porcelain --untracked-files=no`), unpushed (commits ahead of remote tracking or primary),
    last_ts (unix timestamp of latest commit or working-tree modified file), and held_by (open claims/handoffs)."""
    from agentboard import board

    if rows is None:
        rows = board.agent_posts()
    skip = set(skip_repos or ())
    roots = repo_roots(rows)
    view = board.agents_view(rows)
    open_items = view["claims"] + view["handoffs"]
    live_sessions = board.sessions(rows, days=30)
    out: list[dict] = []
    for repo, root in sorted(roots.items()):
        if repo in skip or not root.is_dir():
            continue
        main = primary(root)
        for w in listing(root, include_main=include_main):
            path, branch = Path(w["path"]), w["branch"]
            if w.get("missing") or not path.is_dir():
                continue
            out.append({
                "repo": repo,
                "root": str(root),
                "path": str(path),
                "branch": branch,
                "primary": main,
                "is_main": path.resolve() == root.resolve(),
                "dirty": dirty_tracked_count(path),
                "unpushed": unpushed_count(root, branch, main),
                "last_ts": checkout_last_ts(path, branch),
                "held_by": holders(w, repo, open_items, live_sessions),
            })
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
