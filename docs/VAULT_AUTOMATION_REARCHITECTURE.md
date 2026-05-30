# Vault Automation Rearchitecture

## Current State

The previous Hermes vault jobs are paused:

- `f0d471864312` - Knowledge Graph Enrichment Agent
- `3f4b10dff606` - vault-placeholder-janitor

They should stay paused until the pipeline below exists and has passed dry-run validation.

The obsolete general-purpose Hermes vault job was deleted. Do not recreate or restart that pattern; it used an unbounded agent and an obsolete external refiner pipeline.

## Failure Mode

The failed design gave a general-purpose agent authority to do all of these in one run:

- discover sources
- choose canonical paths
- extract facts
- classify entities
- create or delete Markdown files
- update manifests and stats
- report success

That produced the expected bad outcomes:

- writes to the wrong vault root
- case-duplicated folder trees such as `Entities/` and `NPCs/`
- low-value entity pages from pronouns, fragments, and generic nouns
- misclassified pages such as items written under NPCs
- large context growth, malformed JSON, invalid generated Python, and false success reports
- broad dirty-tree changes without review boundaries

## Product Goal

The end state is fully automated vault maintenance, not manual upkeep. The guardrails exist to make unattended automation safe enough to run continuously.

The vault should contain polished canonical campaign knowledge:

- GM recap posts from `dfwhiterock.blogspot.com`
- weekly Discord digests generated outside the repository
- downtime media-reading updates for books, scrolls, data crystals, maps, inscriptions, catalogs, and library collections
- structured shared spreadsheet data configured outside the repository
- promoted entity articles
- cross-links between recaps, weekly digests, and entity articles

The vault should not contain raw Discord exports, bulk private transcripts, or local filesystem paths for private chat tooling. Those remain outside the repository.

## Design Principles

1. Automation may mutate the canonical vault on a schedule only through deterministic, audited scripts with narrow write scopes and rollback checkpoints.
2. The canonical vault root is exactly `vault/` in this repository. Any external RAG mirror or index is not an authority.
3. Deterministic code owns filesystem discovery, manifests, canonical path mapping, validation, and patch creation.
4. LLMs may only do bounded extraction or review against small text windows with explicit schemas.
5. Every proposed claim must carry provenance: source path plus quoted evidence or line span.
6. New pages require conservative entity validation. Common words, pronouns, roles, sentence fragments, and "X Date/Over/That/This" patterns are rejected before any LLM output is trusted.
7. Scheduled runs should start in read-only/report mode while the pipeline is being rebuilt. Once validation is stable, promotion can become automatic for low-risk changes.
8. A run is not successful unless validation proves the expected artifact was created and no guardrails failed.

## Lessons Learned

Entity discovery cannot rely on regex-style extraction, capitalization rules, or basic grammatical extraction. The campaign data is written by humans during play, so names, grammar, punctuation, capitalization, and terminology are inconsistent. Heuristics are useful only as guardrails, indexes, and candidate filters; they are not an authority for creating or merging article pages.

Use LLMs for reasoning tasks where they are strong: interpreting messy context, proposing entity candidates, identifying likely aliases, spotting contradictions, and drafting summaries. Do not trust a single LLM pass as fact. Every candidate, claim, alias, merge, or article edit must be checked against the two canonical source classes: Blogspot session recaps and Discord chat/digest material. For higher-risk changes, use a second LLM pass as a verifier that must cite source evidence and explicitly reject unsupported claims.

Expect typos and near-duplicates. Candidate matching should combine fuzzy string matching, known aliases, nearby context, source chronology, and entity type. A spelling mismatch should trigger evidence review, not automatic creation of a new page. Automatic mode may link only high-confidence matches to already-promoted entities; uncertain matches belong in review output with the competing candidates and source excerpts.

Do not over-slice context. Single-sentence or single-claim prompts are often too small for this campaign, because identity and meaning depend on section headings, table-role notation, nearby planning bullets, prior session state, and whether a name is an in-world character or an out-of-world player handle. Verification prompts should use context packets: campaign/table context, target entity context, and a generous source window around the relevant passage.

