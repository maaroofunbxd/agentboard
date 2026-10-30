import os

import pytest

from agentboard import config, plugins


def test_attach_mode_default(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTS_DIR", str(tmp_path))
    monkeypatch.delenv("AGENTS_ATTACH", raising=False)
    monkeypatch.delenv("AGENTS_ATTACH_OPEN_PLUGIN", raising=False)
    assert plugins.attach_mode() == "cursor"


def test_attach_mode_interpreter(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTS_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTS_ATTACH", "interpreter")
    monkeypatch.setitem(plugins.shutil.__dict__, "which", lambda _: "/usr/bin/interpreter")
    assert plugins.attach_mode() == "interpreter"


def test_headless_auto_default_off(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTS_DIR", str(tmp_path))
    monkeypatch.delenv("AGENTS_HEADLESS_AUTO", raising=False)
    monkeypatch.delenv("AGENTS_HEADLESS_LLM", raising=False)
    monkeypatch.delenv("AGENTS_HEADLESS_WORK", raising=False)
    assert plugins.headless_auto() == "off"


def test_headless_auto_legacy_llm(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTS_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTS_ATTACH", "interpreter")
    monkeypatch.delenv("AGENTS_HEADLESS_AUTO", raising=False)
    monkeypatch.setenv("AGENTS_HEADLESS_LLM", "1")
    monkeypatch.setitem(plugins.shutil.__dict__, "which", lambda _: "/usr/bin/interpreter")
    assert plugins.headless_auto() == "on"


def test_headless_env_file_does_not_override_shell(monkeypatch, tmp_path):
    env_sh = tmp_path / "headless.env.sh"
    env_sh.write_text('export AGENTS_ATTACH=cursor\nexport AGENTS_HEADLESS_AUTO=off\n', encoding="utf-8")
    monkeypatch.setattr(config, "settings", config.Settings())
    monkeypatch.setenv("AGENTS_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTS_ATTACH", "interpreter")
    monkeypatch.setitem(plugins.shutil.__dict__, "which", lambda _: "/usr/bin/interpreter")
    plugins.load_headless_env_defaults()
    assert os.environ["AGENTS_ATTACH"] == "interpreter"
    assert plugins.attach_mode() == "interpreter"


def test_headless_auto_on_needs_interpreter_attach(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTS_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTS_HEADLESS_AUTO", "on")
    monkeypatch.setenv("AGENTS_ATTACH", "cursor")
    assert plugins.headless_auto_wanted() is True
    assert plugins.headless_auto_on() is False
    assert plugins.headless_auto() == "off"


def test_interpreter_exec_argv():
    argv = plugins.interpreter_exec_argv("hello")
    assert argv[-1] == "hello"
    assert "exec" in argv
