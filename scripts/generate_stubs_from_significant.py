#!/usr/bin/env python3
import re
import argparse
from pathlib import Path

VAULT = Path('vault')
SESS = VAULT / 'sessions'

EXCLUDE_PATTERNS = re.compile(
    r"^(many|several|some|a couple|\d+\b|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.I,
)

GENERIC_WORDS = {
    'goblins','goblin','varumani','wyvern','crocodiles','mantari','skeleton','skeletons',
    'ghoul','ghouls','spiders','spider','construct','constructs','cultists','guards',
    'acolytes','sergeants','merchants','mules','women','men','prisoners','baboon','baboons',
    'cooks','beastman','beastmen','wight',
}

def existing_titles():
    idx = set()
    for folder in ['npcs','factions','items','locations','pcs']:
        for p in (VAULT / folder).glob('*.md'):
            idx.add(p.stem)
    return idx

def parse_significant(lines):
    out = []
    for line in lines:
        line = line.strip('- ').strip()
        if not line:
            continue
        # split on comma to get primary name
        primary = line.split(',', 1)[0].strip()
        # strip any accidental wikilink syntax to display text
        if primary.startswith('[[') and '|' in primary and primary.endswith(']]'):
            primary = primary.split('|',1)[1][:-2]
        primary = primary.strip()
        # choose last part if "Name / Alias" form
        if ' / ' in primary:
            primary = primary.split(' / ')[-1].strip()
        # common normalizations
        if primary.lower() == 'goat':
            primary = 'GOAT'
        # ignore plain lowercase generics
        if EXCLUDE_PATTERNS.match(primary):
            continue
        lower = primary.lower()
        if lower in GENERIC_WORDS:
            continue
        # skip obvious non-entities and noisy patterns
        if any(k in lower for k in ['summoned', 'created', 'unknown', 'weird', 'other', 'varumani miners', 'halfling toll collectors']):
            continue
        if any(ch in primary for ch in '[]/'):
            continue
        # keep title case words or single proper names
        out.append(primary)
    return out

def extract_section(text):
    # Find 'Significant NPCs:' lines and capture bullet lines until blank line or double newline
    results = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().lower().startswith('significant npcs'):
            i += 1
            # skip initial blank lines
            while i < len(lines) and not lines[i].strip():
                i += 1
            block = []
            while i < len(lines) and lines[i].strip():
                block.append(lines[i])
                i += 1
            results.extend(parse_significant(block))
        i += 1
    return sorted(set(results))

def safe_filename(title: str) -> str:
    # Replace filesystem-unsafe characters and collapse spaces
    s = re.sub(r'[\\/:*?"<>|]', ' - ', title)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def write_stub(name: str, appears_in: list):
    fname = safe_filename(name) + '.md'
    path = VAULT / 'npcs' / fname
    if path.exists():
        return False
    fm = [
        '---',
        f'title: "{name}"',
        'tags:',
        '  - npc',
        'aliases:',
        '---',
        f'# {name}',
        '',
        '## Summary',
        '- TODO: Short description.',
        '',
        '## Appears In',
    ]
    for s in sorted(set(appears_in)):
        fm.append(f'- [[sessions/{s}|{s.replace(".md", "")}]]')
    fm.append('')
    path.write_text('\n'.join(fm), encoding='utf-8')
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preview', action='store_true', help='Preview only; do not write files')
    ap.add_argument('--create', action='store_true', help='Create stubs (default if not preview)')
    ap.add_argument('files', nargs='*', help='Specific session files to process')
    args = ap.parse_args()

    exists = existing_titles()
    if args.files:
        targets = [Path(f).name for f in args.files]
    else:
        targets = sorted(str(p.name) for p in SESS.glob('Session *.md'))

    created = []
    preview = {}
    for fname in targets:
        p = SESS / fname
        if not p.exists():
            continue
        text = p.read_text(encoding='utf-8', errors='ignore')
        names = extract_section(text)
        preview[fname] = []
        for nm in names:
            if nm in exists:
                continue
            preview[fname].append(nm)
            if not args.preview and args.create:
                if write_stub(nm, [fname]):
                    created.append(nm)
                    exists.add(nm)
    if args.preview:
        for f, names in preview.items():
            if not names:
                continue
            print(f"== {f} ==")
            for nm in names:
                print(f"- {nm}")
        return
    if created:
        print('Created stubs:', ', '.join(created))
    else:
        print('No new stubs created.')

if __name__ == '__main__':
    main()
