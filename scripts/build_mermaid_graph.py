#!/usr/bin/env python3
import re
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs' / 'LCE_REPORT.md'
OUT = ROOT / 'docs' / 'locations_graph.mmd'
FILTERS = ROOT / 'docs' / 'LCE_FILTERS.json'

EDGE_RE = re.compile(r"^- \[\[([^\]]+)\]\] -> \[\[([^\]]+)\]\](.*)$")

def slug(name: str) -> str:
    s = name.strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    return s.strip('_') or 'X'

def parse_label(suffix: str) -> str:
    # compress annotations to a short label: prefer [via X], fall back to [method: M]
    def clean(val: str) -> str:
        return re.sub(r"\bif stated\b", "", val, flags=re.I).strip()
    via = re.search(r"\[via\s+([^\]]+)\]", suffix, re.I)
    method = re.search(r"\[method:\s*([^\]]+)\]", suffix, re.I)
    feature = re.search(r"\[feature:\s*([^\]]+)\]", suffix, re.I)
    bits = []
    if via:
        bits.append(f"via {clean(via.group(1))}")
    if method:
        bits.append(clean(method.group(1)))
    if feature and not via and not method:
        # only include feature if nothing else
        bits.append(clean(feature.group(1)))
    return "; ".join(bits)

def load_filters():
    if not FILTERS.exists():
        return {"reject_methods": set(), "reject_via": set()}
    try:
        data = json.loads(FILTERS.read_text(encoding='utf-8', errors='ignore'))
    except Exception:
        return {"reject_methods": set(), "reject_via": set()}
    return {
        "reject_methods": set(map(str.lower, data.get("reject_methods", []))),
        "reject_via": set(map(str.lower, data.get("reject_via", []))),
    }

ALLOWED_METHOD_KEYWORDS = {
    'teleport', 'teleportation', 'teleporter',
    'stairs', 'stair', 'staircase',
    'ladder', 'rope ladder', 'rope',
    'bridge', 'tunnel', 'secret door', 'door', 'gate', 'portcullis', 'basket', 'ferry',
    'levitation', 'levitate', 'flight', 'fly', 'flying', 'walk', 'walking', 'hike', 'hiking', 'climb', 'climbing',
    'swim', 'swimming', 'boat', 'crawl', 'descend', 'descending', 'ascending', 'rappel'
}

# Canonical mapping to compress variants to a short set
CANON = {
    'levitation': 'Levitation', 'levitate': 'Levitation',
    'flight': 'Flight', 'fly': 'Flight', 'flying': 'Flight',
    'walk': 'Walk', 'walking': 'Walk', 'hike': 'Walk', 'hiking': 'Walk',
    'climb': 'Climb', 'climbing': 'Climb', 'descend': 'Climb', 'descending': 'Climb', 'ascending': 'Climb', 'rappel': 'Climb',
    'swim': 'Swim', 'swimming': 'Swim', 'boat': 'Boat', 'ferry': 'Ferry',
    'teleport': 'Teleportation', 'teleportation': 'Teleportation', 'teleporter': 'Teleportation', 'rug': 'Teleportation',
    'stairs': 'Stairs', 'stair': 'Stairs', 'staircase': 'Stairs',
    'ladder': 'Ladder', 'rope ladder': 'Ladder', 'rope': 'Rope',
    'bridge': 'Bridge', 'tunnel': 'Tunnel', 'secret door': 'Secret Door', 'door': 'Door', 'gate': 'Gate', 'portcullis': 'Gate', 'basket': 'Basket'
}

def sanitize_label(lbl: str, filters) -> str:
    if not lbl:
        return ''
    # Split on separators and keep plausible bits
    parts = [p.strip() for p in re.split(r"[;|]", lbl) if p.strip()]
    kept = []
    for p in parts:
        low = p.lower()
        # drop known rejects
        if low in filters["reject_methods"] or low in filters["reject_via"]:
            continue
        # drop phrases containing possessives or obvious names/events
        if re.search(r"[\w]('[sS])\b", p):
            continue
        if any(w in low for w in ['murder', 'market', 'brought', 'map from', 'led them', 'talk', 'traveled', 'traced back', 'guide', 'discussion']):
            continue
        # Strip directional fluff and prepositions
        low2 = re.sub(r"\b(north|south|east|west|up|down|top|bottom|base)\b", "", low)
        # Break composite phrases into candidates
        cands = re.split(r"\b(?:then|and|,| to | into | from | past | through | over | across )\b", low2)
        canon_labels = []
        for c in cands:
            c = c.strip()
            if not c:
                continue
            # allow only short chunks
            if len(c.split()) > 4:
                continue
            # Special-case multi-word
            if 'rope ladder' in c:
                canon_labels.append('Ladder')
                continue
            # map tokens
            tokens = c.split()
            mapped = []
            for t in tokens:
                if t in CANON:
                    mapped.append(CANON[t])
                elif t in ALLOWED_METHOD_KEYWORDS:
                    mapped.append(t.title())
            # Deduplicate within this chunk
            uniq = []
            for m in mapped:
                if m and m not in uniq:
                    uniq.append(m)
            if uniq:
                canon_labels.extend(uniq[:2])
        # Deduplicate across chunks and keep small
        final = []
        for m in canon_labels:
            if m not in final:
                final.append(m)
        if final:
            kept.append(' / '.join(final[:2]))
    return '; '.join([k for k in kept if k])

def main():
    if not REPORT.exists():
        raise SystemExit(f"Report not found: {REPORT}")
    lines = REPORT.read_text(encoding='utf-8', errors='ignore').splitlines()
    nodes = {}
    # map (a_id, b_id) -> set of labels
    edge_map = {}
    filters = load_filters()
    for line in lines:
        m = EDGE_RE.match(line.strip())
        if not m:
            continue
        a, b, suffix = m.groups()
        a_id = slug(a)
        b_id = slug(b)
        if a_id == b_id:
            # drop self-loops in the graph for clarity
            continue
        nodes[a_id] = a
        nodes[b_id] = b
        label = parse_label(suffix or '')
        label = sanitize_label(label, filters)
        edge_map.setdefault((a_id, b_id), set())
        if label:
            edge_map[(a_id, b_id)].add(label)

    out = ["graph TD"]
    # declare nodes with labels
    for nid, label in sorted(nodes.items()):
        out.append(f"  {nid}[\"{label}\"]")
    # edges (deduped, up to 2 labels per pair for readability)
    total = 0
    for (a,b), labels in sorted(edge_map.items()):
        lbl = ''
        if labels:
            keep = sorted(labels)[:2]
            lbl = '; '.join(keep)
        if lbl:
            out.append(f"  {a} -->|{lbl}| {b}")
        else:
            out.append(f"  {a} --> {b}")
        total += 1
    OUT.write_text("\n".join(out) + "\n", encoding='utf-8')
    print(f"Wrote {OUT} with {total} edges and {len(nodes)} nodes")

if __name__ == '__main__':
    main()
