#!/bin/sh
# Optional AGENTS_HEADLESS_CMD: LLM via Open Interpreter, driving the `agents` board CLI (not Cursor `agent`).
#
# export AGENTS_HEADLESS_CMD="$HOME/work/agents/hooks/headless-llm.sh"
# export AGENTS_HEADLESS_TIMEOUT=1800

set -e
cd "$AGENTS_HEADLESS_ROOT"
export AGENTS_ACTOR=board:headless
export AGENTS_SESSION=headless

POST_ID="${AGENTS_HEADLESS_POST_ID:?}"
TEXT="${AGENTS_HEADLESS_TEXT:-}"

PROMPT="You are in repo ${AGENTS_HEADLESS_ROOT}. Handle agents board post ${POST_ID}.

Post text:
${TEXT}

Read AGENTS.md if present. Run agents status (full). Do the work per AGENTS.md (no live prod unless post says user approved).
Close with: agents done ${POST_ID} \"summary\"
If blocked: agents reply ${POST_ID} \"blocked: reason\"
Use the shell for every agents command; do not only describe them."

exec interpreter exec -- "$PROMPT"
