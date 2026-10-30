# Ideas for `agents` from MCP Agent Mail and Beads

In 2026-10, two other coordination tools were looked at as possible storage behind `agents` (the board) and
`agents open` (a ticket's open items): MCP Agent Mail and Beads. Both were dropped before install, and the board
stays a plain file. This page records why, and the ideas from them worth building later. None of it is planned or
approved; pick an item, then propose it to the user as usual.

## The decision (user, 2026-10-14)

Plain file only. Neither tool was installed. Both were judged on their README, docs and install scripts at the
pinned tag (session unbxdtools-f778, read only).

| Need | Ours | MCP Agent Mail v0.3.2 | Beads v1.3.1 |
|---|---|---|---|
| ask another repo's sessions, get an answer (`post --to REPO`, `done`, `reply`, `wait ID`) | yes | yes, through its server: threads, replies, acks; addressed to agent names, not repos | no: `bd mail` hands off to an outside program |
| a running session hears of a request without polling | yes (`agents wait`) | partly: a signal file to watch (off by default), or agent-tool hooks | no: `--follow` / `--watch` poll every 1-2 s |
| claims on paths; overlap warned; a conflicting commit blocked | advisory only | partly: path reservations; a pre-commit guard, off unless an env var is set | no: claims on issues, not paths |
| hand-off of half-done work, any tool | yes | no: a message in a thread | partly: a comment, `bd assign`, then `--claim` |
| a ticket's open items checked (PR / board / deadline), DM on change | yes | no | partly: gates on a PR, a CI run, a timer; run by cron; no DM |
| works with no agent tool, and no server running | yes | no: every write goes through its HTTP server | yes, one writer at a time; several need a Dolt server |
| history in git, backed up | yes | partly: a local git archive, never pushed; SQLite beside it | partly: Dolt history, pushed by hand as `refs/dolt/data` |
| install / upkeep cost | none | high: Python 3.12+, ~30 dependencies, a server to keep up | high: 144 MB binary, Dolt, schema migrations, fast releases |

Why each was dropped, beyond the table:

- **Agent Mail** (github.com/Dicklesworthstone/mcp_agent_mail). Its LICENSE is MIT plus a rider that grants no
  rights to Anthropic or OpenAI or anyone acting for them, and counts executing, testing and analysing in automated
  systems as use, so agents built on Claude can't run it without a legal reading first. Its installer runs unpinned
  remote installers, edits shell rc files, and writes agent-tool configs that carry its server token.
- **Beads** (github.com/gastownhall/beads, was steveyegge/beads; MIT). Usage metrics are on by default
  (`BD_DISABLE_METRICS=1` turns them off). A default `bd init` commits with `--no-verify`, points the repo's
  `core.hooksPath` at `.beads/hooks`, and writes AGENTS.md, CLAUDE.md and `.claude/`, `.cursor/`, `.codex/` files;
  `bd init --stealth` with `BEADS_DIR` outside the repo avoids that.

## Ideas worth building

The board's items go in agentboard (github.com/maaroofunbxd/agentboard), then the pin is bumped in unbxdtools when
built. Each keeps the board a plain file, readable by older pins (new fields optional), with no server and no agent
tool.

1. **A claim that refuses an overlap.** Today `agents claim -p PATH` appends a line with no lock and only warns when
   another open claim covers the path, so two sessions can both claim it. Check and append under a file lock, and
   refuse when a live session's open claim overlaps, unless `--force`. (Beads' atomic `--claim`; Agent Mail's
   exclusive reservations.)
2. **Claims that expire.** `agents claim … --for 4h`: past that, the claim is free without a `done`. Today a claim only
   shows as stale after a day. (Agent Mail's reservation TTL.)
3. **An opt-in commit check.** A new `guard` subcommand for a repo's pre-commit: fail when a staged file is inside another live
   session's claim. On this machine hooks come from the global `core.hooksPath` (`~/.git-templates/hooks`, gland's), so
   it would be one more check there, not a replaced hooks folder: Agent Mail's guard moves the existing hooks aside,
   which here would reach every repo. (Agent Mail's pre-commit guard.)
4. **Leases: one holder at a time around a command.** A new `lease` subcommand (lease NAME -- CMD) waits for the lease, runs, releases.
   Two rules in AGENTS.md are this by hand today: mgmt-host commands one at a time (section 2) and merging to main,
   suite, push (section 6, step 3). (Agent Mail's `am-run` build slots; Beads' merge slot.)
5. **An answer-by time on a post.** `agents post --by 2h …`: unanswered after that, it shows as overdue in `status`
   and the asker's `agents wait ID` ends with that. (Agent Mail's `ack_required` with TTL escalation.)
6. **Scripts run after a board write.** An optional `<agents dir>/hooks/on_post` (and on claim, done, reply) gets the
   new line on stdin, so a person can add a desktop notification or a Slack DM without the board knowing any tool.
   (Beads' `on_create` / `on_update` hooks.)

For `agents open` (agentboard's `waits.py`, mounted by unbxdtools' `cli/open_items.py`):

7. **A CI run as an open item.** `--on gh-run:OWNER/REPO@BRANCH`, checked the way `ghci status` checks it: done when
   the branch tip's runs pass. (Beads' `gh:run` gate.)
8. **Open items that wait on each other.** `--after ID`, and the list shows what is ready now and what is still
   blocked. Today `--unblocks` is free text. (Beads' dependencies and `bd ready`.)

Not taken from them: a server, a database (SQLite, Dolt) in place of readable JSONL in git, generated agent names,
and writing any agent tool's config.

Moved from unbxdtools branch `trial-mail-beads` (2026-10-30).
