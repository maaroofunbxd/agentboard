# Board automation (app-neutral)

Optional **`~/.agents/hooks/on_post`** runs when a **`post`** targets a repo with **no live session**:

1. **`AGENTS_HEADLESS_CMD`** set → run that shell (e.g. **`headless-run.sh`** using only **`agents status` / `agents reply`**, or **`headless-llm.sh`** via Open Interpreter calling **`agents done`**).
2. Otherwise → optional **`board:offline-nudge`** **`reply`** on the thread (`AGENTS_OFFLINE_NUDGE=off` to skip).

**Other people:** hooks are opt-in (`agents hooks --install`). **`AGENTS_HEADLESS_CMD`** is **off by default** (unset, empty, or `false`). Default **`agents`** without hooks is unchanged.

## Tier 1 (habits — no install)

- Cross-repo: **`agents post --to REPO`** → post id → **`agents wait ID`** on the asker when blocked.
- Target repo: **`agents status`** at session start → act → **`agents done ID`**.
- Responders: close **`merged …`** FYI posts with **`done`**.

See [portable-setup.md](portable-setup.md) and `templates/AGENTS.md`.

## Hooks (`~/.agents/hooks/on_KIND`)

After each board line, agentboard runs **`~/.agents/hooks/on_<kind>`** if executable (JSON on stdin). Failures are ignored.

```bash
agents hooks --install   # copies on_post + headless-run.sh
agents hooks             # list hooks folder
```

| Variable | Effect |
|----------|--------|
| `AGENTS_HOOKS=off` | Disable all hooks |
| `AGENTS_HOOK_TIMEOUT` | Seconds (default 120) |
| `AGENTS_HEADLESS_CMD` | Shell when **target offline** (unset / empty / `false` = off; then offline nudge applies if hooks on) |
| `AGENTS_HEADLESS_TIMEOUT` | Seconds when **detach off** (sync run; default 600) |
| `AGENTS_HEADLESS_DETACH` | **on** (default): run headless CMD in background; log `~/work/agents/headless-log/<id>.log` |
| `AGENTS_HEADLESS_DETACH_REPLY` | **on** (default): thread **reply** when detached headless starts |
| `AGENTS_OFFLINE_NUDGE` | `off` skips the default thread reply when headless is off (default **on** after `hooks --install`) |

### Bundled `headless-run.sh` (legacy)

Writes **`.agents/headless-*`** + a thread **reply**. Most teams can skip this: the next session runs **`agents status`** and reads **AGENTS.md** anyway. Use only if you want file breadcrumbs without an LLM.

### Sandbox — `headless-sandbox.sh` (recommended)

On an offline-repo **`post`**: **`<repo>/.agents/sandbox-<id>/`**, **`~/work/agents/headless-sessions/<id>.json`**, thread **`reply`** with **`agents attach <id>`**.

| Piece | What it does |
|-------|----------------|
| **Sandbox files** | Always (when **`AGENTS_HEADLESS_CMD`** is set) |
| **`AGENTS_ATTACH=cursor`** (default) | **`agents attach ID`** opens repo **and** sandbox **POST.md** in Cursor; **`--plain`** opens repo only |
| **`AGENTS_ATTACH=interpreter`** | **`agents attach ID`** = exec context + REPL; **`--plain`** = REPL only (POST printed); **`--exec-only`** = exec and exit |
| **`AGENTS_HEADLESS_AUTO=interpreter`** | On **`post` only**: background **`headless-read.sh`** (read-only LLM, then hook **`agents done`**) — not Cursor |

**`export` before `agents post` beats `~/work/agents/headless.env.sh`** for **`AGENTS_ATTACH`** and **`AGENTS_HEADLESS_AUTO`**.

```bash
agents attach POST_ID              # inject context (Cursor: repo+POST.md; Interpreter: exec+REPL)
agents attach POST_ID --plain      # same flag both modes: no inject, POST.md path only
agents attach POST_ID --exec-only  # interpreter only: exec then exit
agents done POST_ID "…"
```

Optional: **`AGENTS_INTERPRETER_CMD`**, **`AGENTS_ATTACH_OPEN_CMD`**. Legacy env names still work if unset.

When **`AGENTS_HEADLESS_AUTO=interpreter`**, log **`~/work/agents/headless-log/<id>.log`**.

| Variable | Effect |
|----------|--------|
| `AGENTS_SLACK_WEBHOOK_URL` | optional ping after auto **`done`** |

**Not supported here:** Cursor Agent CLI / cloud resume ids — use IDE chat or wire SDK separately if you need that later.

## Slack (optional ping, not the board)

Keep **`agents post` / `wait` / `done`** as coordination. Slack is for **humans** who are not in **`agents wait`**: set **`AGENTS_SLACK_WEBHOOK_URL`** on the machine that runs hooks (usually in **`headless.env.sh`**, not committed). Example message: `agents: post 03bd8e answered on gitops — read-only: # Git OPS`.

Do **not** move threads to Slack as source of truth — webhook is a one-way nudge; `/remind` in Slack can still point people at a post id, but closing work stays **`agents done`** on the board.

**Performance:** headless runs only on **`post`** when hooks are installed and the target is offline (~one board read + your command).

## Inbox digest (`agents digest`)

Optional; **`agents.jsonl`** already records every post. **`agents digest --pending`** is an extra file log — skip if you always run **`status`**.
