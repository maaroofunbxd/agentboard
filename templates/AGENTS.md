# Agent instructions

At the start of work:

1. Read `PROJECT.md` for stable project facts and constraints.
2. Read `HANDOFF.md` for the current task and its next action.
3. Treat these repository files as the portable source of context. Do not require access to an earlier chat, an external board, or a connected tool to understand the handoff.
4. When the `agents` command is installed: run **`agents whoami`** once (it prints this session's name, your `AGENTS.local.md` if any, and the repo's board status; say the name in your first message, and do not pipe to `head`). Start **`agents wait` in the background** if your tool wakes the agent when a background command ends.
5. Optional: if **`~/.agents/pending/<this-repo>.jsonl`** exists, read it once (posts that arrived while no session was live), then **`agents status`**.

While working:

- Keep project-wide facts in `PROJECT.md`; keep current task progress in `HANDOFF.md`.
- Do not invent shell commands or assume a CLI/tool is installed. Check command availability before using it.
- Update `HANDOFF.md` when asked to hand work to another session, including what is done, what's left, relevant files, decisions, and the next concrete action.
- Do not put credentials, private customer data, or unnecessary personal data in these files.
- Follow this repository's other instructions and ask the user before external publication or irreversible actions.

## Board (`agents`)

Coordination between sessions on this machine: [agentboard](https://github.com/maaroofunbxd/agentboard). The board is not chat — the other repo only hears you if you **`agents done`** or **`agents reply`** on the thread. See [board automation](../docs/board-automation.md) for optional hooks and digest.

- **Claim / handoff (this repo):** `agents claim "…" -p path`, `agents handoff "done: …; left: …; next: …"`, `agents pickup ID`, close with `agents done ID "…"`.
- **Ask another repo:** `agents post --to REPO "what, why, where to answer"`. Tell the user the post id. If you need the answer before continuing, **run `agents wait ID` in the background in this same turn** when your tool supports it — **do not** only say the other repo can `agents done …` or that the user should `agents wait …`.
- **Answer a post to this repo:** after **`agents status`**, do the work, then **`agents done ID "answer or link"`**. Do not only describe board commands in chat without running them.
- **Follow-up without closing:** `agents reply ID "…"`, then the other side waits with `agents wait ID` again.
- **Urgent:** `agents post --urgent` only when the user says so or something is broken; the CLI confirms on a TTY (or you pass `--yes` after they OK it). It wakes `agents wait` and can notify the user.

Posts nobody closes drop off the default **`agents status`** view after **14 days** but stay in the log — close them when done so the inbox stays usable.

### Offline post → sandbox (experimental / untested)

The offline sandbox hooks (`AGENTS_HEADLESS_CMD`, `headless-sandbox.sh`, and `agents attach` for Cursor / Open Interpreter) are experimental prototypes and not required for normal board work. If you are experimenting with them, see [board-automation.md](https://github.com/maaroofunbxd/agentboard/blob/main/docs/board-automation.md).

### Cross-repo

- **Asker:** `post` → post id → **`wait ID` in background** if blocked; never substitute prose ("watch with agents wait") for running **`wait`**.
- **Responder:** `status` → act → **`done ID`**.

### Incoming posts (don't stall)

- After **`agents status`**, handle posts to this repo before unrelated work when the user expects cross-repo flow.
- **Read-only** (document, answer in thread, point to files, review a PR link): **do the work**, then **`agents done ID`**. Do **not** ask "should I proceed?"
- **Local repo work** (code, docs, tests, branch commits, PRs — nothing that runs **`unbxd`** against a **live site** or shared prod): **proceed** and **`agents done ID`** when finished. Do not ask the user to confirm again unless the post says to wait for approval.
- **Live / prod** (commands that change or query live systems — in Unbxd setups, **`unbxd`** paths that touch sites, clusters, configstore, etc.): **tell the user once** and wait for approval before running those commands; you may still do local prep and answer read-only parts on the board.
- A **`agents reply`** that mentions **`.agents/sandbox-*`** is the offline sandbox hook — read **POST.md**, **`agents attach <id>`** or open the repo in Cursor, then **`agents done ID`**. Legacy **`headless-status-*.json`** / **`headless.jsonl`** only if you still use **`headless-run.sh`**.

### Commits and `done`

- Before **`agents done ID`** on work that changed files: **commit on your branch** (or open a PR) and put the **sha or PR** in the **`done`** message.
- If you must stop with **uncommitted** changes: **`agents handoff`** must say what's dirty and **`next:`** must include the commit (or revert) command — do not leave silent local-only state.
