# Repository templates

Copy these into a repo root (or merge `AGENTS.md` with an existing file).

| File | Role |
|------|------|
| `PROJECT.md` | Stable facts: purpose, constraints, verified commands, what done means |
| `HANDOFF.md` | Current task only — update when handing to another session |
| `AGENTS.md` | Minimal agent instructions for PROJECT + HANDOFF |

Pair with [agentboard](../README.md) (`agents status`, `wait`, `post`, `done`, `claim`, `handoff`, `pickup`) for session-to-session coordination on the machine. Close posts with **`agents done`** when answered or superseded so `status` stays fast.

If you use **offline sandbox hooks** (`AGENTS_HEADLESS_CMD`, **`agents attach`**): merge **`AGENTS.md`** § *Offline post → sandbox* from this template when you bump agentboard — especially **Cursor vs Open Interpreter** and OI **execution sandbox** vs **`.agents/sandbox-*`**. Canonical detail: [docs/board-automation.md](../docs/board-automation.md).

For Unbxd ticket work, use **`unbxd work`** and `records/` in the work repo instead of `HANDOFF.md`; see [docs/task-records.md](../docs/task-records.md).
