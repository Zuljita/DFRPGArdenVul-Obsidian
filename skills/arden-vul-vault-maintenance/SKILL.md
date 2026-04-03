---
name: arden-vul-vault-maintenance
description: Legacy AVV maintenance skill retained for compatibility. Route to the new linked workflow stack beginning with arden-vul-vault-core and arden-vul-vault-context.
---

# Arden Vul Vault Maintenance (Legacy Redirect)

Deprecated for new work.

## Use this route
1. `arden-vul-vault-core`
2. `arden-vul-vault-context`
3. Primary execution skill:
   - GM recap/session-safe edits: `arden-vul-gm-recaps`
   - Entity extraction: `arden-vul-vault-extraction`
   - Weekly summary/entity enrichment: `arden-vul-discord-summary-enrichment`
   - Reconcile/QA before merge: `arden-vul-vault-qa-reconcile`
   - Uncertain identity research: `arden-vul-vault-research-assistant`

## Rule
Do not perform recap-body rewrites from this legacy skill.
