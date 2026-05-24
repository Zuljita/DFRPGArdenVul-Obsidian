# Automation Changelog

Public log of deterministic vault automation changes. Entries avoid private local source paths.

## 2026-05-18 08:27 CDT - bootstrap-low-risk-import

- created vault/sessions/Session 51 - The Vengeance Aspect.md
- created vault/sessions/Session 52a - Ichthelon and the Temple of Thoth.md
- created 9 missing Discord summary notes
- refreshed navigation on adjacent session and Discord summary notes
- verified targeted wikilinks and guardrail validation

## 2026-05-18 08:33 CDT - 20260518T133355Z

- update vault/notes/Discord Summary 2025-W09.md
- update vault/notes/Discord Summary 2025-W33.md
- update vault/notes/Discord Summary 2025-W39.md
- update vault/notes/Discord Summary 2025-W49.md
- update vault/notes/Discord Summary 2026-W15.md
- update vault/notes/Discord Summary 2026-W16.md
- update vault/notes/Discord Summary 2026-W17.md
- update vault/notes/Discord Summary 2026-W18.md
- update vault/notes/Discord Summary 2026-W19.md

## 2026-05-18 08:41 CDT - entity-link-verifier-proof

- generated review-only entity link proposals for recent canonical sources
- LLM-verified 5 proposed links as supported by source context
- applied 5 verified links to vault/notes/Discord Summary 2026-W15.md
- verified wikilinks for the changed summary

## 2026-05-18 08:45 CDT - scheduled-verifier-enabled

- `run-low-risk` now refreshes entity link proposals on each scheduled pass
- ignored local config can enable a small LLM verification batch without exposing endpoint details
- ignored local config keeps verified-link auto-apply disabled unless explicitly enabled

## 2026-05-18 22:04 CDT - verifier-context-packets

- added docs/CAMPAIGN_CONTEXT.md with table-role and setting grounding for automation
- verifier prompts now include campaign context, target entity context, and a wider source window
- existing wikilinks are converted to their visible labels inside verifier source windows so context is not erased
- increased verifier token budget for reasoning models that need more room before final JSON

## 2026-05-18 22:22 CDT - article-research-queue

- added deterministic article improvement queue generation for promoted entity pages
- queue items include weakness reasons and context-preserving RAG search queries
- added private-config-only RAG refresh command for changed vault Markdown files
- scheduled low-risk runs now refresh the article queue while keeping article edits review-gated

## 2026-05-18 22:34 CDT - rag-refresh-verification

- private RAG refresh can now wait for ingest jobs and fail if indexing fails after acceptance
- scheduled RAG refresh, when enabled, waits for indexing status instead of trusting initial queue acceptance
- public docs now recommend `refresh-rag --wait` for post-edit RAG updates

## 2026-05-18 22:45 CDT - tag-guided-identity-research

- documented namespaced tags as retrieval hints for same-entity research, not proof
- added identity-signal tag guidance for ghosts, undead, aliases, possible duplicates, affiliations, sites, and sessions
- article improvement queue now includes article tags and uses supported tags to widen RAG search queries

## 2026-05-18 22:58 CDT - media-library-lane

- documented downtime media discoveries as a distinct automation lane for books, maps, data crystals, scrolls, inscriptions, catalogs, and libraries
- added `build-media-queue` to flag media pages needing sourced contents, reading status, translation status, provenance, or artifact references
- scheduled low-risk runs now refresh the media improvement queue alongside the article queue

## 2026-05-18 23:09 CDT - shared-spreadsheet-source

- added ignored local configuration support for a shared group Google Sheet and worksheet gid
- added `ingest-spreadsheet --write` to snapshot sheet dimensions, hash, headers, and preview under ignored automation data
- scheduled low-risk manifests now include spreadsheet source status without hardcoding spreadsheet URLs in tracked files

## 2026-05-18 23:19 CDT - spreadsheet-row-classification

- added `classify-spreadsheet --write` to route shared sheet rows into review-only proposal lanes
- classifier preserves the sheet's matrix shape and maps row labels to PC mechanics, defense, combat, skills, spells, loot/inventory, media/library, or review
- scheduled low-risk runs now write ignored spreadsheet classification artifacts when the sheet is configured

## 2026-05-18 23:31 CDT - loot-reconciliation-gate

- added `reconcile-loot` to compare spreadsheet loot/inventory rows with Discord summary evidence for destroyed, consumed, lost, sold, or broken items
- scheduled low-risk runs now write a review-only loot reconciliation report
- documented spreadsheet inventory as useful but not promotable until item disposition evidence has been checked

## 2026-05-18 23:55 CDT - loot-disposition-matching

- loot reconciliation now extracts item-like phrases from disposition evidence
- candidate matches include existing vault item/media pages, affected spreadsheet rows, confidence, and review notes
- unmatched phrases are preserved as review prompts for missing pages, aliases, or non-durable expenses

## 2026-05-23 10:45 CDT - 20260523T154443Z

- create vault/notes/Discord Summary 2026-W20.md
- update vault/notes/Discord Summary 2026-W19.md
- update vault/notes/Discord Summary 2026-W20.md
- update vault/sessions/Session 52a - Ichthelon and the Temple of Thoth.md
