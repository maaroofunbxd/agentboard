#!/bin/sh
# AGENTS_HEADLESS_CMD: repo-only sandbox. Optional auto: AGENTS_HEADLESS_AUTO=interpreter
#
# export AGENTS_HEADLESS_CMD="$HOME/work/agents/hooks/headless-sandbox.sh"

set -e
POST_ID="${AGENTS_HEADLESS_POST_ID:?}"
ROOT="${AGENTS_HEADLESS_ROOT:?}"
TO="${AGENTS_HEADLESS_TO:-unknown}"
TEXT="${AGENTS_HEADLESS_TEXT:-}"

AGENTS_DIR="${AGENTS_DIR:-$HOME/work/agents}"
META_DIR="${AGENTS_DIR}/headless-sessions"
LOG_DIR="${AGENTS_DIR}/headless-log"
SANDBOX="$ROOT/.agents/sandbox-${POST_ID}"
META="${META_DIR}/${POST_ID}.json"
WORK_LOG="${LOG_DIR}/${POST_ID}.log"
HOOK_PY="${AGENTS_PYTHON:-python3}"

mkdir -p "$SANDBOX" "$META_DIR" "$LOG_DIR"
export AGENTS_ACTOR=board:headless
export AGENTS_SESSION=headless
export POST_ID TO ROOT SANDBOX META

cd "$ROOT"

set -- $($HOOK_PY -c "
from agentboard.plugins import attach_mode, headless_auto
print(headless_auto(), attach_mode())
" 2>/dev/null || echo off cursor)
AUTO=$1
ATTACH=$2

{
  printf '%s\n' "# Post \`${POST_ID}\` (this repo: \`${TO}\` only)"
  printf '\n%s\n\n' "$TEXT"
  printf '%s\n' "Context here is **only** this repository."
  printf '\n%s\n' "## Handle this post"
  printf '%s\n' "\`agents attach ${POST_ID}\`  — AGENTS_ATTACH (cursor = open repo; interpreter = REPL)"
  printf '%s\n' "\`agents done ${POST_ID} \"answer\"\` when finished"
} >"$SANDBOX/POST.md"

agents status --json >"$SANDBOX/status.json" 2>/dev/null || echo '{}' >"$SANDBOX/status.json"

for f in AGENTS.md PROJECT.md HANDOFF.md README.md; do
  [ -f "$f" ] && cp "$f" "$SANDBOX/$f" 2>/dev/null || true
done

$HOOK_PY <<'PY'
import json, os
from pathlib import Path
meta = {
    "post_id": os.environ["POST_ID"],
    "to": os.environ["TO"],
    "root": os.environ["ROOT"],
    "sandbox_dir": os.environ["SANDBOX"],
    "post_md": str(Path(os.environ["SANDBOX"]) / "POST.md"),
}
Path(os.environ["META"]).write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
PY

READ="${AGENTS_DIR}/hooks/headless-read.sh"
if [ "$AUTO" = "on" ]; then
  agents reply "$POST_ID" "sandbox (${TO}): ${SANDBOX} — attach: agents attach ${POST_ID}; auto read-only log ${WORK_LOG}"
  if [ -x "$READ" ]; then
    (
      export AGENTS_SANDBOX_DIR="$SANDBOX"
      export AGENTS_HEADLESS_ROOT="$ROOT"
      export AGENTS_HEADLESS_POST_ID="$POST_ID"
      export AGENTS_HEADLESS_TEXT="$TEXT"
      export AGENTS_HEADLESS_TO="$TO"
      export AGENTS_HEADLESS_AUTO=on
      export AGENTS_PYTHON="$HOOK_PY"
      "$READ"
    ) >>"$WORK_LOG" 2>&1 &
  fi
elif $HOOK_PY -c "from agentboard.plugins import headless_auto_wanted, attach_mode; exit(0 if headless_auto_wanted() and attach_mode()=='cursor' else 1)" 2>/dev/null; then
  agents reply "$POST_ID" "sandbox (${TO}): ${SANDBOX} — agents attach ${POST_ID} (AGENTS_ATTACH=cursor; AUTO=on ignored — no Cursor auto)"
else
  agents reply "$POST_ID" "sandbox (${TO}): ${SANDBOX} — agents attach ${POST_ID} (AGENTS_ATTACH=${ATTACH}; auto=off)"
fi
