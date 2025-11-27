#!/usr/bin/env python3
import re
from pathlib import Path

TARGETS = [
    'vault/sessions/Session 28 - Teleport Rugs and Baboons.md',
    'vault/sessions/Session 27 - The Tomb of Ptoh-Ristus.md',
    'vault/sessions/Session 26 - The Scouring of the Shire.md',
    'vault/sessions/Session 25 - Looking for the Back Door to the Forum of Set.md',
    'vault/sessions/Session 24b - The Set Cult Strikes Back, Larel\'s Stuff, and the Hall of Shrines.md',
    'vault/sessions/Session 24a - Revenge on the Set Cult.md',
    'vault/sessions/Session 23c - Set Jailbreak and Down to Goblintown.md',
    'vault/sessions/Session 23b - Disrupting Services in the Temple of Set.md',
    'vault/sessions/Session 23a - Gelatinous Cube and Slime Kraken.md',
    'vault/sessions/Session 22 - The Oracle of Thoth and The Litany of Light.md',
    'vault/sessions/Session 21 - The Library of Thoth.md',
    'vault/sessions/Session 20 - The Outer Caverns of Set.md',
]

folders = ['npcs', 'locations', 'items', 'pcs']

def collapse_nested(text: str) -> str:
    # Collapse patterns like [[npcs/[[npcs/Name... -> [[npcs/Name...
    for _ in range(3):
        for folder in folders:
            text = text.replace(f'[[{folder}/[[{folder}/', f'[[{folder}/')
        # Collapse cross-folder nesting like [[npcs/[[items/... -> [[items/...
        text = re.sub(r"\[\[(?:" + "|".join(map(re.escape, folders)) + r")/\[\[(" + "|".join(map(re.escape, folders)) + r")/",
                       r"[[\1/", text)
    return text

def fix_known_locations(text: str) -> str:
    canonical = {
        'Long Stair': '[[locations/Long Stair.md|Long Stair]]',
        'Well of Light': '[[locations/Well of Light.md|Well of Light]]',
        'Gosterwick': '[[locations/Gosterwick.md|Gosterwick]]',
        'Forum of Set': '[[locations/Forum of Set.md|Forum of Set]]',
        'Library of Thoth': '[[locations/Library of Thoth.md|Library of Thoth]]',
        'Pyramid of Thoth': '[[locations/Pyramid of Thoth.md|Pyramid of Thoth]]',
    }
    # handle the specific malformed Pyramid case first
    text = re.sub(r"\[\[locations/Pyramid of \[\[npcs/Pyramid of Thoth[^\]]*\]\]",
                  canonical['Pyramid of Thoth'], text)

    # Replace any variant inside a wikilink with canonical
    for name, canon in canonical.items():
        # any link that starts with [[locations/<name> and goes to the first ]]
        pattern = re.compile(r"\[\[locations/" + re.escape(name) + r"[^\]]*\]\]")
        text = pattern.sub(canon, text)
        # clean up common duplicated tails introduced by prior bad replacements
        tail_re = re.compile(r"\]\](?:\\.md\|)?" + re.escape(name) + r"\]\]")
        text = tail_re.sub(']]', text)
        tail_re2 = re.compile(r"\]\](?:\\.md\|)?" + re.escape(name) + r"(?!\w)")
        text = tail_re2.sub(']]', text)
        tail_re3 = re.compile(r"\]\]\|" + re.escape(name) + r"\]\]")
        text = tail_re3.sub(']]', text)
        tail_re4 = re.compile(r"\]\]\|" + re.escape(name) + r"(?!\w)")
        text = tail_re4.sub(']]', text)
    # Special cleanup: split tail for Long Stair like ']]|Long]] Stair]]'
    text = re.sub(r"\]\]\|Long\]\] Stair\]\]", ']]', text)
    return text

def main():
    for path_str in TARGETS:
        p = Path(path_str)
        if not p.exists():
            print(f"[skip] {path_str}")
            continue
        original = p.read_text(encoding='utf-8', errors='ignore')
        text = original
        text = collapse_nested(text)
        text = fix_known_locations(text)
        if text != original:
            p.write_text(text, encoding='utf-8')
            print(f"[fixed] {path_str}")
        else:
            print(f"[nochange] {path_str}")

if __name__ == '__main__':
    main()
