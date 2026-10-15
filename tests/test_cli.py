"""`agents`: the board's commands, with agentboard's own settings (no wrapper)."""
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentboard import config
from agentboard import tools as agent_tools
from agentboard.cli import agents_app


@pytest.fixture
def jdir(tmp_path, monkeypatch):
    """The board in tmp_path/board, the agent folder in tmp_path/agents, an agent session with no tool's variables."""
    from agentboard import identity

    monkeypatch.setattr(config, "settings", config.Settings())  # the defaults, whatever a wrapper configured
    monkeypatch.setattr(identity, "_session", [])
    monkeypatch.setenv("COLUMNS", "300")  # rich wraps long paths at the terminal's width
    monkeypatch.setenv("AGENTS_BOARD_DIR", str(tmp_path / "board"))
    monkeypatch.setenv("AGENTS_DIR", str(tmp_path / "agents"))
    monkeypatch.setenv("AGENTS_CONFIG", str(tmp_path / "config.toml"))  # never the user's own
    monkeypatch.setattr(config, "fallback_board", lambda: tmp_path / "fallback")
    for var, _ in agent_tools.detect_env():
        monkeypatch.delenv(var, raising=False)
    for var in ("AGENTS_SESSION", "AGENTS_AGENT_PID", "GITHUB_ACTIONS", "GITHUB_ACTOR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENTS_ACTOR", "agent:test")
    return tmp_path / "board"


def run(*args):
    assert args[0] == "agents"
    return CliRunner().invoke(agents_app, list(args[1:]))


def test_agents_claim_status_done(jdir):
    result = run("agents", "claim", "ghci fork-PR fix, branch ghci-fork")
    assert result.exit_code == 0, result.output
    [claim] = json.loads(run("agents", "status", "--json").output)["claims"]
    assert claim["text"] == "ghci fork-PR fix, branch ghci-fork" and claim["actor"] == "agent:test"
    assert f"agents done {claim['id']}" in result.output
    assert run("agents", "handoff", "done: x; left: y; next: make sync").exit_code == 0
    assert run("agents", "done", "nope").exit_code != 0
    assert run("agents", "done", claim["id"], "merged").exit_code == 0
    view = json.loads(run("agents", "status", "--json").output)
    assert view["claims"] == [] and [h["text"] for h in view["handoffs"]] == ["done: x; left: y; next: make sync"]


def test_agents_status_reads_the_old_board_file(jdir):
    jdir.mkdir(parents=True)
    (jdir / "board.jsonl").write_text(json.dumps({"ts": "2099-01-01T00:00:00Z", "kind": "handoff", "id": "bee83f", "text": "old"}) + "\n")
    assert [h["id"] for h in json.loads(run("agents", "status", "--json").output)["handoffs"]] == ["bee83f"]
    assert run("agents", "done", "bee83f").exit_code == 0
    assert json.loads(run("agents", "status", "--json").output)["handoffs"] == []


def test_agents_done_closes_an_old_handoff(jdir):
    jdir.mkdir(parents=True)
    (jdir / "agents.jsonl").write_text(json.dumps({"ts": "2020-01-01T00:00:00Z", "kind": "handoff", "id": "old111", "text": "x"}) + "\n")
    assert run("agents", "done", "old111").exit_code == 0


def test_agents_post_to_a_repo_shows_only_there(jdir, monkeypatch):
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "tools")
    assert run("agents", "post", "document the port", "--to", "API").exit_code == 0
    assert run("agents", "post", "staging pinned to a PR build", "--to", "all").exit_code == 0
    assert run("agents", "post", "no target").exit_code != 0  # --to is required
    here = json.loads(run("agents", "status", "--json").output)
    assert [p["text"] for p in here["posts"]] == ["staging pinned to a PR build"] and here["elsewhere"] == 1
    monkeypatch.setattr(identity, "here", lambda: "api")
    there = json.loads(run("agents", "status", "--json").output)
    assert [p["text"] for p in there["posts"]] == ["document the port", "staging pinned to a PR build"]
    assert there["posts"][0]["repo"] == "tools" and there["posts"][0]["to"] == "api"
    assert len(json.loads(run("agents", "status", "--all", "--json").output)["posts"]) == 2
    assert run("agents", "done", there["posts"][0]["id"], "added in #290").exit_code == 0
    assert [p["text"] for p in json.loads(run("agents", "status", "--json").output)["posts"]] == ["staging pinned to a PR build"]