Use tags as retrieval and reasoning scaffolding, not as proof. Tags should help a researching agent find identity-adjacent evidence, such as “scary ghost” in one session and a named ghost in a later session, by grouping pages with shared type, creature state, faction, culture, location, status, and chronology hints. A shared tag cluster may create an identity hypothesis, but only canonical source evidence can promote an alias, merge, or same-entity claim.

Prefer stable namespaced tags over prose tags:

- entity class: `npc`, `pc`, `location`, `faction`, `item`
- identity signals: `race/<value>`, `type/<value>`, `status/<value>`, `profession/<value>`, `title/<value>`
- affiliations: `faction/<slug>`, `culture/<slug>`, `deity/<slug>`
- location/chronology hints when explicitly supported: `region/<slug>`, `site/<slug>`, `session/<id>`
- uncertainty: `identity/uncertain`, `identity/possible-alias`, `identity/possible-duplicate`

For example, a ghost-like NPC can safely carry `npc`, `race/undead`, `type/ghost`, and `identity/uncertain` when those are supported by the sources. If later evidence suggests it may be Yrtol, the automation should produce a same-entity review packet with source windows from both mentions, not silently merge the pages.

## Proposed Pipeline

### 0. Recovery Gate

Before new automation runs, restore or quarantine the current dirty tree.

Required checks:

- `git status --short`
- no unexpected tracked deletions
- no uppercase duplicate vault category directories
- no generated fragment pages in canonical vault paths
- `python3 scripts/check_wikilinks.py vault`

### 1. Source Discovery

A deterministic script discovers primary sources and writes a read-only manifest.

Inputs:

- Discord weekly digests from a local private source configured outside git
- Discord weekly rollups from a local private source, used only as external source material
- Blogspot Atom feed: `https://dfwhiterock.blogspot.com/feeds/posts/default?alt=json`
- session recaps in `vault/sessions/`

Output:

- `data/automation/source_manifest.json`

Manifest fields:

- source id
- absolute source path
- normalized source type
- mtime
- sha256
- previous processed sha256
- status: new, changed, unchanged, missing

No vault Markdown files are edited in this phase.

### 1A. Discord Digest Generation

The external Discord pipeline should remain outside the vault repo. Vault automation should ingest only finished weekly digests from a private local source, not raw transcript text.

Local source paths must be configured outside git. `scripts/vault_automation.py` supports either environment variables or the ignored file `config/local_sources.json`:

```json
{
  "discord_digest_root": "/private/path/to/digests",
  "discord_rollup_root": "/private/path/to/rollups",
  "llm_base_url": "http://private-local-llm/v1",
  "llm_model": "local-model-name",
  "entity_link_verify_limit": 5,
  "entity_link_apply_limit": 0
}
```

The public repo must not include the concrete local path or the name of the private chat tooling.

### 1B. Blogspot Recap Ingestion

Blogspot is a canonical source. Use the Blogger feed instead of blind scraping:

```text
https://dfwhiterock.blogspot.com/feeds/posts/default?alt=json&max-results=50
```

For each Arden Vul recap post:

- store original URL and published/updated timestamps
- preserve the raw post text as much as possible
- add only approved Markdown additions:
  - previous session link
  - next session link, once available
  - preceding weekly Discord digest link
  - following weekly Discord digest link, once available
  - original source URL
  - inline links to entities already promoted by IAC/ACE

Do not rewrite prose, summarize the post, or normalize facts inside the recap body.

### 1C. Shared Spreadsheet Snapshot

The group spreadsheet is a structured source for party-facing operational data such as character sheets, inventories, loot, media catalogs, map lists, downtime state, and other table-maintained records.

The spreadsheet URL and worksheet gid must be configured outside git through environment variables or ignored local config:

```json
{
  "group_spreadsheet_url": "https://docs.google.com/spreadsheets/d/.../edit?gid=...",
  "group_spreadsheet_gid": "..."
}
```

Use:

```bash
python3 scripts/vault_automation.py ingest-spreadsheet --write --classify
python3 scripts/vault_automation.py classify-spreadsheet --write
```

Output:

- `data/automation/sources/group_spreadsheet_snapshot.json`
- `data/automation/sources/group_spreadsheet_snapshot.md`
- `data/automation/sources/group_spreadsheet_classification.json`
- `data/automation/sources/group_spreadsheet_classification.md`

