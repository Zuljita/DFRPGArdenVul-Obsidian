#!/usr/bin/env python3
"""
Process new Markdown content to:
1) Parse candidate entities that should have their own pages.
2) Check vault indexes, filenames, titles, and aliases for matches.
3) Create missing stubs and insert wikilinks in the source note.

Usage:
  python3 scripts/process_new_data.py --input "vault/sessions/Session 33.md"
  python3 scripts/process_new_data.py --input "vault/sessions/Session 33.md" --create --write

Notes:
  - Default type for ambiguous names can be set with --default (npc/location/faction/item)
  - This script is heuristic; review changes before committing.
"""
import argparse
import os
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "vault"

TYPE_TO_DIR = {
    "npc": "npcs",
    "location": "locations",
    "faction": "factions",
    "item": "items",
}


def normalize_name(name: str) -> str:
    s = name.strip()
    # Remove trailing/leading punctuation, collapse whitespace, lowercase
    s = re.sub(r"[\[\](){}:*`|'\"]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def read_frontmatter_aliases_and_title(p: Path):
    # Very lightweight YAML frontmatter parser for title/aliases
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None, []
    if not text.startswith("---\n"):
        return None, []
    # Capture frontmatter block
    m = re.search(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL | re.MULTILINE)
    if not m:
        return None, []
    fm = m.group(1)
    title = None
    aliases = []
    # title: "Foo"
    m_title = re.search(r"^title:\s*\"?([^\n\"]+)\"?\s*$", fm, flags=re.MULTILINE)
    if m_title:
        title = m_title.group(1).strip()
    # aliases: [..] or block list
    # Try block list first
    block = re.search(r"^aliases:\s*\n((?:\s*-\s*.*\n)+)", fm, flags=re.MULTILINE)
    if block:
        for line in block.group(1).splitlines():
            m_item = re.search(r"-\s*(.*)$", line.strip())
            if m_item:
                val = m_item.group(1).strip().strip('"')
                if val:
                    aliases.append(val)
    else:
        # Inline list aliases: [a, b]
        inline = re.search(r"^aliases:\s*\[(.*)\]\s*$", fm, flags=re.MULTILINE)
        if inline:
            for part in inline.group(1).split(','):
                val = part.strip().strip('"')
                if val:
                    aliases.append(val)
    return title, aliases


def build_entity_index():
    """Return dict name_norm -> {path, display, type} including aliases."""
    index = {}
    for t, sub in TYPE_TO_DIR.items():
        base = VAULT / sub
        if not base.exists():
            continue
        for p in base.glob("*.md"):
            display = p.stem
            title, aliases = read_frontmatter_aliases_and_title(p)
            names = [display]
            if title:
                names.append(title)
            names.extend(aliases)
            for n in names:
                n_norm = normalize_name(n)
                if not n_norm:
                    continue
                # Prefer first seen; don't overwrite to avoid oscillation
                index.setdefault(n_norm, {"path": p, "display": display, "type": t})
    return index


ENTITY_REGEX = re.compile(
    r"\b([A-Z][a-z]+(?:[\-'’][A-Z][a-z]+)?(?:\s+[A-Z][a-z]+(?:[\-'’][A-Z][a-z]+)?){0,4})\b"
)


LOCATION_HINTS = {
    "hall", "temple", "tower", "cavern", "forum", "well", "stair", "tomb",
    "inn", "library", "pyramid", "waterfall", "chasm", "shrine", "caves", "oracle",
}
ITEM_HINTS = {
    "ring", "spear", "gem", "circlet", "tablet", "cloak", "pin", "sack", "chair", "sword", "staff",
}
FACTION_HINTS = {
    "cult", "knights", "company", "band", "guild", "order", "empire", "brigade", "darlings",
}


def guess_type(name: str, default_type: str = "npc") -> str:
    n = name.lower()
    words = set(re.split(r"\W+", n))
    if words & LOCATION_HINTS:
        return "location"
    if words & ITEM_HINTS:
        return "item"
    if words & FACTION_HINTS:
        return "faction"
    return default_type


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_best_match(name_norm: str, index):
    if name_norm in index:
        return index[name_norm]
    # Fuzzy fallback: find the best ratio among keys with similar length
    best = None
    best_score = 0.0
    for key, val in index.items():
        # quick pruning: skip very short keys
        if len(key) < 3 or len(name_norm) < 3:
            continue
        score = similar(name_norm, key)
        if score > best_score:
            best_score = score
            best = val
    if best and best_score >= 0.90:
        return best
    return None


def extract_candidates(text: str):
    # Avoid code blocks and existing wikilinks
    # Strip code blocks
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Collect candidates
    cands = set(m.group(1).strip() for m in ENTITY_REGEX.finditer(text))
    # Filter common stopwords and short tokens
    STOP = {"The", "And", "Of", "A", "An"}
    filtered = []
    for c in cands:
        if c in STOP:
            continue
        if len(c) < 3:
            continue
        filtered.append(c)
    return sorted(filtered, key=lambda s: (-len(s), s))


def load_template(t: str) -> str:
    tpl_map = {
        "npc": VAULT / "templates" / "NPC Template.md",
        "location": VAULT / "templates" / "Location Template.md",
        "faction": VAULT / "templates" / "Faction Template.md",
        "item": VAULT / "templates" / "Item Template.md",
    }
    p = tpl_map.get(t)
    if p and p.exists():
        return p.read_text(encoding="utf-8", errors="ignore")
    # Fallback minimal
    return f"# {t.title()} Name\n\n## Summary\n\n## Notes\n"


def safe_filename(name: str) -> str:
    # Avoid slashes and reserved characters in filenames
    s = name.replace("/", "-")
    s = s.replace(":", " -")
    s = s.replace("|", "-")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def insert_links(content: str, link_map: dict) -> str:
    """
    link_map: original_name -> (folder, display)
    Replace occurrences not already in a wikilink with [[folder/display.md|display]].
    """
    # Protect existing wikilinks
    protected = {}
    def protect(m):
        key = f"__WL{len(protected)}__"
        protected[key] = m.group(0)
        return key
    content2 = re.sub(r"\[\[[\s\S]*?\]\]", protect, content)

    # Sort by descending length to avoid partial overlaps
    for name, (folder, display) in sorted(link_map.items(), key=lambda x: -len(x[0])):
        # word-boundary-ish replace of the exact phrase
        pattern = re.compile(rf"(?<!\[\[)\b{re.escape(name)}\b")
        repl = f"[[{folder}/{display}.md|{display}]]"
        content2 = pattern.sub(repl, content2)

    # Restore wikilinks
    for k, v in protected.items():
        content2 = content2.replace(k, v)
    return content2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to the new/edited Markdown note")
    ap.add_argument("--create", action="store_true", help="Create missing stubs")
    ap.add_argument("--write", action="store_true", help="Write wikilinks into the input file")
    ap.add_argument("--default", choices=list(TYPE_TO_DIR.keys()), default="npc", help="Default type for ambiguous entities")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"Input not found: {src}", file=sys.stderr)
        sys.exit(1)

    index = build_entity_index()
    text = src.read_text(encoding="utf-8", errors="ignore")
    cands = extract_candidates(text)

    existing = {}
    missing = []
    for cand in cands:
        n_norm = normalize_name(cand)
        match = find_best_match(n_norm, index)
        if match:
            existing[cand] = match
        else:
            t = guess_type(cand, args.default)
            missing.append((cand, t))

    print(f"Found {len(cands)} candidates; existing: {len(existing)}, missing: {len(missing)}")
    if existing:
        print("Existing matches:")
        for name, info in sorted(existing.items()):
            print(f"  - {name} -> {info['type']} : {info['path'].relative_to(VAULT)}")
    if missing:
        print("Missing entities:")
        for name, t in missing:
            print(f"  - {name} (as {t})")

    created = {}
    if args.create and missing:
        for name, t in missing:
            folder = TYPE_TO_DIR[t]
            fn = safe_filename(name)
            out = VAULT / folder / f"{fn}.md"
            if out.exists():
                # race: got created by another name — link to it
                display = out.stem
                created[name] = (folder, display)
                continue
            tpl = load_template(t)
            content = tpl
            # Ensure H1 matches the file name/title
            if content.strip().startswith("# "):
                # Replace first H1
                content = re.sub(r"^# .*", f"# {fn}", content, count=1, flags=re.MULTILINE)
            else:
                content = f"# {fn}\n\n" + content
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
            print(f"Created: {out.relative_to(VAULT)}")
            created[name] = (folder, fn)

    # Build link map for both existing and created
    link_map = {}
    for name, info in existing.items():
        folder = TYPE_TO_DIR.get(info['type'], info['path'].parent.name)
        display = info['display']
        link_map[name] = (folder, display)
    for name, pair in created.items():
        link_map[name] = pair

    if args.write and link_map:
        updated = insert_links(text, link_map)
        if updated != text:
            src.write_text(updated, encoding="utf-8")
            print(f"Updated links in: {src}")
        else:
            print("No link insertions applied (content unchanged)")

    print("Done.")


if __name__ == "__main__":
    main()
