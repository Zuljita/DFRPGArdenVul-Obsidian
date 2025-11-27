# IAC/ACE Workflow

This repository uses a two-pass content workflow:

1) Identifying Article Candidates (IAC)
   - Goal: From session text, identify canonical entities that should have articles.
   - Current Scope (2025-11): NPCs, Factions, and Locations. Items are intentionally excluded for now due to high noise; we'll do a separate "Unique Items" pass after IAC/ACE is complete.
   - Inputs: Session markdown files (chunked as needed).
   - Tools:
     - Local LLM (`scripts/local_llm_client.py`) with the Candidate Extraction prompt.
     - Fuzzy/alias mapper that checks existing files + frontmatter aliases.
   - Process:
     - Run LLM extraction per session using the prompt:
       "From the text, list entity candidates grouped by type (NPC, Location, Faction). Title Case; exclude generics and scaffolding words; do not invent; no mapping. Output concise bullets only."
     - Map each candidate to an existing canonical article by filename or frontmatter `aliases`.
     - Use fuzzy matching to catch near-misses/misspellings; prefer adding an alias to the canonical page rather than creating a new file.
      - If truly new, create a stub in the appropriate folder with 1–2 line summary and an Appears In entry for the session. For Locations, prefer creating only when the name is proper and specific (not room descriptors like “Small Cave”, “Shaft”, “Octagonal Room”). Otherwise, defer for manual triage.
   - Validation:
     - Run `scripts/check_wikilinks.py` on changed paths.
     - Log results in `CLEANUP_JOURNAL.md`.

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
