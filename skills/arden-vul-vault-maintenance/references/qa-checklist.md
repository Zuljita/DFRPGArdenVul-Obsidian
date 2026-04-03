# Arden Vul Vault Maintenance QA Checklist

Run this checklist before commit/PR.

## Session fidelity checks
- [ ] Source URL exists and returns successfully.
- [ ] Session text reflects source recap order and meaning.
- [ ] No invented facts or inferred events were added.
- [ ] GM comments / Achievements / XP / Next Week remain distinct sections.

## Formatting checks
- [ ] Player Characters: one entry per line.
- [ ] Significant NPCs: one entry per line.
- [ ] XP section is list-structured (not collapsed paragraph).
- [ ] No stray imported date lines or blog chrome.
- [ ] No malformed wiki syntax (nested/duplicated brackets, repeated render names).

## Linking checks
- [ ] New links resolve to existing canonical notes.
- [ ] PC names link to canonical `vault/pcs/*` pages.
- [ ] Source wording is preserved where practical; canonical target mapping is used.
- [ ] If identity is uncertain, link omitted rather than guessed.

## Alias / dedupe checks
- [ ] No duplicate notes were created for spelling variants.
- [ ] Useful aliases were added only when evidence supports same identity.
- [ ] Any merges/canonicalization decisions are documented in PR notes.

## Footer checks
- [ ] Original Source link present and correct.
- [ ] Previous Session link added if target exists.
- [ ] Next Session link added if target exists.
- [ ] Previous/Next Discord Summary links added only if targets exist.

## PR hygiene checks
- [ ] Diff is focused to intended session/entities only.
- [ ] Scratch files are excluded from commit.
- [ ] Concise Discord-sized PR note prepared:
  - [ ] session(s) changed
  - [ ] entity notes created/updated
  - [ ] aliases added
  - [ ] unresolved ambiguity (if any)
