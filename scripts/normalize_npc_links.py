#!/usr/bin/env python3
import re
import json
from pathlib import Path as _Path
from pathlib import Path

VAULT = Path('vault')

# Map misfiled NPC links to locations (use bare [[Page]] form)
TO_LOCATION = {
    'Gosterwick.md': 'Gosterwick',
    'Goblintown.md': 'Goblintown',
    'Great Chasm.md': 'Great Chasm',
    'Great Hall.md': 'Great Hall',
    'Arden Vul.md': 'Arden Vul',
}

# Links that should be plain text (spells/generics/scaffold words)
TO_PLAIN = {
    'Archontean.md': 'Archontean',
    'Many.md': 'Many',
    'Ruins.md': 'Ruins',
    'Shape Earth.md': 'Shape Earth',
    'Water Vision.md': 'Water Vision',
    'Levitate.md': 'Levitate',
    'Levitation.md': 'Levitation',
    'Wizard Eye.md': 'Wizard Eye',
    'Apportation.md': 'Apportation',
    'Secrets.md': 'Secrets',
    'March.md': 'March',
    'Forum.md': 'Forum',
    'Pyramid.md': 'Pyramid',
    'Cave.md': 'Cave',
    'Cavern.md': 'Cavern',
    'Stair.md': 'Stair',
    'Well.md': 'Well',
    'Cliff Face.md': 'Cliff Face',
    'Climbing.md': 'Climbing',
    'Stone.md': 'Stone',
    'Light.md': 'Light',
    'Flight.md': 'Flight',
    'Darlings.md': 'Darlings',
    'Baboons.md': 'Baboons',
    'Beastmen.md': 'Beastmen',
    'Goblins.md': 'Goblins',
    'Halflings.md': 'Halflings',
    'In Gosterwick.md': 'in Gosterwick',
    'There.md': 'There',
    'Also.md': 'Also',
    'Instead.md': 'Instead',
    'Just.md': 'Just',
    'Next.md': 'Next',
    'Still.md': 'Still',
    'Somehow.md': 'Somehow',
    'Quickly.md': 'Quickly',
    'Tongues.md': 'Tongues',
    'One skeleton.md': 'One skeleton',
    'Skeleton cook.md': 'Skeleton cook',
    'Shambling Mound.md': 'Shambling Mound',
    'Phase spider.md': 'Phase spider',
    'Mountain Lion.md': 'Mountain Lion',
    'Walking Pigs.md': 'Walking Pigs',
    'Pig-headed beastman.md': 'Pig-headed beastman',
    'Telepathic Gold Cat Statue.md': 'Telepathic Gold Cat Statue',
    # keep as entities (named mule + episodic NPC)
    'Weird guy who hangs out with baboons.md': 'Weird guy who hangs out with baboons',
    # newly observed scaffolding/generics/days
    'Basilsday.md': 'Basilsday',
    'Tahsday.md': 'Tahsday',
    'Library.md': 'Library',
    'logovores.md': 'logovores',
    'Giant lizard.md': 'Giant lizard',
    'Skeleton.md': 'Skeleton',
    'Ibis constructs of Thoth.md': 'Ibis constructs of Thoth',
    'Again.md': 'Again',
    'Stuff.md': 'Stuff',
    'The Rescuers.md': 'The Rescuers',
    'The Set Cult Strikes Back.md': 'The Set Cult Strikes Back',
    'Undead librarian.md': 'Undead librarian',
    'clockwork dragonfly.md': 'clockwork dragonfly',
    'Mud People.md': 'Mud People',
    'Dog-headed beastman sergeant.md': 'Dog-headed beastman sergeant',
    'Dwarf prisoner.md': 'Dwarf prisoner',
    'Large statue with hammer hands.md': 'Large statue with hammer hands',
    'Unknown human alchemist, working with the halfling thugs.md': 'Unknown human alchemist, working with the halfling thugs',
    'Unknown human alchemist.md': 'Unknown human alchemist',
    'Unidentified huge flying reptilian beast.md': 'Unidentified huge flying reptilian beast',
    'captured fishman.md': 'captured fishman',
    'chasm cephalopods.md': 'chasm cephalopods',
    'Fire Mephits.md': 'Fire Mephits',
    'Four feral cats.md': 'Four feral cats',
    'Horse Whisperer.md': 'Horse Whisperer',
    'Huge snapping turtle.md': 'Huge snapping turtle',
    'Imperial Stone Guardians.md': 'Imperial Stone Guardians',
    'Insight.md': 'Insight',
    'Club Creon.md': 'Club Creon',
    'Crackers.md': 'Crackers',
    'Shriekers shrieking.md': 'Shriekers shrieking',
    'Staff.md': 'Staff',
    'Stars.md': 'Stars',
    'Three mushroom-smoking fire mephits.md': 'Three mushroom-smoking fire mephits',
    'Two selenite guardians.md': 'Two selenite guardians',
    'Varumani Lifts conductors and laborers.md': 'Varumani Lifts conductors and laborers',
    'Varumani guards.md': 'Varumani guards',
    'Varumani miners.md': 'Varumani miners',
    'Young Varumani pranksters.md': 'Young Varumani pranksters',
    'crocodiles.md': 'crocodiles',
    'feral cats.md': 'feral cats',
    'giant crab.md': 'giant crab',
    'giant lizards.md': 'giant lizards',
    'giant salamander.md': 'giant salamander',
    'other goblins.md': 'other goblins',
    'rock reptiles.md': 'rock reptiles',
    'vanishing earth elementals.md': 'vanishing earth elementals',
    'Vael Levitated.md': 'Vael',
    'Vael Levitating.md': 'Vael',
}

