#!/usr/bin/env python3
"""
LLM Model Benchmark:
- Query available models from the local endpoint
- Determine which models haven't been benchmarked yet
- Run baseline tests: IAC, LCE, ACE (discovery-only), and CAC on a sample file
- Save a static copy of the Goblins faction file for repeatable benchmarks
- Record results under docs/benchmarks/
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Any

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / 'vault'
DOCS = ROOT / 'docs' / 'benchmarks'
SAMPLES = DOCS / 'samples'
RESULTS = DOCS / 'results.jsonl'

SESSION = VAULT / 'sessions' / 'Session 33 - Nyema.md'
SAMPLE_GOBLINS = VAULT / 'factions' / 'Goblins.md'

def run(cmd, timeout=120):
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        return p.returncode, time.perf_counter() - t0, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, timeout, '', 'TIMEOUT'

def query_models(endpoint: str):
    import urllib.request, json as _json
    with urllib.request.urlopen(endpoint.rstrip('/') + '/v1/models', timeout=10) as r:
        data = _json.loads(r.read().decode('utf-8'))
        arr = data.get('data', [])
        # Prefer id, fall back to name
        models = [m.get('id') or m.get('name') for m in arr if isinstance(m, dict)]
    # Filter out obvious non-chat models
    return [m for m in models if 'embed' not in m.lower()]

def benchmark_model(endpoint: str, model: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {'model': model}
    # IAC baseline
    cmd = ['python3', str(ROOT / 'scripts' / 'run_iac.py'), '--file', str(SESSION), '--dry-run', '--kinds', 'NPC,Location,Faction', '--items-mode', 'unique', '--chunk-size', '2400', '--endpoint', endpoint, '--model', model]
    rc, dt, out, err = run(cmd, timeout=120)
    result['iac'] = {'rc': rc, 'time_s': round(dt, 2)}
    try:
        j = json.loads(out)
        rec = j[0] if j else {}
        result['iac']['mapped'] = len(rec.get('mapped', [])) if isinstance(rec, dict) else None
        result['iac']['would_create'] = len(rec.get('would_create', [])) if isinstance(rec, dict) else None
    except Exception:
        result['iac']['error'] = (err or out)[:400]

    # LCE baseline (Temple of Set, para-window=3)
    cmd = ['python3', str(ROOT / 'scripts' / 'lce_extract.py'), '--location', 'Temple of Set', '--session', str(SESSION), '--para-window', '3', '--dry-run', '--endpoint', endpoint, '--model', model]
    rc, dt, out, err = run(cmd, timeout=120)
    edges = sum(1 for line in out.splitlines() if '->' in line)
    narrative = sum(1 for line in out.splitlines() if any(x in line.lower() for x in ['murder','brought','map','talk','led them']))
    result['lce'] = {'rc': rc, 'time_s': round(dt, 2), 'edges': edges, 'narrative_terms': narrative}
    if rc != 0:
        result['lce']['error'] = (err or out)[:400]

    # ACE discovery-only: count missing entity candidates using heuristic fallback
    cmd = ['python3', str(ROOT / 'scripts' / 'process_new_data.py'), '--input', str(SESSION)]
    rc, dt, out, err = run(cmd, timeout=60)
    result['ace'] = {'rc': rc, 'time_s': round(dt, 2)}
    if rc == 0:
        # Parse counts from stdout (loosely)
        # e.g., "Found 45 candidates; existing: 39, missing: 6"
        import re
        m = re.search(r"missing:\s*(\d+)", out)
        if m:
            result['ace']['missing'] = int(m.group(1))
    else:
        result['ace']['error'] = (err or out)[:400]

    # CAC on sample goblins copy
    SAMPLES.mkdir(parents=True, exist_ok=True)
    gob_sample = SAMPLES / 'Goblins.sample.md'
    try:
        text = SAMPLE_GOBLINS.read_text(encoding='utf-8', errors='ignore')
        gob_sample.write_text(text, encoding='utf-8')
    except Exception:
        pass
    # We run CAC against the canonical vault file but write report into docs
    cac_report = DOCS / f'CAC_Goblins_{model.replace("/","_")}.md'
    cmd = ['python3', str(ROOT / 'scripts' / 'cac_check.py'), '--input', str(SAMPLE_GOBLINS.relative_to(VAULT)), '--endpoint', endpoint, '--model', model, '--report', str(cac_report)]
    rc, dt, out, err = run(cmd, timeout=180)
    result['cac'] = {'rc': rc, 'time_s': round(dt, 2), 'report': str(cac_report.relative_to(ROOT))}
    if rc != 0:
        result['cac']['error'] = (err or out)[:400]
    return result

def main():
    p = argparse.ArgumentParser(description='Benchmark local LLM models for IAC/LCE/ACE/CAC')
    p.add_argument('--endpoint', default='http://192.168.21.76:1234')
    p.add_argument('--all', action='store_true', help='Benchmark all available models (except embeddings)')
    p.add_argument('--new', action='store_true', help='Benchmark only models not seen in previous results')
    args = p.parse_args()

    DOCS.mkdir(parents=True, exist_ok=True)
    seen = set()
    if RESULTS.exists():
        with RESULTS.open('r', encoding='utf-8') as f:
            for line in f:
                try:
                    j = json.loads(line)
                    seen.add(j.get('model'))
                except Exception:
                    pass

    models = query_models(args.endpoint)
    # Prefer a stable shortlist unless --all
    shortlist = [m for m in models if any(k in m.lower() for k in ['qwen','llama','mistral','gpt','glm','ministral'])]
    targets = shortlist if args.all else [m for m in shortlist if (args.new and m not in seen) or (not args.new and m in ('qwen2.5-7b-instruct','meta-llama-3.1-8b-instruct','mistralai/ministral-3-14b-reasoning'))]
    if not targets:
        print('No models to benchmark (check --all or --new)')
        return

    for m in targets:
        res = benchmark_model(args.endpoint, m)
        with RESULTS.open('a', encoding='utf-8') as f:
            f.write(json.dumps(res) + '\n')
        print(json.dumps(res, indent=2))

if __name__ == '__main__':
    main()

