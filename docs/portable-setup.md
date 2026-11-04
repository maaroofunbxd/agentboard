# Portable setup (no company wrapper)

Use this when you want **agent coordination** on any machine, without `unbxd` or another organization's CLI.

## Install

```bash
uv tool install git+https://github.com/maaroofunbxd/agentboard
# or: pip install "agentboard @ git+https://github.com/maaroofunbxd/agentboard@v0.5.3"
```

Defaults: board at `~/.agents/board/agents.jsonl`, per-user files under `~/.agents/`. Override with `AGENTS_BOARD_DIR` and `AGENTS_DIR` (see the main README).

## Per repository (once)

1. Copy [`templates/`](../templates/) into the repo root, or merge `templates/AGENTS.md` into an existing `AGENTS.md`.
2. Run `agents link` if you want a personal `AGENTS.local.md` (gitignored) for rules that travel with you.
3. Optional: `agents setup` to copy your global agent instructions into a tool's config.
4. Optional (cross-repo **`post`**): once per machine, **`agents hooks --install`** — see [board-automation.md](board-automation.md). Set **`AGENTS_ATTACH=cursor`** for implementation; Open Interpreter is read-only recon only (OI **execution sandbox** blocks **`.git`** and board paths outside the repo — same in every checkout). Skip hooks if you only use the board inside one repo; skipping does not break anything.

## Daily habit

| Need | Command |
|------|---------|
| What is open for this repo? | `agents status` |
| I'm starting work | `agents claim "…" -p path/to/area` |
| Another session should continue | `agents handoff "done: …; left: …; next: …"` |
| Pick up someone's handoff | `agents pickup ID` |
| Ask another repo's agents | `agents post --to other-repo "…"` |
| Wait for board traffic | `agents wait` (background) |
| Close threads when done | `agents done ID "answer"` — especially **merged …** FYI posts; open posts slow `status` |

Point `next:` at something concrete: read `HANDOFF.md`, run tests, or open a ticket record path.

## With Unbxd `unbxd` (optional)

[unbxdtools](https://github.com/unbxd/unbxdtools) depends on agentboard and loads **`agentboard.settings`** so standalone `agents` and `unbxd` share one board. That wrapper adds `agents open` (waits beside a work record), Jira-aware `work start`, and a `[board]` line after `unbxd` runs. None of that is required for agentboard alone.

## opsjournal (optional, separate)

[opsjournal](https://github.com/maaroofunbxd/opsjournal) is **not** part of agentboard. unbxdtools uses it as the engine behind **`unbxd journal`**: every `unbxd` run and every write to configstore, k8s, cerebro, etc. is logged with `actor` (`user`, `runner`, or `agent:<tool>`).

- **Where it lives with `work`:** JSONL under `<work>/journal/` (and a `journal` git branch for backup). See unbxdtools `docs/unbxd-cli.md` and `src/unbxdtools/engine/journal.py`.
- **Does it change `work` layout?** No. Ticket narrative stays in **`records/*.md`** (`unbxd work note`, `work start`). The journal is an **audit trail of commands and prod changes**, not a replacement for records. `unbxd work today` reads both (Jira, git, journal, board).
- **After you leave Unbxd:** keep agentboard; add opsjournal only if you build or wrap a CLI that changes shared environments and you want the same “who ran what” story (`opsjournal.configure` in that tool's README).

Other small libs often pinned next to unbxdtools (each its own repo): **gland**, **ghci**, **clireview**, **httpcassette**. They do not change the `work` repo structure either; unbxdtools wires them in.

## Further reading

- [Board automation](board-automation.md) — optional hooks + `headless-run.sh`, `agents digest`.
- [Task record shapes](task-records.md) — `work` records vs generic handoff templates (and why they differ).
