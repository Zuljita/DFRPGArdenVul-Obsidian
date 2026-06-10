# Arden Vul Vault — Claude Code Guidelines

## LLM Proposal, Deterministic Validation

Use LLM reasoning for semantic proposals when the task genuinely requires
interpretation. Use deterministic code for structural operations, invariants,
allow/deny constraints, and validation before any write.

> LLMs may propose content. Code must prove the output is structurally safe to apply.

**Structural (code is correct):**
- Parsing YAML frontmatter
- Splitting text on `## ` headings
- Checking if a string contains `[[`
- Deduplicating by hash

**Judgment (LLM proposal is useful):**
- "Is this line an NPC name or a monster type?"
- "Is this claim supported by the source?"
- "Is this entity worth creating a page for?"
- "Does this excerpt match this citation?"
- "Is this alias a sub-entity or a true alternate name?"

**Deterministic safeguards are required for:**
- Exact frontmatter preservation and valid YAML
- Existing heading and wikilink preservation
- Canonical path existence and alias resolution
- Duplicate detection and transaction boundaries
- Source-boundary enforcement
- Rejecting partial or malformed LLM output

Avoid using regex or keyword heuristics as the sole authority for nuanced
content classification. They are still appropriate for explicit repository
policy, exact structural matching, and fail-closed validation.

For semantic classifications, use the existing proposer/verifier pattern
(`verify_new_entity_proposals`, `article_edit_verifier_prompt`, and related
audit steps). The applicator must independently enforce structural constraints
and reject uncertain output.

## Source Hierarchy

Primary sources (ground truth, always prefer):
1. GM session recaps in `vault/sessions/` (Blogspot imports)
2. `vault/notes/Discord Summary YYYY-WNN.md` (curated weekly digests)

Never cite raw Discord rollups as facts. Never ingest OOC tactical planning sections as in-world facts.

## Pipeline Design

- `propose-*` commands generate candidates; LLM does the identification
- `verify-*` commands apply LLM judgment to confirm or reject
- `apply-*` commands write mechanically-verified output to disk
- The verifier is the quality gate — make it strict, not the proposer

## See Also

- `AGENTS.md` — maintenance entry points and source boundaries
- `scripts/vault_automation.py` — the single consolidated harness
- `data/automation/proposals/` — proposal and verification queues (not tracked in git)