def test_old_posts_drop_off(jdir):
    import datetime

    from agentboard import board as j

    rows = [{"ts": "2020-01-01T00:00:00Z", "kind": "post", "id": "p1", "to": "api", "text": "old"}]
    assert j.agents_view(rows, repo="api")["posts"] == []
    now = datetime.datetime(2020, 1, 5, tzinfo=datetime.timezone.utc)
    assert [p["id"] for p in j.agents_view(rows, now=now, repo="api")["posts"]] == ["p1"]


def test_agents_whoami_and_the_name_on_posts(jdir, monkeypatch):
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setattr(identity, "agent_pid", lambda: None)
    assert run("agents", "whoami").exit_code == 1  # no session id (no tool id, no agent process found)
    monkeypatch.setenv("AGENTS_SESSION", "734b")
    result = run("agents", "whoami")
    assert result.exit_code == 0 and result.output.startswith("tools-734b")
    assert json.loads(run("agents", "whoami", "--json").output)["name"] == "tools-734b"
    posted = run("agents", "post", "x", "--to", "all")
    assert "from tools-734b" in posted.output
    [p] = json.loads(run("agents", "status", "--json").output)["posts"]
    assert p["session"] == "734b"


def test_agents_status_outside_a_terminal_is_one_line_each_with_counts_first(jdir, monkeypatch):
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "work")
    long = "rollout: " + "x" * 400
    run("agents", "post", long, "--to", "work")
    run("agents", "claim", "the doc")
    run("agents", "handoff", "done: a; left: b")
    out = run("agents", "status").output.splitlines()
    assert out[0] == "Board for work: 1 post(s), 1 open claim(s), 1 open hand-off(s)"
    assert out[1].startswith("[post ") and out[1].endswith(long) and " to work" in out[1]
    assert out[2].startswith("[claim ") and out[3].startswith("[handoff ")


def test_claim_paths_warn_on_overlap_and_show_in_status(jdir, monkeypatch):
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    assert run("agents", "claim", "ghci fix", "-p", "src/tools/kit/").exit_code == 0
    monkeypatch.setenv("AGENTS_SESSION", "bbbb")
    result = run("agents", "claim", "ghci timeout", "-p", "src/tools/kit/ghci.py")
    assert result.exit_code == 0 and "Overlaps open claim" in result.output and "tools-aaaa" in result.output
    assert "Overlaps" not in run("agents", "claim", "docs", "-p", "docs/cli.md").output
    claims = json.loads(run("agents", "status", "--json").output)["claims"]
    assert [c["paths"] for c in claims] == [["src/tools/kit"], ["src/tools/kit/ghci.py"], ["docs/cli.md"]]
    assert "[paths: src/tools/kit]" in run("agents", "status").output


def test_pickup_turns_a_handoff_into_my_claim(jdir, monkeypatch):
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "work")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    run("agents", "handoff", "done: a; left: b; next: make release", "-t", "PROJ-1")
    [h] = json.loads(run("agents", "status", "--json").output)["handoffs"]
    monkeypatch.setenv("AGENTS_SESSION", "bbbb")
    assert run("agents", "pickup", "nope").exit_code != 0
    assert run("agents", "pickup", h["id"]).exit_code == 0
    view = json.loads(run("agents", "status", "--json").output)
    assert view["handoffs"] == []
    [c] = view["claims"]
    assert c["session"] == "bbbb" and c["ticket"] == "PROJ-1" and f"continuing hand-off {h['id']}" in c["text"]
    assert run("agents", "pickup", h["id"]).exit_code != 0  # already picked up


def test_a_reply_to_a_post_shows_in_the_senders_repo(jdir, monkeypatch):
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    run("agents", "post", "which port does the API listen on? answer in its README", "--to", "api")
    monkeypatch.setattr(identity, "here", lambda: "api")
    monkeypatch.setenv("AGENTS_SESSION", "bbbb")
    [p] = json.loads(run("agents", "status", "--json").output)["posts"]
    assert run("agents", "done", p["id"], "8080, in the README (#12)").exit_code == 0
    assert "replies" in json.loads(run("agents", "status", "--json").output)  # api asked nothing
    monkeypatch.setattr(identity, "here", lambda: "tools")
    [r] = json.loads(run("agents", "status", "--json").output)["replies"]
    assert r["id"] == p["id"] and r["reply"] == "8080, in the README (#12)"
    assert "-> api-bbbb (" in run("agents", "status").output


