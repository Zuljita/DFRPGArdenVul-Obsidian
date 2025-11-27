#!/usr/bin/env python3
import re
import sys
from pathlib import Path

VAULT = Path('vault')

def all_md_files(root: Path):
    return list(root.rglob('*.md'))

def build_index(root: Path):
    # index by basename (case-sensitive) for quick existence checks
    idx = {}
    for p in all_md_files(root):
        idx[p.name] = idx.get(p.name, []) + [p]
    return idx

LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")

def check_file(path: Path, idx):
    unbalanced = []
    missing = []
    with path.open('r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            opens = line.count('[[')
            closes = line.count(']]')
            if opens != closes:
                unbalanced.append((i, line.rstrip('\n')))
            for m in LINK_RE.finditer(line):
                target = m.group(1)
                # Ignore external links and headers
                if target.startswith(('http://', 'https://', '#')):
                    continue
                # If target is a path with extension, check existence directly
                if target.endswith('.md'):
                    # resolve relative to vault root
                    abs_path = VAULT / target
                    if not abs_path.exists():
                        missing.append((i, target))
                else:
                    # No extension; if includes a folder, check direct path; else by basename
                    if '/' in target:
                        abs_path = VAULT / (target + '.md')
                        if not abs_path.exists():
                            missing.append((i, target))
                    else:
                        name = target + '.md'
                        if name not in idx:
                            missing.append((i, target))
    return unbalanced, missing

def main(paths):
    idx = build_index(VAULT)
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"[skip] {p} (not found)")
            continue
        unbalanced, missing = check_file(path, idx)
        if unbalanced or missing:
            print(f"\n== {p} ==")
        if unbalanced:
            print("-- Unbalanced lines --")
            for i, line in unbalanced:
                print(f"{i:5}: {line}")
        if missing:
            print("-- Missing targets --")
            # unique by (line, target)
            seen = set()
            for i, t in missing:
                if (i, t) in seen:
                    continue
                seen.add((i, t))
                print(f"{i:5}: {t}")

if __name__ == '__main__':
    if len(sys.argv) == 1:
        # default: check all sessions
        paths = sorted(str(p) for p in (VAULT / 'sessions').glob('Session *.md'))
    else:
        paths = sys.argv[1:]
    main(paths)
