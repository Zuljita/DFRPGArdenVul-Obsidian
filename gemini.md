# AGENT.md Content

# Repository Guidelines

## Project Structure & Module Organization
- Vault: `vault/` (all player/GM notes). Keep content here.
- Examples: `sessions/`, `npcs/`, `locations/`, `factions/`, `items/`, `attachments/`.
- Imports: `RawFiles/` (raw text or source material to adapt into notes).
- Maintainer-only: `quartz/` (Quartz project). Contributors do not edit.

## Build, Test, and Development Commands
- Edit: Open `vault/` in Obsidian.
- Preview site (maintainer): `cd quartz && pnpm dev` (local dev server; watches `../vault`).
- Build site (maintainer): `cd quartz && pnpm build` → output in `quartz/public/`.
- Link check: ensure build completes without missing pages; fix or create stubs.

## Coding Style & Naming Conventions
- Markdown only; use clear headings (`#`, `##`) and short sections.
- Use Obsidian wikilinks: `[[Page Name]]`. Prefer Title Case page names that match file titles.
- One concept per file; place in the appropriate folder (e.g., `npcs/Elara Brightshield.md`).
- Don’t move core folders; if renaming pages, enable Obsidian “Automatically Update Links”.
- Assets: store images/files in `attachments/` and link relatively.

## Testing Guidelines
- No code tests; content “tests” are: (1) Quartz preview/build succeeds, (2) no broken links, (3) all new wikilinks resolve or have stubs.
- Create stubs for new entities with a short summary and TODOs.

## Commit & Pull Request Guidelines
- Commits: small and scoped. Suggested format: `content(scope): summary`.
  - Example: `content(sessions): add session 12 recap`.
- PRs should include: purpose, affected paths (e.g., `npcs/*`, `locations/*`), screenshots of local preview (optional), and linked issue if applicable.

## Security & Configuration Tips
- Do not include secrets or personal data; redact sensitive details.
- `.obsidian/` is editor config; keep minimal and avoid plugin-specific features when possible.
- Contributors sync/edit only `vault/`. Maintainer handles Quartz builds and hosting.

---

# project_plan.md Content

# DFRPG Arden Vul — Project Plan



This document explains the **lightweight, non-enterprise** workflow for building a player-facing campaign reference for DFRPG Arden Vul using:



* **Obsidian** (authoring + linking)

* **LLM assistance** (article creation + auto-linking + structuring)

* **Quartz** (static site generator)

* **Azure Static Web Apps** (free-tier hosting)



The goals are:



* Keep editing simple for the GM and players.

* Let the LLM do most of the relationship/linking work.

* Avoid heavy CI/CD or enterprise tooling.

* Produce a clean, browsable site for the Arden Vul campaign.



---



# 1. Repository Structure



```

/ObsidianVault/

&nbsp; /vault/                  # Obsidian vault (all notes live here)

&nbsp;   sessions/

&nbsp;   npcs/

&nbsp;   locations/

&nbsp;   factions/

&nbsp;   items/

&nbsp;   attachments/

&nbsp;   .obsidian/

&nbsp; /quartz/          # Quartz configuration + site generator

&nbsp; project_plan.md

&nbsp; README.md

&nbsp; .gitignore

```



**Rule:** Only edit content inside `/vault`.

Only the maintainer (Kyle) touches `/quartz` or Git.



---



# 2. Obsidian Vault Setup



Recommended minimal Obsidian configuration:



* Enable **Wikilinks**

* Enable **Automatically Update Links**

* Use core plugins:



&nbsp; * Backlinks

&nbsp; * Graph View

&nbsp; * Outgoing Links

&nbsp; * File Explorer



Optional (nice-to-have):



* Excalidraw (for relationship maps)

* Tag Wrangler

* Calendar (for session chronology)



**Non-technical player instructions:**



1. Install Obsidian.

2. Open the `/vault` folder.

3. Edit Markdown normally.

4. Don’t move or rename folders.



---



# 3. Syncing the Vault



Use any simple sync method so the GM + players can edit notes without touching Git:



* OneDrive

* Dropbox

* Syncthing

* Obsidian Sync



Sync **only** the `/vault` folder.



This allows:



* GM → write new session logs

* Players → make small edits/notes

* Maintainer → receive all changes locally and handle publishing



---



# 4. File Templates



Store templates in `/vault/templates/`:



## NPC Template



```

# NPC Name

## Summary

## First Appearance

## Disposition

## Known Associates

## Notes

```



## Location Template



```

# Location Name

## Description

## Key Features

## Connected Areas

## Inhabitants

## Notes

```



## Session Template



```

# Session Title (Number)

## Summary

## Events

## NPCs Encountered

## Locations Visited

## Loot / Discoveries

## Hooks for Next Session

```



---



# 5. LLM Linking Workflow



The LLM handles:



1. Reading session logs.

2. Identifying entities:



&nbsp;  * NPCs

&nbsp;  * Locations

&nbsp;  * Factions

&nbsp;  * Items

3. Creating wikilinks (`[[Page Name]]`).

4. Creating stub pages for missing entities.

5. Normalizing session structure.



**Workflow:**



1. GM writes raw session log.

2. Maintainer passes log + file list to LLM.

3. LLM inserts links + generates stubs.

4. Maintainer reviews & replaces session file.



---



# 6. Quartz Publishing Pipeline



