#!/bin/sh
# Read-only headless: gather repo + board context, optionally ask an LLM (read-only), then
# `agents done` from THIS script — not from inside the LLM tool's sandbox.
#
# Optional: set AGENTS_HEADLESS_AUTO=interpreter for LLM auto-done (read-only).
# export AGENTS_HEADLESS_AUTO=interpreter
# Override runner: AGENTS_INTERPRETER_CMD='interpreter exec --'

set -e
cd "$AGENTS_HEADLESS_ROOT"
export AGENTS_ACTOR=board:headless
export AGENTS_SESSION=headless

POST_ID="${AGENTS_HEADLESS_POST_ID:?}"
TO="${AGENTS_HEADLESS_TO:-$(basename "$AGENTS_HEADLESS_ROOT")}"
TEXT="${AGENTS_HEADLESS_TEXT:-}"

slack_ping() {
  [ -n "${AGENTS_SLACK_WEBHOOK_URL:-}" ] || return 0
  MSG="${1:-}"
  [ -n "$MSG" ] || return 0
  curl -sf -X POST -H 'Content-type: application/json' \
    --data "$(python3 -c "import json,sys; print(json.dumps({'text': sys.argv[1]}))" "$MSG")" \
    "$AGENTS_SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true
}

CTX="$(mktemp)"
trap 'rm -f "$CTX"' EXIT

mkdir -p .agents
LOG=".agents/headless-llm.jsonl"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HOOK_PY="${AGENTS_PYTHON:-python3}"

{
  printf '%s\n' "=== board post ${POST_ID} (repo ${TO} only) ===" "$TEXT" ""
  if [ -n "${AGENTS_SANDBOX_DIR:-}" ] && [ -f "${AGENTS_SANDBOX_DIR}/POST.md" ]; then
    printf '%s\n' "=== sandbox POST.md ==="
    cat "${AGENTS_SANDBOX_DIR}/POST.md"
    printf '\n'
  fi
  if [ -n "${AGENTS_SANDBOX_DIR:-}" ] && [ -f "${AGENTS_SANDBOX_DIR}/status.json" ]; then
    printf '%s\n' "=== agents status --json (this repo, from sandbox) ==="
    head -c 100000 "${AGENTS_SANDBOX_DIR}/status.json" || true
    printf '\n'
  else
    printf '%s\n' "=== agents status --json (this repo cwd, truncated) ==="
    agents status --json 2>/dev/null | head -c 100000 || true
    printf '\n'
  fi
  for f in AGENTS.md PROJECT.md HANDOFF.md README.md; do
    base="${AGENTS_SANDBOX_DIR:-.}/$f"
    if [ -f "$base" ]; then
      printf '%s\n' "=== ${f} (from sandbox, first 150 lines) ==="
      head -150 "$base"
      printf '\n'
    elif [ -f "$f" ]; then
      printf '%s\n' "=== ${f} (first 150 lines) ==="
      head -150 "$f"
      printf '\n'
    fi
  done
} >"$CTX"
$HOOK_PY - "$CTX" <<'PY' 2>/dev/null >>"$CTX" || true
import os, sys
from pathlib import Path
from agentboard.sandbox import path_context_block
root = Path(os.environ["AGENTS_HEADLESS_ROOT"]).expanduser()
text = Path(sys.argv[1]).read_text(encoding="utf-8")
block = path_context_block(root, text)
if block:
    print(block)
PY

LLM_USED=0
AUTO="$($HOOK_PY -c "
from agentboard.plugins import headless_auto
print(headless_auto())
" 2>/dev/null || echo off)"
if [ "$AUTO" = "on" ] || [ -n "${AGENTS_HEADLESS_LLM:-}" ]; then
  PROMPT="You are handling an agents board post in repository ${TO} (${AGENTS_HEADLESS_ROOT}).
If the post only asks a question, answer it without editing files.
If the post asks to edit or create files in this repository, make the requested file changes using your file tools.
Do not run shell commands (this hook script will close the board post for you).
At the end of your response, output a single line starting with: ANSWER: followed by a short answer or summary of changes for agents done (plain text, no markdown fences).

Context:
$(cat "$CTX")"
  export PROMPT
  RAW="$($HOOK_PY -c "
import os, subprocess
from agentboard.plugins import headless_exec_argv
proc = subprocess.run(headless_exec_argv(os.environ['PROMPT']), capture_output=True, text=True, check=False)
print(proc.stdout or '', end='')
" 2>/dev/null || true)"
  ANSWER="$(printf '%s\n' "$RAW" | sed -n 's/^ANSWER:[[:space:]]*//p' | tail -1)"
  if [ -z "$ANSWER" ]; then
    ANSWER="read-only (LLM): $(printf '%s\n' "$RAW" | tail -3 | tr '\n' ' ' | cut -c1-400)"
  fi
  LLM_USED=1
else
  if [ -f README.md ]; then
    LINE="$(grep -m1 -v '^#' README.md | grep -v '^[[:space:]]*$' | head -1 || true)"
    ANSWER="read-only: ${LINE:-$(head -1 README.md)}"
  else
    ANSWER="read-only: post received; no README.md in repo root — open session for code work"
  fi
fi

ANSWER="$(printf '%s' "$ANSWER" | tr '\n' ' ' | cut -c1-2000)"
agents done "$POST_ID" "$ANSWER"

export ANSWER
printf '%s\n' "{\"ts\":\"$TS\",\"post_id\":\"$POST_ID\",\"to\":\"$TO\",\"llm\":$LLM_USED,\"answer\":$(python3 -c "import json,os; print(json.dumps(os.environ.get('ANSWER','')[:800]))")}" >>"$LOG"

slack_ping "agents: post ${POST_ID} answered on ${TO} — $(printf '%s' "$ANSWER" | cut -c1-200)"