The snapshot is ignored operational state. It records dimensions, content hash, headers, and a preview so automation can detect changes and route follow-up work. The classification report maps rows into proposal lanes such as PC mechanics, PC defense, PC combat, PC skills, party spells, loot/inventory, media/library, or spreadsheet review. The public repo must not hardcode the private/shared spreadsheet URL.

Spreadsheet data should be treated according to what it represents:

- mechanical or inventory state can inform review proposals for PC/item/library pages
- media catalog entries can feed the media/library queue
- narrative or identity claims still require verification against Blogspot recaps or weekly Discord digests before promotion
- spreadsheet rows must not overwrite recap text or Discord summary text

Loot and inventory rows are a higher-confidence spreadsheet use case than PC article maintenance, but they still need reconciliation. The spreadsheet can represent current party state, while Discord digests may record item disposition events such as destroyed, consumed, lost, sold, broken, or left-behind items. Before promoting spreadsheet inventory as current, run:

```bash
python3 scripts/vault_automation.py reconcile-loot
```

Output:

- `data/automation/proposals/loot_reconciliation.json`
- `data/automation/proposals/loot_reconciliation.md`

This report lists spreadsheet loot/inventory rows beside Discord summary evidence for item disposition. It is review-only; it should become the gate before automatic inventory/page updates.

The report also attempts conservative candidate matching:

- exact or fuzzy matches to existing item/media pages
- extracted item-like phrases that may need pages or aliases
- spreadsheet loot/resource rows likely affected by the evidence

Unmatched phrases are not failures; they are review prompts. They usually mean the vault lacks a page/alias for the object, the spreadsheet tab is too summarized to match directly, or the evidence is about expenses rather than a durable item.

### 2. Candidate Extraction

Use the existing IAC approach from `AGENTS.md`.

Rules:

- chunk input to 2k-3k characters
- call the local model only for candidate lists
- output strict JSON
- reject candidates through deterministic filters
- map candidates to existing page names and aliases locally
- do not use regex, capitalization, or grammar-only extraction as the source of truth
- fuzzy-match likely typos and aliases before proposing a new article
- preserve ambiguous matches for review instead of creating duplicate pages

Output:

- `data/automation/runs/<run-id>/iac_candidates.json`
- `data/automation/runs/<run-id>/candidate_rejections.json`

### 3. Evidence Extraction

Only after candidate mapping, extract claims for accepted entities.

Each claim must include:

- subject
- predicate
- object
- source path
- evidence quote or line span
- confidence
- target page if already mapped

Output:

- `data/automation/runs/<run-id>/claims.json`

Claims without provenance are discarded.

LLM-generated claims must pass an adversarial verification step before promotion:

- verifier receives a context packet with the proposed claim or link, campaign/table context, candidate entity context, and relevant canonical source windows
- verifier must return supported, contradicted, ambiguous, or not found
- supported claims must cite the recap URL or external Discord digest/rollup path plus quote or line span
- contradicted, ambiguous, and not found claims are blocked from automatic promotion

### 4. Change Builder

A deterministic script converts accepted claims into a bounded change set.

Allowed proposal types:

- append sourced bullet to an existing page section
- add alias to existing frontmatter
- create a new stub for a true new entity
- append connection bullet to a location page's `## Connections` section
- flag conflict for manual review

Output:

- `data/automation/runs/<run-id>/proposal.md`
- `data/automation/runs/<run-id>/proposal.patch`

The script must never delete pages. In early rebuild mode, it stops here. In automatic mode, it may apply only changes that pass the validation gate and match an allowlist.

### 5. Validation Gate

Validation must pass before a proposal can be promoted.

Checks:

- patch only touches allowed folders
- no edits outside `vault/` and `data/automation/`
- no uppercase duplicate category roots
- no generated files for rejected names
- all wikilinks resolve or are explicitly listed as proposed stubs
- every new/changed claim has source evidence
- diff size is below configured limits unless manually overridden

Output:

- `data/automation/runs/<run-id>/validation.json`

### 5A. Article Improvement Queue

