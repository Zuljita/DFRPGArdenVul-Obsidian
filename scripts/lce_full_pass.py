#!/usr/bin/env python3
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOC_DIR = ROOT / 'vault' / 'locations'
SESS_DIR = ROOT / 'vault' / 'sessions'
REPORT = ROOT / 'docs' / 'LCE_REPORT.md'

LLM_ENDPOINT = os.environ.get('LLM_ENDPOINT', 'http://192.168.21.76:1234/v1/chat/completions')
LLM_MODEL = os.environ.get('LLM_MODEL', 'qwen2.5-14b-instruct')

EDGE_LINE = re.compile(r"^\- \[\[[^\]]+\]\] -> \[\[[^\]]+\]\]")

def run_extract(location: str) -> str:
    cmd = [
        'python3', 'scripts/lce_extract.py',
        '--location', location,
        '--dry-run'
    ]
    env = os.environ.copy()
    env['LLM_ENDPOINT'] = LLM_ENDPOINT
    env['LLM_MODEL'] = LLM_MODEL
    try:
        out = subprocess.check_output(cmd, env=env, cwd=str(ROOT), timeout=180)
        return out.decode('utf-8', errors='ignore')
    except subprocess.CalledProcessError as e:
        return e.output.decode('utf-8', errors='ignore')
    except Exception:
        return ''

def main():
    locations = sorted(p.stem for p in LOC_DIR.glob('*.md'))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# LCE Report (Aggregated, mapped edges only)',
        '',
        f'- Sessions scanned: {len(list(SESS_DIR.glob("*.md")))}',
        f'- Locations scanned: {len(locations)}',
        '',
    ]
    total_edges = 0
    for name in locations:
        text = run_extract(name)
        if not text:
            continue
        # Keep only mapped edge lines: "- [[A]] -> [[B]] ..."
        mapped = [l for l in text.splitlines() if EDGE_LINE.match(l.strip())]
        if not mapped:
            continue
        lines.append(f'## {name}')
        lines.extend(mapped)
        lines.append('')
        total_edges += len(mapped)
    # Summary at top
    lines.insert(3, f'- Mapped edges: {total_edges}')
    REPORT.write_text('\n'.join(lines), encoding='utf-8')
    print(f"Wrote {REPORT} with {total_edges} edges")

if __name__ == '__main__':
    main()
