# Vault Cleanup Journal

Purpose: Track chunked Significant NPCs cleanup, link normalization, and stub creation so we can resume seamlessly.

## Session Chunk: 28–20 (COMPLETED)
- Actions:
  - Migrated Sundered Span to `locations/` and fixed links.
  - Deterministic link fixes + bracket balance (nested/malformed links resolved).
  - Added helper scripts: `scripts/check_wikilinks.py`, `scripts/fix_sessions_20_28.py`.
  - Created stubs: Sligo the Devious, Leonidas of Archontos, GOAT, Licinia the Seer, Nyema, Right for Riches Company, Guild of Service (moved to factions), Rugs of Instant Access.
  - Created named ape stubs: Yrsko, Umsko; life-stone owner: Schist Corundam; tomb figures: Thrygga the Mighty, Theskalon the Master.
  - Added `locations/Barracks of the Old Ones.md` and linked references.
  - Linked within sessions (Rugs, Company, named NPCs) and revalidated: 0 missing, 0 unbalanced in modified files.

## Session Chunk: 10–1 (IN PROGRESS – PREVIEW)
- Tools prepared:
  - `scripts/generate_stubs_from_significant.py` (now supports `--preview --create` and file lists; safer filters).
  - `scripts/enrich_significant_npcs.py` (adds `[[npcs/Name]]` and race/faction links in Significant NPCs blocks, when pages exist).
- Preview results (no writes):
  - Many early sessions contain multiple “Significant NPCs” sections, often listing monsters/generics rather than proper names (e.g., “Mountain Lion”, “6 Stirges”).
  - Named individuals are present in narrative text (e.g., Brokenneck, Ketil, Marco) but not consistently in Significant NPCs lists.
  - Early sessions (1–4 esp.) have numerous malformed/nested wikilinks which impede reliable extraction.
- Status:
  - Enrichment pass for 1–10 made no changes (by design) to avoid touching malformed content.
  - Next, we should normalize links in sessions 1–10, then re-run Significant NPC extraction and apply stubs/links.

## Next Actions
1) Deterministic link cleanup for Sessions 10–1 (DONE)
   - Scope: fix nested/malformed `[[...]]`, close brackets, normalize common location links (Long Stair, Gosterwick, Well of Light, Pyramid of Thoth).
   - Approach: adapt `scripts/fix_sessions_20_28.py` to sessions 10–1, guarded replacements to avoid double expansions.
   - Validation: run `scripts/check_wikilinks.py` over the chunk to reach 0 unbalanced / 0 missing.

2) Re-run Significant NPCs enrichment for Sessions 10–1 (PREVIEWED)
   - `generate_stubs_from_significant.py --preview` (confirm candidates), then `--create` for vetted names only.
   - `enrich_significant_npcs.py` to insert NPC + race/faction links in Significant NPC blocks.
   - Add race links to Thorcin/Goblins/Varumani/Halflings as appropriate.

3) Narrative pass for named individuals (optional, post-normalization)
   - Use `scripts/entity_curator.py` with local Qwen (chunked) to extract candidates from narrative text.
   - Map to existing pages/aliases and create stubs only for clear individuals (skip summons/generics).

## Session Chunk: 11–19 (COMPLETED)
- Actions:
  - Normalized/cleaned malformed links across Sessions 11–19 (titles + nested links fixed).
  - Validated: 0 missing and 0 unbalanced for all files in this chunk.
  - Significant NPCs preview produced no safe new candidates (blocks are mostly monsters/generics here); holding stubs for narrative extraction later.

## Resume Pointer
- Current target: Sessions 20–28 already completed; Sessions 11–19 complete.
- Next: Apply Significant NPC narrative pass for 1–19 (optional), or proceed to Sessions 33+ if present.

## Notes / Decisions
- Races modeled as factions (Thorcins, Varumani, Goblins, Halflings). We’ll link to these in Significant NPCs where data exists.
- NPC Index created: `npcs/Index.md` (recent additions) to make new entries findable.
- Avoid creating stubs for summons/generics (e.g., “Summoned X”, “Many goblins”, “Pig-Headed Beastman”).

