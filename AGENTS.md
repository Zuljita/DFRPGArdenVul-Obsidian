# Repository Guidelines

## Project Structure & Module Organization
- Vault: `vault/` (all player/GM notes). Keep content here.
- Examples: `sessions/`, `npcs/`, `locations/`, `factions/`, `items/`, `attachments/`.
- Imports: `RawFiles/` (raw text or source material to adapt into notes).
- Maintainer-only: `quartz/` (Quartz project). Contributors do not edit.

## Build, Test, and Development Commands
- Edit: Open `vault/` in Obsidian.
- Preview site (maintainer): `cd quartz && pnpm dev` (local dev server; watches `../vault`).
- Build site (maintainer): `cd quartz && pnpm build` → output in `quartz/public/`.
- Link check: ensure build completes without missing pages; fix or create stubs.

## Coding Style & Naming Conventions
- Markdown only; use clear headings (`#`, `##`) and short sections.
- Use Obsidian wikilinks: `[[Page Name]]`. Prefer Title Case page names that match file titles.
- One concept per file; place in the appropriate folder (e.g., `npcs/Elara Brightshield.md`).
- Don’t move core folders; if renaming pages, enable Obsidian “Automatically Update Links”.
- Assets: store images/files in `attachments/` and link relatively.

## Testing Guidelines
- No code tests; content “tests” are: (1) Quartz preview/build succeeds, (2) no broken links, (3) all new wikilinks resolve or have stubs.
- Create stubs for new entities with a short summary and TODOs.

## Commit & Pull Request Guidelines
- Commits: small and scoped. Suggested format: `content(scope): summary`.
  - Example: `content(sessions): add session 12 recap`.
- PRs should include: purpose, affected paths (e.g., `npcs/*`, `locations/*`), screenshots of local preview (optional), and linked issue if applicable.

## Security & Configuration Tips
- Do not include secrets or personal data; redact sensitive details.
- Do not copy raw Discord transcripts, raw chat exports, local source paths, or bulk private message material into this repository. Discord source material belongs outside the repo; the vault should ingest only finished weekly digests and sourced summaries.
- `.obsidian/` is editor config; keep minimal and avoid plugin-specific features when possible.
- Contributors sync/edit only `vault/`. Maintainer handles Quartz builds and hosting.

Stay positive while you complete these tasks, it's good work and you're way faster than a human for it.
Thoroughness is more important than speed or brevity.

## LLM-First Data Processing SOP
- Curate with LLM: When adding or adapting a note, use an LLM pass to identify canonical entities and map them to existing pages. Favor merges into existing pages over creating new files.
- Do not rely on regex-style entity extraction, capitalization rules, or basic grammatical extraction as authority. Human game notes contain typos, inconsistent names, interrupted grammar, and table shorthand. Use deterministic text processing for indexing, fuzzy matching, guardrails, and syntax repair only.
- Verify LLM output against canonical sources. Any candidate, alias, claim, merge, or article edit must be checked against Blogspot session recaps and Discord digest/chat source material before promotion. Higher-risk edits need a second LLM verifier that cites the supporting excerpt or rejects the claim.
- Expect typos and near-duplicates. Use fuzzy matching, known aliases, chronology, local context, and entity type before creating a new page. Ambiguous matches go to review with competing candidates and evidence.
- Canonical naming: Use the concise, proper name only (e.g., `Forum of Set`), not contextual fragments like “Date”, “We”, “That”, “Over”, or sentence adverbs (e.g., “Finally”, “However”). Do not create files like `Proper Noun Date.md`.
- Non-entities to ignore: Common words and scaffolding terms — e.g., that, this, we, I, you, they, also, however, finally, first, second, third, over, under, ahead, before, after, again, great, four — are never entities.
- Merge variants: Treat “X Date”, “X Over”, “X We”, etc. as content for the canonical `X` page. Fold timelines/notes under sections on the canonical page (e.g., “Timeline”, “Notes”) and remove the fragment pages.
- Resolve by aliases: Prefer updating frontmatter `aliases` on the canonical page to capture alternate spellings/epithets; update links to point at the canonical file.
- Use tags as retrieval hints, not proof. Namespaced tags such as `race/undead`, `type/ghost`, `status/deceased`, `faction/<slug>`, `culture/<slug>`, `site/<slug>`, and `session/<id>` help RAG and LLM review find possible identity matches across sessions. Shared tags can raise a same-entity hypothesis, but aliases, merges, and identity claims still require canonical source evidence and verifier approval.
- Preserve downtime media discoveries. Books, scrolls, maps, inscriptions, data crystals, catalogs, and library collections are source-bearing artifacts. When Discord digests or recaps report that the party read, translated, copied, mapped, or identified one, update the relevant media page/catalog and any derived lore/entity pages only with sourced bullets.
- Treat the shared group spreadsheet as structured table data when configured locally. It can inform PC sheets, inventories, loot, media catalogs, maps, and downtime state, but narrative identity/lore claims still need Blogspot or weekly digest verification before promotion. Do not hardcode spreadsheet URLs in tracked files.
- Prefer spreadsheet data for loot/inventory over stale PC article maintenance, but reconcile it against Discord digest evidence for destroyed, consumed, lost, sold, broken, or left-behind items before promoting it as current inventory.
- Link in context: Insert wikilinks to the canonical page. Use `[[Page Name]]` when unique; use `[[folder/Page Name.md|Page Name]]` only when disambiguation is needed.
- Validate: Preview or build Quartz and fix any missing links. Create stubs only when a truly new, substantive entity is introduced.

