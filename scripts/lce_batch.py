#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOC_DIR = ROOT / 'vault' / 'locations'
REPORT = ROOT / 'docs' / 'LCE_REPORT.md'

LLM_ENDPOINT = os.environ.get('LLM_ENDPOINT', 'http://192.168.21.76:1234/v1/chat/completions')
LLM_MODEL = os.environ.get('LLM_MODEL', 'qwen2.5-14b-instruct')

EDGE_LINE = re.compile(r"^\- \[\[[^\]]+\]\] -> \[\[[^\]]+\]\]")

def run_extract(location: str) -> str:
    cmd = [
        'python3', 'scripts/lce_extract.py', '--location', location, '--dry-run'
    ]
    env = os.environ.copy()
    env['LLM_ENDPOINT'] = LLM_ENDPOINT
    env['LLM_MODEL'] = LLM_MODEL
    try:
        out = subprocess.check_output(cmd, env=env, cwd=str(ROOT), timeout=120)
        return out.decode('utf-8', errors='ignore')
    except Exception as e:
        return ''

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--limit', type=int, default=4)
    ap.add_argument('--reset', action='store_true')
    args = ap.parse_args()

    names = sorted(p.stem for p in LOC_DIR.glob('*.md'))
    batch = names[args.start: args.start + args.limit]
    if args.reset:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text('', encoding='utf-8')

    with REPORT.open('a', encoding='utf-8') as f:
        for loc in batch:
            f.write(f"## {loc}\n")
            text = run_extract(loc)
            for line in text.splitlines():
                if EDGE_LINE.match(line.strip()):
                    f.write(line + "\n")
            f.write("\n")
    print(f"Processed {len(batch)} locations: {', '.join(batch)}")

if __name__ == '__main__':
    main()
