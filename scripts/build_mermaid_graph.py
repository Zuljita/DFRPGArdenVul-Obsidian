#!/usr/bin/env python3
import re
from pathlib import Path

REPORT = Path('docs/LCE_REPORT.md')
OUT = Path('docs/locations_graph.mmd')

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

def main():
    if not REPORT.exists():
        raise SystemExit(f"Report not found: {REPORT}")
    lines = REPORT.read_text(encoding='utf-8', errors='ignore').splitlines()
    nodes = {}
    edges = []
    for line in lines:
        m = EDGE_RE.match(line.strip())
        if not m:
            continue
        a, b, suffix = m.groups()
        a_id = slug(a)
        b_id = slug(b)
        nodes[a_id] = a
        nodes[b_id] = b
        label = parse_label(suffix or '')
        edges.append((a_id, b_id, label))

    out = ["graph TD"]
    # declare nodes with labels
    for nid, label in sorted(nodes.items()):
        out.append(f"  {nid}[\"{label}\"]")
    # edges
    for a, b, lbl in edges:
        if lbl:
            out.append(f"  {a} -->|{lbl}| {b}")
        else:
            out.append(f"  {a} --> {b}")
    OUT.write_text("\n".join(out) + "\n", encoding='utf-8')
    print(f"Wrote {OUT} with {len(edges)} edges and {len(nodes)} nodes")

if __name__ == '__main__':
    main()