## NPC Folder Hygiene (Round 1)
- Actions (Nov 26):
  - Reclassified misfiled location pages from `npcs/`:
    - Moved content for Newmarket into `locations/Newmarket.md` (added Appears In + Timeline), removed `npcs/Newmarket.md`.
    - Created `locations/Imperial Road.md` from `npcs/Imperial Road.md` notes; removed misfiled NPC page.
    - Created `locations/Water Gate.md`, `locations/Goblin Great Hall.md`, `locations/Upper Goblintown.md`, and `locations/Upper Market.md` from corresponding misfiled `npcs/` pages; removed those NPC pages.
    - Moved `npcs/Iconic Location.md` to `lore/Iconic Location.md` and updated inbound links.
  - Normalized an explicit path link in `locations/Waterfall.md` from `[[npcs/Newmarket.md|Newmarket]]` → `[[Newmarket]]`.
- Validation:
  - Ran `scripts/check_wikilinks.py` on `locations/Newmarket.md` and `locations/Imperial Road.md`: 0 unbalanced, 0 missing.
- Notes:
  - `locations/Waterfall.md` still contains many legacy malformed links unrelated to this change; leave for a dedicated cleanup pass.
  - Consolidated NPC duplicates:
    - `npcs/Gosterwick Audun Yellow-Eyes.md` merged into canonical `npcs/Audun Yellow-Eyes.md` (added alias).
    - `npcs/King Weskenim.md` and typo `npcs/King Wiskenim.md` merged into canonical `npcs/Weskenim.md` (added aliases), then removed.

## Link Normalization (Round 2)
- Actions:
  - Added `scripts/normalize_npc_links.py` to systematically fix misfiled `[[npcs/...]]` links.
  - Rules applied:
    - Redirect to locations: `Gosterwick`, `Goblintown`, `Great Chasm`, `Great Hall`.
    - Downgrade to plain text (no link) for spells and scaffold/generics: `Archontean`, `Many`, `Ruins`, `Shape Earth`, `Water Vision`, `Levitate`, `Levitation`, `Wizard Eye`, `Apportation`, `Secrets`, `March`, `Forum`, `Pyramid`, `Cave`, `Cavern`, `Stair`, `Well`, `Cliff Face`, `Climbing`, `Stone`, `Light`, `Flight`, `Darlings`, `Baboons`, `Beastmen`, `Goblins`, `Halflings`, `In Gosterwick`, `There`, `Also`, `Instead`, `Just`, `Next`, `Still`, `Somehow`, `Quickly`, `Tongues`.
  - Ran the script across `vault/` and updated 16 location files plus related pages.
  - Removed misfiled spell page: `npcs/Shape Earth.md`.
- Validation:
  - Re-ran `scripts/check_wikilinks.py` on heavy offenders (`locations/Waterfall.md`, `locations/Well of Light.md`, `locations/Great Cavern.md`): number of missing generic `npcs/...` targets substantially reduced; remaining issues are PCs/NPCs and complex phrases to address later.

## NPC Folder Hygiene (Round 3)
- Actions:
  - Reclassified and consolidated entities flagged by manual + LLM triage:
    - Broken Head: added aliases ("Broken Head", "Sign of the Broken Head") to `locations/Inn of the Broken Head.md`; removed `npcs/Broken Head.md`.
    - Bottomless Purse: created `items/Bottomless Purse.md` and removed `npcs/Bottomless Purse.md`.
    - Crackers: removed `npcs/Crackers.md` (party nickname, not an entity).
    - Dirty starving crazy woman with a giant magic belt → alias on `npcs/Lytta - Versania.md`; removed the fragment page.
    - Demon generics: removed `npcs/Demon.md`, `npcs/Alleged huge ball-shaped demon.md`, `npcs/Small ball-shaped rolling demon.md` (retain named demon `Rizzit` only).
    - Broken Head Lankios: added alias to `npcs/Lankios.md`; removed `npcs/Broken Head Lankios.md`.