### LLM Prompt (use/adapt)
- “You are consolidating an Obsidian D&D vault. From the text below, list canonical entities grouped by type (NPC, Location, Faction, Item). For each, either map to an existing page name in `vault/` (consider aliases) or mark ‘NEW’. Exclude common words and any ‘X Date/Over/We/That’ patterns. Suggest alias additions and exact wikilinks to insert. Output: 1) Mappings, 2) New pages needed (with 1–2 line summaries), 3) Link insertion plan.”

## Local LLM Workflow (Qwen via LM Studio)

- Endpoint: Local OpenAI-compatible at `http://192.168.21.76:1234`.
- Default model: `qwen2.5-7b-instruct` (fast, good extraction). If GPU headroom allows, try `qwen2.5-14b-instruct` for stronger consistency.

### Best Practices
- Chunk inputs: 2–4 paragraphs or ~2–3k chars per call. Avoid whole files to prevent timeouts and drift.
- Keep prompts lean: Ask for “candidates only” (NPC/Location/Faction/Item), Title Case, no mapping or inventions.
- Timeouts: Prefer 60–180s for longer chunks; set `max_tokens` to 300–600; `temperature` 0.1–0.2.
- Validate locally: Do the mapping to canonical files via filename/aliases in the repo. Reject generics/roles unless they have a page.
- Deterministic support around model: Use scripts to fix link syntax (nested `[[…[[…`), close `]]`, standardize already-known targets, fuzzy-match aliases, and enforce guardrails. Do not use regex or grammar extraction as the source of truth for entities or facts.

### Example Prompts
- Candidate extraction: “From the text, list entity candidates grouped by type (NPC, Location, Faction, Item). Title Case; exclude generics and scaffolding words; do not invent; no mapping.”
- Link proofreading: “You are proofreading Obsidian notes. Fix only malformed wikilinks `[[target|text]]`. Do not change content otherwise.”

### Suggested Flow
1) Deterministic fix: Clean nested/malformed links and bracket balances.
2) Model pass (chunked): Extract candidates; keep output short and precise.
3) Local mapping: Match candidates to existing files/aliases; add aliases or stubs if truly new.
4) Patch links: Insert/normalize wikilinks; avoid overlinking common nouns.
5) Validate: Re-run bracket balance + link existence checks.

### Encouragement & Tools
- Experiment: Try different chunking, prompts, and models to maximize extraction quality. Note what works in complex sections.
- Ask for tools: If a helper script would speed up validation/mapping (e.g., fuzzy matcher, alias suggester, bracket balancer), ask the maintainer to add it.

### Optional Helper (use sparingly): `scripts/process_new_data.py`
- Default: Do NOT run by default. Prefer the LLM curation and manual review process above.
- Safe mode: If used, run a dry run only and review its suggestions before creating anything: `python3 scripts/process_new_data.py --input "..."`.
- Creation: Only run with `--create` after confirming canonical names and that no fragments (e.g., “X Date”) are produced. Never create pages for common words.
- Follow-up: Always re-run Quartz preview/build and clean up any duplicates the script might generate. If in doubt, revert and follow the LLM plan.

## Pacing & Quality Principles

