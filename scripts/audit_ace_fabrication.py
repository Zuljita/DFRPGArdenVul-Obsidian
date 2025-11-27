#!/usr/bin/env python3
"""
Audit ACE-edited NPC pages for potential fabrication by checking that
each Relationships bullet has at least some support in session files.

Method (conservative):
- Parse completed targets from docs/ACE_LOG.md (NPC names from wikilinks).
- Load index from scripts/output/npc_mentions.json to know where each NPC
  and any relationship targets are mentioned across sessions.
- For each Relationships line in the NPC page, find wikilink targets.
- Flag a relationship if there is no co-occurrence of the NPC and the target
  in any single session file (same file path under vault/sessions/).

Output: docs/ACE_AUDIT.md with a table of suspects and context.

Note: This is a heuristic; co-occurrence does not prove the stated relation,
but lack of any co-occurrence is a useful signal to re-check wording or add
“Rumor:” qualifiers.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

VAULT = Path('vault')
LOG = Path('docs/ACE_LOG.md')
INDEX = Path('scripts/output/npc_mentions.json')
OUT = Path('docs/ACE_AUDIT.md')

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def parse_completed() -> List[str]:
    if not LOG.exists():
        return []
    text = LOG.read_text(encoding='utf-8', errors='ignore')
    names = re.findall(r"\[\[vault/npcs/[^\]|]+\|([^\]]+)\]\]", text)
    # preserve order of first appearance
    seen = set()
    ordered = []
    for n in names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def load_index() -> Dict[str, dict]:
    return json.loads(INDEX.read_text(encoding='utf-8'))


def path_for_name(index: Dict[str, dict], name: str) -> str | None:
    for data in index.values():
        if (data.get('canonical') or '').strip() == name:
            return data['path']
    return None


def aliases_for_name(index: Dict[str, dict], name: str) -> List[str]:
    for data in index.values():
        if (data.get('canonical') or '').strip() == name:
            out = [name]
            out.extend(data.get('aliases', []) or [])
            # Include simple name variants without titles (e.g., drop surname or given), but keep conservative
            return out
    return [name]


def parse_relationships(npc_path: Path) -> List[Tuple[str, str]]:
    """Return list of (target_text, full_line) from Relationships section."""
    text = npc_path.read_text(encoding='utf-8', errors='ignore')
    # Find Relationships header
    m = re.search(r"^##\s*Relationships\s*$", text, flags=re.M)
    if not m:
        return []
    start = m.end()
    # until next '## ' or end
    m2 = re.search(r"^##\s+", text[start:], flags=re.M)
    end = start + m2.start() if m2 else len(text)
    block = text[start:end]
    pairs = []
    for line in block.splitlines():
        if not line.strip().startswith('-'):
            continue
        for wm in WIKILINK_RE.finditer(line):
            target = wm.group(1).strip()
            pairs.append((target, line.strip()))
    return pairs


def to_session_set(index: Dict[str, dict], name: str) -> set[str]:
    path = path_for_name(index, name)
    if not path:
        return set()
    # Find the index key by matching path
    key = None
    for k, data in index.items():
        if data.get('path') == path:
            key = k
            break
    if key is None:
        return set()
    sess = set()
    for m in index[key].get('mentions', []):
        f = m.get('file','')
        if f.startswith('vault/sessions/'):
            sess.add(f)
    return sess


def main():
    if not INDEX.exists():
        raise SystemExit('Missing scripts/output/npc_mentions.json. Run indexer first.')
    completed = parse_completed()
    idx = load_index()
    lines: List[str] = []
    lines.append('# ACE Audit — Potential Fabrication Flags')
    lines.append('')
    lines.append('Heuristic: flags relationships with no session co-occurrence between the NPC and the linked target. Review and adjust wording or add “Rumor:” as needed.')
    lines.append('')
    lines.append('| NPC | Relationship Line | Reason |')
    lines.append('|:----|:-------------------|:-------|')

    count = 0
    for name in completed:
        npc_path_str = path_for_name(idx, name)
        if not npc_path_str:
            continue
        npc_path = Path(npc_path_str)
        abs_npc_path = Path(npc_path_str)
        if not abs_npc_path.exists():
            abs_npc_path = Path('vault') / npc_path_str  # fallback
        if not abs_npc_path.exists():
            continue
        rels = parse_relationships(abs_npc_path)
        if not rels:
            continue
        npc_sessions = to_session_set(idx, name)
        for target, line in rels:
            # We only consider in-vault links (with or without .md)
            if target.startswith(('http://','https://','#')):
                continue
            if target.startswith('sessions/'):
                # Skip direct session links in relationships (likely miscategorized content)
                continue
            # Normalize to canonical display if like 'npcs/X.md' or 'folder/X.md'
            if target.endswith('.md'):
                disp = target.split('/')[-1].removesuffix('.md')
            elif '/' in target:
                disp = target.split('/')[-1]
            else:
                disp = target
            # Determine link type by folder prefix if present
            link_type = None
            if '/' in target:
                link_type = target.split('/')[0]
            # Primary: NPC target — use index co-occurrence
            if link_type == 'npcs' or path_for_name(idx, disp):
                target_sessions = to_session_set(idx, disp)
                if not (npc_sessions & target_sessions):
                    # Try RawFiles fallback
                    raw_supported = False
                    npc_aliases = aliases_for_name(idx, name)
                    target_aliases = aliases_for_name(idx, disp)
                    for rf in Path('RawFiles').rglob('*'):
                        if not rf.is_file():
                            continue
                        try:
                            rtxt = rf.read_text(encoding='utf-8', errors='ignore')
                        except Exception:
                            continue
                        if any(a in rtxt for a in npc_aliases) and any(b in rtxt for b in target_aliases):
                            raw_supported = True
                            break
                    if not raw_supported:
                        lines.append(f"| {name} | {line.replace('|','\\|')} | No session co-occurrence with {disp} (NPC) |")
                        count += 1
                continue
            # Fallback for non-NPC targets (pcs/, factions/, locations/): scan NPC sessions for the display string
            supported = False
            for sf in npc_sessions:
                stext = Path(sf).read_text(encoding='utf-8', errors='ignore')
                if disp in stext:
                    supported = True
                    break
            if not supported:
                # Secondary: search co-occurrence in RawFiles/* as additional data source
                raw_supported = False
                for rf in Path('RawFiles').rglob('*'):
                    if not rf.is_file():
                        continue
                    try:
                        rtxt = rf.read_text(encoding='utf-8', errors='ignore')
                    except Exception:
                        continue
                    if name in rtxt and disp in rtxt:
                        raw_supported = True
                        break
                if raw_supported:
                    continue
                lines.append(f"| {name} | {line.replace('|','\\|')} | No occurrence of '{disp}' found in same sessions |")
                count += 1

    if count == 0:
        lines.append('| (none) | | |')
    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Wrote audit report to {OUT} with {count} potential flags.')


if __name__ == '__main__':
    main()
