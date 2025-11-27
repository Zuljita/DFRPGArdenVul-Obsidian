#!/usr/bin/env python3
"""
Index NPC mentions across the vault using canonical names and frontmatter aliases.

Outputs:
- JSON index with all mentions + context per NPC
- Markdown punch list sorted by frequency (links+text)
- Optional link-only punch lists
- Session coverage punch lists (by distinct sessions)

Usage:
  python3 scripts/index_npc_mentions.py \
    --vault vault \
    --output-json scripts/output/npc_mentions.json \
    --output-punchlist docs/ACE_PUNCHLIST.md \
    --context-lines 4 \
    --ignore-list config/ace_ignore_npcs.txt \
    --output-punchlist-links docs/ACE_PUNCHLIST_LINKS.md \
    --output-stubs docs/ACE_PUNCHLIST_STUBS.md \
    --output-stubs-links docs/ACE_PUNCHLIST_STUBS_LINKS.md

Notes:
- Detects wikilinks that target the NPC page by matching against filename, folder path, title, and aliases.
- Also searches plain-text mentions using aliases (case-insensitive phrase match with word boundaries where applicable).
- Excludes the NPC's own file from frequency counts.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")


@dataclass
class NPC:
    path: Path
    title: str
    aliases: List[str] = field(default_factory=list)

    def accepted_targets(self) -> List[str]:
        # Link targets we accept inside [[...]] to recognize this NPC
        name = self.path.stem
        targets = {name, f"npcs/{name}", f"{name}.md", f"npcs/{name}.md"}
        # Add title and aliases as valid link targets (Obsidian supports alias linking)
        if self.title:
            targets.add(self.title)
        for a in self.aliases:
            if a:
                targets.add(a)
        # Normalize to lowercase for comparison
        return sorted({t.strip().lower() for t in targets if t and t.strip()})


def iter_md_files(root: Path) -> List[Path]:
    return [p for p in root.rglob('*.md') if p.is_file()]


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], List[str]]:
    """Return (fields, alias_list).
    Minimal YAML-ish frontmatter parser that extracts 'title' and all 'aliases' items.
    Supports multiple 'aliases:' blocks.
    """
    fields: Dict[str, str] = {}
    aliases: List[str] = []
    lines = text.splitlines()
    if not (lines and lines[0].strip() == '---'):
        return fields, aliases
    # Find closing '---'
    end = None
    for i in range(1, min(len(lines), 400)):
        if lines[i].strip() == '---':
            end = i
            break
    if end is None:
        return fields, aliases
    in_aliases = False
    # Parse between 1..end-1
    for i in range(1, end):
        line = lines[i].rstrip('\n')
        # title: "Foo" or title: Foo
        if line.startswith('title:'):
            val = line.split(':', 1)[1].strip().strip('"')
            if val:
                fields['title'] = val
            in_aliases = False
            continue
        if re.match(r"^aliases:\s*$", line):
            in_aliases = True
            continue
        if in_aliases:
            m = re.match(r"^\s*-[ \t]+(.+)$", line)
            if m:
                aliases.append(m.group(1).strip().strip('"'))
                continue
            # Any non-list line ends aliases block
            if line.strip() and not line.lstrip().startswith('#'):
                in_aliases = False
    return fields, aliases


def extract_h1(text: str) -> str:
    for line in text.splitlines():
        if line.startswith('# '):
            return line[2:].strip()
    return ''


def load_npcs(vault: Path) -> Dict[str, NPC]:
    npcs_dir = vault / 'npcs'
    npcs: Dict[str, NPC] = {}
    for p in sorted(npcs_dir.glob('*.md')):
        text = p.read_text(encoding='utf-8', errors='ignore')
        fields, aliases = parse_frontmatter(text)
        title = fields.get('title') or extract_h1(text) or p.stem
        # Deduplicate aliases; include the simple pre-comma variant to catch appositives
        norm_aliases = []
        seen = set()
        for a in aliases:
            for cand in {a, a.split(',')[0].strip()}:
                if cand and cand.lower() not in seen:
                    norm_aliases.append(cand)
                    seen.add(cand.lower())
        npcs[p.stem] = NPC(path=p, title=title, aliases=norm_aliases)
    return npcs


def context_block(lines: List[str], line_idx: int, context: int) -> str:
    start = max(0, line_idx - context)
    end = min(len(lines), line_idx + context + 1)
    return '\n'.join(lines[start:end]).rstrip('\n')


def is_word_boundary_match(text: str, start: int, end: int) -> bool:
    # Ensure alias phrase is not embedded inside a larger word where alnum/underscore bounds exist
    before = text[start - 1] if start > 0 else ' '
    after = text[end] if end < len(text) else ' '
    return (not (before.isalnum() or before == '_')) and (not (after.isalnum() or after == '_'))


def index_mentions(vault: Path, context_lines: int = 4) -> Dict[str, dict]:
    npcs = load_npcs(vault)
    files = [p for p in iter_md_files(vault)]

    # Build quick lookup of accepted targets per NPC (lowercased)
    npc_targets: Dict[str, List[str]] = {k: v.accepted_targets() for k, v in npcs.items()}

    # Output structure
    result: Dict[str, dict] = {}
    for key, npc in npcs.items():
        result[key] = {
            'canonical': npc.title or npc.path.stem,
            'path': str(npc.path.as_posix()),
            'aliases': npc.aliases,
            'mentions': [],  # list of dicts
            'link_mentions': 0,
            'text_mentions': 0,
            # coverage tracking (distinct files/sessions)
            '_files': set(),
            '_link_files': set(),
            '_sessions': set(),
            '_link_sessions': set(),
        }

    for path in files:
        text = path.read_text(encoding='utf-8', errors='ignore')
        lines = text.splitlines()

        # Parse wikilinks once per file
        links = list(WIKILINK_RE.finditer(text))
        # Map file positions to skip for plain-text to avoid double counting
        skip_ranges: List[Tuple[int, int]] = [(m.start(), m.end()) for m in links]

        # Handle wikilink targets
        for m in links:
            target = m.group(1).strip()
            low = target.lower()
            for key, targets in npc_targets.items():
                if low in targets:
                    # Record mention (exclude the NPC's own page from counts)
                    npc = npcs[key]
                    line_idx = text.count('\n', 0, m.start())  # 0-based
                    mention = {
                        'file': str(path.as_posix()),
                        'line': line_idx + 1,
                        'type': 'link',
                        'target': target,
                        'display': m.group(2) or '',
                        'context': context_block(lines, line_idx, context_lines),
                    }
                    rec = result[key]
                    rec['mentions'].append(mention)
                    if path != npc.path:
                        rec['link_mentions'] += 1
                        rec['_link_files'].add(str(path))
                        rec['_files'].add(str(path))
                        # session detection
                        if str(path).startswith('vault/sessions/Session '):
                            rec['_link_sessions'].add(str(path))
                            rec['_sessions'].add(str(path))
                    break

        # Prepare plain-text scan by masking link spans to avoid recounting
        masked = []
        i = 0
        for s, e in sorted(skip_ranges):
            if i < s:
                masked.append(text[i:s])
            masked.append(' ' * (e - s))
            i = e
        masked.append(text[i:])
        masked_text = ''.join(masked)
        masked_lines = masked_text.splitlines()

        # Plain-text alias search per NPC
        for key, npc in npcs.items():
            # Skip searching inside the NPC file itself to keep frequency meaningful
            if path == npc.path:
                continue
            # Build alias candidates: title, filename stem, and aliases
            cand_aliases = [npc.title, npc.path.stem] + npc.aliases
            # Deduplicate (case-insensitive)
            seen = set()
            uniq_aliases = []
            for a in cand_aliases:
                if not a:
                    continue
                la = a.lower()
                if la not in seen:
                    seen.add(la)
                    uniq_aliases.append(a)

            for alias in uniq_aliases:
                if not alias or len(alias) < 2:
                    continue
                pattern = re.escape(alias)
                for m in re.finditer(pattern, masked_text, flags=re.IGNORECASE):
                    # Enforce word-boundary-ish to reduce false positives
                    if not is_word_boundary_match(masked_text, m.start(), m.end()):
                        continue
                    line_idx = masked_text.count('\n', 0, m.start())
                    mention = {
                        'file': str(path.as_posix()),
                        'line': line_idx + 1,
                        'type': 'text',
                        'match': m.group(0),
                        'alias': alias,
                        'context': context_block(masked_lines, line_idx, context_lines),
                    }
                    rec = result[key]
                    rec['mentions'].append(mention)
                    rec['text_mentions'] += 1
                    rec['_files'].add(str(path))
                    if str(path).startswith('vault/sessions/Session '):
                        rec['_sessions'].add(str(path))

    # Finalize: Sort mentions and compute coverage counts
    for key in result:
        rec = result[key]
        rec['mentions'].sort(key=lambda x: (x['file'], x['line']))
        rec['files_count'] = len(rec.pop('_files'))
        rec['link_files_count'] = len(rec.pop('_link_files'))
        rec['sessions_count'] = len(rec.pop('_sessions'))
        rec['link_sessions_count'] = len(rec.pop('_link_sessions'))
    return result


def load_ignore_list(path: Path | None) -> set[str]:
    ignore = set()
    if not path:
        return ignore
    if path.exists():
        for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            ignore.add(s.lower())
    return ignore


def write_outputs(index: Dict[str, dict],
                  output_json: Path,
                  output_punchlist: Path,
                  output_punchlist_links: Path | None = None,
                  output_stubs: Path | None = None,
                  output_stubs_links: Path | None = None,
                  ignore_names: set[str] | None = None):
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open('w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    # Build punch list sorted by total mentions (link + text), descending
    scored = []
    for key, data in index.items():
        nm = (data.get('canonical') or '').lower() or Path(data['path']).stem.lower()
        if ignore_names and (nm in ignore_names):
            continue
        total = int(data.get('link_mentions', 0)) + int(data.get('text_mentions', 0))
        scored.append((total, key, data))
    scored.sort(key=lambda x: (-x[0], x[1]))

    lines: List[str] = []
    lines.append('# ACE Punch List — NPCs by Mention Frequency')
    lines.append('')
    lines.append('Notes: counts exclude mentions inside the NPC’s own article; links and plain-text mentions are both counted. Index JSON contains full context for each occurrence.')
    lines.append('')
    lines.append('| Rank | NPC | Mentions | Links | Text | File |')
    lines.append('|---:|:-----|---:|---:|---:|:-----|')

    rank = 0
    for total, key, data in scored:
        if total == 0:
            continue
        rank += 1
        name = data['canonical']
        links = data.get('link_mentions', 0)
        texts = data.get('text_mentions', 0)
        rel = Path(data['path']).as_posix()
        lines.append(f"| {rank} | [[{rel}|{name}]] | {total} | {links} | {texts} | {rel} |")

    output_punchlist.parent.mkdir(parents=True, exist_ok=True)
    output_punchlist.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    # Link-only overall list
    if output_punchlist_links:
        lines = []
        lines.append('# ACE Punch List — NPCs by Link Mentions Only')
        lines.append('')
        lines.append('Notes: counts include only wikilink mentions (more conservative signal).')
        lines.append('')
        lines.append('| Rank | NPC | Links | File |')
        lines.append('|---:|:-----|---:|:-----|')
        scored_links = []
        for key, data in index.items():
            nm = (data.get('canonical') or '').lower() or Path(data['path']).stem.lower()
            if ignore_names and (nm in ignore_names):
                continue
            links = int(data.get('link_mentions', 0))
            if links > 0:
                scored_links.append((links, key, data))
        scored_links.sort(key=lambda x: (-x[0], x[1]))
        rank = 0
        for links, key, data in scored_links:
            rank += 1
            name = data['canonical']
            rel = Path(data['path']).as_posix()
            lines.append(f"| {rank} | [[{rel}|{name}]] | {links} | {rel} |")
        output_punchlist_links.parent.mkdir(parents=True, exist_ok=True)
        output_punchlist_links.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    # Stubs-only lists
    def is_stub(path: Path) -> bool:
        try:
            txt = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return False
        return re.search(r'^-\s*TODO', txt, flags=re.M) is not None

    def build_stub_rows(metric: str) -> List[Tuple[int, dict]]:
        rows = []
        for key, data in index.items():
            p = Path(data['path'])
            nm = (data.get('canonical') or '').lower() or p.stem.lower()
            if ignore_names and (nm in ignore_names):
                continue
            if not is_stub(p):
                continue
            val = int(data.get(metric, 0))
            if val > 0:
                rows.append((val, data))
        rows.sort(key=lambda x: (-x[0], (Path(x[1]['path']).stem)))
        return rows

    if output_stubs:
        lines = []
        lines.append('# ACE Priority — NPC Stubs by Mention Frequency')
        lines.append('')
        lines.append('Scope: NPC pages containing a TODO stub, ordered by total mentions (links + text), excluding the NPC’s own page.')
        lines.append('')
        lines.append('| Rank | NPC | Mentions | File |')
        lines.append('|---:|:-----|---:|:-----|')
        rows = build_stub_rows('link_mentions')
        # We want links + text here
        rows = []
        for key, data in index.items():
            p = Path(data['path'])
            nm = (data.get('canonical') or '').lower() or p.stem.lower()
            if ignore_names and (nm in ignore_names):
                continue
            if not is_stub(p):
                continue
            total = int(data.get('link_mentions', 0)) + int(data.get('text_mentions', 0))
            if total > 0:
                rows.append((total, data))
        rows.sort(key=lambda x: (-x[0], (Path(x[1]['path']).stem)))
        rank = 0
        for total, data in rows:
            rank += 1
            name = data['canonical']
            rel = Path(data['path']).as_posix()
            lines.append(f"| {rank} | [[{rel}|{name}]] | {total} | {rel} |")
        output_stubs.parent.mkdir(parents=True, exist_ok=True)
        output_stubs.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    if output_stubs_links:
        lines = []
        lines.append('# ACE Priority — NPC Stubs by Link Mentions Only')
        lines.append('')
        lines.append('Scope: NPC pages with a TODO stub, ranked by confirmed wikilink mentions only (conservative).')
        lines.append('')
        lines.append('| Rank | NPC | Links | File |')
        lines.append('|---:|:-----|---:|:-----|')
        rows = build_stub_rows('link_mentions')
        rank = 0
        for links, data in rows:
            rank += 1
            name = data['canonical']
            rel = Path(data['path']).as_posix()
            lines.append(f"| {rank} | [[{rel}|{name}]] | {links} | {rel} |")
        output_stubs_links.parent.mkdir(parents=True, exist_ok=True)
        output_stubs_links.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    # Session-coverage lists (overall)
    sessions_md = output_punchlist.parent / 'ACE_PUNCHLIST_SESSIONS.md'
    lines = []
    lines.append('# ACE Punch List — NPCs by Distinct Session Coverage')
    lines.append('')
    lines.append('Primary sort: sessions with mentions (any), tie-breakers: link sessions, link mentions, text mentions.')
    lines.append('')
    lines.append('| Rank | NPC | Sessions | Link Sessions | Links | Text | File |')
    lines.append('|---:|:-----|---:|---:|---:|---:|:-----|')
    scored_sessions = []
    for key, data in index.items():
        nm = (data.get('canonical') or '').lower() or Path(data['path']).stem.lower()
        if ignore_names and (nm in ignore_names):
            continue
        sess = int(data.get('sessions_count', 0))
        lsess = int(data.get('link_sessions_count', 0))
        l = int(data.get('link_mentions', 0))
        t = int(data.get('text_mentions', 0))
        if sess > 0:
            scored_sessions.append((sess, lsess, l, t, data))
    scored_sessions.sort(key=lambda x: (-x[0], -x[1], -x[2], -x[3], Path(x[4]['path']).stem))
    rank = 0
    for sess, lsess, l, t, data in scored_sessions[:500]:
        rank += 1
        name = data['canonical']
        rel = Path(data['path']).as_posix()
        lines.append(f"| {rank} | [[{rel}|{name}]] | {sess} | {lsess} | {l} | {t} | {rel} |")
    sessions_md.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    # Session-coverage list for high-value without TODO (to surface important pages lacking stubs)
    hv_md = output_punchlist.parent / 'ACE_PUNCHLIST_HIGHVALUE_NO_TODO.md'
    def is_stub(path: Path) -> bool:
        try:
            txt = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return False
        return re.search(r'^-\s*TODO', txt, flags=re.M) is not None
    lines = []
    lines.append('# ACE High-Value — NPCs Without TODO Stub (by Sessions)')
    lines.append('')
    lines.append('Candidates with broad session coverage but no TODO marker. Prioritize these for enrichment despite not being flagged as stubs.')
    lines.append('')
    lines.append('| Rank | NPC | Sessions | Link Sessions | Links | Text | File |')
    lines.append('|---:|:-----|---:|---:|---:|---:|:-----|')
    rows = []
    for key, data in index.items():
        p = Path(data['path'])
        nm = (data.get('canonical') or '').lower() or p.stem.lower()
        if ignore_names and (nm in ignore_names):
            continue
        if is_stub(p):
            continue
        sess = int(data.get('sessions_count', 0))
        lsess = int(data.get('link_sessions_count', 0))
        l = int(data.get('link_mentions', 0))
        t = int(data.get('text_mentions', 0))
        if sess > 0:
            rows.append((sess, lsess, l, t, data))
    rows.sort(key=lambda x: (-x[0], -x[1], -x[2], -x[3], Path(x[4]['path']).stem))
    rank = 0
    for sess, lsess, l, t, data in rows[:200]:
        rank += 1
        name = data['canonical']
        rel = Path(data['path']).as_posix()
        lines.append(f"| {rank} | [[{rel}|{name}]] | {sess} | {lsess} | {l} | {t} | {rel} |")
    hv_md.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', type=Path, default=Path('vault'))
    ap.add_argument('--output-json', type=Path, default=Path('scripts/output/npc_mentions.json'))
    ap.add_argument('--output-punchlist', type=Path, default=Path('docs/ACE_PUNCHLIST.md'))
    ap.add_argument('--output-punchlist-links', type=Path, default=Path('docs/ACE_PUNCHLIST_LINKS.md'))
    ap.add_argument('--output-stubs', type=Path, default=Path('docs/ACE_PUNCHLIST_STUBS.md'))
    ap.add_argument('--output-stubs-links', type=Path, default=Path('docs/ACE_PUNCHLIST_STUBS_LINKS.md'))
    ap.add_argument('--context-lines', type=int, default=4)
    ap.add_argument('--ignore-list', type=Path, default=Path('config/ace_ignore_npcs.txt'))
    args = ap.parse_args()

    index = index_mentions(args.vault, context_lines=args.context_lines)
    ignore = load_ignore_list(args.ignore_list)
    write_outputs(index,
                  args.output_json,
                  args.output_punchlist,
                  args.output_punchlist_links,
                  args.output_stubs,
                  args.output_stubs_links,
                  ignore_names=ignore)
    print(f"Indexed NPC mentions: {sum(len(v['mentions']) for v in index.values())} occurrences across {len(index)} NPCs.")
    print(f"Wrote JSON: {args.output_json}")
    print(f"Wrote punch list: {args.output_punchlist}")
    print(f"Wrote link-only punch list: {args.output_punchlist_links}")
    print(f"Wrote stubs list: {args.output_stubs}")
    print(f"Wrote stubs link-only list: {args.output_stubs_links}")
    print(f"Wrote sessions list: { (args.output_punchlist.parent / 'ACE_PUNCHLIST_SESSIONS.md') }")
    print(f"Wrote high-value no-TODO list: { (args.output_punchlist.parent / 'ACE_PUNCHLIST_HIGHVALUE_NO_TODO.md') }")


if __name__ == '__main__':
    main()
