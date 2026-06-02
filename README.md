# DFRPG Arden Vul — Obsidian Vault

Curated Obsidian vault for a DFRPG campaign set in Arden Vul.

- Vault content lives in `vault/` (open in Obsidian)
- Examples/indices and lore live under `vault/*` folders
- Quartz site for publishing in `quartz/` (maintainer-only)
- Helper scripts in `scripts/` (link checks, normalization, curation)

## Quick Start

- Edit: open `vault/` in Obsidian
- Session link check: `python3 scripts/check_wikilinks.py`
- Quartz preview (maintainer): `cd quartz && pnpm dev`
- Quartz build (maintainer): `cd quartz && pnpm build` (outputs to `quartz/public/`)

## Contributing

Please see `CONTRIBUTING.md` for folder layout, naming, and link conventions.