- Validation:
  - Searched for inbound links to removed pages; none with explicit `[[npcs/...]]` targets required updates. Location aliases ensure `[[Broken Head]]` resolves.

## NPC Folder Hygiene (Round 4)
- Actions:
  - Aliased “Weird guy who hangs out with baboons” → `npcs/Gerrilad.md` and removed the fragment page earlier.
  - Restored `npcs/Zombie porter.md` as an episodic NPC stub (mentioned across multiple sessions).
  - Added named mule `npcs/Inventorium Burdenus Maximus.md` with aliases: Unnamed large mule, Bernie, Max, Bernie Mac, stupid fleabag.
- Script update:
  - Removed `Zombie porter.md` and `Unnamed large mule.md` from the “plain text” normalization list to preserve them as entities going forward.

## NPC Folder Hygiene (Round 5)
- Consolidations:
  - Yrtol: set canonical `npcs/Yrtol.md` and added alias “Yrtol the Angry Ghost”; removed variant page.
  - Thronebreaker: consolidated under `npcs/Thronebreaker.md` with aliases “Thrainor Ironvein” and “Thrainor "Thronebreaker" Ironvein”; removed duplicate `npcs/Ironvein.md`; fixed link in `locations/Great Cavern.md`.
  - Ibis-headed Guardian(s): added alias to singular page and removed plural variant.
- Affiliations:
  - Noted Thronebreaker is a member of the [[factions/Grudge Brigade.md|Grudge Brigade]].

## NPC Folder Hygiene (Round 6)
- Consolidations and removals:
  - Green Lady → alias on `Lady Alexia Basileon`; removed `npcs/Green Lady.md`.
  - Huguette: added alias “Huguette, varlet to Sir Sorrow”; removed variant page.
  - Larel: canonical `Larel One-Eye` with alias “Larel”; removed `npcs/Larel.md`.
  - Rizzit: alias “Rizzit, demon” on canonical `npcs/Rizzit.md`; removed variant page.
  - Created `npcs/Brokenneck.md`; removed long fragment page.
- Generics/monsters unlinked → plain text; removed pages:
  - Flaming skull, Dire snapping turtle, Invisible Stalker, Ghoul, Set Guards, Goblin.
- PCs and deities hygiene:
  - Repointed `Dundee` links to `pcs/Michael J. Dundee.md`; removed `npcs/Dundee.md`.
  - Added alias “Lord Thoth” → `npcs/Thoth.md`; removed `npcs/Lord Thoth.md`.
- Link fixes across locations:
  - Converted Goblin links to `[[factions/Goblins|Goblin]]`.
  - Fixed Roskelly links to `[[npcs/Roskelly Winterleaf|Roskelly]]`.
  - Converted Ghouls/Invisible Stalker/Set Guards mentions to plain text where present.

## NPC Folder Hygiene (Round 7)
- Purpose: Consolidate Stamelis variants and fix Library link target.
- Aliases added:
  - `npcs/Stamelis.md` — added aliases: "Animated bust of Stamelis, Librarian of Thoth", "Magically animated head of Stamelis".
- Pages removed:
  - `npcs/Animated bust of Stamelis.md`
  - `npcs/Magically animated head of Stamelis.md`
- Links fixed:
  - `locations/Library of Thoth.md` — Residents list now links to `[[npcs/Stamelis.md|Stamelis]]` (removed variant targets).
- Validation:
  - Ran `scripts/check_wikilinks.py vault/locations/Library\ of\ Thoth.md`.
  - Stamelis-related links resolve; file still contains pre-existing missing links and nested-link issues to be handled in Backlog #9.

## Links & PCs (Round 8)
- Purpose: Final pass on generics and ensure PCs are under `pcs/`.
- Generics scan:
  - Searched for lingering `[[npcs/Ghouls]]`, `[[npcs/Set Guards]]`, `[[npcs/Invisible Stalker]]`, and `[[npcs/Goblin]]` → no remaining matches.
