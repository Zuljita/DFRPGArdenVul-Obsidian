# IAC/ACE Workflow

This repository uses a two-pass content workflow:

1) Identifying Article Candidates (IAC)
   - Goal: From session text, identify canonical entities that should have articles.
   - Current Scope: NPCs, Factions, and Locations. Items are intentionally excluded due to high noise; use `--kinds NPC,Location,Faction` (default).
   - Inputs: Full session or Discord Summary markdown files (no chunking — Gemma 4 26B has 262k context).
   - Tools:
     - Maintained path: `scripts/run_iac.py`, which calls `scripts/local_llm_client.py` with the Candidate Extraction prompt.
     - Fuzzy/alias mapper that checks existing files + frontmatter aliases.
     - `scripts/entity_curator.py` is older and noisier; use it only for exploratory/manual review.
   - Current local model target:
     - Endpoint: `http://100.76.165.94:1234`
     - Model: `google/gemma-4-26b-a4b`
     - Override with `LMSTUDIO_BASE_URL`, `LMSTUDIO_IAC_MODEL`, or CLI flags.
   - Process:
     - Run LLM extraction on the full file in a single call (no chunking).
     - Map each candidate to an existing canonical article by filename or frontmatter `aliases`.
     - Use fuzzy matching to catch near-misses/misspellings; prefer adding an alias to the canonical page rather than creating a new file.
     - If truly new, create a stub in the appropriate folder with 1–2 line summary and an Appears In entry. For Locations, prefer creating only when the name is proper and specific (not room descriptors). Otherwise, defer for manual triage.
   - Examples:
     - Session: `python3 scripts/run_iac.py --file “vault/sessions/Session 50 - The Iron Circlet of Ghanor.md” --dry-run --kinds NPC,Location,Faction`
     - Discord digest: `python3 scripts/run_iac.py --digest “vault/notes/Discord Summary 2026-W11.md” --dry-run --kinds NPC,Location,Faction`
     - All digests: `python3 scripts/run_iac.py --all-digests --dry-run --kinds NPC,Location,Faction`
   - Validation:
     - Run `scripts/check_wikilinks.py` on changed paths.
     - Log results in `CLEANUP_JOURNAL.md`.

3) Discord Digest → Session Linking
   - Goal: Add a “Discord Discussions” bullet to each session's `## Session Navigation` footer,
     linking to the weekly Discord summaries that cover the period between that session and the one before it.
   - Tool: `scripts/link_sessions_to_digests.py` — uses Gemma to determine the mapping.
   - Pre-filter: sessions with a `source_url` month after the last available Discord summary are skipped automatically.
   - Examples:
     - Single session: `python3 scripts/link_sessions_to_digests.py --session “vault/sessions/Session 46 - ...” --dry-run`
     - All sessions: `python3 scripts/link_sessions_to_digests.py --all --dry-run`
   - Review the dry-run output before writing. Remove any links that seem off (e.g., sessions 48-49 may reference earlier weeks if newer summaries haven't been imported yet).
   - Re-run after importing new Discord summaries to fill coverage gaps.

2) Article Candidate Enrichment (ACE)
   - Goal: Enrich stubs with details from sessions and Discord notes, then use LLM for short summaries and notes/history sections.
   - Process:
     - Cross-reference candidates with mentions in sessions and external notes.
     - Add known facts deterministically; keep fiction minimal.
     - Use local LLM to draft short summaries/timelines; review and trim to facts.
   - Validation:
     - Re-run link checker and ensure no duplicate entities.

Items (Future Pass)
- Rationale: Freeform item extraction produces many false positives (generic loot, scenery, consumables). We will defer Items until after NPC/Faction IAC/ACE.
- Proposed approach:
  - Dedicated LLM prompt for “unique or named items only” (Wand/Ring/Tablet/’X of Y’), with a low cap per session.
  - Post-filter against patterns and existing `items/` to keep only strong candidates.
  - Enrich through ACE.

Best Practices
- Prefer merges into existing pages; use frontmatter `aliases` to capture variants.
- Avoid creating pages for generics, spells, or common monsters—demote to plain text unless named.
- Keep stubs concise and tagged; one concept per file.
