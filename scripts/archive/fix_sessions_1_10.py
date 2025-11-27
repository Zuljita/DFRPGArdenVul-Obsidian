#!/usr/bin/env python3
import re
from pathlib import Path

VAULT = Path('vault')
SESS = VAULT / 'sessions'

folders = ['npcs', 'locations', 'items', 'pcs', 'factions']

def collapse_nested(text: str) -> str:
    # Collapse double-folder nesting [[folder/[[folder/X -> [[folder/X
    for _ in range(3):
        for folder in folders:
            text = text.replace(f'[[{folder}/[[{folder}/', f'[[{folder}/')
    # Cross-folder nesting: [[foo/[[bar/Name -> [[bar/Name
    cross = re.compile(r"\[\[(?:" + "|".join(map(re.escape, folders)) + r")/\[\[(" + "|".join(map(re.escape, folders)) + r")/")
    text = cross.sub(lambda m: f'[[{m.group(1)}/', text)
    return text

def fix_known_locations(text: str) -> str:
    canonical = {
        'Long Stair': '[[locations/Long Stair.md|Long Stair]]',
        'Well of Light': '[[locations/Well of Light.md|Well of Light]]',
        'Gosterwick': '[[locations/Gosterwick.md|Gosterwick]]',
        'Pyramid of Thoth': '[[locations/Pyramid of Thoth.md|Pyramid of Thoth]]',
        'Library of Thoth': '[[locations/Library of Thoth.md|Library of Thoth]]',
        'Forum of Set': '[[locations/Forum of Set.md|Forum of Set]]',
        'Yellow Cloak Inn': '[[locations/Yellow Cloak Inn.md|Yellow Cloak Inn]]',
    }
    # Handle malformed Pyramid chain like [[locations/Pyramid of [[npcs/Pyramid of Thoth]] or deeper
    text = re.sub(r"\[\[locations/Pyramid of \[\[(?:npcs|locations)/Pyramid of (?:\[\[(?:npcs|locations)/)?Thoth[^\]]*\]\]", canonical['Pyramid of Thoth'], text)
    # Handle malformed Forum chain like Forum of [[npcs/Forum of [[npcs/Set.md|Set]]
    text = re.sub(r"Forum of \[\[(?:npcs|locations)/Forum of \[\[(?:npcs|locations)/Set\.md\|?Set\]\]", 'Forum of Set', text)
    # Normalize specific location links
    for name, canon in canonical.items():
        pattern = re.compile(r"\[\[(?:locations/)?" + re.escape(name) + r"[^\]]*\]\]")
        text = pattern.sub(canon, text)
        # also handle missing closing or extra tails seen in earlier sessions
        text = re.sub(r"\[\[(?:locations/)?" + re.escape(name) + r"\.md\|?" + re.escape(name) + r"\]\]", canon, text)
    return text

def cleanup_tails(text: str) -> str:
    # Remove duplicated trailing words after a closed link, e.g., ']] Stair]]'
    text = re.sub(r"\]\]\s*Stair\]\]", ']]', text)
    # Fix Well of Light duplicate closers
    text = re.sub(r"\]\]\s*Well of Light\]\]", ']]', text)
    # Remove stray .md|Name]] tails
    text = re.sub(r"\]\]\.md\|[A-Za-z ']+\]\]", ']]', text)
    return text

def fix_file(path: Path) -> bool:
    original = path.read_text(encoding='utf-8', errors='ignore')
    text = original
    text = collapse_nested(text)
    text = fix_known_locations(text)
    text = cleanup_tails(text)
    if text != original:
        path.write_text(text, encoding='utf-8')
        return True
    return False

def main():
    # Target Sessions 1–10 and the combined 8b/9 file
    targets = []
    for p in SESS.glob('Session *.md'):
        try:
            n = int(p.name.split(' ')[1])
        except Exception:
            continue
        if 1 <= n <= 10:
            targets.append(p)
    # Also include any file starting with "Sessions 8"
    targets += list(SESS.glob('Sessions 8*.md'))
    changed = []
    for p in sorted(set(targets), key=lambda x: x.name):
        if fix_file(p):
            changed.append(p.name)
    if changed:
        print('Fixed:', ', '.join(changed))
    else:
        print('No changes')

if __name__ == '__main__':
    main()
