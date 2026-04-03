---
name: arden-vul-discord-summary-enrichment
description: Build and enrich Arden Vul Discord weekly summaries from raw exports and update canonical entity pages while preserving GM recap bodies. Use after loading arden-vul-vault-core and arden-vul-vault-context.
---

# Arden Vul Discord Summary Enrichment

## Required pre-steps
1. Read `arden-vul-vault-core`.
2. Read `arden-vul-vault-context`.

## Guardrails
1. Never edit GM recap body text in `vault/sessions/*.md`.
2. Session files may receive only explicit footer/navigation updates when required.
3. No invented facts.
4. Prefer no link over wrong link.

## Workflow
1. Determine week/date range.
2. Extract facts with channel/date provenance.
3. Update/create weekly summary file.
4. Link key nouns to canonical pages using fuzzy+context checks.
5. If uncertain/conflicting mapping, invoke `arden-vul-vault-research-assistant` first.
6. Enrich canonical pages with concise durable facts + backlinks.
7. Record progress and unresolved items.

## Output format
- Weeks processed
- Summary files changed
- Entity pages changed
- Alias/duplicate decisions
- Unresolved ambiguities
