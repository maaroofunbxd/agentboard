#!/bin/sh
# Bundled headless handler: snapshot status, log for the next session, reply on the thread with where to look.
set -e
cd "$AGENTS_HEADLESS_ROOT"
mkdir -p .agents
export AGENTS_ACTOR=board:headless
export AGENTS_SESSION=headless
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
STATUS_JSON=".agents/headless-status-${AGENTS_HEADLESS_POST_ID}.json"
LOG=".agents/headless.jsonl"

agents status --json > "$STATUS_JSON" 2>/dev/null || echo '{"error":"agents status failed"}' > "$STATUS_JSON"

printf '%s\n' "{\"ts\":\"$TS\",\"post_id\":\"$AGENTS_HEADLESS_POST_ID\",\"status_file\":\"$STATUS_JSON\",\"text\":$(python3 -c "import json,os; print(json.dumps(os.environ.get('AGENTS_HEADLESS_TEXT','')[:500]))")}" >> "$LOG"

SUMMARY="offline headless: wrote $STATUS_JSON and line in $LOG — next session: read those, then agents status, act, agents done ${AGENTS_HEADLESS_POST_ID}"
agents reply "$AGENTS_HEADLESS_POST_ID" "$SUMMARY"
