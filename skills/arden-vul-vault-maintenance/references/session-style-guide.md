# Arden Vul Session Conversion Style Guide

## 1. Scope

Session pages should reproduce the actual session recap content from the GM blog as faithfully as possible.

Include:
- Date
- Weather
- Player Characters
- Significant NPCs
- Main recap body
- GM comments / notes
- Achievements
- XP
- Next Week
- Source / navigation footer

Do not include:
- blog comments
- labels / tags
- share buttons
- newer / older post links
- sidebar content
- unrelated footer or blog chrome

Preserve the meaning and structure of the source recap.
Do not invent lore, interpretation, or extra events.

## 2. Session page rules

Before editing anything:
- Read the entire source recap.
- Read the entire existing session page.
- Consult `vault/notes/Arden Vul GM Source Index.md` to determine canonical source URL, session ordering, and related Discord summaries.

Session pages should:
- preserve the source recap content and order of events
- preserve the source section structure where practical
- add internal vault links for relevant proper nouns
- use canonical vault targets when linking, even if the source uses variant spellings
- preserve source-visible wording unless a normalization rule below applies

Formatting rules:
- Player Characters and Significant NPCs should be one entry per line
- XP should preserve list structure rather than being flattened into a paragraph
- Keep GM comments, Achievements, and Next Week as distinct sections
- Add a footer section at the bottom with:
  - Original Source
  - Previous Session
  - Next Session
  - Previous Discord Summary
  - Next Discord Summary

If one of those targets does not exist, omit the link rather than inventing one.

## 3. Normalization rules

Use the source recap as the visible text baseline, but apply these rules:

- Fix obvious conversion damage such as collapsed lines, broken sentence joins, malformed wiki links, duplicate rendered names, and stray imported dates.
- Do not silently rewrite the recap for style.
- Do not normalize obvious typos.
- When source spelling differs from canonical vault naming:
  - preserve the source wording in the recap when reasonable
  - link to the canonical vault page
  - add aliases to the target page when useful

## 4. Entity resolution and note creation

First identify relevant proper nouns using full-document reasoning, not brittle capitalization heuristics alone.

For each candidate entity:
- gather notes from the source recap about who or what it is
- search the vault using multiple terms:
  - exact name
  - alternate spellings
  - shortened forms
  - titles
  - descriptive context
- load likely matching notes fully into context before deciding identity

When matching:
- prefer existing canonical notes over creating new ones
- if two entities are probably the same, unify on one canonical note and add aliases as needed
- if identity is uncertain, do not force a match

Create a new entity note only if:
- no existing note is a good match after repeated search
- the entity is specific and materially important
- the entity is likely to matter beyond a single throwaway mention

Do not create notes for trivial generic mentions, or GURPS terms of art/Spells/Advantages/Disadvantages/Skills unless they are clearly important.

When updating an entity note:
- add durable facts learned from the source recap
- avoid duplicating the full session recap
- add an `Appears in` reference to the session page
- add aliases for useful spelling variants or typos where appropriate

## 5. Scratch work

You may use a temporary scratch file while working to track:
- candidate entities
- evidence for identity resolution
- possible aliases
- unresolved questions

Do not commit the scratch file unless explicitly instructed.
Delete or discard it before finalizing your work.

## 6. Required output

After finishing the session update:
- review all changed session and entity notes
- verify that all new links resolve
- verify that no duplicate notes were created for spelling variants
- verify that the source footer is present and correct

If GitHub access is available:
- create a branch
- commit the changes
- open a PR
- include a PR summary listing:
  - session page changed
  - new entity notes created
  - existing entity notes updated
  - aliases added
  - unresolved ambiguities, if any

If GitHub access is not available:
- generate the same PR summary in markdown for manual use

## 7. Hard rules

- Do not invent facts.
- Do not create duplicate notes for spelling variants.
- Do not assume two entities are identical without evidence.
- Do not leave malformed wiki syntax in rendered content.
- Do not commit temporary scratch files unless explicitly instructed.
- When uncertain, prefer no link over a wrong link.