- Roskelly hygiene:
  - Updated `locations/Muirasso's Tomb.md` to `[[npcs/Roskelly Winterleaf.md|Roskelly]]`.
  - Removed fragment `npcs/Roskelly and several halfling toll collectors.md` and adjusted the link to plain text suffix.
- PCs under pcs/ (repointed):
  - Replaced `[[npcs/Ioannes.md|Ioannes]]` → `[[pcs/Ioannes Grammatikos Byzantios.md|Ioannes]]`.
  - Replaced `[[npcs/Michael.md|Michael]]` → `[[pcs/Michael J. Dundee.md|Michael]]`.
  - Replaced `[[npcs/Uvash.md|Uvash]]` → `[[pcs/Uvash Edzuson.md|Uvash]]`.
  - Replaced `[[npcs/Vael.md|Vael]]` → `[[pcs/Vael Sunshadow.md|Vael]]`.
  - Replaced `[[npcs/Vallium.md|Vallium]]` → `[[pcs/Vallium Halcyon.md|Vallium]]`.
- Affected files:
  - `locations/Waterfall.md`, `Well of Light.md`, `Tomb of Theskalon.md`, `Tomb of Ptoh.md`, `Shrines.md`, `Pyramid of Thoth.md`, `Oracle of Thoth.md`, `Muirasso's Tomb.md`, `Library of Thoth.md`, `Hall of Judgment.md`, `Great Cavern.md`, `Glory of Thoth.md`, `Forum of Arden Vul.md`.
- Validation:
  - Ran link checker on the above files; many pre-existing missing targets remain (monsters/generics and malformed links) to be addressed by Backlog #9 and #10.

## Nested Links Cleanup (Round 9)
- Purpose: Fix nested/malformed location link patterns in key files.
- Tool:
  - Added `scripts/fix_nested_wikilinks.py` (conservative regex for `[[locations/The [[locations/X.md|X]].md|The [[locations/X.md|X]]]]` → `[[locations/X.md|The X]]`).
- Updated files:
  - `locations/Great Cavern.md`, `locations/Library of Thoth.md` (initial pass), then broadened to: `locations/Tomb of Theskalon.md`, `locations/Howling Caves.md`, `locations/Great Hall.md`, `locations/Goblin Market.md`, `locations/Goblintown.md`.
- Validation:
  - Ran `scripts/check_wikilinks.py` on both files; nested link errors reduced. Remaining issues are unrelated to this pattern and will be handled in subsequent cleanup passes.

## Malformed Links Cleanup (Round 12)
- Tool updates:
  - Enhanced `scripts/fix_nested_wikilinks.py` to:
    - Strip nested links inside outer link labels (e.g., session links containing location links in labels).
    - Collapse links whose TARGET contains a nested wikilink to plain text.
    - Close unclosed `[[sessions/...|Label` at end-of-line and split long labels at `—` into `[[...|Label]] — text`.
- Applied to files with nested patterns (automated find):
  - Locations: Great Cavern, Waterfall, Well of Light, Tomb of Theskalon, Library of Thoth, Howling Caves, Hall of Judgment, Great Hall, Great Chasm, Goblin Market, Goblintown, Yellow Cloak Inn, Muirasso's Tomb.
  - Also cleaned nested label cases found in items/, factions/, pcs/, and relevant npcs/ pages where session links appear in labels.
- Results:
  - Great Cavern and Waterfall: all unbalanced `[[...]]` resolved for modified lines.
  - Library of Thoth: now 0 missing/0 unbalanced (for scope changed).
- Remaining missing links are generics/spells/items to be handled by normalizer evolution and content triage (later rounds).

## IAC Pass (Round 13)
- Scope: Run Identifying Article Candidates on Session 32 and 31.
- Tooling: `scripts/run_iac.py` with filters loaded from `config/entity_filters.json`.
- Session 32: All candidates mapped; no new stubs created.
- Session 31: Mapped PCs/NPCs/Factions; created deity stubs `npcs/Anubis.md`, `npcs/Horus.md`.
  - Corrections: Avoided noisy creations by adding stoplists; moved `Mithric` to `lore/Mithric.md` (normalizer redirect) and removed `Varuda` (added to `stop_factions`).
