import datetime

import pytest

from agentboard import waits as work_waits
from agentboard.waits import Item

NOW = datetime.datetime(2026, 10, 13, 12, 0, tzinfo=datetime.timezone.utc)


def test_parse_on_accepts_the_kinds_and_says_what_it_takes():
    assert work_waits.parse_on("gh:acme/app#6174") == "gh:acme/app#6174"
    assert work_waits.parse_on("board:df8d4f") == "board:df8d4f"
    assert work_waits.parse_on("user") == "user" and work_waits.parse_on("manual") == "manual"
    assert work_waits.parse_on("date:2026-10-18T05:30+05:30") == "date:2026-10-18T05:30+05:30"
    assert work_waits.parse_on("date:2026-10-18").startswith("date:2026-10-18T00:00")  # local midnight, with its zone
    for bad in ("slack:invite C1", "gh:gitops#1", "board:xyz", "date:soon"):
        with pytest.raises(ValueError, match="gh:OWNER/REPO#N|ISO"):
            work_waits.parse_on(bad)


def test_state_round_trip(tmp_path):
    path = tmp_path / "cache" / "state.json"
    assert work_waits.load_state(path) == {}
    work_waits.save_state(path, {"a": {"state": "review"}})
    assert work_waits.load_state(path) == {"a": {"state": "review"}}


def test_file_round_trip_keeps_only_stored_fields_and_skips_a_broken_line(tmp_path):
    path = work_waits.waits_path(tmp_path / "2026-10-12-PROJ-1-search.md")
    assert path.name == "2026-10-12-PROJ-1-search.waits.jsonl"
    work_waits.save(path, [Item(id="a1b2c3", text="review", on="user", who="you", state="you", ticket="PROJ-1")])
    path.write_text(path.read_text() + "{not json\n")
    [item] = work_waits.load(path, "PROJ-1")
    assert (item.id, item.text, item.on, item.ticket, item.state) == ("a1b2c3", "review", "user", "PROJ-1", "")
    assert '"state"' not in path.read_text()


def test_dates_are_due_soon_within_48h_and_passed_after():
    items = [Item(id="1", text="t", on="date:2026-10-16T12:00+00:00"), Item(id="2", text="t", on="date:2026-10-14T12:00+00:00"),
             Item(id="3", text="t", on="date:2026-10-13T11:00+00:00")]
    assert work_waits.check(items, NOW) == []
    assert [i.state for i in items] == ["later", "soon", "passed"]
    assert [i.needs_you for i in items] == [False, True, True]


def test_board_items_follow_replies_and_the_answer():
    rows = [{"kind": "post", "id": "df8d4f", "to": "api", "text": "please build"}]
    def board():
        return rows

    item = Item(id="1", text="t", on="board:df8d4f")
    work_waits.check([item], NOW, board=board)
    assert item.state == "open" and not item.needs_you
    rows.append({"kind": "reply", "ref": "df8d4f", "text": "a question back"})
    work_waits.check([item], NOW, board=board)
    assert item.state == "replied" and "a question back" in item.detail
    rows.append({"kind": "done", "ref": "df8d4f", "text": "built, main abc123"})
    work_waits.check([item], NOW, board=board)
    assert item.state == "answered" and "built, main abc123" in item.detail and item.needs_you
    assert work_waits.default_who("board:df8d4f", board) == "api sessions"
    assert work_waits.check([item], NOW) and item.state == "unchecked"  # no board given


def test_gh_states_and_a_failed_check_is_soft(monkeypatch):
    answers = {"pr": {"state": "OPEN", "reviewDecision": "REVIEW_REQUIRED", "isDraft": False, "url": "u", "title": "T",
                      "reviewRequests": [{"login": "alice"}]}}

    def gh(*args):
        if "offline" in answers:
            raise RuntimeError("error connecting to api.github.com")
        return answers["pr"]

    monkeypatch.setattr(work_waits, "_gh", gh)
    item = Item(id="1", text="t", on="gh:acme/app#6174", ticket="PROJ-1")
    work_waits.check([item], NOW)
    assert item.state == "review" and "alice" in item.detail and not item.needs_you
    answers["pr"] = {**answers["pr"], "reviewDecision": "APPROVED"}
    work_waits.check([item], NOW)
    assert item.state == "approved" and item.needs_you
    answers["pr"] = {**answers["pr"], "state": "MERGED"}
    work_waits.check([item], NOW)
    assert item.state == "merged"
    answers["offline"] = True
    errors = work_waits.check([item], NOW)
    assert item.state == "unchecked" and errors and "api.github.com" in errors[0]


def test_gh_falls_back_to_an_issue(monkeypatch):
    def gh(*args):
        if args[0] == "pr":
            raise RuntimeError("GraphQL: Could not resolve to a PullRequest with the number of 7.")
        return {"state": "CLOSED", "url": "u", "title": "an issue"}

    monkeypatch.setattr(work_waits, "_gh", gh)
    item = Item(id="1", text="t", on="gh:o/r#7")
    work_waits.check([item], NOW)
    assert item.state == "closed" and item.needs_you


def test_track_notes_changes_and_the_dm_is_only_about_what_moved():
    item = Item(id="1", text="review", on="gh:o/r#1", ticket="PROJ-1", state="review")
    state = work_waits.track([item], NOW, {})
    assert work_waits.unnotified([item], state) == []  # first sighting: no DM for a new item
    item.state = "unchecked"  # offline: keeps what it saw
    work_waits.track([item], NOW, state)
    assert state["1"]["state"] == "review" and item.seen == "review"
    item.state = "approved"
    work_waits.track([item], NOW, state)
    assert (item.was, state["1"]["state"]) == ("review", "approved") and item.changed
    assert work_waits.unnotified([item], state) == [item]
    text, blocks = work_waits.dm([item], [item])
    assert text == "Open items: 1 changed, 1 need you"
    assert "waiting for review → *approved, not merged*" in blocks[0]["text"]["text"]
    work_waits.mark_notified([item], state)
    assert work_waits.unnotified([item], state) == []
    item.done = "2026-10-13"
    work_waits.track([item], NOW, state)
    assert state == {}  # done items are forgotten


def test_text_puts_what_needs_you_first_then_groups_by_ticket():
    items = [Item(id="a", text="later", on="manual", who="devops", ticket="PROJ-2", state="manual"),
             Item(id="b", text="decide", on="user", ticket="own-x", state="you"),
             Item(id="c", text="deadline", on="date:x", ticket="PROJ-2", state="passed")]
    text = work_waits.to_text(items)
    assert text.index("Needs you (2)") < text.index("[c] deadline") < text.index("[b] decide") < text.index("PROJ-2 (1)")
    assert "[a] later — not checked automatically · who: devops" in text
