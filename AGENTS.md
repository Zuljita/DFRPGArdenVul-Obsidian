# Arden Vul Vault Automation

## Authoritative Path

The supported maintenance entry point is:

```bash
python3 scripts/vault_automation.py run-low-risk
```

Hermes runs that command through `/home/kyle/.hermes/scripts/arden_vault_run.sh`.
The wrapper uses `flock` so overlapping runs exit instead of competing.

The harness imports completed Discord revisions, maintains navigation and
low-risk vault edits, refreshes Chroma staging indexes, and mirrors a consistent
snapshot to the PostgreSQL RAG service on port `8897`.

## Source Boundaries

- Curated vault markdown lives in `vault/`.
- Raw Discord streams and rollups live outside this repo in
  `/home/kyle/discord-chat-explorer`.
- Do not commit raw Discord transcripts.
- Player-facing RAG indexes curated vault notes, including
  `vault/notes/Discord Summary YYYY-WNN.md`.
- Keep `config/entity_filters.json` and `config/ace_ignore_npcs.txt`; the
  harness uses both when evaluating new entity candidates.

## Retained Scripts

| Script | Purpose |
|---|---|
| `scripts/vault_automation.py` | Consolidated scheduled harness |
| `scripts/check_wikilinks.py` | Manual wikilink validation |
| `scripts/dedup_qc.py` | Manual duplicate review |
| `scripts/discord_media_ingest.py` | Focused Discord media import |
| `scripts/tag_enrichment.py` | Deterministic tag enrichment |
| `scripts/fetch_loot_sheet.py` | Loot spreadsheet fetch |
| `scripts/generate_armory.py` | Party armory generation |
| `scripts/import_library.py` | Library import |
| `scripts/gcs_to_md.py` | Character sheet conversion |

## Validation

```bash
python3 -m py_compile scripts/*.py
python3 scripts/check_wikilinks.py
python3 scripts/vault_automation.py --help
```