- Filters: Added `stop_factions` (None, Archon(s), Archonteans, Legionnaires, Priests of Thoth/Set/Horus, Varuda) and `stop_npcs` (Ashe the Goblin, Vael Lockmaster). Added GM spells from RawFiles/Discord/NewSpells.txt.
- Normalizer redirects: `Ashe -GOAT- Maykum.md` → `npcs/Ashe Maykum.md`; `Mithric.md` → `lore/Mithric.md`.
- Validation: `scripts/check_wikilinks.py` on Session 31 now clean (for scope changed).

## IAC Pass (Round 14)
- Scope: Session 29 — NPC, Location, Faction (items excluded).
- Stoplists: Expanded `stop_location` with common room/feature descriptors (spiral stairs/rooms, graveyard rooms, pits, stairways, etc.) and added faction noise (clerics, goblin guards, wraiths, right for riches, set outpost). This keeps IAC creations clean.
- Run results:
  - Mapped: expected NPCs/PCs; locations like Tower of Scrutiny, Gosterwick, Pyramid of Thoth, Well of Light, Howling Caves, Long Stair, Upper Goblintown, Glory of Thoth, Halls of Thoth; faction Right for Riches Company.
  - Creations: none retained. Two accidental room-feature stubs were briefly created (`locations/Room with Spiral Stairs.md`, `locations/Small Room with Two Exits.md`); both removed and phrases added to `stop_location` to prevent reoccurrence.
- Validation: No missing entities introduced by this pass.

## IAC Pass (Round 13)
- Scope: Identifying Article Candidates on Session 32 (working backwards).
- SOP: documented IAC/ACE in `docs/SOP_IAC_ACE.md`.
- Tooling: added `scripts/run_iac.py` (chunks text, uses local LLM for candidate extraction, fuzzy/alias mapper, safe stub creation).
- Results (Session 32):
  - Mapped to existing pages (examples): Akla-Chah, (PCs) Vallium/Ioannes/Vael/Uvash/Michael J. Dundee, Lacrymosa (Merenuithiel Armaris), King Weskenim, Temrin, Ummchark, Hallsted, Claudine, Rizzit, Palestrim, Hal, Keth, Isidor; Locations like Great Cavern/Long Stair/Goblin Great Hall; Factions Varumani, Survivors of the Stone, Dalton's Darlings; Items Rugs of Instant Access, Larel's Cloak, Ring of Free Action, Bag of Holding.
  - New stubs created: none (all candidates resolved to existing or aliases; noisy generics/spells were filtered).
- Next: proceed to Session 31 with IAC; only create stubs for true individuals/factions/items (not spells or room descriptors).

## Normalizer Evolution (Round 10)
- Purpose: Demote additional scaffold/generic `npcs/` links to plain text and add targeted redirects.
- Script updates: `scripts/normalize_npc_links.py`
  - Added TO_PLAIN entries: Basilsday, Tahsday, Library, logovores, Giant lizard, Skeleton, Ibis constructs of Thoth.
  - Added TO_REDIRECT entries to repoint `npcs/` → canonical pages:
    - PCs: Ioannes → `pcs/Ioannes Grammatikos Byzantios`, Michael → `pcs/Michael J. Dundee`, Uvash → `pcs/Uvash Edzuson`, Vael → `pcs/Vael Sunshadow`, Vallium → `pcs/Vallium Halcyon`.
    - Weird combo: `Thoth Umsko` → `npcs/Umsko`.
- Run: Executed normalizer across `vault/` (11 files updated; mainly location pages touched earlier).
- Validation: Re-checked key files (`Library of Thoth`, `Great Cavern`, `Tomb of Theskalon`, `Well of Light`). Missing links reduced substantially on changed files; remaining issues are unrelated generics (items/ spells/ monsters) or long nested session excerpts to be handled in later passes.

