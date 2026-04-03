---
tags:
  - note
  - qa-report
---

# Arden Vul Vault-Wide QA Batch Report

---
## Batch Run — 2026-03-13 19:11 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Monster variant cluster likely needs family-page consolidation:**
  - `monsters/Flying Monkey Statue (Huge Ears).md`
  - `monsters/Flying Monkey Statue (Huge Eyes).md`
  - High name similarity (0.94) with only descriptor drift; likely one canonical parent (`Flying Monkey Statue`) with variant subheads/stubs.

### naming drift
- **Path-style links are mixed with bare-name links across NPC pages**, creating inconsistent naming conventions and increasing drift risk (`[[npcs/Vivian.md|Vivian]]` vs `[[Vivian]]`).
- **Transcript-import artifacts present inside link targets**, e.g. nested target fragments like `locations/[[npcs/Arden.md` and `factions/Cult of [[npcs/Set.md` (malformed target strings observed at scale).
- **Unresolved name variants (likely aliases or missing canonical pages):** `Archontean`, `Thorcin`, `Ioannes`, `Vael`, `Larel`, `Sortian`, `Thothian` (appear as broken link targets in multiple files).

### weak-evidence claims
- `sessions/Session 2 - Halfling Rent-Seekers.md` has high uncertainty density (>=12 weak-confidence markers: "unclear/possibly/maybe/might be/unsure/inaudible/?").
- NPC entries that quote long session snippets appear to include partially ingested transcript blocks; these should be treated as **low-confidence secondary evidence** until recap/blog corroboration.

### structure issues
- **Large malformed-link footprint detected:** 795 nested-link/malformed targets across vault markdown during this batch scan.
- **Broken link targets (top recurring):** `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), plus several session/file-path variants without `.md` normalization.
- Representative corruption pattern confirmed in `npcs/Vivian.md` history line containing `[[locations/[[npcs/Arden.md|Arden]] Vul.md|...]]`.

### suggested changes
1. Add a **link-normalization cleanup pass** (safe, mechanical) to repair nested-target patterns like `[[foo/[[bar]]...]]` before semantic QA decisions.
2. Standardize on one vault link style for entities (recommended: `[[Entity Name]]` + aliases in frontmatter) and reserve path links for disambiguation only.
3. Create/confirm canonical pages or aliases for high-frequency unresolved ethnonyms/titles (`Archontean`, `Thorcin`, `Thothian`) and principal names (`Ioannes`, `Vael`).
4. Consolidate Flying Monkey Statue variants into one family page with variant subheads; keep lightweight redirect/stub pages if needed.
5. Flag transcript-heavy sections with confidence tags (`confidence: low|medium|high`) to separate canon statements from uncertain raw capture text.

---
## Batch Run — 2026-03-13 19:19 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Variant duplicate cluster reconfirmed:**
  - `monsters/Flying Monkey Statue (Huge Ears).md`
  - `monsters/Flying Monkey Statue (Huge Eyes).md`
  - Classification: **merge-into-existing** (family page + variant subheads/stubs).
- **Session split naming likely intentional, but still drift-prone for reconciler automation:**
  - `sessions/Session 24a - Revenge on the Set Cult.md`
  - `sessions/Session 24b - The Set Cult Strikes Back, Larel's Stuff, and the Hall of Shrines.md`
  - `sessions/Session 23a/23b/23c ...`
  - Classification: **keep** (serial suffix model), with alias/index normalization needed.

### naming drift
- **Broken target strings continue to indicate canonical-name drift:** `Archontean` (20 refs), `Thorcin` (18), `Ioannes` (16), `Vael` (8), `Larel` (7), `Sortian` (7), `Thothian` (6).
- **Mixed target styles remain widespread** (`[[Entity]]`, `[[folder/Entity.md|Entity]]`, and malformed nested forms), increasing false duplicate signals during QA.
- **Path-like session references omit normalization** in many links (e.g., raw `sessions/Session 34a ...` targets), causing avoidable unresolved-link noise.

### weak-evidence claims
- **High-uncertainty file remains the primary weak-evidence hotspot:** `sessions/Session 2 - Halfling Rent-Seekers.md` (9+ uncertainty markers in latest pass).
- **Transcript-derived assertions in character pages remain weakly grounded** when they include long quoted blocks from recording-note style text without recap/blog corroboration.
- Classification guidance for these claims: default to **hold-for-review** unless corroborated in recap/session canon pages.

### structure issues
- **Malformed-link footprint remains high:** 152 files currently contain nested/malformed wiki-link patterns.
- Highest-density files this pass include:
  - `locations/Great Cavern.md` (51)
  - `pcs/Ioannes Grammatikos Byzantios.md` (34)
  - `pcs/Vallium Halcyon.md` (32)
  - `npcs/Thoth.md` (28)
  - `sessions/Session 32 - Fast Exploration.md` (28)
- Structural takeaway: link-shape corruption is broad enough that semantic QA decisions are being masked by syntax noise.

### suggested changes
1. Run a **mechanical link-shape repair pass** first (nested `[[...[[...]]...]]` and path-target normalization) before deeper entity reconciliation.
2. Add/confirm canonical alias mappings for top unresolved targets (`Archontean`, `Thorcin`, `Thothian`, `Ioannes`, `Vael`, `Larel`, `Sortian`) to reduce repeated false-positive “new entity” detections.
3. Introduce a lightweight **Session Reference Index** page listing canonical session filenames + aliases (`24a`, `24b`, etc.) for safer auto-linking.
4. Apply `hold-for-review` tags to transcript-heavy claims lacking recap corroboration, especially in early-session notes with explicit uncertainty markers.
5. After syntax cleanup, rerun vault-wide QA and promote only unambiguous low-risk merges (starting with Flying Monkey Statue variant consolidation).


---
## Batch Run — 2026-03-13 19:29 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Confirmed cross-type duplicate page title:**
  - `npcs/Angry scary ghost.md`
  - `monsters/Angry scary ghost.md`
  - Candidate canonical match: same encounter/session scope (`Session 6`) with overlapping identity.
  - Decision label: **merge-into-existing** (or `rename-to-canonical` if monster taxonomy requires separate naming).