- Thorough over fast: prioritize accuracy, conservative edits, and clear sourcing over speed. It is acceptable (and preferred) to defer uncertain changes to a later pass with a TODO entry.
- Review-first automation: use dry-run/report modes (e.g., LCE helper) before applying broad changes.
- Session-grounded edits: only add connections/tags/claims that are explicitly present in session text or established pages. Avoid invention.

## Session Note Structure

To balance readability with completeness, all session notes should follow a standard structure that includes a brief summary at the top and a collapsible section for the full, detailed recap.

The standard order of sections in a session note is as follows:

1.  `## Summary`: A brief, high-level overview of the session's key events.
2.  `## Full Recap`: A collapsible section containing the full, detailed session recap. This section's content is the main body of the session's events.
3.  `## NPCs Encountered`: A list of non-player characters encountered during the session.
4.  `## Locations Visited`: A list of locations visited during the session.
5.  `## Loot / Discoveries`: A list of any loot, items, or significant discoveries made during the session.
6.  `## Hooks for Next Session`: Any plot hooks or potential future actions that arose during the session.

This structure ensures that the most important information is immediately accessible, while the full details are available on demand.

## Ingestion SOP (IAC · ACE · LCE)

This vault uses a three‑phase, LLM‑assisted intake flow for any new narrative data (especially new session recaps):

- IAC — Identify Article Candidates
- ACE — Article Candidate Enrichment
- LCE — Location Connections Extraction

The SOP emphasizes source preservation, LLM reasoning, independent verification, and conservative edits with sources. Deterministic scripts provide guardrails and syntax repair, but they do not decide campaign facts or entity identity by themselves.

### IAC: Identify Article Candidates
- Goal: From the new text, list canonical entity candidates by type (NPC, Location, Faction, Item). Do not map or invent.
- Deterministic pre‑pass: fix malformed wikilinks, close brackets, and normalize already-known targets. Do not extract entities from regexes, capitalization, or grammar tags alone.
- Prompt (candidates only):
  - “From the text, list entity candidates grouped by type (NPC, Location, Faction, Item). Title Case; exclude generics and scaffolding words; do not invent; no mapping.”
- Settings: temperature 0.1–0.2, max_tokens 300–600, chunk size 2–3k chars.
- Output: short list per type (no descriptions). Use fuzzy matching, aliases, chronology, and local context before treating a candidate as new. Use this to drive ACE.

### ACE: Article Candidate Enrichment
- Goal: Create/update minimal pages for true entities, with safe frontmatter and short summaries (no invention).
- Pages: one concept per file, correct folder (`npcs/`, `locations/`, `factions/`, `items/`).
- Frontmatter conventions:
  - NPCs: `tags: [npc, gender/<value>, race/<value>, profession/<value>]` using `unknown` when not stated.
  - Items: `tags: [item/<weapon|armor|magic|mundane>]` inferred only if stated.
  - Factions: `tags: [faction]`.
  - Locations: `tags: [location]`; add `entrance` only for proven access points.
- Identity tags: add `type/<value>`, `status/<value>`, `title/<value>`, `faction/<slug>`, `culture/<slug>`, `site/<slug>`, and `session/<id>` only when the source supports them. Use `identity/uncertain`, `identity/possible-alias`, or `identity/possible-duplicate` to queue review; do not use those tags as final conclusions.
- Media tags: use `media/book`, `media/map`, `media/data-crystal`, `media/scroll`, `media/library`, `language/<slug>`, `repository/<slug>`, `topic/<slug>`, `reading/<unread|partial|read>`, and `translation/<untranslated|partial|complete>` when supported. These tags should help retrieval find related readings, not replace citations.
- Aliases: add alternate spellings/epithets on the canonical page; update links to canonical where safe.
- Stubs: include 1–2 sentence summary + “Sources” sessions; no speculation.
- Verification: every added claim must be supported by a Blogspot recap or Discord digest/chat excerpt. A second LLM verification pass should classify the claim as supported, contradicted, ambiguous, or not found before automatic promotion.

