#!/usr/bin/env python3
import argparse
import json
import os
import re
from pathlib import Path
from urllib import request

VAULT = Path('vault')
SESSIONS_DIR = VAULT / 'sessions'

ENDPOINT = os.environ.get('LM_STUDIO_ENDPOINT', 'http://192.168.21.76:1234/v1/chat/completions')
MODEL = os.environ.get('LM_MODEL', 'qwen2.5-7b-instruct')

CHUNK_SIZE = 2500  # ~2–3k chars per call

PROMPT = (
    "From the text, list entity candidates grouped by type (NPC, Location, Faction, Item). "
    "Title Case; exclude generics and scaffolding words; do not invent; no mapping. "
    "Return a compact JSON object with keys 'NPC', 'Location', 'Faction', 'Item', each a unique array of strings."
)

def chunk_text(text, size=CHUNK_SIZE):
    for i in range(0, len(text), size):
        yield text[i:i+size]

def llm_call(content: str, enabled=True):
    if not enabled:
        return None
    payload = {
        'model': MODEL,
        'temperature': 0.1,
        'max_tokens': 400,
        'messages': [
            {'role': 'system', 'content': 'You are precise and return strictly valid JSON.'},
            {'role': 'user', 'content': PROMPT + "\n\nTEXT:\n" + content}
        ],
    }
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(ENDPOINT, data=data, headers={'Content-Type': 'application/json'})
    try:
        with request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode('utf-8'))
            text = out['choices'][0]['message']['content']
            return text
    except Exception as e:
        return None

def parse_json_or_list(text: str):
    # Try parse JSON; else fall back to empty
    try:
        obj = json.loads(text)
        res = {k: set(map(str.strip, v)) for k, v in obj.items() if isinstance(v, list)}
        for k in ['NPC', 'Location', 'Faction', 'Item']:
            res.setdefault(k, set())
        return res
    except Exception:
        return {'NPC': set(), 'Location': set(), 'Faction': set(), 'Item': set()}

def heuristic_candidates(text: str):
    # Very conservative: quoted Title Case and capitalized multi-word phrases not at sentence start
    cands = {'NPC': set(), 'Location': set(), 'Faction': set(), 'Item': set()}
    # Quoted Title Case phrases
    for m in re.finditer(r'"([A-Z][A-Za-z]+(?:[ \-](?:of|the|and|[A-Z][A-Za-z\.\-]+))*)"', text):
        phrase = m.group(1)
        if len(phrase.split()) <= 8:
            # assign to unknown bucket; we will classify later as Item if includes Rugs, Chair, Rod, Wand; Location if Hall, Temple; else NPC/Faction heuristics
            if any(w in phrase for w in ['Rug', 'Rugs', 'Chair', 'Rod', 'Wand', 'Pebble', 'Mirror', 'Scepter', 'Armor']):
                cands['Item'].add(phrase)
            elif any(w in phrase for w in ['Hall', 'Temple', 'Library', 'Well', 'Cavern', 'Chasm', 'Pyramid', 'Palace', 'Court', 'Arena']):
                cands['Location'].add(phrase)
            elif any(w in phrase for w in ['Company', 'Brigade', 'Cult']):
                cands['Faction'].add(phrase)
            else:
                cands['NPC'].add(phrase)
    # Known patterns from text
    patterns = [
        (r'Rugs of Instant Access', 'Item'),
        (r'Returning Pebble', 'Item'),
        (r'Right for Riches Company', 'Faction'),
        (r'Anaximander', 'NPC'),
        (r'Sligo the Devious', 'NPC'),
        (r'Leonidas of Archontos', 'NPC'),
    ]
    for pat, typ in patterns:
        if re.search(pat, text):
            cands[typ].add(pat)
    return cands

def index_existing():
    idx = {}
    for folder in ['npcs', 'locations', 'factions', 'items', 'pcs']:
        for p in (VAULT / folder).glob('*.md'):
            title = p.stem
            idx.setdefault(title, []).append(p)
    return idx

def create_stub(title: str, kind: str, appears_in: list):
    folder = {'NPC': 'npcs', 'Location': 'locations', 'Faction': 'factions', 'Item': 'items'}[kind]
    path = VAULT / folder / f"{title}.md"
    if path.exists():
        return False
    fm = [
        '---',
        f'title: "{title}"',
        'tags:',
        f'  - {folder[:-1] if folder != "pcs" else "pc"}',
        'aliases:',
        '---',
        f'# {title}',
        '',
        '## Summary',
        f'- TODO: Short description for {kind.lower()}.',
        '',
        '## Appears In',
    ]
    for s in sorted(set(appears_in)):
        fm.append(f'- [[sessions/{s}|{s.replace(".md", "")}]]')
    fm.append('')
    path.write_text("\n".join(fm), encoding='utf-8')
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--create', action='store_true', help='Create stubs for NEW entities')
    ap.add_argument('files', nargs='*', help='Session files to process')
    ap.add_argument('--no-llm', action='store_true', help='Disable LLM calls; use heuristic only')
    args = ap.parse_args()

    files = [Path(f) for f in (args.files or sorted(SESSIONS_DIR.glob('Session *.md')))]
    existing = index_existing()
    aggregated = {'NPC': set(), 'Location': set(), 'Faction': set(), 'Item': set()}
    appearances = {}  # title -> set of sessions

    for f in files:
        text = f.read_text(encoding='utf-8', errors='ignore')
        agg_chunk = {'NPC': set(), 'Location': set(), 'Faction': set(), 'Item': set()}
        use_llm = not args.no_llm
        for chunk in chunk_text(text):
            out = llm_call(chunk, enabled=use_llm)
            if out:
                res = parse_json_or_list(out)
            else:
                res = heuristic_candidates(chunk)
            for k in agg_chunk:
                agg_chunk[k].update(res.get(k, set()))
        # aggregate overall and record appearances per session
        for k in aggregated:
            for title in agg_chunk[k]:
                aggregated[k].add(title)
                appearances.setdefault(title, set()).add(f.name)

    # Map to existing vs new
    mapping = {'existing': {}, 'new': {}}
    for k, vals in aggregated.items():
        mapping['existing'][k] = []
        mapping['new'][k] = []
        for title in sorted(vals):
            if title in existing:
                mapping['existing'][k].append(title)
            else:
                mapping['new'][k].append(title)

    print('Mappings (existing):')
    for k in ['NPC', 'Location', 'Faction', 'Item']:
        print(f'- {k}: ' + ", ".join(mapping['existing'][k]))
    print('\nNew pages needed:')
    for k in ['NPC', 'Location', 'Faction', 'Item']:
        for title in mapping['new'][k]:
            print(f'- {k}: {title}')
    print('\nLink insertion plan:')
    for k in ['NPC', 'Location', 'Faction', 'Item']:
        for title in mapping['new'][k]:
            sess = sorted(appearances.get(title, []))
            if sess:
                print(f'- {title}: appears in {", ".join(sess)} -> link as [[{k.lower()}s/{title}.md|{title}]]')

    if args.create:
        created = []
        for k in ['NPC', 'Location', 'Faction', 'Item']:
            for title in mapping['new'][k]:
                sess = sorted(appearances.get(title, []))
                if create_stub(title, k, sess):
                    created.append((k, title))
        if created:
            print('\nCreated stubs:')
            for k, title in created:
                print(f'- {k}: {title}')
        else:
            print('\nNo stubs created (none new or already existed).')

if __name__ == '__main__':
    main()
