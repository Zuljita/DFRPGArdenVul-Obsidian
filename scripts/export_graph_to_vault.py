#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH_SRC = ROOT / 'docs' / 'locations_graph.mmd'
OUT = ROOT / 'vault' / 'graphs' / 'Location Connections.md'

def main():
    if not GRAPH_SRC.exists():
        raise SystemExit(f"Graph source not found: {GRAPH_SRC}")
    text = GRAPH_SRC.read_text(encoding='utf-8', errors='ignore')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    md = [
        '# Location Connections',
        '',
        'Auto-generated from LCE edges. Update by running the LCE scripts and rebuilding.',
        '',
        '```mermaid',
        text.strip(),
        '```',
        '',
    ]
    OUT.write_text('\n'.join(md), encoding='utf-8')
    print(f"Wrote {OUT}")

if __name__ == '__main__':
    main()

