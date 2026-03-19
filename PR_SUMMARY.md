# PR Summary: Canonical Naming Fixes and Article Links

## Changes Made

### 1. Created Canonical "Rudishva Identity Plaque" Page
- **New file:** `items/Rudishva Identity Plaque.md`
- Consolidates all identity credential variants (Yellow, Rust/Brown, Sky Blue, Silver, Oval)
- Documents color-coded security system
- Links to existing `Rudishva Identity Cards.md` and `Yellow Rudishva Identity Plaque.md`

### 2. Created "Thothian Teleportation Ring" Page
- **New file:** `items/Thothian Teleportation Ring.md`
- Replaces inconsistent "Stamellis teleportation ring" references
- Documents glass activation squares, Arcanum enrichment, and network functionality
- Links from Stamelis, Arcanum, and existing auto-generated note

### 3. Created "Knight Sixth" Page
- **New file:** `npcs/Knight Sixth.md`
- Fixes "knight Sixt" → "Knight Sixth" (canonical name)
- Documents the knight being sought by companions with pale, scarred faces
- Links to Second Chance and Iris

### 4. Updated Existing Pages

#### `items/Rudishva Identity Cards.md`
- Added link to new canonical `Rudishva Identity Plaque.md`
- Updated to serve as variant catalog pointing to canonical page

#### `items/Yellow Rudishva Identity Plaque.md`
- Added link to new canonical `Rudishva Identity Plaque.md`
- Expanded with properties and Beacon system details

#### `npcs/Stamelis.md`
- Fixed "Thothian Teleportation Rings" → linked to `[[items/Thothian Teleportation Ring.md]]`

#### `items/Arcanum.md`
- Added link to `[[items/Thothian Teleportation Ring.md]]`
- Added "Related Topics" section

#### `notes/Thothian Teleportation Rings.md` (auto-generated)
- Added link to canonical `[[items/Thothian Teleportation Ring.md]]`

#### `notes/Discord Summary 2025-W43.md`
- Fixed "Sixt" → "[[npcs/Knight Sixth.md|Sixth]]"
- Updated truncation table

#### `notes/Discord Summary 2026-W04.md`
- Linked "Identity plaque" → `[[items/Rudishva Identity Plaque.md|Identity plaques]]`
- Updated truncation entry

## Naming Conventions Established

| Old/Inconsistent | New/Canonical |
|-----------------|---------------|
| knight Sixt | [[Knight Sixth]] |
| Stamellis teleportation ring | [[Thothian Teleportation Ring]] |
| Identity Plaques/ID badge/etc | [[Rudishva Identity Plaque]] |

## Next Steps for Truncated Data

The Discord summaries contain 50+ truncated entries flagged with `[TRUNCATED - needs source data]`. These require fetching from the original Discord channels:

**High Priority:**
- W43: Sligo/Leonidas story conclusion, Uvash church blueprints
- W45: Colored keycard access levels, laser weapon training
- W48: Stamelis teleport ring details, Prior of Thoth bags
- 2026-W04: Identity plaque color system (13 total truncations)

**Process:**
1. Search source Discord channels (town-rolls, archive, etc.) by date
2. Fill in truncated text in weekly summary files
3. Create/update wiki articles from complete entries
4. Check for existing articles before creating new ones