def test_nudge_tells_a_session_once_about_what_is_new_for_its_repo(jdir, monkeypatch, capsys):
    from agentboard import board as j
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    j.nudge(["k8s", "find", "x"])
    assert capsys.readouterr().err == ""  # never read the board: nothing (AGENTS.md says read it first)
    j.mark_seen("aaaa", "2020-01-01T00:00:00Z")
    j.post("post", "for api only", to="api")
    j.post("claim", "my own claim")
    j.nudge(["k8s", "find", "x"])
    assert capsys.readouterr().err == ""  # not for this repo, or this session's own
    monkeypatch.setenv("AGENTS_SESSION", "bbbb")
    j.post("post", "merged agents-nudge: merge main", to="tools")
    j.post("handoff", "done: a; left: b")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    j.nudge(["agents", "status"])
    assert capsys.readouterr().err == ""  # the board command itself shows it
    j.nudge(["k8s", "find", "x"])
    err = capsys.readouterr().err
    assert err.startswith("[board] new for tools since 2020-01-01T00:00:00Z: 1 handoff, 1 post.") and "agents status" in err
    j.nudge(["k8s", "find", "x"])
    assert capsys.readouterr().err == ""  # told once


def _repo(tmp_path, name):
    import subprocess

    root = tmp_path / name
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def test_agents_link_makes_a_local_ignored_symlink_and_whoami_prints_it(jdir, monkeypatch, tmp_path):
    import os
    import subprocess

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    root = _repo(tmp_path, "api")
    monkeypatch.chdir(root)
    monkeypatch.setenv("AGENTS_SESSION", "734b")
    target = Path(os.environ["AGENTS_DIR"]) / "api.md"
    assert "create" in run("agents", "link", "--dry-run").output and not target.exists()
    result = run("agents", "link")
    assert result.exit_code == 0, result.output
    link = root / "AGENTS.local.md"
    assert link.is_symlink() and link.resolve() == target.resolve() and "## What agents need from me" in target.read_text()
    assert "AGENTS.local.md" in (root / ".git" / "info" / "exclude").read_text().split()
    assert subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True).stdout == ""
    assert "Already linked" in run("agents", "link").output  # idempotent
    link.write_text(target.read_text() + "- answer in bullets\n")  # edit from the repo: lands in the work repo
    assert "- answer in bullets" in target.read_text()
    out = run("agents", "whoami").output
    assert out.startswith("api-734b") and "- answer in bullets" in out
    assert run("agents", "link", "--remove").exit_code == 0
    assert not link.exists() and target.exists() and "AGENTS.local.md" not in (root / ".git" / "info" / "exclude").read_text()