# Load dynamic filters: spells and other demotions
cfg_path = _Path('config/entity_filters.json')
if cfg_path.exists():
    try:
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    except Exception:
        cfg = {}
    spells = set(cfg.get('spells', []))
    # add spell names to TO_PLAIN mapping
    for sp in spells:
        TO_PLAIN[f"{sp}.md"] = sp

# Repoint certain misfiled npc targets to canonical pages (pcs/, npcs/, factions/)
TO_REDIRECT = {
    # PCs
    'Ioannes.md': 'pcs/Ioannes Grammatikos Byzantios.md',
    'Ioannes Grammatikos Byzantios.md': 'pcs/Ioannes Grammatikos Byzantios.md',
    'Michael.md': 'pcs/Michael J. Dundee.md',
    'Uvash Edzuson.md': 'pcs/Uvash Edzuson.md',
    'Vael Sunshadow.md': 'pcs/Vael Sunshadow.md',
    'Vallium Halcyon.md': 'pcs/Vallium Halcyon.md',
    # Weird deity+name combo observed
    'Thoth Umsko.md': 'npcs/Umsko.md',
    # Locations
    'Arden Vul.md': 'locations/Arden Vul.md',
    # NPC name tidy-ups
    'Isocritis.md': 'npcs/Isocritis Half-Hand.md',
    'Mithric.md': 'lore/Mithric.md',
    'Ashe -GOAT- Maykum.md': 'npcs/Ashe Maykum.md',
}

PAT = re.compile(r"\[\[(npcs/([^\]|]+))(?:\|([^\]]*))?\]\]")

def transform(match):
    full = match.group(1)   # e.g., 'npcs/Gosterwick.md'
    target = match.group(2) # e.g., 'Gosterwick.md'
    label = match.group(3)  # optional label

    if target in TO_LOCATION:
        page = TO_LOCATION[target]
        if label:
            return f"[[{page}|{label}]]"
        else:
            return f"[[{page}]]"

    if target in TO_PLAIN:
        # Drop link, keep label if present, else the plain name
        return label if label else TO_PLAIN[target]

    if target in TO_REDIRECT:
        new_path = TO_REDIRECT[target]
        # Preserve original label if present; otherwise, use the basename without .md
        new_label = label if label else new_path.split('/')[-1].removesuffix('.md')
        return f"[[{new_path}|{new_label}]]"

    # Default: leave unchanged
    return match.group(0)

def process_file(p: Path):
    s = p.read_text(encoding='utf-8', errors='ignore')
    ns = PAT.sub(transform, s)
    # Contextual demotions: avoid over-linking deities in PC headers/descriptions
    # Example: "Dwarven cleric of [[npcs/Zodarrim.md|Zodarrim]]" -> plain text
    ns = re.sub(r"(?i)(cleric|priest) of \[\[npcs/Zodarrim\.md\|[^\]]+\]\]", r"\\1 of Zodarrim", ns)
    # Do not link deities when part of structure/location names like "Pyramid of Thoth"
    # Convert '[[npcs/Thoth.md|Thoth]]' (or Set) to plain text when preceded by these heads
    heads = r"Temple|Pyramid|Library|Forum|Glory|Catacombs|Chamber|Shrine|Sanctuary|Statue|Priory|Order|Monastery|Hall|Tower|Gate|Gates|Tomb|Stairs|Vault|Arena"
    ns = re.sub(rf"(?i)\b({heads}) of \[\[npcs/Thoth\.md\|[^\]]+\]\]", r"\\1 of Thoth", ns)
    ns = re.sub(rf"(?i)\b({heads}) of \[\[npcs/Set\.md\|[^\]]+\]\]", r"\\1 of Set", ns)
    if ns != s:
        p.write_text(ns, encoding='utf-8')
        return True
    return False

def main():
    changed = []
    for p in VAULT.rglob('*.md'):
        if process_file(p):
            changed.append(str(p))
    print(f"normalized {len(changed)} files")
    for c in changed:
        print(c)

if __name__ == '__main__':
    main()
