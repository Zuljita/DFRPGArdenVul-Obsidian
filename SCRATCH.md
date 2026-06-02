# Vault Automation Scratchpad

Rolling session notes. Run `python3 scripts/vault_automation.py summarize-scratchpad` to condense with Heavy when this grows unwieldy.

---

## Session: 2026-06-01 — New Entity Pipeline + Truncation Fixes

### Completed this session
- 3 filter fixes: Discord Summary kind, standard potions, player names
- Pale Green Horn now surfaces from Party Armory (was being filtered out)
- Action items rebuilt: 11 accepted; Discord summaries now feeding it
- Full vault walk across all 132 sources
- 22 new entity stub pages created and committed
- RAG refreshed: 4324 Arden chunks (was 4263)

**New pages created:**
Varuda, United Goblin Tribes, Chairduster, Hellas, Surgical Construct, Demmasday Market,
Grain House, Kazildor, Secure Treasury, Vault, Bracers of Force, Magebane Grenade, Returning
Javelin, Serpent Amulet, Statuette of Feline Friendship, Torc of Protection, Wand of See Secrets,
Ankh Key, Magebane Potion, Wand of Illumination, The Rug, Divine Grace

### Bugs fixed this session
- `verify-new-entities` was overwriting verifications each run (re-ran same top-50 repeatedly)
  → Fixed: now skips already-verified proposals and appends new results (cursor behaviour)
- Artificial truncation limits across the pipeline:
  → `verify-new-entities` default: 20 → -1 (unlimited)
  → `propose-new-entities` --limit default: 50 → 500
  → `verify-article-edits` default: 10 → -1
  → `propose-article-edits` default: 5 → -1
  → `propose-metadata-edits` default: 5 → -1
  → `action_items_max_items` default: 50 → 200
  → `build-action-items` --max-items default: 50 → 200

### PENDING: Pale Green Horn page
- Proposal at rank 75 of 154; not yet verified (was outside old top-50 window)
- verify-new-entities was re-running on top-50 again when the cursor fix was committed
- After the running verify job finishes, the next `verify-new-entities` (unlimited) will include rank 75
- TODO: run `verify-new-entities` (no args) → then `apply-verified-new-entities --apply` → then `refresh-vault-rag`

### Branch state
- Branch: `codex/contextual-rag-automation`
- Commits this session:
  - `Fix verify-new-entities to skip already-processed proposals`
  - `Remove artificial truncation limits across the pipeline`

---

## Known remaining work (from previous audit)

- **Pale Green Horn dedicated item page** — see PENDING above
- **Historical thread archive** — `Active Action Items.md` stays narrow; need separate `status: legacy` archive for dormant hooks (Ruby Chair, Fire Mephit mushrooms, Tikun Thane, old unexplored locations)
- **Semantic chunking** — "What Happened" sections in long sessions produce many sequential word-count chunks; consider splitting on subsection headers
- **"Latest known status" sections** — NPC/item/location pages lack generated "as of session N" summaries
- **Player vs GM tagging** — no metadata separation between player-facing facts and GM-only commentary
- **Encoding/typo cleanup** — Â artifacts and "United Goblns" still in some imported notes
- **Shield Lectern** — no dedicated note; only surfaces via Discord summary Unresolved Threads
