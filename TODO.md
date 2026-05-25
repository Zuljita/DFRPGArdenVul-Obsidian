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
- Placeholder vs canonical name audit: scan and merge via aliases where a placeholder and real name both exist (example handled: Craas → Craastonistorex); compile list for review.

## Media Research Sprint (planned)

Bulk up the media/library lane. Recent IAC pass created stubs for several campaign-specific items but media coverage in the vault is still thin compared to NPCs/locations. A focused research sprint would target this area specifically.

- Run `propose-article-edits` over the media-improvement queue (already produced by `build-media-queue`) rather than the article-improvement queue, so the proposer concentrates on book/scroll/map/data-crystal/library pages.
- Treat media discoveries from Discord rollups as the primary source class: per-channel rollups under `#town-rolls`, `#downtime-activities`, and `#questions-for-gm` often contain reading results, translation progress, and catalog updates.
- Apply `media/<book|map|scroll|data-crystal|library|catalog|journal|inscription>` tags during the sprint so the existing `media_kind()` heuristic doesn't need to guess.
- Make the index page (`vault/notes/Books and Written Sources Catalog.md` and related catalogs) indicate **read status per PC**: each entry needs `reading/<pc-slug>/<unread|partial|read|translated>` tags or a structured table. Concretely: when a PC reads a book in Discord, the verifier should pick up the event and either tag the media page (e.g. `reading/vael/read`) or add a sourced bullet to the catalog page. Makes it trivial to ask "what books has Vael not read yet that we have?" for downtime planning.
- Likely needs a small extension to the article-edit lane to recognize read-status events in source text and propose tag additions (currently we only handle bullet/alias/summary additions).

## IAC Cleanup Follow-ups (from May 25 batch)

- Rudishva tech items (Rudishva Teleporter, Rudishva Teleportation Pad, Rudishva Power Disc) currently have "Rudishva" in the page name. Architecturally cleaner to rename to the bare item type (`Teleporter`, `Teleportation Pad`, `Power Disc` — or whatever the canonical noun is) and apply a `manufactured-by/rudishva` (or `tech/rudishva`) tag. Same pattern for Thothian items (Thothian Teleportation Ring etc).
- Rugs of Instant Access canonical merge: current vault has Teleport Rug (campaign-applied name), Purple Rug, Green Rug, and similar. All are the rulebook item "Rug of Instant Access" — collapse into one canonical page with aliases for each color variant. Verifier flagged Purple Rug as duplicate of Teleport Rug during the IAC pass, but the deeper merge needs manual judgement.
- Salamander Amulet: the verifier confirmed it as a campaign entity, but it's actually a DF_Adventurers rulebook item. The hybrid rules-rag check returned literal hits (DF_Adventurers p.118 §Other Items, DF_Magic_Items p.9 §Alchemical Charms) yet the verifier still confirmed because of "the party purchased one". Delete `vault/items/Salamander Amulet.md` or re-tag it as a known rulebook item.
- Imperial Field Plate, Potion of Wisdom: review whether these are rulebook variants worth deleting after manual inspection.
- Cross-candidate dedup gap: the IAC pass surfaced both `Salamander Amulets` (plural) and `Salamander Amulet` (singular) as separate candidates. The word-overlap dedup only checks against existing vault pages, not against other proposals in the same batch. Worth adding before the next IAC pass.
- The new-entity lane doesn't auto-run as part of `run-low-risk` yet — propose-new-entities/verify/apply are manual-only. Once we trust the rules-rag filter across a few more sessions of output, wire it in (with apply gated behind a small new config knob like `new_entity_apply_limit`).