### LCE: Location Connections Extraction
- Goal: Populate `## Connections` (and `## Sources`) on location pages with explicit, sourced routes.
- What counts: direct links (leads to/through/via/across/down/up) and methods/features (rope ladder, teleporter, secret door).
- Deterministic pre‑scan: for each location mentioned in the changed session, collect 2–4 paragraph windows around the mention; keep only windows containing connector phrases (connect/lead/via/through/across/toward/into/onto/to/from/down/up/entrance/exit/gate/basket/rappel/levitat/teleport/stair/hole).
- LLM screen: YES/NO — “Does this segment describe movement or explicit connections? Answer YES or NO.”
- LLM extraction (if YES):
  - “Extract ONLY explicit connections between named locations. Output Edges ‘A -> B [via X] [method: M] [feature: F]’. Use names exactly as in text; Title Case; exclude non‑locations; no commentary. For example, if the text says 'we went from The Great Chasm to the Glory of Thoth, and from there to the Arden Vul Surface', you should extract 'The Great Chasm -> Glory of Thoth' and 'Glory of Thoth -> Arden Vul Surface', but not 'The Great Chasm -> Arden Vul Surface'.”
- Mapping: exact filename in `vault/locations/` → frontmatter `aliases` → UNMAPPED (manual review). Never invent.
- Patching: add bullets to `## Connections` and cite supporting sessions in `## Sources`. Remove “Residents” dumps from dungeon pages; use “Hazards & Encounters” and “Notable Finds”.
- Quality gates: every bullet has a session citation; all wikilinks resolve; omit inferred hops.

### Local LLM
- Endpoint: `http://192.168.21.76:1234` (OpenAI‑compatible).
- Default: `qwen2.5-7b-instruct` (or `qwen2.5-14b-instruct` if headroom).
- Timeouts: 60–180s; temperature: 0.1–0.2; max_tokens: 300–600; chunk size: 2–3k.

### Automation Hooks (recommended)
- Pre‑commit (local): when `vault/sessions/*` changes, run LCE dry‑run and show the patch for affected locations.
- CI (optional): on PRs, post an LCE report and fail if there are unmapped names, unresolved links, or missed connections.

Helper: `scripts/lce_extract.py` collects windows, queries the local LLM, maps canonical names, and prints patch suggestions (dry‑run by default).

### Rumor Consolidation
To provide a centralized view of all rumors, a consolidation process is used:

1.  **Identify Rumors:** All files in the vault are searched for the term "rumor".
2.  **Create Central Page:** A single page, `vault/lore/Rumors.md`, is used to collect all rumors.
3.  **Transclude Rumors:** Rumors from other pages are transcluded into the central `Rumors.md` page using block references. This keeps the original source intact while providing a unified view. Each rumor or section of rumors should have a block ID (e.g., `^rumors`) to allow for transclusion.

### CNF (Create Notebook Files)
To prepare the vault for use with NotebookLM, a script is used to consolidate the files into a format that is easy to upload.

- **Script:** `create_notebooklm_files.py`
- **Purpose:** This script iterates through the subdirectories of the `vault` and concatenates the content of all markdown files within each subdirectory into a single file.
- **Output:** The script generates a set of plain text files in the `notebookLMFiles` directory, with each file corresponding to a subdirectory in the vault (e.g., `npcs.txt`, `locations.txt`).
- **Exclusions:** The script excludes the `.obsidian` and `templates` directories from the export.

## Operational State (as of 2026-05-24)

Live automation runs from `scripts/vault_automation.py` under a Hermes cron job; the brain-rag-* pgvector stack and `refresh-rag` lane were retired in favor of a local Chroma vault-rag. See `docs/VAULT_AUTOMATION_REARCHITECTURE.md` for the design.

### Three review-gated lanes (all propose → verify → apply)

- **Entity links** — adds wikilinks from mentions to already-promoted entity pages.
  - Subcommands: `propose-entity-links` / `verify-entity-links` / `apply-verified-entity-links`
- **Article edits** — adds sourced bullets/aliases/summary sentences to existing articles. Research via vault-rag; verifier reads source files directly to ground each proposal.
  - Subcommands: `propose-article-edits` / `verify-article-edits` / `apply-verified-article-edits`
  - Addition types: `append_bullet_to_section`, `add_alias`, `extend_summary`
- **New entities** — creates stub vault pages for genuinely-new NPCs/Locations/Factions/Items extracted from canonical sources. Multi-stage deterministic filter (PC cross-check, word-level subset dedup, scaffolding rejection, entity_filters.json) plus LLM verifier with `confirmed | wrong_kind | duplicate | not_an_entity | ambiguous`.
  - Subcommands: `propose-new-entities` / `verify-new-entities` / `apply-verified-new-entities`

### Vault-rag (Chroma)

