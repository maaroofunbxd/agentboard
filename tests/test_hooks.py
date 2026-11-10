"""Tests for board hooks."""
import stat

import pytest

from agentboard import board, config, hooks
from agentboard import tools as agent_tools


@pytest.fixture
def jdir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "settings", config.Settings())
    monkeypatch.setenv("AGENTS_BOARD_DIR", str(tmp_path / "board"))
    monkeypatch.setenv("AGENTS_DIR", str(tmp_path / "agents"))
    for var in agent_tools.every_env():
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENTS_NOTIFY", "off")
    return tmp_path / "board"


def test_hook_runs_on_append(jdir, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "settings", config.Settings())
    monkeypatch.setenv("AGENTS_BOARD_DIR", str(jdir))
    agents = tmp_path / "agents"
    monkeypatch.setenv("AGENTS_DIR", str(agents))
    hook_dir = agents / "hooks"
    hook_dir.mkdir(parents=True)
    log = hook_dir / "on_post"
    log.write_text("#!/bin/sh\ncat >> " + str(agents / "hook.log") + "\n", encoding="utf-8")
    log.chmod(log.stat().st_mode | stat.S_IXUSR)
    board.post("post", "hello", to="api")
    assert (agents / "hook.log").read_text().strip().startswith("{")


def test_append_still_works_when_hook_fails(jdir, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "settings", config.Settings())
    monkeypatch.setenv("AGENTS_BOARD_DIR", str(jdir))
    agents = tmp_path / "agents"
    monkeypatch.setenv("AGENTS_DIR", str(agents))
    hook_dir = agents / "hooks"
    hook_dir.mkdir(parents=True)
    log = hook_dir / "on_post"
    log.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    log.chmod(log.stat().st_mode | stat.S_IXUSR)
    entry = board.post("post", "still here", to="api")
    rows = board.agent_posts()
    assert any(r.get("id") == entry["id"] for r in rows)


def test_hooks_off(jdir, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "settings", config.Settings())
    monkeypatch.setenv("AGENTS_BOARD_DIR", str(jdir))
    monkeypatch.setenv("AGENTS_HOOKS", "off")
    agents = tmp_path / "agents"
    monkeypatch.setenv("AGENTS_DIR", str(agents))
    hook_dir = agents / "hooks"
    hook_dir.mkdir(parents=True)
    log = hook_dir / "on_post"
    log.write_text("#!/bin/sh\necho ran >> " + str(agents / "x") + "\n", encoding="utf-8")
    log.chmod(log.stat().st_mode | stat.S_IXUSR)
    board.post("post", "x", to="api")
    assert not (agents / "x").exists()


def test_install_examples(jdir, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "settings", config.Settings())
    monkeypatch.setenv("AGENTS_DIR", str(tmp_path / "agents"))
    installed = hooks.install_examples(force=True)
    assert any(p.endswith("on_post") for p in installed)
    assert (hooks.hooks_dir() / "on_post").is_file()
