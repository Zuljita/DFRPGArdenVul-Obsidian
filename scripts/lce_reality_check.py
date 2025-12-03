#!/usr/bin/env python3
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs' / 'LCE_REPORT.md'
OUT = ROOT / 'docs' / 'LCE_SANITY.md'
FILTERS = ROOT / 'docs' / 'LCE_FILTERS.json'

EDGE_RE = re.compile(r"^- \[\[([^\]]+)\]\] -> \[\[([^\]]+)\]\](.*)$")
VIA_RE = re.compile(r"\[via\s+([^\]]+)\]", re.I)
METHOD_RE = re.compile(r"\[method:\s*([^\]]+)\]", re.I)

LLM_ENDPOINT = os.environ.get('LLM_ENDPOINT', 'http://192.168.21.76:1234/v1/chat/completions')
LLM_MODEL = os.environ.get('LLM_MODEL', 'qwen2.5-7b-instruct')

def call_llm(items, prompt_tmpl, sys='Answer YES or NO only.', temperature=0.1, max_tokens=8):
    import urllib.request, json as _json
    results = {}
    for it in items:
        payload = {
            'model': LLM_MODEL,
            'messages': [
                {'role': 'system', 'content': sys},
                {'role': 'user', 'content': prompt_tmpl.format(x=it)},
            ],
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        data = _json.dumps(payload).encode('utf-8')
        try:
            req = urllib.request.Request(LLM_ENDPOINT, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode('utf-8')
                j = _json.loads(body)
                txt = j['choices'][0]['message']['content'].strip().upper()
                results[it] = 'YES' in txt
        except Exception:
            results[it] = True  # be permissive on failure
    return results

def main():
    if not REPORT.exists():
        raise SystemExit(f"Report not found: {REPORT}")
    lines = REPORT.read_text(encoding='utf-8', errors='ignore').splitlines()
    vias = set(); methods = set()
    for ln in lines:
        m = EDGE_RE.match(ln.strip())
        if not m:
            continue
        suf = m.group(3) or ''
        for vm in VIA_RE.finditer(suf):
            val = vm.group(1).strip()
            if val:
                vias.add(val)
        for mm in METHOD_RE.finditer(suf):
            val = mm.group(1).strip()
            if val:
                methods.add(val)

    vias = sorted(vias)
    methods = sorted(methods)

    # LLM screens
    via_ok = call_llm(vias, 'Does this phrase describe a route segment, connector, or place (not an event/person)? "{x}"')
    method_ok = call_llm(methods, 'Is this a travel method or movement mode (e.g., stairs, teleportation, bridge, rope ladder, levitation, flight, walking, swimming)? "{x}"')

    reject_via = [v for v, ok in via_ok.items() if not ok]
    reject_methods = [m for m, ok in method_ok.items() if not ok]

    OUT.write_text('\n'.join([
        '# LCE Sanity Check', '',
        f'- Unique via phrases: {len(vias)}',
        f'- Unique methods: {len(methods)}',
        f'- Rejected via: {len(reject_via)}',
        f'- Rejected methods: {len(reject_methods)}',
        '', '## Rejected via', *[f'- {v}' for v in sorted(reject_via)],
        '', '## Rejected methods', *[f'- {m}' for m in sorted(reject_methods)],
        '',
    ]), encoding='utf-8')

    # Emit filters for graph builder
    data = {'reject_via': sorted(reject_via), 'reject_methods': sorted(reject_methods)}
    FILTERS.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(f"Wrote {OUT} and {FILTERS}")

if __name__ == '__main__':
    main()

