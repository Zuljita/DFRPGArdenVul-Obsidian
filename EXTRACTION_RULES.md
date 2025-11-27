# Entity Extraction & Linking Rules

These rules guide creating and linking entities from session logs. They aim to be conservative, consistent, and avoid noise.

## Locations
- Only create when specific and named:
  - Patterns: “X of Y” where X ∈ {Well, Hall(s), Temple, Forum, Library, Tower, Tomb, Cavern, Inn, Oracle, Stair, Bridge, Pyramid, Market, Dam}.
  - Named prefixes: “Great …”, “Long …”, “Inn of …”, “Halls of …”.
- Do not create for generic terms: “chasm”, “cave(s)”, “hall(s)”, “stairs”, “river”, “bridge” (unless named as above).
- Prefer canonical names (e.g., “Halls of Thoth”, “Forum of Set”, “Long Stair”).

## NPCs
- Create for clearly named people/creatures:
  - Proper nouns and appositives: “Name, role”.
  - Possessives indicating identity: “Plumthorn’s gang” → faction; “Plumthorn” → NPC.
- Ignore generic groups: “several mages”, “many goblins/goats”, “varumani guards”. Keep as plain text.
- Do not create for function words or sentence fragments.

## Factions
- Create when group identity is explicit:
  - Keywords: Cult, Order, Knights, Brigade, Empire, Guild, College, Company, Band, Gang, Temple Guard.
  - Adventuring parties are factions (unless you decide to keep a separate “parties” folder).
- Individuals with titles (Sir/Lady/Count/… or “Name, role”) are NPCs; attach `member_of` to their NPC pages.

## Items
- Create for named artifacts/treasure (e.g., Regalia, magic items).
- Do not create for spells/abilities.

## Spells & Abilities (never entities)
- Examples: Levitate/Levitation, Apportation, Gift of Tongues, Great Haste, Water Vision, etc.
- Remove/avoid links for these; keep as plain text.

## Linking
- First-mention linking only per file.
- Don’t link inside existing wikilinks.
- Don’t link inside front matter (YAML) or headings (H1).
- Avoid linking generic words; maintain an ignore list.

## Hygiene
- Reclassify misfiled pages (e.g., cities under `locations`, cultures/factions under `factions`).
- Merge duplicates via `aliases` in canonical pages; delete variants.
- Purge location-derived NPC stubs; attach their history notes to the location’s page.
