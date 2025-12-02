#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path.cwd()
VAULT = ROOT / 'vault'
FOLDERS = ['npcs', 'locations', 'items', 'monsters', 'factions']
OUT = ROOT / 'docs' / 'DEDUPE_REPORT.md'

def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\([^)]*\)", "", s)  # drop parentheticals
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def main():
    groups = {}
    for folder in FOLDERS:
        for p in (VAULT / folder).glob('*.md'):
            key = (folder, norm(p.stem))
            groups.setdefault(key, []).append(p)

    lines = ["# Dedupe Report", ""]
    total = 0
    for (folder, key), paths in sorted(groups.items()):
        if len(paths) <= 1:
            continue
        # Skip cases that are intentionally distinct (simple heuristics)
        stems = [p.stem for p in paths]
        if folder == 'monsters' and any('Huge Ears' in s or 'Huge Eyes' in s for s in stems):
            continue
        lines.append(f"## {folder}: '{key}'")
        for p in paths:
            lines.append(f"- {p.as_posix()}")
        lines.append("")
        total += 1

    if total == 0:
        lines.append("No likely duplicates found.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding='utf-8')
    print(f"Wrote {OUT} (groups: {total})")

if __name__ == '__main__':
    main()

