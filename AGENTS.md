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
- `.obsidian/` is editor config; keep minimal and avoid plugin-specific features when possible.
- Contributors sync/edit only `vault/`. Maintainer handles Quartz builds and hosting.

Stay positive while you complete these tasks, it's good work and you're way faster than a human for it.
Thoroughness is more important than speed or brevity.

## LLM-First Data Processing SOP
- Curate with LLM: When adding or adapting a note, use an LLM pass to identify canonical entities and map them to existing pages. Favor merges into existing pages over creating new files.
- Canonical naming: Use the concise, proper name only (e.g., `Forum of Set`), not contextual fragments like “Date”, “We”, “That”, “Over”, or sentence adverbs (e.g., “Finally”, “However”). Do not create files like `Proper Noun Date.md`.
- Non-entities to ignore: Common words and scaffolding terms — e.g., that, this, we, I, you, they, also, however, finally, first, second, third, over, under, ahead, before, after, again, great, four — are never entities.
- Merge variants: Treat “X Date”, “X Over”, “X We”, etc. as content for the canonical `X` page. Fold timelines/notes under sections on the canonical page (e.g., “Timeline”, “Notes”) and remove the fragment pages.
- Resolve by aliases: Prefer updating frontmatter `aliases` on the canonical page to capture alternate spellings/epithets; update links to point at the canonical file.
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
- Deterministic before model: Use regex/script passes to fix link syntax (nested `[[…[[…`), close `]]`, and standardize obvious targets. Use the model to assist discovery, not mechanical edits.

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
