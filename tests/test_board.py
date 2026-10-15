"""board.py and identity.py without the CLI."""
import datetime
import json

import pytest

from agentboard import board, config, identity
from agentboard import tools as agent_tools


@pytest.fixture
def jdir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "settings", config.Settings())
    monkeypatch.setenv("AGENTS_BOARD_DIR", str(tmp_path / "board"))
    monkeypatch.setenv("AGENTS_DIR", str(tmp_path / "agents"))
    for var, _ in agent_tools.detect_env():
        monkeypatch.delenv(var, raising=False)
    for var in ("AGENTS_ACTOR", "AGENTS_SESSION", "AGENTS_AGENT_PID", "GITHUB_ACTIONS", "GITHUB_ACTOR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(identity, "_session", [])
    monkeypatch.setenv("AGENTS_NOTIFY", "off")  # no desktop pop-ups from the tests
    return tmp_path / "board"


def test_agents_claims_and_handoffs(jdir):
    claim = board.post("claim", "retry fix")
    board.post("handoff", "left: push")
    view = board.agents_view(board.agent_posts())
    assert [c["text"] for c in view["claims"]] == ["retry fix"] and not view["claims"][0]["stale"]
    assert [h["text"] for h in view["handoffs"]] == ["left: push"]
    board.post("done", "merged", ref=claim["id"])
    assert board.agents_view(board.agent_posts())["claims"] == []
    assert all(r["_stream"] == "agents" for r in board.read(board.AGENTS))


def test_a_line_is_one_json_object_with_the_documented_fields(jdir):
    board.post("post", "hello", to="api")
    [line] = (jdir / "agents.jsonl").read_text().splitlines()
    row = json.loads(line)
    assert {"ts", "by", "actor", "kind", "id", "text", "to"} <= set(row) and row["kind"] == "post"


def test_old_claims_go_stale_and_kinds_are_checked(jdir):
    board.post("claim", "old one")
    later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)
    assert board.agents_view(board.agent_posts(), now=later)["claims"][0]["stale"]
    with pytest.raises(ValueError):
        board.post("suggest", "x")


def test_session_id_and_name(jdir, monkeypatch):
    real_pid = identity.agent_pid
    monkeypatch.setattr(identity, "agent_pid", lambda: None)
    assert identity.session_id() is None and "session" not in board.who()  # a person at a terminal
    monkeypatch.setattr(identity, "agent_pid", real_pid)
    monkeypatch.setattr(identity, "_session", [])
    monkeypatch.setenv("AGENTS_ACTOR", "agent:claude-code")  # a tool in tools.py exports its session id and process
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "734bb659-c2f3-4289")
    monkeypatch.setenv("CLAUDE_PID", "4506")
    assert identity.session_id() == "734b.4506" and identity.session_name("api") == "api-734b.4506"
    assert board.who()["session"] == "734b.4506"
    monkeypatch.setattr(identity, "_session", [])
    monkeypatch.setenv("CLAUDE_PID", "9001")  # a resumed / forked copy: same id, another process
    assert identity.session_id() == "734b.9001"
    monkeypatch.setattr(identity, "_session", [])
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    monkeypatch.delenv("CLAUDE_PID")
    monkeypatch.setenv("AGENTS_ACTOR", "agent:codex")
    monkeypatch.setattr(identity, "agent_pid", lambda: 81234)
    assert identity.session_id() == "p81234"  # any other agent tool: its process
    monkeypatch.setattr(identity, "_session", [])
    monkeypatch.setenv("AGENTS_SESSION", "codex 7/a")
    assert identity.session_id() == "codex-7-a"  # any tool can name its session


def test_a_wrapper_names_the_variables(jdir, monkeypatch):
    config.configure(env_prefix="MYTOOL")
    monkeypatch.setenv("MYTOOL_SESSION", "abcd")
    monkeypatch.setenv("AGENTS_SESSION", "not-this")
    assert identity.session_id() == "abcd"


def test_here_is_the_main_repo_in_any_worktree(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    main = tmp_path / "api"
    subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True)
    subprocess.run(["git", "-C", str(main), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", "-b", "fix", str(tmp_path / "api-fix")], check=True)
    for where in (main, tmp_path / "api-fix"):
        monkeypatch.chdir(where)
        assert identity.here() == "api"
    monkeypatch.chdir(tmp_path)
    assert identity.here() is None


def test_agent_pid_from_any_tool(jdir, monkeypatch):
    monkeypatch.setenv("AGENTS_AGENT_PID", "777")  # any tool can say which process is the agent
    assert identity.agent_pid() == 777


def test_resolve_to_a_repo_all_or_one_session(jdir, monkeypatch):
    from agentboard import board as j
    from agentboard import identity

    monkeypatch.setattr(identity, "here", lambda: "api")
    monkeypatch.setenv("AGENTS_SESSION", "fd00.60203")
    j.post("claim", "x")
    rows = j.agent_posts()
    assert j.resolve_to(rows, "api") == ("api", None) and j.resolve_to(rows, "all") == ("all", None)
    assert j.resolve_to(rows, "api-fd00") == ("api", "fd00") and j.resolve_to(rows, "api-fd00.60203") == ("api", "fd00.60203")
    assert j.resolve_to(rows, "api-zzzz") == ("api-zzzz", None)  # no such session: a repo of that name
    assert j.resolve_to(rows, "api-") == ("api-", None)
    # an old line (no to_session) is for everyone; a thread on a claim is read like one on a post
    old = {"kind": "post", "id": "aaaaaa", "to": "api", "text": "old"}
    assert j.addressed(old, "fd00.60203") and j.addressed({"to_session": "fd00"}, "fd00.60203") and not j.addressed({"to_session": "fd00"}, "e6e6.1")
    [claim] = [r for r in rows if r["kind"] == "claim"]
    assert j.thread(rows, claim["id"]) == [claim] and j.thread(rows, "nope00") == []
