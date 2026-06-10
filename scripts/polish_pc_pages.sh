#!/usr/bin/env bash
# Polish pass — picks top articles by staleness+quality score, rewrites prose,
# fixes typos, and leaves the resulting changes uncommitted for review.
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

# Extract and report changed paths without staging or committing them.
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
printf '  changed: %s\n' "${CHANGED_ARRAY[@]}" >> "$LOG"
echo "  left ${#CHANGED_ARRAY[@]} article(s) uncommitted for review" >> "$LOG"
