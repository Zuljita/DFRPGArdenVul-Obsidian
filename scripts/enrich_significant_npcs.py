#!/usr/bin/env python3
import re
from pathlib import Path

VAULT = Path('vault')
SESS = VAULT / 'sessions'

FACTION_MAP = {
    'thorcin': 'Thorcins',
    'thorcins': 'Thorcins',
    'archontean': 'Archontean Empire',
    'goblin': 'Goblins',
    'goblins': 'Goblins',
    'varumani': 'Varumani',
    'halfling': 'Halflings',
    'halflings': 'Halflings',
    'rudishva': 'Rudishva',
}

# Known faction pages for direct match in lines
KNOWN_FACTIONS = {p.stem: p for p in (VAULT / 'factions').glob('*.md')}

def link_target(folder: str, name: str) -> str:
    return f'[[{folder}/{name}.md|{name}]]'

def link_exists(path: Path) -> bool:
    return path.exists()

def enrich_line(line: str, session_name: str):
    # Only process bullet lines under Significant NPCs
    if '[[' in line:  # avoid touching already-linked lines to reduce risk
        return line
    original = line
    # Extract primary name (before first comma)
    m = re.match(r'\s*-\s*([^,\n]+)(.*)', line)
    if not m:
        return line
    name = m.group(1).strip()
    tail = m.group(2)
    # Link NPC name if stub exists
    npc_path = VAULT / 'npcs' / f'{name}.md'
    if link_exists(npc_path):
        name_link = link_target('npcs', name)
        line = f'- {name_link}{tail}'
    # Link race words if faction page exists
    def repl_race(match):
        word = match.group(0)
        key = word.lower()
        faction = FACTION_MAP.get(key)
        if not faction:
            return word
        fpath = VAULT / 'factions' / f'{faction}.md'
        if not link_exists(fpath):
            return word
        return link_target('factions', faction)

    # Replace only first occurrence of a race demonym
    for pat in sorted(FACTION_MAP.keys(), key=len, reverse=True):
        regex = re.compile(rf'\b{re.escape(pat)}\b', re.I)
        if regex.search(line):
            line = regex.sub(repl_race, line, count=1)
            break

    # Link explicit faction names present in line (e.g., Cult of Set, Grudge Brigade)
    for fname in KNOWN_FACTIONS.keys():
        # Avoid races handled above; only proper multi-word/known names
        if fname.lower() in FACTION_MAP.values():
            continue
        if re.search(rf'\b{re.escape(fname)}\b', line):
            line = re.sub(rf'\b{re.escape(fname)}\b', link_target('factions', fname), line)
    return line

def process_file(path: Path):
    text = path.read_text(encoding='utf-8', errors='ignore')
    lines = text.splitlines()
    out = []
    i = 0
    changed = False
    while i < len(lines):
        out.append(lines[i])
        if lines[i].strip().lower().startswith('significant npcs'):
            i += 1
            # retain blank lines after header
            while i < len(lines) and not lines[i].strip():
                out.append(lines[i]); i += 1
            # process bullets until blank line or EOF
            start = len(out)
            while i < len(lines) and lines[i].strip():
                newl = enrich_line(lines[i], path.name)
                out.append(newl)
                if newl != lines[i]:
                    changed = True
                i += 1
            continue
        i += 1
    if changed:
        path.write_text('\n'.join(out) + '\n', encoding='utf-8')
    return changed

def main():
    changed_files = []
    for p in sorted(SESS.glob('Session *.md')):
        if process_file(p):
            changed_files.append(p.name)
    if changed_files:
        print('Enriched:', ', '.join(changed_files))
    else:
        print('No changes applied.')

if __name__ == '__main__':
    main()

