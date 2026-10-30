from pathlib import Path

from agentboard.sandbox import build_attach_prompt, file_excerpt, paths_mentioned_in_text, path_context_block


def test_paths_from_backticks_and_tokens():
    text = "Edit `src/unbxdtools/cli/ner.py` and docs/unbxd-cli.md near ner tag"
    paths = paths_mentioned_in_text(text)
    assert "src/unbxdtools/cli/ner.py" in paths
    assert "docs/unbxd-cli.md" in paths


def test_file_excerpt_under_root(tmp_path):
    f = tmp_path / "src" / "foo.py"
    f.parent.mkdir(parents=True)
    f.write_text("line1\nline2\n", encoding="utf-8")
    assert "line1" in (file_excerpt(tmp_path, "src/foo.py") or "")
    assert file_excerpt(tmp_path, "../etc/passwd") is None


def test_build_attach_prompt_includes_existing_file(tmp_path):
    f = tmp_path / "docs" / "x.md"
    f.parent.mkdir(parents=True)
    f.write_text("# hi", encoding="utf-8")
    post = "Please update docs/x.md"
    out = build_attach_prompt("abc123", tmp_path, post)
    assert "abc123" in out
    assert "docs/x.md" in out
    assert "# hi" in out


def test_path_context_skips_missing(tmp_path):
    assert path_context_block(tmp_path, "see src/missing.py") == ""
