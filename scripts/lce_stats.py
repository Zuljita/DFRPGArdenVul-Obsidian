#!/usr/bin/env python3
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs' / 'LCE_REPORT.md'
OUT = ROOT / 'docs' / 'LCE_STATS.md'

EDGE_RE = re.compile(r"^- \[\[([^\]]+)\]\] -> \[\[([^\]]+)\]\](.*)$")

def main():
    if not REPORT.exists():
        raise SystemExit(f"Report not found: {REPORT}")
    lines = REPORT.read_text(encoding='utf-8', errors='ignore').splitlines()
    edges = []
    for line in lines:
        m = EDGE_RE.match(line.strip())
        if m:
            a, b, _ = m.groups()
            edges.append((a, b))
    nodes = set()
    for a, b in edges:
        nodes.add(a); nodes.add(b)
    self_loops = sum(1 for a,b in edges if a == b)
    out = Counter(); inn = Counter()
    for a,b in edges:
        out[a]+=1; inn[b]+=1
    deg = Counter({n: out[n]+inn[n] for n in nodes})
    lines_out = [
        '# LCE Stats',
        '',
        f'- Edges (raw): {len(edges)}',
        f'- Nodes: {len(nodes)}',
        f'- Self-loops: {self_loops}',
        '',
        '## Top Degree (in+out)',
    ]
    for n,c in deg.most_common(20):
        lines_out.append(f'- {n}: deg={c}, out={out[n]}, in={inn[n]}')
    OUT.write_text('\n'.join(lines_out) + '\n', encoding='utf-8')
    print(f"Wrote {OUT}")

if __name__ == '__main__':
    main()

