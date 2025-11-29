# TODO

- Per-session backlinks: add a footer line to each session linking back to `[[sessions/Index]]` (or add a breadcrumb) for easy navigation.
- Entity extraction: scan sessions to identify NPCs, locations, factions, and items; create stubs in `vault/npcs/`, `vault/locations/`, `vault/factions/`, `vault/items/` with minimal front matter and tags; convert mentions to `[[wikilinks]]` where confident.
- Optional: generate a `vault/people/` or `vault/glossary/` index page grouping new entities by type.

## Library Science Follow-ups

- Enrich remaining NPCs with `gender/unknown`, `race/unknown`, `profession/unknown` defaults?
- Sweep item files for broader tagging (`item/magic` etc.) based on their descriptions?
- Add `## Connections` detail to other entrances where text allows (e.g., link exact paths between surface ↔ dungeon pages)?