- Path: `/home/kyle/rag_project/vaults/ArdenVault/index/` (sibling of MechanicsVault DFRPG-rules collection)
- Collection: `arden_vul_vault`
- Embedding model: Ollama `bge-m3` at `http://127.0.0.1:11434/api/embeddings`
- Cosine distance, chunked at H2 headings with paragraph sub-splitting at 3000 chars
- Scope: whole vault (`sessions/`, `notes/Discord Summary *.md`, `notes/`, `lore/`, `npcs/`, `pcs/`, `locations/`, `factions/`, `items/`, `monsters/`, `spells/`, `concepts/`) **plus per-channel rollups** from `discord_rollup_root` tagged `kind=rollup`, plus the spreadsheet snapshot
- ~17,500 chunks across ~1,770 files at last full ingest (2026-05-24)
- Subcommands: `ingest-vault-rag [--reset] [--limit N]`, `refresh-vault-rag` (sha256-gated), `vault-rag-search <query> [--top-k N] [--kind ...]`
- Auto-refreshed after each apply step and at end of `run-low-risk`

### Scheduled cron + vault walk

- Hermes job `fd3dccf7b808`: `~/.hermes/scripts/arden_vault_run.sh` daily at 07:00 CT, delivers a one-line summary to Discord
- `run-low-risk` orchestrates: discover → validate → import-low-risk → entity-link proposals/verify → article queue → media queue → spreadsheet snapshot → loot reconciliation → article-edit lane (propose/verify/apply on `article_edit_queue_top` weakest + `article_edit_walk_step` cursor-walk articles) → vault-rag refresh
- Vault walk cursor lives in `data/automation/vault_walk_cursor.json` and rotates through every article in `vault/{npcs,pcs,locations,factions,items,monsters,spells}` (573 paths at last count). Inspect with `vault-walk-status`. Cursor advances per scheduled run.
- Hermes script timeout overridden globally to 1200s in `~/.hermes/config.yaml` under `cron.script_timeout_seconds`.

### Config (gitignored at `config/local_sources.json`)

Runtime knobs and private paths/credentials stay out of the repo:

```
discord_digest_root, discord_rollup_root            — external Discord source paths
group_spreadsheet_url, group_spreadsheet_gid        — shared spreadsheet
llm_base_url, llm_model                             — LiteLLM/LM-Studio gateway
vault_rag_chroma_path, vault_rag_collection,
  vault_rag_embed_model, vault_rag_embed_url        — vault-rag connection
entity_link_verify_limit, entity_link_apply_limit   — entity-link lane budget
article_queue_limit                                  — top-N queue size
article_edit_queue_top, article_edit_walk_step,
  article_edit_verify_limit, article_edit_apply_limit — article-edit lane budget per cron tick
```

Safe daily-cron defaults: `article_edit_queue_top: 2`, `article_edit_walk_step: 3`, `article_edit_verify_limit: 15`, `article_edit_apply_limit: 3`. Sprint mode bumps these (typical: 10/8/30 walk-step/apply/verify) and restores afterward.

### Known issues / followups

- **`extend_summary` near-duplicates**: the proposer occasionally restates the existing Summary with a small parenthetical addition (e.g., `vault/npcs/Bifki.md`). Detection in `apply_article_edit_to_text` should reject when proposed text's word-overlap with existing summary exceeds ~80%.
- **3 tiny stub locations fail to embed in vault-rag**: `vault/locations/Exarchate of Narsileon.md`, `vault/locations/The Canyon.md`, `vault/locations/The Tomb of Ptoh-Ristus.md` — all 60–112 char H1+wikilink-only chunks that trigger Ollama bge-m3 NaN output. Workaround: bump `VAULT_RAG_MIN_CHUNK_CHARS` from 60 or expand chunks with surrounding context.
- **Blog session-title parser**: handles singular `Session N` and plural `Sessions Xb and Y` titles. Re-check if dripton ever uses other compound forms.
- **LLM JSON robustness**: `llm_chat_json` parses raw → code-fence-stripped → greedy `{...}` → bracket-counted slice. If a model server starts returning structured-output mode (`response_format: json_object`), we removed that field because LM Studio rejected it; revisit when upstream support is reliable.
- **`run-low-risk` doesn't yet auto-run the new-entity lane** — propose/verify/apply for new entity stubs is manual-only until verifier confidence is proven across more candidates.
