---
tags:
  - note
  - qa-report
---

# Arden Vul QA Reconciliation Report

Date: 2026-03-13
Scope: Transcript-derived proposed entries and related link targets.

## Decisions

### 1) `locations/Newmarket.md`
- Candidate canonical match: `locations/Newmarket.md`
- Decision: **merge-into-existing**
- Rationale:
  - Same place semantics (town south of Gosterwick, ~3 days)
  - Existing canonical page already established as Newmarket
  - Avoid split-link drift
- Action taken:
  - Merged Session 0-style facts into `Newmarket.md` timeline/notes context via linked session facts
  - Repointed links from `New Market` -> `Newmarket`
  - Removed proposed duplicate page `locations/Newmarket.md`

### 2) `locations/Narsileon.md`
- Candidate canonical match: `locations/Narsileon.md`
- Decision: **rename-to-canonical** (implemented as merge)
- Rationale:
  - High-probability transcription/romanization drift
  - Existing canonical city page `Narsileon.md`
- Action taken:
  - Repointed links from `Narsilian` -> `Narsileon`
  - Removed proposed duplicate page `locations/Narsileon.md`

### 3) `sessions/Session 0 - Campaign Setup and Character Q&A.md`
- Candidate canonical match: none (new useful pre-campaign source note)
- Decision: **keep**
- Rationale:
  - Distinct pre-campaign metadata and expectations
  - Useful provenance from recording note
- Action taken:
  - Kept page, updated place links to canonical location names

### 4) `items/Silver ID Card.md`
- Candidate canonical match: none exact (`Yellow Rudishva Identity Plaque.md` is different)
- Decision: **hold-for-review**
- Rationale:
  - Plaque/card naming could be item drift
  - Needs cross-check with recap/blog phrasing before final canonical item decision
- Action taken:
  - Left page in place, flagged for manual naming confirmation

### 5) Recording notes corpus `lore/recording-notes/*`
- Candidate canonical match: source-layer only
- Decision: **keep**
- Rationale:
  - Provides traceable provenance
  - Useful for later spot-audit and conflict checks
- Action taken:
  - Kept corpus and canonicalized links where needed

## Follow-up Queue
- Verify whether `Silver ID Card` should be merged into an existing identity-plaque/card item line.
- Run one more pass for near-duplicate NPC/item naming variants introduced by transcription.

## 2026-03-13 23:00 UTC — Publish hardening 2/5 unresolved-link triage
Scope: top unresolved clean-name targets (`Vael`, `Ioannes`, `Larel`, `Sortian`) after recent repair pass.

### Decisions

#### A) `Vael`
- Candidate canonical match: `pcs/Vaelethron 'Vael' Sunshadow.md`
- Decision: **rename-to-canonical** (implemented via alias stub)
- Rationale:
  - Existing canonical PC page already present
  - All unresolved instances were bare-name links
- Action taken:
  - Added `pcs/Vael.md` stub/alias page pointing to `pcs/Vaelethron 'Vael' Sunshadow.md`

#### B) `Ioannes`
- Candidate canonical match: `pcs/Ioannes Grammatikos Byzantios.md`
- Decision: **rename-to-canonical** (implemented via alias stub)
- Rationale:
  - Existing canonical PC page already present
  - Repeated unresolved references were short-name links
- Action taken:
  - Added `pcs/Ioannes.md` stub/alias page pointing to `pcs/Ioannes Grammatikos Byzantios.md`

#### C) `Larel`
- Candidate canonical match: `npcs/Larel One-Eye.md`
- Decision: **rename-to-canonical** (implemented via alias stub)
- Rationale:
  - Existing canonical NPC page already present
  - Bare-name references appear to refer to the same named figure
- Action taken:
  - Added `npcs/Larel.md` stub/alias page pointing to `npcs/Larel One-Eye.md`

#### D) `Sortian`
- Candidate canonical match: `factions/Sortians.md`
- Decision: **merge-into-existing** (implemented via singular alias stub)
- Rationale:
  - Existing canonical faction page already present (`Sortians` plural)
  - Unresolved references used singular demonym form (`Sortian`)
- Action taken:
  - Added `factions/Sortian.md` stub/alias page pointing to `factions/Sortians.md`

### Result snapshot
- Resolved unresolved counts for top targets:
  - `Vael`: 8 → 0
  - `Ioannes`: 15 → 0
  - `Larel`: 7 → 0
  - `Sortian`: 7 → 0
- Total top-target unresolved reductions: **37 resolved**

### Remaining blockers (outside this scoped triage)
- High-volume malformed nested targets still dominate unresolved QA signal (e.g., nested `[[...[[...]]...]]` fragments).
- Session-title canonicalization drift remains for several lettered/long-title session pages.

## 2026-03-13 23:15 UTC — Publish hardening 3/5 canonical+alias lock (high-drift concepts)
Scope: stabilize concept-level canon for `Archontean`, `Thorcin`, `Thothian`; keep one canonical concept page and downgrade duplicate concept pages to alias stubs.

### Decisions

#### A) `Archontean`
- Canonical page: `lore/Archontean.md`
- Decision: **keep**
- Rationale:
  - Concept term (culture/civilization adjective), not a standalone faction page title
  - Best fit is lore namespace for concept-level canon
- Action taken:
  - Kept `lore/Archontean.md` as canonical concept page
  - Corrected related link to existing faction page `factions/Archontean Empire.md`

#### B) `Thorcin` / `Thorcins`
- Canonical page: `lore/Thorcin.md`
- Duplicate page: `factions/Thorcins.md`
- Decision: **merge-into-existing** (implemented as alias stub conversion)
- Rationale:
  - `Thorcin` drift appears as concept/culture token across the vault
  - Prior full `factions/Thorcins.md` content overlapped concept-level scope
- Action taken:
  - Converted `factions/Thorcins.md` from full page to lightweight alias stub pointing to `lore/Thorcin.md`
  - Preserved backlinks by keeping legacy path in place with redirect/stub content

#### C) `Thothian`
- Canonical page: `lore/Thothian.md`
- Decision: **keep**
- Rationale:
  - Concept/tradition term (not a distinct NPC/faction title)
  - Lore namespace is canonical for recurring tradition terminology
- Action taken:
  - Kept `lore/Thothian.md` as canonical concept page
  - Normalized related calendar link to canonical title target (`[[The Archontean Calendar]]`)

### Result snapshot
- Canonical concept pages locked: **3** (`Archontean`, `Thorcin`, `Thothian`)
- Duplicate full pages converted to alias stubs: **1** (`factions/Thorcins.md`)
- Backlink-preserving legacy paths retained: **1** (`factions/Thorcins.md`)
