#!/usr/bin/env python3
import re
from pathlib import Path

SRC = Path('RawFiles/GMRecaps.txt')
OUTDIR = Path('RawFiles/GMRecaps')

HEADER_PATTERNS = [
    # Standard: DFRPG Arden Vul Session 12: Title
    re.compile(r'^DFRPG Arden Vul Session (\d+)([a-z]?):\s*(.+)$'),
    # Variant (Session 7): DFRPG Session 7: Title
    re.compile(r'^DFRPG Session (\d+):\s*(.+)$'),
    # Combined header: DFRPG Arden Vul Sessions 8b and 9: Title
    re.compile(r'^DFRPG Arden Vul Sessions (\d+[a-z]?) and (\d+):\s*(.+)$'),
]

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}\r?$')

def sanitize_title(title: str) -> str:
    # Keep letters, numbers, spaces, underscores, and hyphens; drop other punctuation
    # Convert spaces to underscores; collapse multiple underscores
    keep = []
    for ch in title:
        if ch.isalnum() or ch in [' ', '_', '-']:
            keep.append(ch)
        else:
            # drop punctuation like commas, apostrophes, colons, exclamations, etc.
            continue
    s = ''.join(keep).strip()
    s = s.replace(' ', '_')
    while '__' in s:
        s = s.replace('__', '_')
    return s

def find_headers(lines):
    headers = []  # list of dicts: {idx, kind, data, start_idx}
    for i, line in enumerate(lines):
        text = line.rstrip('\n')
        # Try combined header first to avoid mis-capturing
        m3 = HEADER_PATTERNS[2].match(text)
        if m3:
            n1, n2, title = m3.groups()
            headers.append({'idx': i, 'kind': 'combined', 'n1': n1, 'n2': n2, 'title': title})
            continue
        m1 = HEADER_PATTERNS[0].match(text)
        if m1:
            n, suffix, title = m1.groups()
            headers.append({'idx': i, 'kind': 'standard', 'n': int(n), 'suffix': suffix or '', 'title': title})
            continue
        m2 = HEADER_PATTERNS[1].match(text)
        if m2:
            n, title = m2.groups()
            headers.append({'idx': i, 'kind': 'variant', 'n': int(n), 'suffix': '', 'title': title})
            continue
    # Attach the preceding date line for each header as start
    for h in headers:
        j = h['idx'] - 1
        start = h['idx']
        while j >= 0:
            if DATE_RE.match(lines[j].rstrip('\n')):
                start = j
                break
            # stop if we hit a blank line followed by another top-level heading-like line
            j -= 1
        h['start_idx'] = start
    return headers

def main():
    if not SRC.exists():
        raise SystemExit(f"Source not found: {SRC}")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    text = SRC.read_text(encoding='utf-8', errors='ignore')
    lines = text.splitlines(True)  # keep line endings
    headers = find_headers(lines)
    # Filter to sessions <= 15 or combined within 15
    filtered = []
    for h in headers:
        if h['kind'] == 'combined':
            # Include if both numbers are <= 15 (8b and 9)
            try:
                n1_num = int(re.match(r'^(\d+)', h['n1']).group(1))
            except Exception:
                n1_num = 0
            n2_num = int(h['n2'])
            if n1_num <= 15 and n2_num <= 15:
                filtered.append(h)
        else:
            if h['n'] <= 15:
                filtered.append(h)
    # Sort by start index
    filtered.sort(key=lambda x: x['start_idx'])
    # Determine slice ranges
    slices = []
    for i, h in enumerate(filtered):
        start = h['start_idx']
        end = filtered[i+1]['start_idx'] if i+1 < len(filtered) else None
        slices.append((h, start, end))

    created = []
    for h, start, end in slices:
        chunk = ''.join(lines[start:end])
        if h['kind'] == 'combined':
            fn = f"Sessions_{h['n1']}_and_{h['n2']}_{sanitize_title(h['title'])}.txt"
        else:
            num = f"{h['n']}{h['suffix']}"
            fn = f"Session_{num}_{sanitize_title(h['title'])}.txt"
        outpath = OUTDIR / fn
        if outpath.exists():
            # Do not overwrite existing files
            continue
        outpath.write_text(chunk, encoding='utf-8')
        created.append(outpath.name)

    if created:
        print("Created:", ", ".join(created))
    else:
        print("No new files created (maybe already split)")

if __name__ == '__main__':
    main()

