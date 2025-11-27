#!/usr/bin/env python3
import re
import sys
from pathlib import Path

PATTERNS = [
    # Pattern: [[locations/The [[locations/X.md|X]].md|The [[locations/X.md|X]]]] -> [[locations/X.md|The X]]
    (
        re.compile(r"\[\[locations/The \[\[locations/([^|\]]+)\.md\|([^\]]+)\]\]\.md\|The \[\[locations/\1\.md\|\2\]\]\]\]"),
        r"[[locations/\1.md|The \2]]",
    ),
]

def fix_text(text: str) -> str:
    changed = text
    # Apply exact patterns first
    for pat, repl in PATTERNS:
        changed = pat.sub(repl, changed)
    # Then iteratively strip nested links inside outer link labels, e.g.:
    # [[sessions/File.md|... [[locations/X.md|X]] ...]] -> [[sessions/File.md|... X ...]]
    nested_in_label = re.compile(r"(\[\[[^\]|]+\|[^\]]*?)\[\[[^|\]]+\|([^\]]+)\]\]([^\]]*\]\])")
    while True:
        new_changed = nested_in_label.sub(r"\1\2\3", changed)
        if new_changed == changed:
            break
        changed = new_changed
    # Finally, collapse links whose TARGET path contains a nested link, e.g.:
    # [[factions/Guards from the [[factions/Cult of Set.md|Cult of Set]]]] -> Guards from the Cult of Set
    nested_in_target = re.compile(r"\[\[([^\]|]*?)\[\[[^|\]]+\|([^\]]+)\]\]([^\]]*?)\]\]")
    while True:
        new_changed = nested_in_target.sub(r"\1\2\3", changed)
        if new_changed == changed:
            break
        changed = new_changed
    # Ensure session links close before long descriptions:
    # [[sessions/File.md|Label — long text]] -> [[sessions/File.md|Label]] — long text
    sessions_label_trailer = re.compile(r"\[\[(sessions/[^|\]]+)\|([^\]]*?) — (.+)")
    changed = sessions_label_trailer.sub(r"[[\1|\2]] — \3", changed)
    # If a session link still lacks a closing ]], close it at line end
    sessions_unclosed_eol = re.compile(r"(\[\[sessions/[^\]|]+\|[^\]]+)(?=\n)")
    changed = sessions_unclosed_eol.sub(r"\1]]", changed)
    return changed

def process_file(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    fixed = fix_text(src)
    if fixed != src:
        path.write_text(fixed, encoding="utf-8")
        return True
    return False

def main(argv):
    if len(argv) < 2:
        print("Usage: fix_nested_wikilinks.py <file> [<file> ...]", file=sys.stderr)
        return 2
    changed_any = False
    for p in argv[1:]:
        path = Path(p)
        if not path.exists():
            print(f"warn: not found: {p}")
            continue
        if process_file(path):
            print(f"fixed: {p}")
            changed_any = True
    return 0 if changed_any else 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