## NPC Folder Hygiene (Round 11)
- Consolidations:
  - Skalla: canonical `npcs/Skalla.md`; added aliases "Skalla, skeleton warrior" and "Thoth Skalla". Removed `npcs/Skalla, skeleton warrior.md` and `npcs/Thoth Skalla.md`. Updated links in `Waterfall.md` and `Well of Light.md` to point at `Skalla`.
  - Sparky: kept `npcs/Sparky the goat.md` with alias "Sparky"; removed `npcs/Sparky.md`.
- Reclassifications:
  - Created `locations/Arden Vul.md` and redirected links from `[[npcs/Arden Vul.md|...]]` to `[[locations/Arden Vul.md|...]]` via normalizer. Removed `npcs/Arden Vul.md`.
  - Moved group to faction: `npcs/Survivors of the Stone, dwarven adventuring party.md` → `factions/Survivors of the Stone.md` (with alias). Updated links in `Great Cavern.md` and `Session 32`.
- Generics/scaffolding demoted to plain text and pages removed:
  - Demoted via normalizer: Again, Stuff, The Rescuers, The Set Cult Strikes Back, Undead librarian, clockwork dragonfly.
  - Deleted pages after demotion: `npcs/Again.md`, `npcs/The Rescuers.md`, `npcs/The Set Cult Strikes Back.md`, `npcs/Undead librarian.md`, `npcs/clockwork dragonfly.md`.
  - Deleted unused monster/generic stubs with no inbound links: `Assassin Vine`, `Carcass creeper`, `Chasm Kraken`, `Dust monster`, `Gelatinous Cube`, `Large Black Pudding`, `Lizardman`, `Magic Mouths`, `Mummy`, `Set animals`, `Several Set guards`, `Sheep-headed Critters`, `Skeleton`.
- One-off cleanup:
  - Removed stray `npcs/Arden Vul Iconic Locatons.md` (typo fragment).
- Validation:
  - Ran `scripts/normalize_npc_links.py` and `scripts/check_wikilinks.py` on updated hotspots. Remaining issues are session-excerpt artifacts and other generics to be addressed in subsequent passes.

## Structural Cleanup
- Archived obsolete one-off fixer scripts to reduce clutter:
  - Moved `scripts/fix_sessions_1_10.py`, `scripts/fix_sessions_11_19.py`, `scripts/fix_sessions_20_28.py` → `scripts/archive/`.
- Reclassifications:
  - Created `locations/Troll Lifts.md`; removed `npcs/Troll Lifts.md`.
  - Removed fragment `npcs/Wight In Gosterwick.md` (covered by canonical `npcs/Wight.md`).
  - Created `locations/Scorpion Teleporter.md` and `locations/Swift River.md`; removed `npcs/Scorpion Teleporter.md` and `npcs/Swift River.md`.
  - Updated `Pyramid of Thoth`, `Glory of Thoth`, `Well of Light`, `Waterfall`, and `Hall of Judgment` to link to the new location pages.
  - Converted `[[npcs/Scrutiny]]` links to `[[locations/Tower of Scrutiny|Scrutiny]]` and removed `npcs/Scrutiny.md`.
  - Factions moved from `npcs/`:
    - Added `factions/Green Fang Kobolds.md` and `factions/Five Families.md`; removed `npcs/Green Fang Kobolds.md` and `npcs/Five Families.md`.
    - Added aliases on `factions/Grudge Brigade.md` (“Grudge Brigade Mercenary Company”) and `factions/Hama and Company, adventurers.md` (“Hama and Company”); removed `npcs/Grudge Brigade Mercenary Company.md` and `npcs/Hama and Company.md`.
- Link corrections:
  - `locations/Tomb of Theskalon.md`: `[[npcs/Club Creon.md|Club Creon]]` → `[[npcs/Creon.md|Creon]]`.
  - Faction/location redirects: Updated links to canonical pages and removed `npcs/` duplicates.
    - `[[npcs/Rarities Factor]]` → `[[factions/Rarities Factor]]` (and removed `npcs/Rarities Factor.md`).
    - `[[npcs/Prosperity Factor]]` → `[[factions/Prosperity Factor]]` (and removed `npcs/Prosperity Factor.md`).
    - `[[npcs/Varumani]]` → `[[factions/Varumani]]` (and removed `npcs/Varumani.md`).
    - `[[npcs/Narsileon]]` → `[[locations/Narsileon]]` (and removed `npcs/Narsileon.md`).
    - Removed `npcs/Sun-Scarred Knights.md` in favor of `factions/Sun-Scarred Knights.md`.
    - Removed `npcs/Azure Keep.md` (exists in `locations/`).
