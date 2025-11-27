# Contributing Guidelines

## Scope
- Edit only `vault/` content. Maintainer handles `quartz/` builds/hosting.
- One concept per file; place in the appropriate folder (e.g., `npcs/Name.md`).

## Naming & Links
- Markdown only. Title Case filenames and headings.
- Use Obsidian wikilinks `[[Page Name]]`. Prefer the canonical page name.
- Use aliases on canonical pages to capture variants; repoint links to canonical.
- Assets go in `attachments/` with relative links.

## Hygiene
- Avoid creating fragments like “X Date/Over/We/That …”. Merge into canonical pages.
- Create stubs for truly new entities with a short summary + TODOs.
- Validate: run `scripts/check_wikilinks.py vault` (0 missing, 0 unbalanced).

## Project Structure
- `vault/`: all notes (sessions, npcs, locations, items, factions, lore, etc.)
- `scripts/`: curation helpers (link checks, normalization, extraction)
- `quartz/`: Quartz project (maintainer only)

## Commit Style
- Small, scoped commits. Suggested: `content(scope): summary`.
- Example: `content(npcs): merge Kronos variants; add alias`.

## Safety
- No secrets or personal data. Redact when in doubt.

