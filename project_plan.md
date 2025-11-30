\# DFRPG Arden Vul — Project Plan



This document explains the \*\*lightweight, non-enterprise\*\* workflow for building a player-facing campaign reference for DFRPG Arden Vul using:



\* \*\*Obsidian\*\* (authoring + linking)

\* \*\*LLM assistance\*\* (article creation + auto-linking + structuring)

\* \*\*Quartz\*\* (static site generator)

\* \*\*Azure Static Web Apps\*\* (free-tier hosting)



The goals are:



\* Keep editing simple for the GM and players.

\* Let the LLM do most of the relationship/linking work.

\* Avoid heavy CI/CD or enterprise tooling.

\* Produce a clean, browsable site for the Arden Vul campaign.



---



\# 1. Repository Structure



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

&nbsp; project\_plan.md

&nbsp; README.md

&nbsp; .gitignore

```



\*\*Rule:\*\* Only edit content inside `/vault`.

Only the maintainer (Kyle) touches `/quartz` or Git.



---



\# 2. Obsidian Vault Setup



Recommended minimal Obsidian configuration:



\* Enable \*\*Wikilinks\*\*

\* Enable \*\*Automatically Update Links\*\*

\* Use core plugins:



&nbsp; \* Backlinks

&nbsp; \* Graph View

&nbsp; \* Outgoing Links

&nbsp; \* File Explorer



Optional (nice-to-have):



\* Excalidraw (for relationship maps)

\* Tag Wrangler

\* Calendar (for session chronology)



\*\*Non-technical player instructions:\*\*



1\. Install Obsidian.

2\. Open the `/vault` folder.

3\. Edit Markdown normally.

4\. Don’t move or rename folders.



---



\# 3. Syncing the Vault



Use any simple sync method so the GM + players can edit notes without touching Git:



\* OneDrive

\* Dropbox

\* Syncthing

\* Obsidian Sync



Sync \*\*only\*\* the `/vault` folder.



This allows:



\* GM → write new session logs

\* Players → make small edits/notes

\* Maintainer → receive all changes locally and handle publishing



---



\# 4. File Templates



Store templates in `/vault/templates/`:



\## NPC Template



```

\# NPC Name

\## Summary

\## First Appearance

\## Disposition

\## Known Associates

\## Notes

```



\## Location Template



```

\# Location Name

\## Description

\## Key Features

\## Connected Areas

\## Inhabitants

\## Notes

```



\## Session Template



```

\# Session Title (Number)

\## Summary

\## Full Recap

\## NPCs Encountered

\## Locations Visited

\## Loot / Discoveries

\## Hooks for Next Session

```



---



\# 5. LLM Linking Workflow



The LLM handles:



1\. Reading session logs.

2\. Identifying entities:



&nbsp;  \* NPCs

&nbsp;  \* Locations

&nbsp;  \* Factions

&nbsp;  \* Items

3\. Creating wikilinks (`\[\[Page Name]]`).

4\. Creating stub pages for missing entities.

5\. Normalizing session structure.



\*\*Workflow:\*\*



1\. GM writes raw session log.

2\. Maintainer passes log + file list to LLM.

3\. LLM inserts links + generates stubs.

4\. Maintainer reviews \& replaces session file.



---



\# 6. Quartz Publishing Pipeline



Quartz lives in `/quartz`. It converts the Obsidian vault into a static website.



\*\*Maintainer-only tasks:\*\*



\* Install Node.

\* Install Quartz dependencies.

\* Build site:



```

cd quartz

npx quartz build

```



\* Output appears in `/quartz/public/`.

\* Publish manually or deploy to Azure Static Web Apps.



No CI/CD needed unless desired.



---



\# 7. Azure Static Web App Hosting



The cheapest and simplest Azure option.



Steps:



1\. Create a Static Web App in Azure Portal.

2\. Connect GitHub repo.

3\. Set build output path to `/quartz/public/`.

4\. Deploy manually or via optional GitHub Actions.



Free-tier limits easily cover our tiny audience.



---



\# 8. Maintenance Workflow



\## GM



\* Writes new session log in `/vault/sessions/`.

\* Doesn’t worry about linking.



\## Players



\* Use Obsidian to browse or edit small notes.



\## Maintainer



1\. Pull synced vault updates.

2\. Run LLM to perform linking + stubs + formatting.

3\. Commit changes.

4\. Build Quartz.

5\. Publish to Azure.



---



\# 9. Scope



We are \*\*not\*\* building:



\* A CMS

\* A WYSIWYG web editor

\* A CI-heavy enterprise pipeline

\* A canonical data authority system



We \*\*are\*\* building:



\* A clean Obsidian vault

\* A simple static site

\* A workflow where the LLM handles the tedious linking



---



\# 10. Future Optional Enhancements



Optional (only if wanted):



\* Mermaid diagrams for faction and NPC relationships

\* Excalidraw for dungeon area maps

\* Custom Quartz themes

\* Automated LLM scripts



These are not required for the core workflow.



---



\# Conclusion



This project keeps everything simple while still enabling powerful linking and browsing for the Arden Vul campaign.

Obsidian is the editing surface, the LLM provides structure, Quartz publishes the site, and Azure hosts it.

This setup is lightweight, maintainable, and easy for the entire group to use.