- **Systemic namespace collision pages (expected but noisy for automation):**
  - `npcs/Index.md`, `locations/Index.md`, `items/Index.md`, `factions/Index.md`, `pcs/Index.md`
  - `locations/README.md`, `items/README.md`, `factions/README.md`
  - Decision label: **keep** (structural docs), but exclude from duplicate detectors.

### naming drift
- Top unresolved target names still indicate canonical drift and/or alias gaps:
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `Vael` (8), `Larel` (7), `Sortian` (7), `Thothian` (6), `Mithric` (10).
- Session-link naming remains inconsistent (`Session 34a...`, `Session 34c...`, `Session 42b...`) with missing normalization to exact filenames, increasing false broken-link counts.
- Lore-note references (`Recording 2026-02-13`, `Recording 2026-02-06`, `Recording 2026-01-30`) are heavily linked by shorthand names rather than canonical page/file targets.

### weak-evidence claims
- Terms like `Vael`, `Larel`, and `Sortian` currently appear mostly as unresolved references; absent clear canonical pages, classify incoming transcript-derived additions using these tokens as **hold-for-review** until corroborated.
- `The Living Wheelbarrow` appears as a repeated unresolved target (12 refs) but without immediate canonical anchor in this pass; treat as **weak-evidence alias candidate** pending source cross-check.

### structure issues
- **Frontmatter quality issue is widespread:** 307 markdown files currently contain duplicate tag entries (e.g., repeated `npc` in many NPC pages).
- Duplicate-tag issue is low semantic risk but high maintenance noise for tooling that relies on deduplicated metadata.
- Broken-link leaderboard continues to mix true missing pages with alias/name-style drift, indicating the need for an alias index before further semantic reconciliation.

### suggested changes
1. Add a QA pre-filter that excludes structural docs (`Index`, `README`) from duplicate-entity scans.
2. Resolve `Angry scary ghost` cross-type duplication by selecting one canonical page and converting the other to a stub/alias.
3. Create a canonical alias map for high-frequency unresolved names (`Archontean`, `Thorcin`, `Ioannes`, `Mithric`, `Vael`, `Larel`, `Sortian`, `Thothian`).
4. Run a safe metadata cleanup pass to deduplicate frontmatter `tags` arrays (mechanical, low-risk, broad payoff).
5. Normalize session references to exact vault filenames (including lettered sessions like `34a/34c/42b`) before next semantic QA batch.

---
## Batch Run — 2026-03-13 19:39 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Cross-type duplicate still unresolved (high-confidence merge candidate):**
  - `npcs/Angry scary ghost.md`
  - `monsters/Angry scary ghost.md`
  - Decision label: **merge-into-existing** (single canonical page + cross-link stub), unless taxonomy policy explicitly requires NPC/monster split.
- **Only three normalized-title duplicate clusters vault-wide this pass:**
  - `*/Index.md` (structural, keep)
  - `*/README.md` (structural, keep)
  - `Angry scary ghost` (semantic duplicate, reconcile)

### naming drift
- **Recurring unresolved names continue to dominate drift noise:**
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), `Larel` (7), `Sortian` (7), `Thothian` (6), `Lacrymosa` (7).
- **Session-title targets are frequently linked as raw text instead of exact canonical page names**, especially:
  - `Session 34a - Hunting the Thane`
  - `Session 34c - Burglary and Death`
  - `Session 42b - Neferet and the Wraiths`
  - This inflates false broken-link/"new entity" detections.

### weak-evidence claims
- **Uncertainty hotspot persists:** `sessions/Session 2 - Halfling Rent-Seekers.md` (12 weak-confidence markers this pass).
- Additional weak-evidence concentration detected in transcript-source material:
  - `lore/recording-notes/Recording 2025-04-04.md` (9)
  - `sessions/Session 1 - First Visit to the Ruins of Arden Vul.md` (8)
- Reconciliation guidance unchanged: classify transcript-derived additions from these pages as **hold-for-review** unless recap/canon corroborates.

### structure issues
- **Orphan-link surface is large:** 127 content pages currently show zero inbound wiki links in this pass.
- Representative orphans include: `npcs/Jarnno the False.md`, `npcs/Domo Gribble.md`, `npcs/Voice of Thoth.md`, `npcs/Egill Flat-nose.md`, `npcs/Bastet.md`.
- While some may be legitimate edge entities, this scale suggests index/alias coverage gaps rather than purely intentional isolation.

### suggested changes
1. Resolve `Angry scary ghost` as the next unambiguous, low-risk semantic reconciliation (single canonical page + stub on the deprecated path).
2. Add alias/index entries for the top unresolved drift names (`Archontean`, `Thorcin`, `Ioannes`, `Lacrymosa`, `Thothian`) before running deeper duplicate detection.
3. Build a mechanical normalizer for session-title links to exact existing filenames (particularly split-letter sessions like `34a/34c/42b`).
4. Generate an "orphan triage" checklist from the 127 zero-inbound pages, starting with NPCs that are expected to be discoverable via index pages.
5. Keep transcript-heavy claims in `hold-for-review` until corroborated by recap/session canon sources.

---
## Batch Run — 2026-03-13 19:49 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Newly confirmed cross-folder duplicate concepts (non-structural):**
  - `npcs/Magae.md` vs `lore/Magae.md`
  - `npcs/Irthuin.md` vs `lore/Irthuin.md`
  - Decision label: **rename-to-canonical** (prefer `lore/*` for world/continent concepts) or **merge-into-existing** with NPC-page stubs.
- **Previously identified semantic duplicate remains open:**
  - `npcs/Angry scary ghost.md` vs `monsters/Angry scary ghost.md`
  - Decision label: **merge-into-existing** (single canonical + stub/alias).

### naming drift
- Unresolved drift tokens remain concentrated and unchanged at top of leaderboard:
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), `Lacrymosa` (7), `Larel` (7), `Sortian` (7), `Thothian` (6).
- Letter-suffixed session names are still heavily referenced as raw targets rather than exact canonical file links:
  - `Session 34a - Hunting the Thane` (9)
  - `Session 42b - Neferet and the Wraiths` (7)
  - `Session 34c - Burglary and Death` (7)
- Lore pages still frequently cross-link world entities via NPC path targets (e.g., `[[lore/Magae.md|Magae]]`), reinforcing taxonomy drift.

### weak-evidence claims
- Weak-confidence hotspots remain stable:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (14 markers)
  - `sessions/Session 1 - First Visit to the Ruins of Arden Vul.md` (9)
  - `lore/recording-notes/Recording 2025-04-04.md` (9)
