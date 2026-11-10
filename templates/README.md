# Repository templates

Copy these into a repo root (or merge `AGENTS.md` with an existing file).

| File | Role |
|------|------|
| `PROJECT.md` | Stable facts: purpose, constraints, verified commands, what done means |
| `HANDOFF.md` | Current task only — update when handing to another session |
| `AGENTS.md` | Minimal agent instructions for PROJECT + HANDOFF |

Pair with [agentboard](../README.md) (`agents status`, `wait`, `post`, `done`, `claim`, `handoff`, `pickup`) for session-to-session coordination on the machine. Close posts with **`agents done`** when answered or superseded so `status` stays fast.

Optional offline hooks and the experimental/untested Cursor & Open Interpreter sandbox prototypes are documented in [docs/board-automation.md](../docs/board-automation.md).

For Unbxd ticket work, use **`unbxd work`** and `records/` in the work repo instead of `HANDOFF.md`; see [docs/task-records.md](../docs/task-records.md).
