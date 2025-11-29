# TODO

- Per-session backlinks: add a footer line to each session linking back to `[[sessions/Index]]` (or add a breadcrumb) for easy navigation.
- Entity extraction: scan sessions to identify NPCs, locations, factions, and items; create stubs in `vault/npcs/`, `vault/locations/`, `vault/factions/`, `vault/items/` with minimal front matter and tags; convert mentions to `[[wikilinks]]` where confident.
- Optional: generate a `vault/people/` or `vault/glossary/` index page grouping new entities by type.

## Library Science Follow-ups

- Enrich remaining NPCs with `gender/unknown`, `race/unknown`, `profession/unknown` defaults?
- Sweep item files for broader tagging (`item/magic` etc.) based on their descriptions?
- Add `## Connections` detail to other entrances where text allows (e.g., link exact paths between surface ↔ dungeon pages)?

## Feedback Follow-ups (thorough > fast)

- Clean malformed session wikilinks for Sessions 22, 24b, 27 across PC/NPC pages:
  - `npcs/Thoth.md` (nested/duplicated link artifacts; rumor block formatting)
  - `npcs/Ibis.md` (Session 24b and 27 lines)
  - `pcs/Vael Sunshadow.md`, `pcs/Vallium Halcyon.md`, `pcs/Ioannes Grammatikos Byzantios.md` (session link clutter)
- Verify “Announcing DFRPG Arden Vul” Coinage section formatting; fix any coding glitch.
- Confirm whether Craastonistorex is the dragon Ioannes researched; ensure cross-links/readability in relevant session/NPC pages.
- Audit “Azure Shield” mentions in Session 24b across entries; ensure clean links and no nested pipes.
- Re-check `npcs/Basilisk.md`, `npcs/Hushbreaker.md`, `npcs/Sanguinette.md` for Session 27 consistency (bullets/sources style).
- Continue LCE on hubs: Howling Caves, Glory of Thoth, Well of Light adjacencies, Great Hall ↔ beastman path, Great Chasm ladders/bridges/gates; add multi‑step Routes where sessions show chains.
- Placeholder vs canonical name audit: scan and merge via aliases where a placeholder and real name both exist (example handled: Craas → Craastonistorex); compile list for review.
- Add pre-commit hook + PR job to run `scripts/lce_extract.py` in report mode on changed sessions; attach report to PRs.
