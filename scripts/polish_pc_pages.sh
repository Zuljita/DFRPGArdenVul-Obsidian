#!/usr/bin/env bash
# Polish pass for all PC pages — runs RAG research + LLM rewrite + typo-fix QA, then applies.
# Changes are committed locally. Push to remote manually after reviewing with `git diff HEAD~1`.
set -euo pipefail

cd "$(dirname "$0")/.."
LOG_DIR="data/automation/runs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/polish-pc-pages.log"
PYTHON=/usr/bin/python3

echo "=== polish_pc_pages.sh $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$LOG"

PAGES=(
  "vault/pcs/Vaelethron 'Vael' Sunshadow.md"
  "vault/pcs/Ioannes Grammatikos Byzantios.md"
  "vault/pcs/Vallium Halcyon.md"
  "vault/pcs/Uvash Edzuson.md"
  "vault/pcs/Michael J. Dundee.md"
  "vault/pcs/grudge-brigade/Ashe Maykum.md"
  "vault/pcs/grudge-brigade/Coinbase.md"
  "vault/pcs/grudge-brigade/Sister Valya -Basilisk- Hushbreaker.md"
  "vault/npcs/Merenuithiel Lacrymosa Armaris.md"
  "vault/npcs/Thrainor Thronebreaker Ironvein.md"
)

CHANGED=()
for PAGE in "${PAGES[@]}"; do
  echo "  polishing: $PAGE" >> "$LOG"
  RESULT=$("$PYTHON" scripts/vault_automation.py polish-article \
    --apply --article "$PAGE" 2>> "$LOG") || true
  echo "  $RESULT" >> "$LOG"
  if echo "$RESULT" | grep -q '"changed": true'; then
    CHANGED+=("$PAGE")
  fi
done

if [ ${#CHANGED[@]} -eq 0 ]; then
  echo "  no changes produced" >> "$LOG"
  exit 0
fi

# Commit all changed pages in one commit
git add -- "${CHANGED[@]}"
git commit -m "chore: automated polish pass on PC pages ($(date -u +%Y-%m-%d))

Pages updated:
$(printf '  - %s\n' "${CHANGED[@]}")

Review with: git diff HEAD~1
Push manually after review.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" >> "$LOG" 2>&1

echo "  committed ${#CHANGED[@]} page(s)" >> "$LOG"