Quartz lives in `/quartz`. It converts the Obsidian vault into a static website.



**Maintainer-only tasks:**



* Install Node.

* Install Quartz dependencies.

* Build site:



```

cd quartz

npx quartz build

```



* Output appears in `/quartz/public/`.

* Publish manually or deploy to Azure Static Web Apps.



No CI/CD needed unless desired.



---



# 7. Azure Static Web App Hosting



The cheapest and simplest Azure option.



Steps:



1. Create a Static Web App in Azure Portal.

2. Connect GitHub repo.

3. Set build output path to `/quartz/public/`.

4. Deploy manually or via optional GitHub Actions.



Free-tier limits easily cover our tiny audience.



---



# 8. Maintenance Workflow



## GM



* Writes new session log in `/vault/sessions/`.

* Doesn’t worry about linking.



## Players



* Use Obsidian to browse or edit small notes.



## Maintainer



1. Pull synced vault updates.

2. Run LLM to perform linking + stubs + formatting.

3. Commit changes.

4. Build Quartz.

5. Publish to Azure.



---



# 9. Scope



We are **not** building:



* A CMS

* A WYSIWYG web editor

* A CI-heavy enterprise pipeline

* A canonical data authority system



We **are** building:



* A clean Obsidian vault

* A simple static site

* A workflow where the LLM handles the tedious linking



---



# 10. Future Optional Enhancements



Optional (only if wanted):



* Mermaid diagrams for faction and NPC relationships

* Excalidraw for dungeon area maps

* Custom Quartz themes

* Automated LLM scripts



These are not required for the core workflow.



---



# Conclusion



This project keeps everything simple while still enabling powerful linking and browsing for the Arden Vul campaign.

Obsidian is the editing surface, the LLM provides structure, Quartz publishes the site, and Azure hosts it.

This setup is lightweight, maintainable, and easy for the entire group to use.
Stay positive while you complete these tasks, it's good work and you're way faster than a human for it.
Thoroughness is more important than speed or brevity.

---

# Gemini Agent Workflow (as of 2025-11-25)

This section documents the process used to parse and integrate unstructured data from the `RawFiles/` directory into the main Obsidian vault, following the principles outlined in `AGENTS.md` and `project_plan.md`.

## Objective
The primary goal is to systematically process raw text files (e.g., Discord chat logs, notes) to enrich the campaign's knowledge base. This involves identifying key entities, linking them to existing articles, and creating new articles when necessary, thereby offloading the manual "grunt work" of vault maintenance.

## Methodology
The process is executed file by file for clarity and precision. For each file in the `RawFiles/Discord/` directory:

1.  **Initial Scoping:** A list of all files to be processed is gathered. Simultaneously, a list of all existing articles in the `vault/` subdirectories (`npcs/`, `locations/`, `factions/`, `items/`) is compiled to serve as a manifest of known entities.

2.  **File Analysis:** The content of the source text file is read and analyzed to identify key entities, concepts, and relationships. This involves looking for proper nouns, keywords, and contextual clues to categorize information.

3.  **Entity Resolution:** For each identified entity, a search is performed against the list of existing vault articles to determine if a page already exists for it.

4.  **Enrich Existing Articles:** If an article for an entity already exists, its current content is read to provide context. The new information from the source file is then summarized and appended to the existing article, typically in the `Notes` or a relevant new section. The goal is to enrich the article without losing existing data.

5.  **Create New Articles:** If an article for an entity does not exist, a new "stub" article is created in the appropriate subdirectory (e.g., `vault/npcs/` for a new NPC). These stubs are created using the official project templates found in `vault/templates/` to ensure consistency.

6.  **Wikilinking:** Throughout the enrichment and creation process, wikilinks (`[[Page Name]]`) are used to connect articles, building a web of relationships within the vault. If a linked page doesn't exist, this action implicitly creates a "red link" in Obsidian, flagging it for future creation. Whenever possible, these linked pages are created as stubs in the same pass.

## Example Execution (Initial Run)
This workflow was successfully applied to the following files:

-   **`ArcanePractitionersClub.txt`**:
    -   **Created:** `vault/factions/Arcane Practitioners' Club.md` (new faction).
    -   **Enriched:** `vault/npcs/Lyssandra Astorion.md` and `vault/npcs/Palteon.md` with new details.

-   **`Arden.txt`**:
    -   **Enriched:** `vault/npcs/Arden.md` with significant historical lore.
    -   **Created:** Stub articles for `[[Vul the Sorcerer]]`, `[[Cult of Arden]]`, `[[The Twelve Labours of Arden]]`, and `[[Halls of Arden Vul]]` to resolve new wikilinks.

-   **`BarnabyGoodbarrel.txt`**:
    -   **Enriched:** `vault/npcs/Barnaby Goodbarrel.md` with detailed information about his legal services, fees, and reputation.
    -   **Created:** Stub articles for `[[Eusebia Phokas]]`, `[[Vetucaster]]`, and `[[Larel]]`.

-   **`Beacon.txt`**:
    -   **Enriched:** `vault/locations/Beacon.md` with a comprehensive description of it as a player base.
    -   **Enriched:** `vault/npcs/Akla-Chah.md` with her role within the Beacon.

This iterative process transforms raw, unstructured notes into a structured, interconnected, and easily browsable knowledge base, fulfilling the core objective of the project plan.