- Classification guidance: transcript-derived claims from these sources stay **hold-for-review** absent recap/canon corroboration.

### structure issues
- **Malformed nested-link surface remains broad:** 151 files currently contain nested/malformed wiki-link patterns.
- Highest malformed-link density this pass:
  - `locations/Great Cavern.md` (50)
  - `pcs/Ioannes Grammatikos Byzantios.md` (33)
  - `pcs/Vallium Halcyon.md` (31)
  - `npcs/Thoth.md` (27)
  - `sessions/Session 32 - Fast Exploration.md` (27)
- QA report files themselves are now appearing in some automated weak-evidence/broken-link scans; these should be excluded from reconciliation metrics to avoid self-noise.

### suggested changes
1. Reclassify `Magae` and `Irthuin` as **lore-canonical** entities; convert `npcs/*` versions to lightweight stubs or merge content into `lore/*` pages.
2. Keep `Angry scary ghost` queued as next semantic merge after link-shape cleanup.
3. Add a QA scanner exclusion list for `vault/notes/*` to prevent report text from polluting weak-evidence and broken-link counts.
4. Continue mechanical nested-link normalization first, then rerun semantic reconciliation so duplicate/alias decisions are based on clean link targets.
5. Add explicit alias entries for high-frequency unresolved ethnonyms/titles (`Archontean`, `Thorcin`, `Thothian`) before next batch.

