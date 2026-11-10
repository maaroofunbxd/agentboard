# Board automation (app-neutral)

> **Status (experimental / untested):** The headless sandbox (`headless-sandbox.sh`), `agents attach` (`cursor` and `interpreter` modes), and unattended Open Interpreter (`AGENTS_HEADLESS_AUTO`, `headless-read.sh`, `headless-llm.sh`) are **experimental prototypes that are untested / do not work reliably end-to-end**. They are kept in-tree for reference only. Use Tier 1 board coordination (`agents post`, `agents wait`, `agents status`, `agents done`) for real work.

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
| `AGENTS_HEADLESS_DETACH` | **on** (default): run headless CMD in background; log `<agents dir>/headless-log/<id>.log` |
| `AGENTS_HEADLESS_DETACH_REPLY` | **off** (default): extra thread **reply** when detached headless starts (`on` to enable) |
| `AGENTS_OFFLINE_NUDGE` | `off` skips the default thread reply when headless is off (default **on** after `hooks --install`) |

### Bundled `headless-run.sh` (legacy / experimental)

Writes **`.agents/headless-*`** + a thread **reply**. Most teams can skip this: the next session runs **`agents status`** and reads **AGENTS.md** anyway. Use only if you want file breadcrumbs without an LLM.

### Sandbox & `agents attach` — `headless-sandbox.sh` (experimental / untested)

> **Note:** The Cursor and Open Interpreter attach/headless paths below are **untested prototypes and do not work reliably in practice** (kept as reference notes only).

On an offline-repo **`post`**: **`<repo>/.agents/sandbox-<id>/`**, **`~/work/agents/headless-sessions/<id>.json`**, thread **`reply`** with **`agents attach <id>`**.

| Piece | What it does |
|-------|----------------|
| **Sandbox files** | Always (when **`AGENTS_HEADLESS_CMD`** is set) |
| **`AGENTS_ATTACH=antigravity`** | **`agents attach ID`** opens repo **and** sandbox **POST.md** in Antigravity IDE; **`--plain`** opens repo only |
| **`AGENTS_ATTACH=agy`** | **`agents attach ID`** = **`agy -i`** (interactive CLI with context); **`--plain`** = **`agy`** REPL; **`--exec-only`** = **`agy -p`** and exit |
| **`AGENTS_ATTACH=cursor`** (default) | **`agents attach ID`** opens repo **and** sandbox **POST.md** in Cursor; **`--plain`** opens repo only |
| **`AGENTS_ATTACH=interpreter`** | **`agents attach ID`** = exec context + REPL; **`--plain`** = REPL only (POST printed); **`--exec-only`** = exec and exit |
| **`AGENTS_HEADLESS_AUTO=on`** | On **`post` only**: background **`headless-read.sh`** (`agy --mode accept-edits -p` when `AGENTS_ATTACH=agy\|antigravity`, or `agy -p` when `AGENTS_HEADLESS_AUTO=read`, then hook **`agents done`**) |

**Do not use Open Interpreter to implement board posts.** It is a poor fit for commits, worktrees, and closing the board: subprocess sandboxes often deny writes to **`.git`** and **`agents.jsonl`**, and attach starts in the repo's **main checkout** unless you opened a worktree yourself. Use **`AGENTS_ATTACH=cursor`** (or open the sandbox **POST.md** in Cursor), do real edits on a **branch/worktree**, then run **`agents done ID "…"`** from your normal terminal. Interpreter attach is OK for **read-only** exploration before you switch to Cursor; **`AGENTS_HEADLESS_AUTO=on`** is the only supported unattended Interpreter path (read-only on **`post`**, not attach).

**Model and permissions are Open Interpreter's, not agentboard's.** **`agents attach`** only runs `interpreter` / `interpreter exec -- …` with `cwd` set to the repo; it does not set which LLM runs (use Interpreter's **`/model`** or `model` in **`config.toml`**). It also does **not** pass **`--sandbox`** or **`--permissions`** — you get whatever defaults are in Open Interpreter's config (often **`workspace-write`** + **`on-request`** approvals). Optional: **`AGENTS_INTERPRETER_CMD`** to wrap the exec step (e.g. `interpreter --sandbox read-only exec --`).

#### Open Interpreter execution sandbox (≠ agentboard sandbox)

Two different “sandboxes” show up in this flow:

| Name | What it is |
|------|------------|
| **agentboard sandbox** | **`.agents/sandbox-<post-id>/`** on disk — POST.md and context for attach. |
| **Open Interpreter sandbox** | OS-enforced limits on **shell commands the model runs** inside Interpreter. |

Open Interpreter's local exec uses modes such as **`read-only`**, **`workspace-write`**, and **`danger-full-access`**, plus approval policies (**`untrusted`**, **`on-request`**, **`never`**). Inspect or change them in the TUI with **`/permissions`**, or in [config](https://www.openinterpreter.com/docs/terminal/config-reference) (`sandbox_mode`, `default_permissions`, `approval_policy`). On macOS enforcement uses Seatbelt-style profiles; denied writes often show as **`Operation not permitted`**.

Typical attach pain points (even with a “good” model):

- **`.git/`** is treated as a sensitive control directory — **`git worktree`**, new branches, and ref updates may fail under **`workspace-write`** until you widen policy or use **`danger-full-access`** in a environment you trust ([OI sandbox docs](https://www.openinterpreter.com/docs/terminal/sandbox)).
- **`~/work/journal/agents.jsonl`** is usually **outside** the repo workspace root — **`agents done`** from inside Interpreter may fail to append the board; run **`agents done`** from your normal shell after real work.
- **`--safe`** / **`safe_mode`** in Open Interpreter is a **different** experimental layer (Semgrep scan, no auto-run) — not the same as **`sandbox_mode`**. Do not confuse the two when debugging.

**Recommended for board attach:** **`read-only`** (or Cursor) for recon; implement with **`AGENTS_ATTACH=cursor`**. If you insist on Interpreter for writes, use an isolated checkout, explicit **`--add-dir`** for any extra roots, and only **`danger-full-access`** when you accept full local risk — agentboard does not configure that for you.

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
