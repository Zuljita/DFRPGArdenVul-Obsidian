#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import re as _re

VAULT = Path('vault')

ENTITY_DIRS = {
    'NPC': 'npcs',
    'Location': 'locations',
    'Faction': 'factions',
    'Item': 'items',
}
EXTRA_POOLS = ['pcs']  # allow resolving NPCs to PCs

LLM_PROMPT = (
    "From the text, list entity candidates grouped by type (NPC, Location, Faction, Item). "
    "Title Case; exclude generics and scaffolding words; do not invent; no mapping. Output concise bullets only."
)

# Load filter config
def load_filters() -> Dict[str, List[str]]:
    p = Path('config/entity_filters.json')
    if not p.exists():
        return {}
    try:
        import json as _json
        return _json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def is_unique_item(name: str, canon: Dict[str, Dict[str, Any]], filters: Dict[str, List[str]]) -> bool:
    key = normalize_key(name)
    # Keep if already exists as an item
    if key in canon.get('items', {}):
        return True
    # Filter obvious commodity items
    commodity = set([s.lower() for s in filters.get('commodity_items', [])])
    if key in commodity:
        return False
    # Heuristic: prefer names with " of " patterns and proper nouns
    patterns = filters.get('unique_item_patterns', [])
    for pat in patterns:
        if _re.search(pat, name):
            return True
    # Fallback: multi-word with at least one capitalized word beyond first token
    tokens = name.split()
    if len(tokens) >= 2 and any(t[:1].isupper() for t in tokens[1:]):
        return True
    return False

@dataclass
class Canonical:
    title: str
    path: Path
    aliases: List[str]


def load_canonicals() -> Dict[str, Dict[str, Canonical]]:
    canon: Dict[str, Dict[str, Canonical]] = {k: {} for k in list(ENTITY_DIRS.values()) + EXTRA_POOLS}
    for kind in ENTITY_DIRS.values():
        d = VAULT / kind
        if not d.exists():
            continue
        for p in d.rglob('*.md'):
            try:
                txt = p.read_text(encoding='utf-8')
            except Exception:
                continue
            title = extract_frontmatter_value(txt, 'title') or p.stem
            aliases = extract_frontmatter_list(txt, 'aliases')
            c = Canonical(title=title, path=p, aliases=aliases)
            canon[kind][normalize_key(title)] = c
            for a in aliases:
                canon[kind][normalize_key(a)] = c
    # also load extras (pcs)
    for kind in EXTRA_POOLS:
        d = VAULT / kind
        if not d.exists():
            continue
        for p in d.rglob('*.md'):
            try:
                txt = p.read_text(encoding='utf-8')
            except Exception:
                continue
            title = extract_frontmatter_value(txt, 'title') or p.stem
            aliases = extract_frontmatter_list(txt, 'aliases')
            c = Canonical(title=title, path=p, aliases=aliases)
            canon[kind][normalize_key(title)] = c
            for a in aliases:
                canon[kind][normalize_key(a)] = c
    # build all-name index for cross-kind mapping
    canon['_all'] = {}
    for pool_name, pool in canon.items():
        if pool_name == '_all':
            continue
        for k, c in pool.items():
            canon['_all'][k] = c
    return canon


def extract_frontmatter_value(text: str, key: str) -> Optional[str]:
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    block = m.group(1)
    mm = re.search(rf"^{re.escape(key)}:\s*\"?([^\n\"]+)\"?\s*$", block, re.M)
    return mm.group(1).strip() if mm else None


def extract_frontmatter_list(text: str, key: str) -> List[str]:
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    if not m:
        return []
    block = m.group(1)
    # naive yaml list parser for one level strings
    if re.search(rf"^{re.escape(key)}:\s*$", block, re.M):
        # capture following dash lines until next non-indented
        lines = block.splitlines()
        res = []
        capture = False
        for line in lines:
            if capture:
                if line.startswith('  -'):
                    val = line.split('-', 1)[1].strip()
                    val = val.strip('"')
                    if val:
                        res.append(val)
                elif line.startswith(' '):
                    continue
                else:
                    break
            else:
                if re.match(rf"^{re.escape(key)}:\s*$", line):
                    capture = True
        return res
    return []