Deep research should start with deterministic article selection, not an open-ended crawl.

`scripts/vault_automation.py build-article-queue` scores promoted entity articles under `vault/npcs`, `vault/pcs`, `vault/locations`, `vault/factions`, and `vault/items`.

The score is only a triage signal. It looks for article weakness such as:

- short bodies
- TBD/TODO/placeholder text
- unresolved unknown markers
- few or no wikilinks
- missing source/session sections
- missing summary/overview sections

Output:

- `data/automation/proposals/article_improvement_queue.json`
- `data/automation/proposals/article_improvement_queue.md`

Each queue item includes RAG search queries broad enough to preserve context, for example title, kind, campaign name, recap context, digest context, known aliases, and identity-signal tags. The queue does not edit vault files.

### 5B. RAG-Grounded Article Research

The intended research loop is:

1. Select the highest-scoring article from the queue.
2. Search the vault-rag Chroma collection with the article title, type, aliases, and campaign context queries.
3. Retrieve source windows from canonical and structured source classes:
   - Blogspot session recaps stored in `vault/sessions/`
   - private weekly Discord digests imported to `vault/notes/`
   - ignored snapshots of the shared group spreadsheet for structured table data
4. Ask an LLM to propose article edits with citations to retrieved source windows.
5. Ask a verifier LLM to classify each proposed addition as supported, contradicted, ambiguous, or not found.
6. Build a patch only for supported additions.
7. Run validation.
8. After accepted edits are applied, refresh the vault-rag Chroma collection so subsequent research sees the new content.

The vault-rag store is a sibling of the DFRPG rules Chroma collection (`MechanicsVault`) and lives at `/home/kyle/rag_project/vaults/ArdenVault/index/` with collection name `arden_vul_vault`. It uses Ollama `bge-m3` for embeddings. Connection target and collection name are the separator between vault data and any other RAG corpus (rules, paperclip, etc.). No project tokens or shared databases.

The repo-side hooks for ingest/search live in `scripts/vault_automation.py` (subcommands `ingest-vault-rag`, `refresh-vault-rag`); private paths and model names stay outside git.

### 5C. Media And Library Updates

Downtime reading is a distinct automation lane. Books, data crystals, maps, scrolls, inscriptions, and library collections can reveal lore, locations, routes, factions, identities, artifact functions, languages, and open hooks. Those updates should not be lost inside generic chat summaries.

The canonical source remains the weekly Discord digest or Blogspot recap that reports the reading result. The vault may contain derived media pages, catalogs, and lore updates, but raw chat and private media tooling stay outside git.

Media pages should use consistent metadata when known:

- type: `book`, `journal`, `scroll`, `map`, `data-crystal`, `inscription`, `library`, `catalog`
- found in: session or digest link
- repository/location: where the item is stored, such as Beacon library or Library of Thoth
- reading status: unread, partial, read, translated, untranslated
- language/script: Mithric, Rudishva, Thothian, unknown, etc.
- reliability: direct text, paraphrase, player interpretation, rumor
- derived claims: sourced bullets only

Tags should support retrieval:

- `media/book`, `media/map`, `media/data-crystal`, `media/scroll`, `media/library`
- `language/<slug>`
- `repository/<slug>`
- `topic/<slug>`
- `reading/unread`, `reading/partial`, `reading/read`, `translation/untranslated`, `translation/partial`, `translation/complete`

`scripts/vault_automation.py build-media-queue` scans likely media/library pages in `vault/notes`, `vault/lore`, `vault/items`, and `vault/locations`, then writes:

- `data/automation/proposals/media_improvement_queue.json`
- `data/automation/proposals/media_improvement_queue.md`

The media queue flags pages with missing source provenance, missing contents or reading/translation status, unresolved catalog markers, missing map image references, and data crystals without captured contents. It is review/research-only.

Media updates must follow the same verification rule as entity updates: a reading-derived claim can be added only when a verifier can ground it in a canonical recap or weekly digest source window. For example, reading a Rudishva data crystal may update the crystal page, a lore topic, and one or more entity pages, but each added bullet must cite the canonical source that reported the reading result.

### 6. Promotion

Promotion has two modes:

Automatic mode:

