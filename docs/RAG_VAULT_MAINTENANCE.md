# RAG and Vault Maintenance

## Current Architecture

There is one supported vault maintenance path:

```text
Hermes cron
  -> /home/kyle/.hermes/scripts/arden_vault_run.sh
  -> scripts/vault_automation.py run-low-risk
  -> curated Obsidian vault
  -> Chroma staging index
  -> PostgreSQL mirror
  -> postgres-rag-api on port 8897
  -> Tailscale Funnel for human access
```

The Arden Chroma staging index is still used during publication. The retired
Chroma HTTP API has been deleted.

## Scheduled Work

| Schedule | Entry point | Role |
|---|---|---|
| Hourly daytime Hermes cron | `/home/kyle/.hermes/scripts/arden_vault_run.sh` | Vault import, low-risk maintenance, index refresh |
| `discord-chat-explorer.timer` | `discord_chat_explorer.py` | Export Discord source streams |
| Rollup after export | `discord_weekly_rollup.py` | Produce weekly rollups |
| Saturday `discord-weekly-digest.timer` | `run_digest_pipeline.py` | Digest, QA, and revision for completed weeks |

`run_digest_pipeline.py` ignores an in-progress Friday-boundary rollup.

## Intentionally Retained Manual Tools

- `scripts/check_wikilinks.py`
- `scripts/dedup_qc.py`
- `scripts/discord_media_ingest.py`
- `scripts/tag_enrichment.py`
- `scripts/fetch_loot_sheet.py`
- `scripts/generate_armory.py`
- `scripts/import_library.py`
- `scripts/gcs_to_md.py`

The separate MechanicsVault manual RAG remains available under
`/home/kyle/rag_project/scripts/`:

- `ingest_dfrpg.py`
- `backfill_failed.py`
- `query_mechanics.py`
- `rag_answer.py`

## Deferred Ingest Boundary

The ArdenVault Chroma index remains temporarily under
`/home/kyle/rag_project/vaults/ArdenVault/index/` because the current
SHA-gated ingester writes it before publishing a snapshot to PostgreSQL. Remove
that staging index only after Arden publication writes directly to PostgreSQL.

## Removed Paths

The cleanup deleted the retired `8893` ingest API, `8894` query API, `8895`
SearXNG adapter, `8896` Chroma rollback API, duplicate systemd vault timer,
older IAC/ACE and graph scripts, one-off repair scripts, raw Discord repo
exports, generated text exports, and parallel weekly digest paths.
