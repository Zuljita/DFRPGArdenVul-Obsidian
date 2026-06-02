---
name: arden-vul-discord-pipeline
description: Operate and troubleshoot the Arden Vul Discord export, weekly rollup, digest, QA, revision, and vault import pipeline.
---

# Arden Vul Discord Pipeline

## Guardrails

1. Do not print or commit Discord tokens or raw Discord transcripts.
2. Treat `revised-digest.md` as the final weekly source article.
3. Use the consolidated vault harness for import and vault maintenance.
4. Keep the proposal workflow dormant until it is deliberately repaired.

## Source Pipeline

The source pipeline lives in `/home/kyle/discord-chat-explorer`.

| Stage | Script | Schedule |
|---|---|---|
| Export | `discord_chat_explorer.py` | `discord-chat-explorer.timer` |
| Rollup | `discord_weekly_rollup.py` | Triggered after export |
| Digest, QA, revision | `run_digest_pipeline.py` | `discord-weekly-digest.timer` |

Rollups use a Friday 23:00 Central boundary. `run_digest_pipeline.py` ignores
the in-progress week and processes only completed rollups.

Useful checks:

```bash
systemctl status discord-chat-explorer.timer discord-weekly-digest.timer --no-pager
journalctl -u discord-chat-explorer.service -n 120 --no-pager
python3 /home/kyle/discord-chat-explorer/run_digest_pipeline.py --dry-run
```

## Vault Import

The supported vault path is:

```bash
cd /home/kyle/.openclaw/workspace/DFRPGArdenVul-Obsidian
python3 scripts/vault_automation.py run-low-risk
```

The harness imports completed revised digests into
`vault/notes/Discord Summary YYYY-WNN.md`, refreshes navigation, performs
low-risk maintenance, updates Chroma staging indexes, and mirrors the snapshot
to PostgreSQL for the public RAG API.

Manual maintenance should use focused retained tools only:

```bash
python3 scripts/check_wikilinks.py
python3 scripts/dedup_qc.py
python3 scripts/discord_media_ingest.py --help
python3 scripts/tag_enrichment.py --help
```