- Generic/fragments removal (after link cleanup):
   - Deleted no-longer-linked pages: One skeleton, Skeleton cook, Shambling Mound, Phase spider, Mountain Lion, Walking Pigs, Pig-headed beastman, Telepathic Gold Cat Statue, Zombie porter, Unnamed large mule, Weird guy who hangs out with baboons.

## IAC Pass (Round 15)
- Scope: Session 28 — NPC, Location, Faction (items excluded).
- Stoplists: Reused filters from `config/entity_filters.json` (no changes needed after Round 14 expansions).
- Mapped and linked (first mention per file):
  - NPCs: Theopilos, Egill Flat-nose, Grugga, Stamelis, Yamki, Trefko, Burris, Ghost of Ptirasa, Skalla, Bottleneck.
  - Factions/Locations: Rarities Factor (faction), Narsileon (location). Left Baliff's Truncheon as plain text pending filename normalization elsewhere (existing vault link checker flags it).
- Creations: none. No new stubs introduced.
- Validation: `scripts/check_wikilinks.py` on Session 28 returns clean for this scope.

## IAC Pass (Round 16)
- Scope: Sessions 27 → 20 — NPC, Location, Faction (items excluded).
- Method: Followed SOP. Linked first mentions within each file, focused on Significant NPCs sections; avoided generics and spells. Reused stoplists from `config/entity_filters.json`.
- Mapped/linked highlights:
  - S27: Vivian; Sanguinette; Bottleneck.
  - S26: Briar; Phlebotomas Plumthorn; Roskelly Winterleaf; Blandveg; Bottleneck; Killick; Weskenim; Gribble; Palestrim; Skimmel; Reeflik; Sir Sorrow; Huguette; Rizzit; Claudine of Narsileon; Thorgrim the Easy; Leifcrim.
  - S25: Barnaby Goodbarrel; Yrtol; Varumani (faction).
  - S24a: Jador the Just; Audun Yellow-Eyes; Freydis the Stern; Knights of the Azure Shield (faction); Sparky the goat; Apophis the giant lizard.
  - S24b: Roskelly Winterleaf; Ibis-headed guardian(s) of Thoth; Knights of the Azure Shield (faction).
  - S23a: Lillian; Kronos; Slime Kraken; Susarra.
  - S23b: Lillian; Susarra.
  - S23c: Susarra; Hidlat; Kathroc; Lenuel; Eadgithu; Geleg; Lillian; Azgallatu; Grist the Hammer; Gribble; Killick (via alias); Pelestrim; Weskenim; Jador the Just; Anaximander.
  - S22: Yamki; Anaximander; Stamelis.
  - S21: Isocritis Half-Hand; Stamelis; Umsko; Yamki; Thalia; Fetch.
  - S20: Egrk.
- Creations: none. No new stubs introduced.
- Validation: `scripts/check_wikilinks.py` run on all updated sessions — no missing targets for new links.

## Filename Hygiene
- Normalized: `vault/locations/Baliff\'s Truncheon.md` → `vault/locations/Baliff's Truncheon.md` (removed stray backslash).
- Validation: Link targets now resolve in `locations/Gosterwick.md` and any `[[Baliff's Truncheon]]` references.