def normalize_key(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def call_llm(files: List[Path], endpoint: str = None, model: str = None, temperature: float = 0.1, max_tokens: int = 400, timeout: int = 180) -> str:
    model = model or 'qwen2.5-7b-instruct'
    endpoint = endpoint or 'http://192.168.21.76:1234'
    cmd = [
        'python3', 'scripts/local_llm_client.py',
        '--endpoint', endpoint,
        '--prompt', LLM_PROMPT,
        '--files', *[str(f) for f in files],
        '--model', model,
        '--temperature', str(temperature),
        '--max-tokens', str(max_tokens),
        '--timeout', str(timeout),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"LLM call failed: {res.stderr}\n{res.stdout}")
    return res.stdout


def parse_candidates(text: str) -> Dict[str, List[str]]:
    # Expect concise bullets like:
    # - NPC: Name A; Name B
    # - Location: Place X
    groups = defaultdict(list)
    for line in text.splitlines():
        line = line.strip('- ').strip()
        if not line or ':' not in line:
            continue
        head, tail = line.split(':', 1)
        head = head.strip().lower()
        vals = re.split(r"[,;]", tail)
        vals = [v.strip() for v in vals if v.strip()]
        if head.startswith('npc'):
            groups['NPC'].extend(vals)
        elif head.startswith('location'):
            groups['Location'].extend(vals)
        elif head.startswith('faction'):
            groups['Faction'].extend(vals)
        elif head.startswith('item'):
            groups['Item'].extend(vals)
    # de-dup per group
    for k in list(groups.keys()):
        seen = []
        for v in groups[k]:
            if normalize_key(v) not in {normalize_key(x) for x in seen}:
                seen.append(v)
        groups[k] = seen
    return groups


def find_match(kind: str, name: str, canon: Dict[str, Dict[str, Canonical]]) -> Tuple[Optional[Canonical], Optional[str]]:
    key = normalize_key(name)
    pools = [canon.get(ENTITY_DIRS.get(kind, ''), {})]
    if kind == 'NPC':
        pools.append(canon.get('pcs', {}))
    # also try cross-kind matches to avoid duplicate creations
    pools.append(canon.get('_all', {}))
    for idx in pools:
        if key in idx:
            return idx[key], None
    # fuzzy across pools
    best: Tuple[float, Optional[Canonical], Optional[str]] = (0.0, None, None)
    for idx in pools:
        for k2, c in idx.items():
            score = similarity(key, k2)
            if score > best[0]:
                best = (score, c, k2)
    if best[0] >= 0.9:
        return best[1], best[2]
    return None, None


def create_stub(kind: str, name: str, appears_in: Path) -> Path:
    folder = VAULT / ENTITY_DIRS[kind]
    folder.mkdir(parents=True, exist_ok=True)
    safe = name.replace('/', '-').strip()
    target = folder / f"{safe}.md"
    if target.exists():
        return target
    frontmatter = [
        '---',
        f'title: "{name}"',
        'tags:',
        f'  - {ENTITY_DIRS[kind][:-1]}',
        'aliases:',
        '---',
        f'# {name}',
        '',
        '## Summary',
        '- TODO: Short description.',
        '',
        '## Appears In',
        f'- [[{appears_in.relative_to(VAULT)}|{appears_in.stem}]]',
        '',
    ]
    target.write_text("\n".join(frontmatter), encoding='utf-8')
    return target


def chunk_text(text: str, max_chars: int = 2400) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    size = 0
    for para in text.split('\n\n'):
        if size + len(para) + 2 > max_chars and current:
            parts.append('\n\n'.join(current))
            current = []
            size = 0
        current.append(para)
        size += len(para) + 2
    if current:
        parts.append('\n\n'.join(current))
    return parts


def run_iac_on_file(session_file: Path, dry_run: bool=False, kinds: Optional[List[str]] = None, chunk_size: int = 2400, endpoint: str = None, model: str = None) -> Dict[str, List[Tuple[str, str]]]:
    canon = load_canonicals()
    filters = load_filters()
    # Chunk session content to improve extraction
    text = session_file.read_text(encoding='utf-8', errors='ignore')
    chunks = chunk_text(text, max_chars=chunk_size)
    tmpdir = Path('.iac_tmp')
    tmpdir.mkdir(exist_ok=True)
    merged: Dict[str, List[str]] = defaultdict(list)
    for i, chunk in enumerate(chunks):
        fp = tmpdir / f"{session_file.stem}.part{i+1}.md"
        fp.write_text(chunk, encoding='utf-8')
        try:
            out = call_llm([fp], endpoint=endpoint, model=model)
        finally:
            try:
                fp.unlink()
            except OSError:
                pass
        g = parse_candidates(out)
        for k, vals in g.items():
            merged[k].extend(vals)
    # de-dup merged
    for k in list(merged.keys()):
        seen = []
        for v in merged[k]:
            if normalize_key(v) not in {normalize_key(x) for x in seen}:
                seen.append(v)
        merged[k] = seen
    groups = merged
    actions: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    # stoplists to reduce false positives
    stop_location = set([s.lower() for s in filters.get('stop_location', [])])
    stop_item = set([s.lower() for s in filters.get('stop_items', [])])
    stop_faction = set([s.lower() for s in filters.get('stop_factions', [])])
    stop_npcs = set([s.lower() for s in filters.get('stop_npcs', [])])
    spells = set([s.lower() for s in filters.get('spells', [])])
    seen_keys = set()
    allowed = set(kinds) if kinds else set(ENTITY_DIRS.keys())
    # Optional unique item filter
    unique_mode = globals().get('_IAC_ITEMS_MODE', 'all')

    for kind, names in groups.items():
        if kind not in ENTITY_DIRS:
            continue
        if kind not in allowed:
            continue
        # Post-filter items when unique-mode is requested
        if kind == 'Item' and unique_mode == 'unique':
            names = [n for n in names if is_unique_item(n, canon, filters)]
        for name in names:
            nkey = normalize_key(name)
            if nkey in seen_keys:
                continue
            if (
                (kind == 'Location' and nkey in stop_location)
                or (kind == 'Item' and (nkey in stop_item or nkey in spells))
                or (kind == 'NPC' and (nkey in spells or nkey in stop_npcs))
                or (kind == 'Faction' and nkey in stop_faction)
            ):
                continue
            match, fuzzy_key = find_match(kind, name, canon)
            if match:
                # If fuzzy match via alias key, consider adding alias in ACE; for IAC we only record.
                actions['mapped'].append((name, str(match.path)))
                seen_keys.add(nkey)
                continue
            # create stub
            if not dry_run:
                created = create_stub(kind, name, session_file)
                actions['created'].append((name, str(created)))
            else:
                actions['would_create'].append((name, ENTITY_DIRS[kind]))
            seen_keys.add(nkey)
    return actions


def main():
    ap = argparse.ArgumentParser(description='Run Identifying Article Candidates (IAC) on sessions.')
    ap.add_argument('--file', help='Path to a session markdown file')
    ap.add_argument('--all', action='store_true', help='Process all sessions (descending by session id)')
    ap.add_argument('--kinds', default='NPC,Location,Faction', help='Comma-separated kinds to process (default: NPC,Location,Faction)')
    ap.add_argument('--items-mode', choices=['all','unique'], default='all', help='Item selection: all (default) or unique')
    ap.add_argument('--chunk-size', type=int, default=2400, help='Chunk size for IAC model calls (chars)')
    ap.add_argument('--endpoint', default=None, help='LLM endpoint (OpenAI-compatible)')
    ap.add_argument('--model', default=None, help='LLM model name')
    ap.add_argument('--dry-run', action='store_true', help='Do not create files, just print actions')
    args = ap.parse_args()

    targets: List[Path] = []
    if args.file:
        targets = [Path(args.file)]
    elif args.all:
        sessions = sorted((VAULT / 'sessions').glob('*.md'), reverse=True)
        targets = sessions
    else:
        ap.error('Specify --file <session.md> or --all')

    summary = []
    kinds = [k.strip() for k in args.kinds.split(',') if k.strip()]
    # set global for unique filtering
    globals()['_IAC_ITEMS_MODE'] = args.items_mode
    for sf in targets:
        acts = run_iac_on_file(sf, dry_run=args.dry_run, kinds=kinds, chunk_size=args.chunk_size, endpoint=args.endpoint, model=args.model)
        summary.append({'file': str(sf), **{k: v for k, v in acts.items()}})

    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