- blog recap import/update
- weekly digest import/update
- navigation link updates between known recap/digest neighbors
- inline entity links for already-promoted article pages, but only after source-context verification

Review mode:

- review `proposal.md`
- apply `proposal.patch` on a clean branch
- run validation again
- commit small scoped changes

Review mode is required for new entity page creation, entity merges, deletions, and deep research changes until the validators are strong enough to promote them safely.

Entity-link promotion uses a three-step gate:

```bash
python3 scripts/vault_automation.py propose-entity-links
python3 scripts/vault_automation.py verify-entity-links --limit 25
python3 scripts/vault_automation.py apply-verified-entity-links --apply --limit 25
```

The proposal step only matches already-promoted entity pages and writes review artifacts under `data/automation/proposals/`. The verifier step asks the local LLM to classify each proposal as `supported`, `contradicted`, `ambiguous`, or `not_found` using only the source context excerpt. The apply step writes links only for `supported` proposals and never creates pages or claims.

## Cron Shape

Replace agentic vault jobs with deterministic cron/systemd tasks:

```text
python3 scripts/vault_automation.py run-low-risk
```

`run-low-risk` performs source discovery, allowlisted canonical import, navigation refresh, review-only entity link proposal generation, optional LLM verification, and validation in one service-safe command. If `entity_link_apply_limit` is greater than zero in the ignored local config, it may also apply that many supported verified links. It writes generated operational state under `data/automation/`, which is ignored by git:

- `source_manifest.json`
- `last_validation.json`
- `runs/<run-id>/run.json`

It also refreshes the article and media improvement queues on each scheduled pass. Vault-rag refresh is a separate manual step (`refresh-vault-rag`) until the research lane is stable enough to schedule.

Systemd templates are checked in under `docs/systemd/`:

- `arden-vault-automation.service`
- `arden-vault-automation.timer`

Install them with:

```bash
sudo install -m 0644 docs/systemd/arden-vault-automation.service /etc/systemd/system/arden-vault-automation.service
sudo install -m 0644 docs/systemd/arden-vault-automation.timer /etc/systemd/system/arden-vault-automation.timer
sudo systemctl daemon-reload
sudo systemctl enable --now arden-vault-automation.timer
systemctl list-timers --all --no-pager | grep arden-vault
```

During rebuild, scheduled output should be one of:

- `[SILENT]` when no new sources or proposals exist
- a short report with paths to proposal artifacts
- an error report with failed guardrail names

The current automatic scope is limited to low-risk changes: Blogspot recap imports, weekly digest imports, and navigation refreshes. Later, automation may commit on a dedicated branch after proposal/verification gates exist for entity edits and deep research changes.

## Guardrails

Hard stop conditions:

- dirty git tree has tracked deletions before the run
- canonical vault path cannot be resolved
- source manifest points at any external RAG mirror or index as authority
- proposed patch creates `vault/Entities`, `vault/NPCs`, `vault/Items`, `vault/Locations`, `vault/Factions`, or `vault/Sessions`
- proposed patch deletes any Markdown file
- generated JSON fails schema validation
- LLM output contains tool/chat artifacts such as `<|channel>` or markdown fences around JSON
- raw Discord transcript paths or private local source paths are proposed for copying into the vault
- a Blogspot recap change alters non-link prose

## Near-Term Work Plan

1. Freeze and recover the current dirty tree.
2. Repair the Discord systemd chain so rollups are generated reliably after chat sync.
3. Extend `scripts/vault_automation.py` to discover Blogspot feed posts and external Discord digests.
4. Add recap/digest import with automatic neighbor-linking only.
5. Add inline links to already-promoted entities.
6. Add IAC/ACE promotion as a separate, guarded pipeline.
7. Use `build-article-queue` to pick weak promoted articles for RAG-grounded research.
8. Use `build-media-queue` to pick books, maps, data crystals, and library pages for downtime-reading updates.
9. Snapshot the shared spreadsheet and route changed rows into article/media/PC/item proposal queues.
10. Add deep research jobs that produce sourced article and media update proposals.
11. Refresh private RAG after accepted article/media edits.
12. Resume cron first in report mode, then enable automatic low-risk imports once validation is stable.