def test_agents_link_refuses_to_replace_a_real_file(jdir, monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    root = _repo(tmp_path, "web")
    (root / "AGENTS.local.md").write_text("mine\n")
    monkeypatch.chdir(root)
    result = run("agents", "link")
    assert result.exit_code != 0 and "real file" in result.output and (root / "AGENTS.local.md").read_text() == "mine\n"


def test_whoami_reads_the_work_repo_file_without_a_link(jdir, monkeypatch, tmp_path):
    import os

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    root = _repo(tmp_path, "infra")
    monkeypatch.chdir(root)
    agents = Path(os.environ["AGENTS_DIR"])
    agents.mkdir(parents=True)
    (agents / "infra.md").write_text("## How I want answers\n- short\n")
    monkeypatch.setenv("AGENTS_SESSION", "734b")
    assert "- short" in run("agents", "whoami").output
    assert json.loads(run("agents", "whoami", "--json").output)["local_from"].endswith("agents/infra.md")


def test_agents_link_starts_from_the_repos_sample(jdir, monkeypatch, tmp_path):
    import os

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    root = _repo(tmp_path, "tools")
    (root / "AGENTS.local.md.example").write_text("# sample\n## How I want answers\n")
    monkeypatch.chdir(root)
    assert "from AGENTS.local.md.example" in run("agents", "link", "--dry-run").output
    assert run("agents", "link").exit_code == 0
    assert (Path(os.environ["AGENTS_DIR"]) / "tools.md").read_text().startswith("# sample")


def test_agents_link_writes_a_claude_local_that_imports_it(jdir, monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    root = _repo(tmp_path, "api")
    (root / "AGENTS.md").write_text("# API rules\n")  # a repo with AGENTS.md and no CLAUDE.md
    monkeypatch.chdir(root)
    assert run("agents", "link", "--for", "claude-code").exit_code == 0
    claude = (root / "CLAUDE.local.md").read_text().splitlines()
    assert claude[1:] == ["@AGENTS.md", "@AGENTS.local.md"]  # keeps Claude reading the repo's own AGENTS.md
    assert {"AGENTS.local.md", "CLAUDE.local.md"} <= set((root / ".git" / "info" / "exclude").read_text().split())
    assert "Already linked" in run("agents", "link", "--for", "claude-code").output
    assert run("agents", "link", "--remove").exit_code == 0 and not (root / "CLAUDE.local.md").exists()


def test_agents_link_leaves_a_users_own_claude_local_alone(jdir, monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    root = _repo(tmp_path, "web")
    (root / "CLAUDE.md").write_text("@AGENTS.md\n")
    (root / "CLAUDE.local.md").write_text("my notes\n")
    monkeypatch.chdir(root)
    result = run("agents", "link", "--for", "claude-code")
    assert result.exit_code != 0 and "import AGENTS.local.md in it yourself" in result.output
    assert (root / "CLAUDE.local.md").read_text() == "my notes\n"


def test_agents_status_this_session_and_its_marker(jdir, monkeypatch):
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    run("agents", "claim", "mine to close")
    monkeypatch.setenv("AGENTS_SESSION", "bbbb")
    run("agents", "claim", "another session's")
    out = run("agents", "status", "--this-session").output
    assert "another session's" in out and "mine to close" not in out and out.startswith("Board of this session: ")
    full = run("agents", "status").output
    assert "(this session): another session's" in full and "mine to close" in full and "(this session): mine" not in full
    monkeypatch.delenv("AGENTS_SESSION")
    monkeypatch.setattr(identity, "agent_pid", lambda: None)
    assert run("agents", "status", "--this-session").exit_code != 0  # no session id: says how to get one


def test_agents_status_this_session_leaves_the_nudge(jdir, monkeypatch, capsys):
    from agentboard import board as j
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    j.mark_seen("aaaa", "2020-01-01T00:00:00Z")
    monkeypatch.setenv("AGENTS_SESSION", "bbbb")
    j.post("post", "please add --memory", to="tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    assert "--memory" not in run("agents", "status", "--this-session").output
    capsys.readouterr()
    j.nudge(["k8s", "find", "x"])
    assert capsys.readouterr().err.startswith("[board] new for tools")  # the request it didn't show still nudges
    run("agents", "status")
    j.nudge(["k8s", "find", "x"])
    assert capsys.readouterr().err == ""  # the full board marks it read


def test_agents_wait_wakes_for_a_request_not_for_a_claim(jdir, monkeypatch):
    from agentboard import board as j
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    monkeypatch.setenv("AGENTS_ACTOR", "agent:codex")
    j.mark_seen("aaaa", "2020-01-01T00:00:00Z")
    monkeypatch.setenv("AGENTS_SESSION", "bbbb")
    j.post("claim", "someone's claim")
    closed = j.post("post", "already answered", to="tools")
    j.post("done", "answered", ref=closed["id"])
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    result = run("agents", "wait", "--timeout", "0.05", "--every", "0.01")
    assert result.exit_code == 124 and "Nothing new" in result.output  # a claim, or a post already closed: keep working
    monkeypatch.setenv("AGENTS_SESSION", "bbbb")
    ask = j.post("post", "please add --memory", to="tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    result = run("agents", "wait", "--timeout", "1", "--every", "0.01")
    out = result.output
    assert result.exit_code == 0 and out.startswith("[board] new for tools: 1 post\n")
    assert f"[post {ask['id']}]" in out and "please add --memory" in out and "someone's claim" not in out
    assert f'codex "Take post {ask["id"]} on the tools board (agents status)"' in out and "Leave it on the board" in out
    assert run("agents", "wait", "--timeout", "0.05", "--every", "0.01").exit_code == 124  # told once


def test_agents_wait_reply_only_says_tell_the_user(jdir, monkeypatch):
    from agentboard import board as j
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    asked = j.post("post", "api: what port does it use?", to="api")
    j.mark_seen("aaaa", "2020-01-01T00:00:00Z")
    monkeypatch.setattr(identity, "here", lambda: "api")
    monkeypatch.setenv("AGENTS_SESSION", "cccc")
    j.post("done", "8080", ref=asked["id"])
    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    out = run("agents", "wait", "--timeout", "1", "--every", "0.01").output
    assert f"[reply {asked['id']}]" in out and ": 8080" in out and "Tell the user about the replies" in out and "new session" not in out


def test_agents_conversation_post_reply_wait_done(jdir, monkeypatch):
    from agentboard import board as j
    from agentboard import identity

    asker, answerer = "aaaa.1", "bbbb.2"

    def be(session, repo):
        monkeypatch.setenv("AGENTS_SESSION", session)
        monkeypatch.setattr(identity, "here", lambda: repo)

    be(asker, "work")
    posted = run("agents", "post", "a board without polling?", "--to", "work")
    assert posted.exit_code == 0
    ref = json.loads(run("agents", "status", "--json").output)["posts"][-1]["id"]
    assert "agents wait " + ref in posted.output
    assert run("agents", "wait", ref, "--timeout", "0.01", "--every", "0.01").exit_code == 124  # nothing yet
    assert run("agents", "reply", "nope", "x").exit_code != 0

    be(answerer, "tools")
    replied = run("agents", "reply", ref, "which repos?")
    assert replied.exit_code == 0 and f"agents wait {ref}" in replied.output

    be(asker, "work")
    waited = run("agents", "wait", ref, "--timeout", "1", "--every", "0.01")
    assert waited.exit_code == 0 and f"[reply {ref}]" in waited.output and "which repos?" in waited.output
    assert [r["reply"] for r in json.loads(run("agents", "status", "--json").output)["replies"]] == ["which repos?"]
    assert run("agents", "reply", ref, "work and web").exit_code == 0
    assert run("agents", "wait", ref, "--timeout", "0.01", "--every", "0.01").exit_code == 124  # its own line doesn't count

    be(answerer, "tools")
    closed = run("agents", "done", ref, "built in abc123")
    assert closed.exit_code == 0

    be(asker, "work")
    waited = run("agents", "wait", ref, "--timeout", "1", "--every", "0.01")
    assert f"[answer {ref}]" in waited.output and "The thread is closed" in waited.output
    assert [r["kind"] for r in j.thread(j.agent_posts(), ref)] == ["post", "reply", "reply", "done"]


def test_a_followup_on_a_post_reaches_the_repo_it_asked(jdir):
    from agentboard import board as j

    rows = [{"ts": "2026-10-13T00:00:00Z", "kind": "post", "id": "p1", "repo": "work", "session": "a", "to": "tools"},
            {"ts": "2026-10-13T00:01:00Z", "kind": "reply", "ref": "p1", "repo": "tools", "session": "b", "text": "which?"},
            {"ts": "2026-10-13T00:02:00Z", "kind": "reply", "ref": "p1", "repo": "work", "session": "a", "text": "both"}]
    assert [r["reply"] for r in j.replies(rows, "work")] == ["which?"]
    assert [r["reply"] for r in j.replies(rows, "tools")] == ["both"]
    assert [r["text"] for r in j.board_asks(rows, "tools", "b", "2026-10-13T00:01:30Z")] == ["both"]


def test_agents_link_needs_no_agent_tool_file(jdir, monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    root = _repo(tmp_path, "api")
    monkeypatch.chdir(root)
    assert run("agents", "link").exit_code == 0
    assert (root / "AGENTS.local.md").is_symlink() and not (root / "CLAUDE.local.md").exists()
    assert run("agents", "link", "--for", "codex").exit_code != 0  # it has no per-clone file of its own


def test_agents_setup_keeps_a_users_own_claude_md_unless_forced(jdir, monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("my own rules\n")
    monkeypatch.setenv("HOME", str(home))
    result = run("agents", "setup")
    assert result.exit_code != 0 and "--force" in result.output
    assert (home / ".claude" / "CLAUDE.md").read_text() == "my own rules\n"
    assert run("agents", "setup", "--force").exit_code == 0
    assert (home / ".claude" / "CLAUDE.md.bak").read_text() == "my own rules\n"


def test_agents_setup_without_any_agent_tool_only_makes_global_md(jdir, monkeypatch, tmp_path):
    import os

    monkeypatch.setenv("HOME", str(tmp_path / "bare"))
    assert run("agents", "setup").exit_code == 0
    assert (Path(os.environ["AGENTS_DIR"]) / "global.md").is_file()
    assert not (tmp_path / "bare" / ".claude").exists()
    assert "no agent tool installed" in run("agents", "setup").output


def test_agents_setup_copies_global_md_into_claude_and_adds_the_prompt_hook(jdir, monkeypatch, tmp_path):
    import os

    template = tmp_path / "global-template.md"
    template.write_text("# Team rules\n- read the board first\n")
    config.configure(prompt_hook="mytool prompt", global_template=template)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(json.dumps({"theme": "light"}))
    monkeypatch.setenv("HOME", str(home))
    source = Path(os.environ["AGENTS_DIR"]) / "global.md"
    assert "create" in run("agents", "setup", "--dry-run").output and not source.exists()
    result = run("agents", "setup")
    assert result.exit_code == 0, result.output
    assert source.read_text() == template.read_text()  # started from the wrapper's template
    claude = (home / ".claude" / "CLAUDE.md").read_text()
    assert claude.startswith("<!-- made by `agents setup`") and claude.endswith(source.read_text())
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    assert settings["theme"] == "light"  # the rest of the settings stay
    assert settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "mytool prompt"
    assert "Already set up" in run("agents", "setup").output  # idempotent: one hook, same copy
    source.write_text(source.read_text() + "- answer in bullets\n")  # edit the origin, run again
    assert run("agents", "setup").exit_code == 0
    assert (home / ".claude" / "CLAUDE.md").read_text().endswith("- answer in bullets\n")


def test_the_board_is_off_without_a_store(jdir):
    config.configure(board_dir=lambda: None, off_reason="no board here")
    result = run("agents", "claim", "x")
    assert result.exit_code != 0 and "no board here" in result.output
    assert json.loads(run("agents", "status", "--json").output)["claims"] == []


def test_another_store_takes_the_lines(jdir):
    class Memory:
        def __init__(self):
            self.rows = {}

        def append(self, stream, line):
            self.rows.setdefault(stream, []).append(line)

        def lines(self, stream):
            return list(self.rows.get(stream, []))

        def changed(self, stream):
            return float(len(self.rows.get(stream, [])))

    mem = Memory()
    config.configure(store=lambda: mem)
    assert run("agents", "claim", "in memory").exit_code == 0
    assert [r["text"] for r in mem.rows["agents"]] == ["in memory"] and not jdir.exists()
    assert [c["text"] for c in json.loads(run("agents", "status", "--json").output)["claims"]] == ["in memory"]


def test_main_loads_a_wrappers_settings(jdir, monkeypatch):
    from importlib import metadata

    from agentboard import cli

    class EP:
        name, value = "mytool", "mytool.board"

        def load(self):
            config.configure(command="mytool agents")

    class Broken(EP):
        name = "broken"

        def load(self):
            raise ImportError("gone")

    class EPs(list):
        def select(self, group):
            return self if group == cli.SETTINGS_GROUP else []

    monkeypatch.setattr(metadata, "entry_points", lambda: EPs([Broken(), EP()]))
    cli.load_wrappers()
    assert config.settings.command == "mytool agents"
    monkeypatch.setattr(config, "settings", config.Settings())
    monkeypatch.setenv("AGENTS_WRAPPERS", "off")
    cli.load_wrappers()
    assert config.settings.command == "agents"


def test_a_reply_on_a_claim_or_handoff_reaches_its_session(jdir, monkeypatch):
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "api")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    run("agents", "claim", "retry on timeouts, branch retry", "-p", "src/client.py")
    run("agents", "handoff", "done: half; left: tests; next: agents pickup")
    view = json.loads(run("agents", "status", "--json").output)
    [claim], [handoff] = view["claims"], view["handoffs"]
    monkeypatch.setenv("AGENTS_SESSION", "bbbb")
    assert run("agents", "reply", claim["id"], "I need src/client.py too; which part is yours?").exit_code == 0
    assert run("agents", "reply", "nope00", "x").exit_code != 0
    monkeypatch.setenv("AGENTS_SESSION", "cccc")
    assert run("agents", "pickup", handoff["id"]).exit_code == 0
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    replies = {r["id"]: r["reply"] for r in json.loads(run("agents", "status", "--json").output)["replies"]}
    assert replies == {claim["id"]: "I need src/client.py too; which part is yours?"}  # the pickup is not a reply
    # `wait ID` on the claim: the reply from bbbb came after aaaa's last line on it
    result = run("agents", "wait", claim["id"], "--timeout", "0.1", "--every", "0.01")
    assert result.exit_code == 0 and "which part is yours?" in result.output and "api-bbbb" in result.output


def test_a_post_to_one_session_wakes_only_that_session(jdir, monkeypatch):
    from agentboard import board as j
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "api")
    monkeypatch.setenv("AGENTS_SESSION", "fd00.60203")
    run("agents", "claim", "the split")
    monkeypatch.setenv("AGENTS_SESSION", "e6e6.1")
    run("agents", "claim", "something else")
    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    result = run("agents", "post", "your claim overlaps mine", "--to", "api-fd00")
    assert result.exit_code == 0 and "For api-fd00 only" in result.output, result.output
    run("agents", "post", "for every api session", "--to", "api")
    run("agents", "post", "a repo with a dash, no session", "--to", "my-lib")
    lines = [json.loads(x) for x in (jdir / "agents.jsonl").read_text().splitlines()]
    posts = {r["text"]: r for r in lines if r["kind"] == "post"}
    assert posts["your claim overlaps mine"]["to"] == "api" and posts["your claim overlaps mine"]["to_session"] == "fd00"
    assert "to_session" not in posts["for every api session"]
    assert posts["a repo with a dash, no session"]["to"] == "my-lib" and "to_session" not in posts["a repo with a dash, no session"]
    monkeypatch.setattr(identity, "here", lambda: "api")
    out = run("agents", "status").output
    assert " to api-fd00" in out and "your claim overlaps mine" in out  # the repo sees it, marked for that session
    rows = j.agent_posts()
    assert [r["text"] for r in j.board_asks(rows, "api", "fd00.60203", "2020-01-01T00:00:00Z") if r["kind"] == "post"] == \
        ["your claim overlaps mine", "for every api session"]
    assert [r["text"] for r in j.board_asks(rows, "api", "e6e6.1", "2020-01-01T00:00:00Z") if r["kind"] == "post"] == \
        ["for every api session"]


def test_sessions_live_or_ended_and_whoami_names_the_process(jdir, monkeypatch):
    import os

    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "api")
    monkeypatch.setenv("AGENTS_SESSION", f"p{os.getpid()}")  # this test's process: live
    result = run("agents", "whoami")
    assert f"process {os.getpid()}" in result.output and f"board: {jdir / 'agents.jsonl'}" in result.output
    run("agents", "claim", "mine, still running")
    monkeypatch.setenv("AGENTS_SESSION", "ab12.4194303")  # no such process (pid_max is lower on macOS and Linux)
    run("agents", "handoff", "left behind")
    monkeypatch.setenv("AGENTS_SESSION", "nopid")
    run("agents", "claim", "a session that set its own name: no process to check")
    out = run("agents", "status").output
    live = [line for line in out.splitlines() if "(live)" in line]
    assert len(live) == 1 and f"from api-p{os.getpid()} " in live[0], out
    rows = json.loads(run("agents", "sessions", "--json").output)
    by = {r["name"]: r for r in rows}
    assert by[f"api-p{os.getpid()}"]["live"] is True and by[f"api-p{os.getpid()}"]["open"][0]["text"] == "mine, still running"
    assert by["api-ab12.4194303"]["live"] is False and by["api-nopid"]["live"] is None
    states = {line.split(" ", 1)[0]: line.split(": ", 1)[1].split(",", 1)[0] for line in run("agents", "sessions").output.splitlines()}
    assert states == {f"api-p{os.getpid()}": "live", "api-ab12.4194303": "ended", "api-nopid": "unknown"}
    # the pid's process is younger than the session's first line: another process got that pid
    assert identity.alive(f"p{os.getpid()}", "2000-01-01T00:00:00Z") is False
    assert identity.alive(f"p{os.getpid()}") is True and identity.pid_of("fd00.60203") == 60203 and identity.pid_of("aaaa") is None


def test_a_tools_row_gives_the_session_an_address(jdir, monkeypatch):
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "api")
    monkeypatch.delenv("AGENTS_ACTOR")
    tool = agent_tools.named("claude-code")
    monkeypatch.setenv(tool.detect[0], "1")
    monkeypatch.setenv(tool.session_env, "0f3a1b2c-full-session-id")
    monkeypatch.setenv(tool.pid_env, "4194303")
    run("agents", "claim", "from a known tool")
    [line] = [json.loads(x) for x in (jdir / "agents.jsonl").read_text().splitlines()]
    assert line["actor"] == "agent:claude-code" and line["tool_session"] == "0f3a1b2c-full-session-id"
    [row] = json.loads(run("agents", "sessions", "--json").output)
    assert row["resume"] == "claude --resume 0f3a1b2c-full-session-id" and row["address"].endswith("/0f3a1b2c-full-session-id.jsonl")
    assert "claude --resume 0f3a1b2c-full-session-id" in run("agents", "sessions").output


def test_post_and_wait_say_when_no_session_of_the_repo_is_live(jdir, monkeypatch):
    import os

    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "api")
    monkeypatch.setenv("AGENTS_SESSION", "ab12.4194303")  # an api session whose process is gone
    run("agents", "claim", "left long ago")
    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    first = run("agents", "post", "first question", "--to", "api").output
    assert "No session of api is live (its last line 0m ago). An answer waits" in first, first
    second = run("agents", "post", "second question", "--to", "api").output
    first_id = next(json.loads(x)["id"] for x in (jdir / "agents.jsonl").read_text().splitlines() if "first question" in x)
    assert f"1 other open post(s) to it, the oldest ({first_id}) waiting 0m" in second, second
    assert "never written to the board" in run("agents", "post", "anyone?", "--to", "nobody").output
    assert "live" not in run("agents", "post", "heads-up", "--to", "all").output
    waited = run("agents", "wait", first_id, "--timeout", "0.01", "--every", "0.01").output
    assert waited.startswith("No session of api is live") and "1 other open post(s)" in waited, waited
    monkeypatch.setattr(identity, "here", lambda: "api")
    monkeypatch.setenv("AGENTS_SESSION", f"p{os.getpid()}")  # an api session that runs: this test's process
    run("agents", "claim", "here now")
    monkeypatch.setattr(identity, "here", lambda: "tools")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    assert f"Live: api-p{os.getpid()};" in run("agents", "post", "third", "--to", "api").output


def test_one_board_for_every_copy_config_file_where_and_merge(jdir, monkeypatch, tmp_path):
    from agentboard import board as j
    from agentboard import cli, identity

    monkeypatch.setattr(identity, "here", lambda: "api")
    monkeypatch.setenv("AGENTS_SESSION", "aaaa")
    # the config file is read when the variable is unset; the variable wins over it
    monkeypatch.delenv("AGENTS_BOARD_DIR")
    config.write_config({"board_dir": str(tmp_path / "real")})
    assert j.board_dir() == tmp_path / "real"
    monkeypatch.setenv("AGENTS_BOARD_DIR", str(jdir))
    assert j.board_dir() == jdir
    # a stray board (a copy without the wrapper wrote there) is warned about, then merged in and set aside
    monkeypatch.setenv("AGENTS_BOARD_DIR", str(tmp_path / "fallback"))
    run("agents", "handoff", "left on the stray board")
    monkeypatch.setenv("AGENTS_BOARD_DIR", str(jdir))
    run("agents", "claim", "on the real board")
    assert "another board with 1 line(s) is in" in run("agents", "status").output  # CliRunner mixes in stderr
    assert json.loads(run("agents", "where", "--json").stdout)["other_boards"][0]["lines"] == 1
    result = run("agents", "where", "--merge", str(tmp_path / "fallback"))
    assert result.exit_code == 0 and "1 line(s) copied" in result.output, result.output
    assert {r["text"] for r in j.agent_posts()} == {"left on the stray board", "on the real board"}
    assert not (tmp_path / "fallback" / "agents.jsonl").exists() and "another board" not in run("agents", "status").output
    assert run("agents", "where", "--merge", str(jdir)).exit_code != 0  # not the board it reads
    # --save writes this copy's locations; a wrapper's first run writes its own only when there's no file yet
    (tmp_path / "config.toml").unlink()
    assert run("agents", "where", "--save").exit_code == 0 and config.read_config()["board_dir"] == str(jdir)
    (tmp_path / "config.toml").unlink()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("CI", raising=False)
    cli.save_wrapper_locations()
    assert not (tmp_path / "config.toml").exists()  # no wrapper: nothing to save
    monkeypatch.setattr(config, "settings", config.configure(board_dir=lambda: tmp_path / "wrapped"))
    cli.save_wrapper_locations()
    assert config.read_config()["board_dir"] == str(tmp_path / "wrapped")
    config.write_config({"board_dir": "/elsewhere"})
    cli.save_wrapper_locations()
    assert config.read_config()["board_dir"] == "/elsewhere"  # an existing file is never overwritten
    assert j.board_dir() == tmp_path / "wrapped"  # and the wrapper wins over it
    with pytest.raises(ValueError):
        config.write_config({"board_dir": 'a"b'})
