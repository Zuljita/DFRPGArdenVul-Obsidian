#!/usr/bin/env python3
from fix_sessions_1_10 import fix_file  # reuse helpers indirectly not feasible; duplicate minimal logic
import re
from pathlib import Path

VAULT = Path('vault')
SESS = VAULT / 'sessions'

def read(p: Path):
    return p.read_text(encoding='utf-8', errors='ignore')

def write(p: Path, s: str):
    p.write_text(s, encoding='utf-8')

folders = ['npcs','locations','items','pcs','factions']

def collapse_nested(text: str) -> str:
    for _ in range(3):
        for folder in folders:
            text = text.replace(f'[[{folder}/[[{folder}/', f'[[{folder}/')
    cross = re.compile(r"\[\[(?:"+"|".join(map(re.escape, folders))+r")/\[\[("+"|".join(map(re.escape, folders))+r")/")
    text = cross.sub(lambda m: f'[[{m.group(1)}/', text)
    return text

def fix_known(text: str) -> str:
    canonical = {
        'Long Stair': '[[locations/Long Stair.md|Long Stair]]',
        'Well of Light': '[[locations/Well of Light.md|Well of Light]]',
        'Gosterwick': '[[locations/Gosterwick.md|Gosterwick]]',
        'Pyramid of Thoth': '[[locations/Pyramid of Thoth.md|Pyramid of Thoth]]',
        'Library of Thoth': '[[locations/Library of Thoth.md|Library of Thoth]]',
        'Forum of Set': '[[locations/Forum of Set.md|Forum of Set]]',
    }
    text = re.sub(r"\[\[locations/Pyramid of \[\[(?:npcs|locations)/Pyramid of (?:\[\[(?:npcs|locations)/)?Thoth[^\]]*\]\]", canonical['Pyramid of Thoth'], text)
    text = re.sub(r"Forum of \[\[(?:npcs|locations)/Forum of \[\[(?:npcs|locations)/Set\.md\|?Set\]\]", 'Forum of Set', text)
    for name, canon in canonical.items():
        pattern = re.compile(r"\[\[(?:locations/)?"+re.escape(name)+r"[^\]]*\]\]")
        text = pattern.sub(canon, text)
        text = re.sub(r"\[\[(?:locations/)?"+re.escape(name)+r"\.md\|?"+re.escape(name)+r"\]\]", canon, text)
    # tails
    text = re.sub(r"\]\]\s*Stair\]\]", ']]', text)
    text = re.sub(r"\]\]\s*Well of Light\]\]", ']]', text)
    text = re.sub(r"\]\]\.md\|[A-Za-z ']+\]\]", ']]', text)
    return text

def fix_file_here(p: Path) -> bool:
    orig = read(p)
    s = orig
    s = collapse_nested(s)
    s = fix_known(s)
    if s != orig:
        write(p, s)
        return True
    return False

def main():
    changed = []
    for p in SESS.glob('Session *.md'):
        try:
            n = int(p.name.split(' ')[1])
        except Exception:
            continue
        if 11 <= n <= 19:
            if fix_file_here(p):
                changed.append(p.name)
    if changed:
        print('Fixed:', ', '.join(sorted(changed)))
    else:
        print('No changes')

if __name__ == '__main__':
    main()

