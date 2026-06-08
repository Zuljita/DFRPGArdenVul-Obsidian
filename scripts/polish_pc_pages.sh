#!/usr/bin/env bash
# Polish pass — picks top articles by staleness+quality score, rewrites prose,
# fixes typos, commits locally. Push to remote manually after reviewing with
# `git diff HEAD~1`.
set -euo pipefail

cd "$(dirname "$0")/.."
LOG_DIR="data/automation/runs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/polish-queue.log"
PYTHON=/usr/bin/python3

echo "=== polish_pc_pages.sh $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$LOG"

RESULT=$("$PYTHON" scripts/vault_automation.py polish-queue \
  --apply --limit 5 2>> "$LOG")
echo "$RESULT" >> "$LOG"

# Extract changed paths from JSON and commit if anything changed
CHANGED=$(echo "$RESULT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
pages = [p['path'] for p in d.get('pages', []) if p.get('changed')]
print('\n'.join(pages))
" 2>/dev/null || true)

if [ -z "$CHANGED" ]; then
  echo "  no changes produced" >> "$LOG"
  exit 0
fi

mapfile -t CHANGED_ARRAY <<< "$CHANGED"
git add -- "${CHANGED_ARRAY[@]}"
git commit -m "chore: automated polish pass ($(date -u +%Y-%m-%d))

Articles updated (top of staleness+quality queue):
$(printf '  - %s\n' "${CHANGED_ARRAY[@]}")

Review with: git diff HEAD~1
Push manually after review.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" >> "$LOG" 2>&1

echo "  committed ${#CHANGED_ARRAY[@]} article(s)" >> "$LOG"
