# RAG and Vault Maintenance

## Current Architecture

There is one supported vault maintenance path:

```text
Hermes cron
  -> /home/kyle/.hermes/scripts/arden_vault_run.sh
  -> scripts/vault_automation.py run-low-risk
  -> curated Obsidian vault
  -> PostgreSQL/pgvector rag_chunks database
  -> postgres-rag-api on port 8897
  -> Tailscale Funnel for human access
```

Arden publication writes directly to PostgreSQL. There is no intermediate
vector index or separate Arden ingest API.

## Scheduled Work

| Schedule | Entry point | Role |
|---|---|---|
| Hourly daytime Hermes cron | `/home/kyle/.hermes/scripts/arden_vault_run.sh` | Vault import, low-risk maintenance, index refresh |
| Weekday daytime Hermes cron | `arden_vault_walk_weekday.sh` | Incremental article enrichment |
| Weekend overnight Hermes cron | `arden_vault_walk_weekend.sh` | Recent-article enrichment |
| Daily 20:30 Hermes cron | `arden_vault_polish.sh` | Independently verified five-article polish pass |
| `discord-chat-explorer.timer` | `discord_chat_explorer.py` | Export Discord source streams |
| Rollup after export | `discord_weekly_rollup.py` | Produce weekly rollups |
| Saturday `discord-weekly-digest.timer` | `run_digest_pipeline.py` | Digest, QA, and revision for completed weeks |

`run_digest_pipeline.py` ignores an in-progress Friday-boundary rollup.

## Scheduled Mutation Guardrails

Scheduled proposal runs assign a unique `batch_id`. Verification and application
only consume proposals from that batch; supported proposals left over from older
runs are never applied implicitly.

The scheduler enforces these hard per-run ceilings:

- Entity links: 10
- Article edits: 3
- Metadata edits: 5
- New entities: 3
- Distinct vault files across all lanes, including imports: 15

Negative legacy configuration values such as `-1` resolve to the safe defaults
above rather than unlimited processing. Work beyond a ceiling is reported as
deferred for a later batch.

### Polish Verification

`polish-article` and `polish-queue` use a second LLM pass before writing a
rewrite. The verifier receives the original article, proposed rewrite, and all
retrieved source chunks. It evaluates factual support, lost still-valid facts,
relationship changes, new revelations, and overall article quality.

Evidence-backed title, identity, relationship, and structural changes are
allowed. Rejected rewrites and verifier errors leave the original article
untouched. Audit results are written under `data/automation/polish/`; approved
rewrites remain uncommitted for the later branch-level review.

Set `polish_verifier_model` in ignored local configuration to use a different
model for this pass. When omitted, the verifier is still an independent call
using the configured vault model.

Polish attempts enter a seven-day rotation cooldown by default, including
approved, rejected, unchanged, and verifier-error outcomes. This keeps daily
runs moving through the wider queue instead of repeatedly selecting the same
highest-scoring pages. Configure `polish_retry_days` locally to change the
cooldown.

Hourly `run-low-risk` does not perform article edits. Scheduled article
enrichment is owned by `vault-walk-step`; polishing is owned by `polish-queue`.

### RAG Publication

`run-low-risk` suppresses publication side effects inside its metadata,
new-entity, and optional article-edit applicators. After all lanes finish, the
orchestrator performs one SHA-gated PostgreSQL publication pass. Standalone
manual apply commands retain immediate publication so they remain complete when
run outside the scheduler.

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

## Removed Paths

The cleanup deleted the retired `8893` ingest API, `8894` query API, `8895`
SearXNG adapter, `8896` rollback API, duplicate systemd vault timer, older
IAC/ACE and graph scripts, one-off repair scripts, raw Discord repo exports,
generated text exports, and parallel weekly digest paths.