## IAC Pass (Round 17)
- Scope: Sessions 19 → 15 — NPC, Location, Faction (items excluded).
- Method: Conservative first-mention links in Significant NPCs blocks; avoided generics (monsters/constructs) per SOP.
- Mapped/linked highlights:
  - S19: Kronos; Lankios; Ibis-headed guardian of Thoth; Sekhmet; Osiris.
  - S18: Yrsko; Brokenneck; Marco; Ketil; Egrk; Stamelis.
  - S17: Lankios.
  - S16: Gerrilad; Sisko; Trefko; Njal; Samantha the Red; Tresti; Gwelf; Jost; Dalton; Jason; Helga. Left Heliagabulus/Isisor/Yvette unlinked (no pages).
  - S15: Camilla.
- Creations: none. No new stubs introduced.
- Validation: `scripts/check_wikilinks.py` on all updated sessions — clean.

## IAC Pass (Round 18)
- Scope: Sessions 14 → 10 — NPC, Location, Faction (items excluded).
- Linked first mentions in Significant NPCs:
  - S14: Lytta/Versania; Camilla; Vivian; Jador the Just.
  - S13: Hama and Company (faction); Yrtol; Camilla.
  - S12: Fael; Onyx; Skizz and Burzip.
  - S11: Klisko.
  - S10: Sakeon; Fael; Kronos Kettle-Belly; Estelle.
- Creations: none. No new stubs introduced.
- Validation: `scripts/check_wikilinks.py` on updated sessions — clean.

## IAC Pass (Round 19)
- Scope: Sessions 9 → 1 — NPC, Location, Faction (items excluded).
- Linked first mentions:
  - Sessions 8b/9: Muirasso; Gog; Roskelly; Eggbert; Kronos Kettle-Belly; Estelle; Crisarius Three-Legs; Fenitior Stone-Hands; Godric the Wise.
  - Session 1: Knights of the Azure Shield (faction).
- Others (2–6): Significant NPCs blocks are empty; no changes required.
- Validation: `scripts/check_wikilinks.py` on changed files — clean.

## Session 7 Split (partial)
- Extracted non-session blog note from Session 7 into `notes/Choice Density and Loose Ends.md` and added cross-link.
- Normalized Freydis links to canonical `npcs/Freydis the Stern.md` in Sessions 7 and 8a.
- Note: Session 7 contains appended content for later sessions (e.g., 8a); next pass will truncate file to only Session 7 content now that the standalone 8a/8b pages exist.

## Link Fixes (Targeted)
- Session 2: Linked Margot the Red in Significant NPCs.
- Session 4: Linked Roskelly Winterleaf in Significant NPCs.
- Session 5: Linked Roskelly Winterleaf, Count Skleros, Bellringer; normalized Freydis link.
- Session 6: Linked Jacobus (first mention in Significant NPCs).
- Session 7: Removed stray, out-of-context halflings line.
- Session 8a: Linked Sir Lucia; Sir Basil; Sir Irene; Alexios; Demetrios; Zoe; Phlebotomas Plumthorn; Roskelly Winterleaf; Dalton; Helga; Isidor; Gog. Updated Dalton’s Darlings to faction link.
- Session 10: Linked Unnamed large mule → [[npcs/Inventorium Burdenus Maximus]].
- Dalton’s Darlings: Removed NPC duplicate `npcs/Dalton's Darlings, adventuring party.md`; updated inbound links to `factions/Dalton's Darlings.md` (Great Cavern, Sessions 8a/22/23c/32).

## Feedback Applied
- Coinbase: Merged variants. Added alias "Coinbase Ethereum Thuringwador" to `npcs/Coinbase.md`; removed duplicate `npcs/Coinbase Ethereum Thuringwador.md`.
- Dalton’s Darlings: Confirmed faction exists; annotated `npcs/Dalton.md` affiliations → member of `[[factions/Dalton's Darlings]]`.
- Session 23a amalgam: Removed erroneous `npcs/Ghouls Gelatinous Cube Slime Kraken Susarra.md` (artifact of combined NPC list); session already links individual entities.
- Unknown alchemist → Blandveg: Added aliases to `npcs/Blandveg.md` for "Unknown human alchemist" variants; linked Significant NPCs in Sessions 7 and 8a to Blandveg.
- Session 7 multi-session note: Marked for future split/triage (contains multiple sessions worth of data); will handle in a dedicated pass.
