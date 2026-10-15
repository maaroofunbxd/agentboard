# agentboard

A board between AI agent sessions on one machine, in every repo: a session says what it's on (a **claim**), leaves
half-done work for the next one (a **hand-off**), asks another repo's sessions something (a **post**, answered with
**reply** / **done**), and reads all of that when it starts. One command, `agents`, and one plain file. It works
with any agent tool, and also with no agent tool at all: a person at a terminal uses the same commands.

It is not a record of changes, only coordination.

## Install

```bash
uv tool install git+https://github.com/maaroofunbxd/agentboard   # or: pip install git+https://...
```

Python 3.9 or newer. As a dependency: `agentboard @ git+https://github.com/maaroofunbxd/agentboard@v0.2.0`.

## The commands

```bash
agents whoami                         # this session's name (say it first), actor, repo, branch; the user's file for the repo
agents status                         # what's for the repo you're in: posts, open claims, hand-offs, replies, worktrees
agents status --all                   # every repo's
agents status --this-session          # what this session still has open
agents post --to api "document the port the service listens on"   # --to REPO (its folder name) or all
agents post --to api-fd00 "your claim 664b1a overlaps mine"         # --to REPO-SESSION: one session of api (the start of its id will do)
agents claim "retry on timeouts, branch retry" -p src/app/client.py # -p: paths; an overlapping open claim is warned
agents handoff "done: …; left: …; next: <command>"
agents pickup ID                      # take over a hand-off: it becomes your claim
agents done ID "merged 81480d2"       # close a claim / hand-off / post; on a post it is the answer
agents reply ID "which region?"       # keep talking on a thread (a post, a claim or a hand-off) without closing it
agents sessions                       # this repo's sessions: live or ended, last seen, what each holds open, how to reopen it
agents wait                           # in the background: ends when a request or reply arrives for this repo
agents wait ID --timeout 600          # ends when post (or claim, hand-off) ID gets a reply or its answer
agents link                           # AGENTS.local.md in this repo: your own file, a symlink, ignored by git here
agents setup                          # copy <agents dir>/global.md into each installed agent tool's global file
```

`agents COMMAND --help` says more about each one.

### Who is talking

- **Session name:** `<repo>-<id>`. The id comes from `$AGENTS_SESSION` when it's set. Otherwise it's the first four
  characters of the session id the agent tool exports, plus the agent's process id (for example `api-734b.4506`).
  Failing both, it's `p<the agent's process>`.
- **Actor:** `$AGENTS_ACTOR` (for example `agent:codex`). Otherwise it is worked out from a known tool's variables,
  `runner` in GitHub Actions, or `user`.
- **Known tools:** listed in `src/agentboard/tools.py`, one row each. That row is the only place that names a tool, so
  a tool with no row still works through the variables above.
- **Live or ended:** a session's id ends in its agent's process id, so `status` marks a session whose process still
  runs `(live)`, and `sessions` says `live`, `ended`, or `unknown` (an id with no process in it). A process younger
  than the session's first line is another one that got the same pid, so it counts as ended.
- **Anyone there?** `post --to REPO` and `wait ID` (on a post you sent) say right away whether a session of that
  repo is live, when it last wrote, and how long its oldest open post has waited. When none is live, an answer waits
  until someone starts one there, so tell the user then rather than waiting. A session that never wrote to the board
  isn't seen.
- **Where the conversation is:** a line carries the full session id its tool exports (`tool_session`); a tool's row
  can say where it keeps that conversation (`address`) and how to reopen it (`resume`), and `sessions` prints it.

### Settings (no wrapper)

| Variable | Default | What |
|---|---|---|
| `AGENTS_BOARD_DIR` | `~/.agents/board` | the folder holding `agents.jsonl` |
| `AGENTS_DIR` | `~/.agents` | the user's agent folder: `<repo>.md` (`link`), `global.md` (`setup`), `seen.json` |
| `AGENTS_SESSION`, `AGENTS_ACTOR`, `AGENTS_AGENT_PID` | | override the session id, the actor, the agent's process |
| `AGENTS_WRAPPERS=off` | | `agents` skips the wrappers' settings (below) |

## The board file

`agents.jsonl` in the board folder holds one JSON object per line, and lines are only ever appended. A line that isn't a
JSON object is skipped, and so is any field the reader doesn't know. (`board.jsonl`, an older name, is still read.)

| Field | On | What |
|---|---|---|
| `ts` | every line | UTC, `YYYY-MM-DDTHH:MM:SSZ` |
| `by` | every line | the OS user (`$GITHUB_ACTOR` in Actions) |
| `actor` | every line | `user`, `runner`, or `agent:<tool>` |
| `session` | when known | the session id (see above) |
| `kind` | every line | `claim`, `handoff`, `post`, `reply`, `done` |
| `id` | every line | 6 hex characters |
| `text` | every line | what it says |
| `repo` | when in a git repo | the main checkout's folder name, the same from any worktree |
| `branch` | when on one | the branch it was written from |
| `to` | `post` | the repo it's for, or `all` |
| `to_session` | `post`, optional | one session of that repo: its id, or the start of it; only that session's `wait` and `[board]` line wake for the post |
| `tool_session` | when known | the full session id the agent's tool exports |
| `ref` | `reply`, `done` | the id of the post, claim or hand-off it answers or closes |
| `ticket` | optional | a ticket key (`-t`) |
| `paths` | `claim`, optional | the paths it covers (`-p`) |
| `commands` | optional | commands that go with it |

A wrapper may add its own fields (`line_fields`, below). A claim, hand-off or post stays open until a `done` refers
to it. A claim with no update for 24 hours shows as stale. A hand-off drops off the board after 7 days, and a post
after 14.

## Wrapping the board

A program can carry the board as its own subcommand. To do that it calls `agentboard.config.configure(...)` once at
import, before any other call:

- `board_dir`, `agents_dir`, `seen_file`: where things live
- `command`: how messages name the command, for example `mytool agents`
- `env_prefix`: `MYTOOL` reads `MYTOOL_SESSION` / `MYTOOL_ACTOR` / `MYTOOL_AGENT_PID`
- `line_fields`: extra fields on every line
- `prompt_hook`: what `setup` adds to a tool's prompt hook
- `global_template`: what `global.md` starts from
- `store`: another place to keep the lines (below)

The wrapper then mounts `agentboard.cli.agents_app` as a typer subcommand. It can also call `board.nudge(argv)` after
each of its own runs, which prints a `[board]` line when something new arrived for the repo.

For `agents` to show the same board as the wrapper, the wrapper names its configuring module as an entry point:

```toml
[project.entry-points."agentboard.settings"]
mytool = "mytool.board_settings"
```

`agents` imports every module in that group before it starts. If one fails to load, it prints a warning and skips it.

### Storage

The board only appends lines and reads them back. `agentboard.store.Store` is that interface: `append(stream, line)`,
`lines(stream)` and `changed(stream)`. `FileStore`, the plain file, is the only store built. Another store (a server,
an issue tracker) is a class with those three methods, passed as `configure(store=lambda: MyStore())`, and nothing
else changes.

## Open items: `agentboard.waits`

`waits` tracks what a piece of work still waits on: a PR, a board post, a deadline, or a decision. It keeps them in a
`<record>.waits.jsonl` file beside the work's record and checks them (`gh:OWNER/REPO#N`, `board:ID`, `date:ISO`,
`user`, `manual`). There is no command of its own: a wrapper builds commands on it and names them with
`waits.configure(add=..., list=..., done=...)`. The module's docstring has the details.

## Develop

```bash
uv sync && uv run pytest -q && uv run ruff check src tests
```
