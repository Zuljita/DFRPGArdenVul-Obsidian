#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / 'vault'

# Reuse helpers by importing from process_new_data if available
try:
    from process_new_data import build_entity_index, extract_candidates, insert_links  # type: ignore
except Exception:
    # Minimal fallbacks
    def build_entity_index():
        idx = {}
        for folder in ['npcs', 'locations', 'factions', 'items', 'pcs']:
            base = VAULT / folder
            if not base.exists():
                continue
            for p in base.glob('*.md'):
                display = p.stem
                idx[display.lower()] = {'path': p, 'display': display, 'type': folder[:-1]}
        return idx

    def extract_candidates(text: str):
        ENTITY_REGEX = re.compile(r"\b([A-Z][a-z]+(?:[\-'’][A-Z][a-z]+)?(?:\s+[A-Z][a-z]+(?:[\-'’][A-Z][a-z]+)?){0,4})\b")
        text = re.sub(r"```[\s\S]*?```", " ", text)
        cands = set(m.group(1).strip() for m in ENTITY_REGEX.finditer(text))
        STOP = {"The", "And", "Of", "A", "An"}
        filtered = []
        for c in cands:
            if c in STOP:
                continue
            if len(c) < 3:
                continue
            filtered.append(c)
        return sorted(filtered, key=lambda s: (-len(s), s))

    def insert_links(content: str, link_map: dict) -> str:
        protected = {}
        def protect(m):
            key = f"__WL{len(protected)}__"
            protected[key] = m.group(0)
            return key
        content2 = re.sub(r"\[\[[\s\S]*?\]\]", protect, content)
        for name, (folder, display) in sorted(link_map.items(), key=lambda x: -len(x[0])):
            pattern = re.compile(rf"(?<!\[\[)\b{re.escape(name)}\b")
            repl = f"[[{folder}/{display}.md|{display}]]"
            content2 = pattern.sub(repl, content2)
        for k, v in protected.items():
            content2 = content2.replace(k, v)
        return content2

TYPE_TO_DIR = {
    'npc': 'npcs',
    'location': 'locations',
    'faction': 'factions',
    'item': 'items',
}

def normalize_name(name: str) -> str:
    s = name.strip()
    s = re.sub(r"[\[\](){}:*`|'\"]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower()

def main():
    ap = argparse.ArgumentParser(description='Run IAC across sessions and insert links globally for mapped entities only.')
    ap.add_argument('--write', action='store_true', help='Apply changes to files')
    args = ap.parse_args()

    index = build_entity_index()
    sessions = sorted((VAULT / 'sessions').glob('Session *.md'))

    # Step 1: collect candidates from sessions and map to existing entities only
    link_map = {}  # name -> (folder, display)
    for sf in sessions:
        text = sf.read_text(encoding='utf-8', errors='ignore')
        cands = extract_candidates(text)
        for cand in cands:
            n = normalize_name(cand)
            if n in index:
                info = index[n]
                folder = TYPE_TO_DIR.get(info.get('type', ''), info['path'].parent.name)
                display = info['display']
                link_map.setdefault(cand, (folder, display))

    print(f"Mapped {len(link_map)} candidates from sessions to existing entities.")

    # Step 2: insert links in sessions and the rest of the vault
    changed = []
    targets = [p for p in VAULT.rglob('*.md') if '.obsidian' not in str(p) and 'templates' not in str(p)]
    for p in targets:
        original = p.read_text(encoding='utf-8', errors='ignore')
        updated = insert_links(original, link_map)
        if updated != original:
            if args.write:
                p.write_text(updated, encoding='utf-8')
            changed.append(str(p.relative_to(VAULT)))

    print(f"Updated links in {len(changed)} files.")
    if not args.write:
        print("Dry-run complete. Re-run with --write to apply changes.")

if __name__ == '__main__':
    main()