---
## Batch Run — 2026-03-13 19:59 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Duplicate set remains stable and focused (3 semantic clusters):**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md`
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md`
  - `npcs/Magae.md` ↔ `lore/Magae.md`
- Classification guidance (unchanged):
  - `Angry scary ghost` → **merge-into-existing**
  - `Irthuin`/`Magae` → **rename-to-canonical** (prefer `lore/*` canon) with stubs at legacy NPC paths.

### naming drift
- Top unresolved targets are still concentrated in a small recurring set:
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), `Lacrymosa` (7), `Larel` (7), `Sortian` (7), `Thothian` (6).
- Session-title drift remains a major false-positive source:
  - `Session 34a - Hunting the Thane` (9)
  - `Session 42b - Neferet and the Wraiths` (7)
  - `Session 34c - Burglary and Death` (7)
  - `Session 35 - The Scepter - Flute of the Goblins` (6)
- Additional unresolved proper nouns worth alias triage this pass: `Obsidian Gates` (6), `Order of the Azure Shield` (5), `Kerbog Khan` (4), `Huge Green Dragon` (4).

### weak-evidence claims
- Weak-confidence hotspot ranking (marker-count scan) now shows additional session files needing cautious reconciliation:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (16)
  - `sessions/Session 1 - First Visit to the Ruins of Arden Vul.md` (12)
  - `lore/recording-notes/Recording 2025-04-04.md` (9)
  - `sessions/Session 8a - Never Trust a Scorpion.md` (8)
  - `sessions/Session 6 - Good Ghost, Bad Ghost.md` (8)
  - `sessions/Session 21 - The Library of Thoth.md` (8)
  - `sessions/Session 16 - Random Scorpion Teleport to the Hall of Judgment.md` (8)
- Reconciliation policy remains: transcript-derived additions from these pages default to **hold-for-review** without recap/canon corroboration.

### structure issues
- The duplicate landscape is now clearly **semantic rather than volumetric** (only 3 non-structural normalized-title clusters detected vault-wide).
- Broken-link/top-missing counts remain dominated by alias/session-link normalization gaps rather than clear absent-content gaps.
- `Arden.txt` appears as a repeated unresolved target (5 refs), indicating a likely path/artifact leakage into wiki links.

### suggested changes
1. Execute the three unambiguous duplicate reconciliations in one controlled pass (`Angry scary ghost`, `Irthuin`, `Magae`) with canonical stubs to preserve backlinks.
2. Build a small alias map for the new secondary unresolved set (`Obsidian Gates`, `Order of the Azure Shield`, `Kerbog Khan`, `Huge Green Dragon`) after the primary drift names.
3. Add a session-link normalizer rule for lettered session titles and long hyphenated names (especially Session 35 title variant).
4. Treat `Arden.txt` references as structural contamination; normalize/remove as a mechanical cleanup prior to further semantic QA.
5. Keep strict `hold-for-review` handling for claims sourced from the seven high-uncertainty files listed above.

---
## Batch Run — 2026-03-13 20:09 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Non-structural duplicate set is unchanged (still only 3 clusters):**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md` → **merge-into-existing**
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md` → **rename-to-canonical** (lore canon + NPC stub)
  - `npcs/Magae.md` ↔ `lore/Magae.md` → **rename-to-canonical** (lore canon + NPC stub)
- This stability suggests the remaining QA risk is mostly link corruption/alias drift, not discovery of new duplicate entities.

### naming drift
- Recurring unresolved names remain concentrated and stable:
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), `Larel` (7), `Sortian` (7).
- Session-title target drift persists in raw-target links (lettered/long-title sessions):
  - `Session 34a - Hunting the Thane` (9), `Session 42b - Neferet and the Wraiths` (7), `Session 34c - Burglary and Death` (7), `Session 35 - The Scepter - Flute of the Goblins` (6).
- Corruption-heavy path fragments continue to dominate missing-target counts (e.g., `locations/[[npcs/Arden`, `factions/Cult of [[npcs/Set`), indicating syntax drift is still the primary upstream issue.

### weak-evidence claims
- Weak-confidence marker scan (excluding intent to treat QA-note files as canon evidence) still flags early/mid campaign sessions as highest-risk sources:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (9)
  - `sessions/Session 16 - Random Scorpion Teleport to the Hall of Judgment.md` (7)
  - `sessions/Session 6 - Good Ghost, Bad Ghost.md` (6)
  - `sessions/Session 19 - The Pool of Donkey Ears.md` (5)
  - `sessions/Session 8a - Never Trust a Scorpion.md` (5)
- Claims sourced primarily from these pages should remain **hold-for-review** unless corroborated by cleaner recap/canon pages.

### structure issues
- **Malformed nested-link footprint increased slightly:** 153 files with nested/malformed wiki links this pass.
- Highest malformed-link density:
  - `locations/Great Cavern.md` (50)
  - `pcs/Ioannes Grammatikos Byzantios.md` (33)
  - `npcs/Thoth.md` (32)
  - `pcs/Vallium Halcyon.md` (31)
  - `sessions/Session 32 - Fast Exploration.md` (27)
- Missing-target leaderboard remains dominated by malformed fragments rather than clear absent canonical pages, confirming structure cleanup should precede semantic reconciliation.

### suggested changes
1. Keep semantic reconciliation queue focused on the 3 stable duplicate clusters; defer broader merge actions until link-shape cleanup reduces false matches.
2. Prioritize mechanical repair rules for top corruption signatures (`locations/[[npcs/...`, `factions/...[[npcs/...`, double-embedded NPC names) before next entity-level QA pass.
3. Add scanner-level exclusions for `vault/notes/*` in weak-evidence tallies so QA report text does not self-inflate uncertainty metrics.
4. Build a targeted alias table for persistent unresolved names (`Archontean`, `Thorcin`, `Ioannes`, `The Living Wheelbarrow`, `Vael`, `Larel`, `Sortian`) and apply during reconciliation classification.
5. After structural normalization, rerun duplicate detection and promote only unambiguous low-risk merges/renames.

---
## Batch Run — 2026-03-13 20:19 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Duplicate set remains tight and unchanged (3 non-structural clusters):**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md` → **merge-into-existing**
  - `npcs/Magae.md` ↔ `lore/Magae.md` → **rename-to-canonical** (lore-canonical + NPC stub)
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md` → **rename-to-canonical** (lore-canonical + NPC stub)
- No additional semantic duplicate clusters surfaced in this pass, reinforcing that current QA drag is mostly structural/link-related.

### naming drift
- High-frequency unresolved/broken targets still show strong naming/taxonomy drift:
  - `Arden Vul` (128), `Gosterwick` (117), `Cult of Set` (43), `Thoth` (35), `Wicktrimmer` (33), `Rarities Factor` (31), `Archontean Empire` (26), `Archontean` (20).
- Corrupted path-shaped targets continue to dominate top misses and mask real entity reconciliation:
  - `locations/[[npcs/Arden.md` (431)
  - `factions/Cult of [[npcs/Set.md` (110)
  - `npcs/Merenuithiel Lacrymosa [[npcs/Merenuithiel Lacrymosa Armaris.md` (102)
- Drift note: some unresolved names (e.g., `Arden Vul`, `Cult of Set`, `Thoth`) likely represent alias/namespace choices rather than absent content; they should be normalized through alias mapping rather than treated as new-entity proposals.

### weak-evidence claims
- Highest uncertainty-marker files this pass:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (12)
  - `sessions/Session 1 - First Visit to the Ruins of Arden Vul.md` (9)
  - `sessions/Session 16 - Random Scorpion Teleport to the Hall of Judgment.md` (8)
  - `sessions/Session 6 - Good Ghost, Bad Ghost.md` (7)
  - `sessions/Session 25 - Looking for the Back Door to the Forum of Set.md` (7)
  - `sessions/Session 28 - Teleport Rugs and Baboons.md` (7)
- Reconciliation classification guidance unchanged: transcript-derived claims from these files default to **hold-for-review** unless corroborated by stronger recap/canon pages.

### structure issues
- **Malformed nested-link footprint remains severe:** 151 files contain malformed wiki-link targets.
- Highest malformed-link density currently:
  - `locations/Great Cavern.md` (50)
  - `pcs/Ioannes Grammatikos Byzantios.md` (33)
  - `pcs/Vallium Halcyon.md` (31)
  - `npcs/Thoth.md` (27)
  - `sessions/Session 32 - Fast Exploration.md` (27)
- Structural corruption is still large enough to produce misleading missing-target leaderboards, so deeper semantic reconciliation continues to be partially blocked by syntax noise.

### suggested changes
1. Keep duplicate reconciliation queue constrained to the 3 stable, high-confidence clusters; avoid broad merge sweeps until malformed-link cleanup reduces false matches.
2. Prioritize mechanical cleanup for top corruption signatures (`locations/[[npcs/...`, `factions/...[[npcs/...`, double-embedded proper names) as the next low-risk/high-impact maintenance pass.
3. Add/expand alias mappings for high-volume unresolved canonical concepts (`Arden Vul`, `Cult of Set`, `Thoth`, `Archontean/Archontean Empire`) to reduce naming-drift false positives.
4. Maintain strict **hold-for-review** on claims sourced mainly from the six highest-uncertainty session files listed above.
5. After link-shape normalization, rerun vault-wide QA and only then promote additional low-risk semantic renames/merges.

---
## Batch Run — 2026-03-13 20:29 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Semantic duplicate set remains exactly three clusters (stable for 50+ minutes):**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md` → **merge-into-existing**
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md` → **rename-to-canonical** (lore canonical + NPC stub)
  - `npcs/Magae.md` ↔ `lore/Magae.md` → **rename-to-canonical** (lore canonical + NPC stub)
- **Near-duplicate title drift candidate discovered in lore namespace:**
  - `lore/The Archontean Calendar.md`
  - `lore/Arden Vul The Archontean Calendar.md`
  - Classification: **hold-for-review** pending content diff to determine whether one is canonical and the other should become redirect/stub.

### naming drift
- Top unresolved targets remain dominated by malformed path fragments and recurring alias gaps:
  - `locations/[[npcs/Arden.md` (431), `factions/Cult of [[npcs/Set.md` (110), `npcs/Merenuithiel Lacrymosa [[npcs/Merenuithiel Lacrymosa Armaris.md` (102)
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), `Larel` (7), `Sortian` (7)
- Session naming normalization drift still active:
  - `Session 34a - Hunting the Thane` (9)
  - `Session 42b - Neferet and the Wraiths` (7)
  - `Session 34c - Burglary and Death` (7)
  - `Session 35 - The Scepter - Flute of the Goblins` (6)

### weak-evidence claims
- No new high-confidence canon evidence surfaced this batch to promote previously held transcript-derived claims.
- Prior guidance stands: unresolved-name claims sourced from high-uncertainty session pages should remain **hold-for-review** unless corroborated by cleaner recap/canon entries.

### structure issues
- **Malformed nested-link count remains extremely high:** 803 malformed targets detected this batch scan.
- Structural corruption still overwhelms semantic signal; most “missing entity” counts are syntax artifacts, not genuine absent pages.
- This continues to block reliable expansion of duplicate/alias reconciliation beyond the three stable clusters.

### suggested changes
1. Keep semantic reconciliation scope constrained to the three stable duplicate clusters until malformed-link counts materially decline.
2. Add a targeted reconciliation check for the Archontean Calendar pair to determine canonical title and prevent future drift.
3. Run mechanical repairs first for the top corruption signatures (`locations/[[npcs/...`, `factions/...[[npcs/...`, and doubled proper-name embeddings).
4. Preserve strict **hold-for-review** on transcript-derived claims tied to unresolved alias tokens until corroboration is found.
5. Rerun vault-wide QA after syntax normalization and then promote only unambiguous low-risk merges/renames.

---
## Batch Run — 2026-03-13 20:39 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Semantic duplicate set remains stable (3 non-structural clusters):**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md` → **merge-into-existing**
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md` → **rename-to-canonical** (lore canonical + NPC stub)
  - `npcs/Magae.md` ↔ `lore/Magae.md` → **rename-to-canonical** (lore canonical + NPC stub)
- **Archontean Calendar pair remains a likely duplicate/drift split:**
  - `lore/The Archontean Calendar.md` (clean canonical-style page)
  - `lore/Arden Vul The Archontean Calendar.md` (contains malformed nested links in title/body)
  - Decision label: **hold-for-review** pending controlled merge to avoid propagating malformed link syntax.

### naming drift
- Recurring unresolved targets (top this pass) remain concentrated:
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), `Lacrymosa` (7), `Larel` (7), `Sortian` (7).
- Session-title drift persists for lettered/long session names:
  - `Session 34a - Hunting the Thane` (9)
  - `Session 42b - Neferet and the Wraiths` (7)
  - `Session 34c - Burglary and Death` (7)
  - `Session 35 - The Scepter - Flute of the Goblins` (6)
- Additional unresolved-name candidates surfaced again: `Obsidian Gates` (6), `Order of the Azure Shield` (5), `Kerbog Khan` (4), `Huge Green Dragon` (4).

### weak-evidence claims
- Highest uncertainty-marker files this pass:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (16)
  - `sessions/Session 1 - First Visit to the Ruins of Arden Vul.md` (12)
  - `lore/recording-notes/Recording 2025-04-04.md` (9)
  - `sessions/Session 21 - The Library of Thoth.md` (8)
  - `sessions/Session 16 - Random Scorpion Teleport to the Hall of Judgment.md` (8)
  - `sessions/Session 6 - Good Ghost, Bad Ghost.md` (8)
  - `sessions/Session 8a - Never Trust a Scorpion.md` (8)
- Reconciliation policy remains: transcript-derived additions from these sources default to **hold-for-review** unless corroborated by recap/canon pages.

### structure issues
- **Malformed nested-link footprint remains severe:** 784 malformed targets across 149 files this pass.
- Highest malformed-link density files:
  - `locations/Great Cavern.md` (50)
  - `pcs/Ioannes Grammatikos Byzantios.md` (33)
  - `pcs/Vallium Halcyon.md` (31)
  - `sessions/Session 32 - Fast Exploration.md` (27)
  - `npcs/Thoth.md` (26)
- Structural corruption still dominates broken-link signal, limiting confidence for broader semantic reconciliation.

### suggested changes
1. Keep semantic reconciliation limited to the 3 stable duplicate clusters until malformed-link counts materially drop.
2. Triage `lore/The Archontean Calendar.md` vs `lore/Arden Vul The Archontean Calendar.md` as a targeted merge candidate, preferring the cleaner canonical page and preserving unique facts.
3. Prioritize mechanical cleanup of highest-impact malformed-link files (`Great Cavern`, `Ioannes Grammatikos Byzantios`, `Vallium Halcyon`, `Session 32`, `Thoth`).
4. Build/expand alias mappings for persistent unresolved names (`Archontean`, `Thorcin`, `Ioannes`, `The Living Wheelbarrow`, `Vael`, `Lacrymosa`, `Larel`, `Sortian`).
5. Maintain strict **hold-for-review** treatment for claims sourced from top uncertainty files until corroboration exists.

---
## Batch Run — 2026-03-13 20:49 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Non-structural duplicate set remains exactly 3 clusters (stable):**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md` → **merge-into-existing**
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md` → **rename-to-canonical** (prefer lore-canonical + NPC stub)
  - `npcs/Magae.md` ↔ `lore/Magae.md` → **rename-to-canonical** (prefer lore-canonical + NPC stub)
- No newly surfaced semantic duplicate entities this batch.

### naming drift
- Top unresolved target names are still concentrated and unchanged:
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), `Lacrymosa` (7), `Larel` (7), `Sortian` (7).
- Session-title normalization drift persists (raw title targets instead of exact canonical filenames):
  - `Session 34a - Hunting the Thane` (9)
  - `Session 42b - Neferet and the Wraiths` (7)
  - `Session 34c - Burglary and Death` (7)
  - `Session 35 - The Scepter - Flute of the Goblins` (6)

### weak-evidence claims
- High-uncertainty source files this pass:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (16)
  - `sessions/Session 1 - First Visit to the Ruins of Arden Vul.md` (12)
  - `lore/recording-notes/Recording 2025-04-04.md` (9)
  - `sessions/Session 21 - The Library of Thoth.md` (8)
  - `sessions/Session 16 - Random Scorpion Teleport to the Hall of Judgment.md` (8)
  - `sessions/Session 6 - Good Ghost, Bad Ghost.md` (8)
  - `sessions/Session 8a - Never Trust a Scorpion.md` (8)
- Any transcript-derived additions sourced primarily from these files should remain **hold-for-review** unless corroborated by recap/canon pages.

### structure issues
- **Malformed nested-link footprint remains severe and flat:** 800 malformed targets across 152 files this pass.
- Highest malformed-link density files currently:
  - `locations/Great Cavern.md` (50)
  - `pcs/Ioannes Grammatikos Byzantios.md` (33)
  - `pcs/Vallium Halcyon.md` (31)
  - `npcs/Thoth.md` (27)
  - `sessions/Session 32 - Fast Exploration.md` (27)
  - `sessions/Session 26 - The Scouring of the Shire.md` (26)
  - `sessions/Session 24b - The Set Cult Strikes Back, Larel's Stuff, and the Hall of Shrines.md` (25)
  - `pcs/Vaelethron 'Vael' Sunshadow.md` (22)

### suggested changes
1. Keep semantic reconciliation constrained to the 3 stable duplicate clusters until malformed-link counts decline materially.
2. Prioritize mechanical cleanup in the eight highest-density malformed-link files to maximize signal gain for the next QA pass.
3. Add alias mappings for persistent unresolved names (`Archontean`, `Thorcin`, `Ioannes`, `The Living Wheelbarrow`, `Vael`, `Lacrymosa`, `Larel`, `Sortian`) before broad merge decisions.
4. Add a session-title linker normalizer for letter-suffixed sessions and long hyphenated titles to reduce recurring broken-target noise.
5. Maintain strict **hold-for-review** for claims sourced from the listed high-uncertainty files until corroboration is available.

---
## Batch Run — 2026-03-13 20:59 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Semantic duplicate set remains stable (3 confirmed clusters):**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md` → **merge-into-existing**
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md` → **rename-to-canonical** (prefer lore page + NPC stub)
  - `npcs/Magae.md` ↔ `lore/Magae.md` → **rename-to-canonical** (prefer lore page + NPC stub)
- **Archontean Calendar split now looks like a high-confidence duplicate pair after content check:**
  - `lore/The Archontean Calendar.md`
  - `lore/Arden Vul The Archontean Calendar.md`
  - The second page appears transcript-derived and malformed-link contaminated; recommendation remains **merge-into-existing** with only unique GM-note details retained.

### naming drift
- Top unresolved targets continue to cluster around the same names/titles:
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), `Lacrymosa` (7), `Larel` (7), `Sortian` (7).
- Session-title references are still drifting as raw titles rather than canonical filenames:
  - `Session 34a - Hunting the Thane` (9)
  - `Session 42b - Neferet and the Wraiths` (7)
  - `Session 34c - Burglary and Death` (7)
  - `Session 35 - The Scepter - Flute of the Goblins` (6)

### weak-evidence claims
- Highest uncertainty-marker files this pass:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (9)
  - `sessions/Session 16 - Random Scorpion Teleport to the Hall of Judgment.md` (7)
  - `sessions/Session 6 - Good Ghost, Bad Ghost.md` (6)
  - `sessions/Session 8a - Never Trust a Scorpion.md` (5)
  - `sessions/Session 31 - I Want to Believe.md` (5)
  - `sessions/Session 25 - Looking for the Back Door to the Forum of Set.md` (5)
- Keep transcript-derived additions from these pages at **hold-for-review** unless recap/canon corroborates.

### structure issues
- **Malformed nested-link footprint remains severe:** 808 malformed targets across 153 files.
- Highest-density files this pass:
  - `locations/Great Cavern.md` (50)
  - `pcs/Ioannes Grammatikos Byzantios.md` (33)
  - `pcs/Vallium Halcyon.md` (31)
  - `npcs/Thoth.md` (31)
  - `sessions/Session 32 - Fast Exploration.md` (27)
  - `sessions/Session 26 - The Scouring of the Shire.md` (26)

### suggested changes
1. Keep semantic reconciliation queue focused on the 3 stable duplicate clusters plus the Archontean Calendar pair.
2. Perform targeted mechanical cleanup first in the six highest malformed-link-density files to increase signal quality.
3. Add alias mappings for persistent unresolved names (`Archontean`, `Thorcin`, `Ioannes`, `The Living Wheelbarrow`, `Vael`, `Lacrymosa`, `Larel`, `Sortian`).
4. Add session-title normalization for letter-suffixed and long hyphenated session names to reduce recurring drift noise.
5. Continue strict **hold-for-review** handling for transcript-heavy claims until corroborated by cleaner canon/recap pages.

---
## Batch Run — 2026-03-13 21:09 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Semantic duplicate set remains stable (3 confirmed clusters):**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md` → **merge-into-existing**
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md` → **rename-to-canonical** (prefer lore page + NPC stub)
  - `npcs/Magae.md` ↔ `lore/Magae.md` → **rename-to-canonical** (prefer lore page + NPC stub)
- No additional non-structural duplicate clusters surfaced in this pass.

### naming drift
- Top unresolved canonical-name drift signals remain concentrated:
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12).
- Missing-target leaderboard remains dominated by malformed-path fragments rather than true missing entities:
  - `locations/[[npcs/Arden.md` (428)
  - `factions/Cult of [[npcs/Set.md` (110)
  - `npcs/Merenuithiel Lacrymosa [[npcs/Merenuithiel Lacrymosa Armaris.md` (102)
- Additional drift indicator: `The Archontean Calendar.md` appears as unresolved target (23 refs), consistent with title/namespace inconsistency around Archontean Calendar pages.

### weak-evidence claims
- Highest uncertainty-marker sources this pass:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (12)
  - `lore/recording-notes/Recording 2025-04-04.md` (9)
  - `sessions/Session 1 - First Visit to the Ruins of Arden Vul.md` (8)
  - `sessions/Session 8a - Never Trust a Scorpion.md` (7)
  - `sessions/Session 6 - Good Ghost, Bad Ghost.md` (7)
  - `sessions/Session 16 - Random Scorpion Teleport to the Hall of Judgment.md` (7)
- Claims sourced primarily from these pages should remain **hold-for-review** unless corroborated by recap/canon pages.

### structure issues
- **Malformed nested-link footprint remains severe:** 803 malformed targets across 151 files.
- Highest malformed-link density files:
  - `locations/Great Cavern.md` (50)
  - `pcs/Ioannes Grammatikos Byzantios.md` (33)
  - `pcs/Vallium Halcyon.md` (31)
  - `npcs/Thoth.md` (31)
  - `sessions/Session 32 - Fast Exploration.md` (27)
  - `sessions/Session 26 - The Scouring of the Shire.md` (26)
  - `sessions/Session 24b - The Set Cult Strikes Back, Larel's Stuff, and the Hall of Shrines.md` (25)
  - `pcs/Vaelethron 'Vael' Sunshadow.md` (22)

### suggested changes
1. Keep semantic reconciliation queue constrained to the 3 stable duplicate clusters until malformed-link counts materially decline.
2. Prioritize mechanical cleanup for top malformed signatures (`locations/[[npcs/...`, `factions/...[[npcs/...`, doubled proper-name embeddings) before broader semantic merges.
3. Add alias mappings for recurring unresolved names (`Archontean`, `Thorcin`, `Ioannes`, `The Living Wheelbarrow`) to reduce naming-drift false positives.
4. Triage Archontean Calendar naming split as a focused reconciliation item to stabilize `The Archontean Calendar` link target behavior.
5. Maintain strict **hold-for-review** treatment for claims sourced from the listed high-uncertainty files until corroboration is available.

---
## Batch Run — 2026-03-13 21:19 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Non-structural duplicate set expanded to 5 clusters this pass:**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md` → **merge-into-existing**
  - `monsters/Flying Monkey Statue (Huge Ears).md` ↔ `monsters/Flying Monkey Statue (Huge Eyes).md` → **merge-into-existing** (family-page model)
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md` → **rename-to-canonical** (prefer `lore/*`)
  - `npcs/Magae.md` ↔ `lore/Magae.md` → **rename-to-canonical** (prefer `lore/*`)
  - `lore/recording-notes/Recording 2025-03-07.md` ↔ `lore/recording-notes/Recording 2025-03-07 (diarized test).md` → **hold-for-review** (test artifact vs canon source; likely drop/archive test file)

### naming drift
- **Top unresolved targets remain highly stable**, indicating alias/index debt more than new-content growth:
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), `Larel` (7), `Sortian` (7), `Thothian` (6).
- **Session link normalization drift persists** via raw path-style targets instead of exact canonical links:
  - `sessions/Session 34a - Hunting the Thane` (9)
  - `sessions/Session 42b - Neferet and the Wraiths` (7)
  - `sessions/Session 34c - Burglary and Death` (7)
  - `sessions/Session 35 - The Scepter - Flute of the Goblins` (6)
- **Path contamination still present:** `RawFiles/Discord/Arden.txt` appears as a wiki-link target (5 refs), likely accidental ingestion from source artifacts.

### weak-evidence claims
- **Current highest weak-confidence concentration:**
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (13 markers)
  - `sessions/Session 1 - First Visit to the Ruins of Arden Vul.md` (9)
  - `sessions/Session 16 - Random Scorpion Teleport to the Hall of Judgment.md` (8)
- Claims derived primarily from these files should remain **hold-for-review** unless recap/canonical corroboration is present.

### structure issues
- **Malformed/nested-link footprint remains unchanged at scale:** 151 files currently contain malformed `[[...]]` target patterns.
- **Metadata hygiene issue persists:** 226 files still have duplicate frontmatter tag entries, creating avoidable QA/tooling noise.
- Duplicate/alias detection remains partially masked by syntax-level corruption and unnormalized session targets.

### suggested changes
1. Add `Recording 2025-03-07 (diarized test).md` to a QA/test-artifact quarantine rule and decide canonical retention (`keep canonical`, `archive/drop diarized test`).
2. Execute a mechanical pass for malformed nested wiki-links before the next semantic reconciliation cycle.
3. Run a safe dedupe for frontmatter `tags` arrays (mechanical, low-risk, high coverage).
4. Create alias/index entries for the stable unresolved set (`Archontean`, `Thorcin`, `Ioannes`, `The Living Wheelbarrow`, `Vael`, `Larel`, `Sortian`, `Thothian`).
5. Normalize session-title links to exact existing filenames (especially lettered sessions and long hyphenated titles).

---
## Batch Run — 2026-03-13 21:29 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Semantic duplicate set remains stable (3 high-confidence clusters):**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md`
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md`
  - `npcs/Magae.md` ↔ `lore/Magae.md`
- Decision labels unchanged from prior batches:
  - `Angry scary ghost` → **merge-into-existing**
  - `Irthuin` / `Magae` → **rename-to-canonical** (prefer `lore/*`) with legacy stubs.

### naming drift
- Drift/noise is still dominated by malformed nested targets rather than clean alias-only misses.
- Most frequent unresolved canonical-name candidates (non-path corruption):
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12).
- Largest unresolved target strings are clearly parser-hostile nested fragments, e.g.:
  - `locations/[[npcs/Arden` (431)
  - `factions/Cult of [[npcs/Set` (110)
  - `npcs/Merenuithiel Lacrymosa [[npcs/Merenuithiel Lacrymosa Armaris` (102)

### weak-evidence claims
- Current marker scan highlights uncertainty-heavy session notes:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (9)
  - `sessions/Session 16 - Random Scorpion Teleport to the Hall of Judgment.md` (7)
  - `sessions/Session 6 - Good Ghost, Bad Ghost.md` (6)
- `notes/Arden Vul Vault-Wide QA Batch Report.md` now appears in weak-evidence counts due to natural-language wording in the report itself; this is meta-noise, not canon risk.

### structure issues
- **Nested/malformed wiki-link footprint remains high and steady:** 807 malformed link targets across 151 files.
- Highest-density files this run:
  - `locations/Great Cavern.md` (50)
  - `pcs/Ioannes Grammatikos Byzantios.md` (33)
  - `pcs/Vallium Halcyon.md` (31)
  - `npcs/Thoth.md` (27)
  - `sessions/Session 32 - Fast Exploration.md` (27)
- Structural interpretation: syntax corruption is still the primary blocker; semantic reconciliation quality is capped until link-shape cleanup runs first.

### suggested changes
1. Keep semantic duplicate decisions queued (no change) and prioritize a **mechanical nested-link repair pass** first.
2. Add scanner exclusions for `vault/notes/*` when computing weak-evidence and broken-link leaderboards to reduce self-generated report noise.
3. After mechanical cleanup, rerun reconciliation and then execute unambiguous low-risk merges in this order:
   - `Angry scary ghost` merge
   - `Irthuin` canonicalization to `lore/`
   - `Magae` canonicalization to `lore/`
4. Add/confirm alias mappings for top clean unresolved names (`Archontean`, `Thorcin`, `Ioannes`, `The Living Wheelbarrow`) once malformed-target noise is reduced.


---
## Batch Run — 2026-03-13 21:39 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Semantic duplicate cluster remains unchanged and high-confidence:**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md`
  - Decision label: **merge-into-existing**.
- **Cross-taxonomy canonicalization candidates remain stable:**
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md`
  - `npcs/Magae.md` ↔ `lore/Magae.md`
  - Decision label: **rename-to-canonical** (prefer `lore/*` canon + legacy stubs).
- No new non-structural same-title duplicates were detected in this batch.

### naming drift
- Top clean unresolved target names (excluding malformed nested targets) are unchanged:
  - `Archontean` (20), `Thorcin` (18), `Ioannes` (16), `The Living Wheelbarrow` (12), `Vael` (8), `Larel` (7), `Sortian` (7).
- Session-title normalization drift remains active:
  - `sessions/Session 34a - Hunting the Thane` (9)
  - `sessions/Session 42b - Neferet and the Wraiths` (7)
  - `sessions/Session 34c - Burglary and Death` (7)
  - `sessions/Session 35 - The Scepter - Flute of the Goblins` (6)
- `npcs/Lacrymosa` still appears as an unresolved path-style target (7), indicating a canonical path/name mismatch rather than a likely new entity.

### weak-evidence claims
- With `vault/notes/*` excluded from evidence scoring, uncertainty hotspots are still concentrated in session recaps:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (9 markers)
  - `sessions/Session 16 - Random Scorpion Teleport to the Hall of Judgment.md` (7)
  - `sessions/Session 6 - Good Ghost, Bad Ghost.md` (6)
  - plus a tier of files at 5 markers (`Session 1`, `8a`, `19`, `25`, `31`).
- Reconciliation policy recommendation unchanged: transcript-heavy claims in these files remain **hold-for-review** unless corroborated by stronger canonical recap evidence.

### structure issues
- **Malformed nested-link footprint remains effectively flat:** 795 malformed targets across 150 files (excluding `vault/notes/*`).
- Highest malformed-link density this run:
  - `locations/Great Cavern.md` (50)
  - `pcs/Ioannes Grammatikos Byzantios.md` (33)
  - `pcs/Vallium Halcyon.md` (31)
  - `npcs/Thoth.md` (27)
  - `sessions/Session 32 - Fast Exploration.md` (27)
- Top malformed target fragments are still parser-hostile nested forms (`locations/[[npcs/Arden.md`, `factions/Cult of [[npcs/Set.md`, etc.), continuing to mask semantic QA signals.

### suggested changes
1. Continue to defer semantic merges until after mechanical nested-link repair; syntax noise remains the primary reconciliation blocker.
2. Keep the queued low-risk semantic actions in the same order after cleanup:
   - `Angry scary ghost` merge
   - `Irthuin` canonicalization to `lore/`
   - `Magae` canonicalization to `lore/`
3. Add explicit alias/path normalization for top unresolved clean names (`Archontean`, `Thorcin`, `Ioannes`, `The Living Wheelbarrow`, `Vael`).
4. Run a dedicated session-link normalizer for lettered and long-title session pages (`34a/34c/35/42b`) to reduce recurring broken-link noise.
5. Keep `vault/notes/*` excluded from weak-evidence and malformed-link leaderboards to avoid report-induced metric drift.

---
## Batch Run — 2026-03-13 21:49 UTC (cron dd4fc190, analysis-only)

### duplicates/aliases
- **Semantic duplicate clusters remain unchanged (3 total):**
  - `npcs/Angry scary ghost.md` ↔ `monsters/Angry scary ghost.md` → **merge-into-existing**
  - `npcs/Irthuin.md` ↔ `lore/Irthuin.md` → **rename-to-canonical** (`lore/*` preferred)
  - `npcs/Magae.md` ↔ `lore/Magae.md` → **rename-to-canonical** (`lore/*` preferred)
- No new non-structural same-title duplicates surfaced in this batch.

### naming drift
- Top unresolved clean-name targets (still recurring):
  - `Arden Vul` (128), `Gosterwick` (117), `Cult of Set` (43), `Archontean Empire` (26), `Archontean` (20), `Narsileon` (19).
- Long-form session-title targets continue to appear as raw unresolved links (e.g., `Session 8b and 9 - Muirasso's Tomb and the Broken Head` at 39 refs), suggesting title/alias normalization drift rather than net-new entity creation.
- Persistent entity-name drift remains visible around known canonical PCs/NPCs (`Wicktrimmer`, `Demma`, `Thoth`) due to mixed link styles and malformed nested targets.

### weak-evidence claims
- Current uncertainty hotspot ranking is stable:
  - `sessions/Session 2 - Halfling Rent-Seekers.md` (16 markers)
  - `sessions/Session 1 - First Visit to the Ruins of Arden Vul.md` (12)
  - `lore/recording-notes/Recording 2025-04-04.md` (9)
  - `sessions/Session 8a - Never Trust a Scorpion.md` (8)
  - `sessions/Session 6 - Good Ghost, Bad Ghost.md` (8)
- Reconciliation policy remains: transcript-heavy claims from these files should default to **hold-for-review** unless corroborated in stronger recap/canonical sources.

### structure issues
- **Malformed nested-link surface remains the dominant blocker:** 793 malformed targets across 149 files (excluding `vault/notes/*`).
- Highest malformed-link density this batch:
  - `locations/Great Cavern.md` (50)
  - `pcs/Ioannes Grammatikos Byzantios.md` (33)
  - `pcs/Vallium Halcyon.md` (31)
  - `npcs/Thoth.md` (27)
  - `sessions/Session 32 - Fast Exploration.md` (27)
- Most frequent malformed target fragments are still parser-hostile nested forms:
  - `locations/[[npcs/Arden.md` (428)
  - `factions/Cult of [[npcs/Set.md` (110)
  - `npcs/Merenuithiel Lacrymosa [[npcs/Merenuithiel Lacrymosa Armaris.md` (102)

### suggested changes
1. Continue prioritizing **mechanical nested-link repair** before additional semantic reconciliation (signal quality still syntax-capped).
2. Keep the 3 queued semantic actions unchanged until after structural cleanup (`Angry scary ghost`, `Irthuin`, `Magae`).
3. Add alias/page normalization for the highest recurring unresolved clean targets (`Arden Vul`, `Gosterwick`, `Cult of Set`, `Archontean Empire`) to reduce false broken-link pressure.
4. Add session-title alias normalization for multi-session/compound titles (starting with `Session 8b and 9 - Muirasso's Tomb and the Broken Head`).
5. Preserve strict **hold-for-review** handling for claims sourced from the top uncertainty files listed above.
