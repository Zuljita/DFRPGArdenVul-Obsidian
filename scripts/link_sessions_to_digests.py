#!/usr/bin/env python3
"""
Link each session file to the Discord weekly digest(s) that covered discussions
between that session and the one before it.

Builds a compact index of all Discord Summary files, passes the session content
and the index to Gemma, and adds a "Discord Discussions" bullet to the session's
"## Session Navigation" section.

Usage:
  python3 scripts/link_sessions_to_digests.py --session "vault/sessions/Session 50 - ..."
  python3 scripts/link_sessions_to_digests.py --all [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

VAULT = Path('vault')
NOTES_DIR = VAULT / 'notes'
SESSIONS_DIR = VAULT / 'sessions'

DEFAULT_ENDPOINT = (
    os.environ.get('LMSTUDIO_BASE_URL')
    or os.environ.get('LLM_ENDPOINT')
    or 'http://100.76.165.94:1234'
)
DEFAULT_MODEL = (
    os.environ.get('LMSTUDIO_IAC_MODEL')
    or os.environ.get('LMSTUDIO_MODEL')
    or 'google/gemma-4-26b-a4b'
)

LINK_PROMPT = """/no_think
You are curating an Obsidian knowledge vault for a tabletop RPG campaign (DFRPG Arden Vul).

Your task: determine which Discord weekly summary files should be linked from a session's
navigation footer. Each Discord Summary covers one calendar week of player discussion.

STEP 1 — Identify the real-world date of the target session:
- Look for a "source_url" field in the session frontmatter. Blog post URLs encode the date:
  e.g. "blogspot.com/2026/04/..." means the session was in April 2026.
- Look for explicit date mentions in the session body (e.g. "March 20, 2026").
- Use "## Session Navigation" to find the previous session, which provides a lower bound.

STEP 2 — Select summaries:
1. Include summaries whose date range overlaps with or immediately follows the previous session.
2. Include summaries covering the week the target session was played.
3. Include summaries explicitly mentioning this session in "Related Sessions".
4. EXCLUDE summaries whose entire date range clearly predates the previous session.
5. EXCLUDE summaries whose date range clearly postdates the target session.
6. If the session appears too recent and no matching summaries exist, return an empty list.

Prefer precision — link 1-4 summaries at most. Do not link summaries speculatively.

Return strictly valid JSON and nothing else:
{{"links": ["Discord Summary YYYY-WNN", "Discord Summary YYYY-WNN"]}}

DISCORD SUMMARY INDEX (all available summaries, sorted by date):
{index}

TARGET SESSION CONTENT:
{session_content}
"""


def build_summary_index() -> List[Dict]:
    """Parse all Discord Summary files and return a compact list of dicts."""
    date_range_re = re.compile(
        r'\*{0,2}Date Range[:：]\*{0,2}\s*(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})'
    )
    related_re = re.compile(r'\[\[Session ([^\]|]+)')

    summaries = []
    for f in sorted(NOTES_DIR.glob('Discord Summary *.md')):
        text = f.read_text(encoding='utf-8', errors='ignore')

        m = date_range_re.search(text)
        date_start = m.group(1) if m else None
        date_end = m.group(2) if m else None
        date_range = f"{date_start} to {date_end}" if date_start else 'unknown'

        # Extract sessions mentioned in the Related Sessions section
        related_block = re.search(r'Related Sessions.*?(?=\n##|\Z)', text, re.S | re.DOTALL)
        sessions_mentioned: List[str] = []
        if related_block:
            sessions_mentioned = [s.strip() for s in related_re.findall(related_block.group(0))]

        # Brief content blurb (first substantive line after the date range header)
        content_body = re.sub(r'^---.*?---\s*', '', text, flags=re.S)
        content_body = re.sub(r'^#+.*\n', '', content_body, count=2)
        content_body = re.sub(r'\*{0,2}Date Range.*\n?', '', content_body)
        blurb = ' '.join(content_body.split())[:200]

        summaries.append({
            'week': f.stem,
            'date_range': date_range,
            'date_start': date_start,
            'date_end': date_end,
            'sessions_mentioned': sessions_mentioned,
            'blurb': blurb,
            'path': f,
        })

    return summaries


def format_index(summaries: List[Dict]) -> str:
    dates = [s['date_end'] for s in summaries if s.get('date_end')]
    coverage = f"Coverage: {min(dates)} to {max(dates)}" if dates else "Coverage: unknown"
    lines = [f"# Discord Summary Index ({coverage})", ""]
    for s in summaries:
        sess_str = (
            ', '.join(s['sessions_mentioned']) if s['sessions_mentioned'] else 'none'
        )
        line = f"- {s['week']} | {s['date_range']} | Related: {sess_str}"
        if s['blurb']:
            line += f" | {s['blurb'][:120]}"
        lines.append(line)
    return '\n'.join(lines)


def extract_session_yearmonth(session_file: Path) -> Optional[str]:
    """Return 'YYYY-MM' from session_date frontmatter or source_url path."""
    text = session_file.read_text(encoding='utf-8', errors='ignore')
    # Prefer explicit session_date frontmatter field
    m = re.search(r'^session_date:\s*(\d{4})-(\d{2})-\d{2}\s*$', text, re.M)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    # Fall back to date encoded in source_url blogspot path
    m = re.search(r'source_url:.*?(\d{4})/(\d{2})/', text)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def call_gemma(prompt: str, endpoint: str, model: str, timeout: int = 120) -> str:
    url = endpoint.rstrip('/') + '/v1/chat/completions'
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens': 300,
        'stream': False,
        'reasoning_effort': 'none',
        'enable_thinking': False,
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    message = data['choices'][0]['message']
    return (message.get('content') or message.get('reasoning_content') or '').strip()


def parse_links_from_response(text: str) -> List[str]:
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        obj = json.loads(cleaned)
        links = obj.get('links', [])
        if isinstance(links, list):
            return [str(l).strip() for l in links if str(l).strip()]
    except (json.JSONDecodeError, AttributeError):
        pass
    return []


def get_session_files() -> List[Path]:
    """Return all session files sorted by session number (ascending)."""
    def sort_key(p: Path) -> Tuple:
        m = re.search(r'Session (\d+)([abc]?)', p.stem, re.I)
        return (int(m.group(1)), m.group(2)) if m else (0, '')

    return sorted(
        (f for f in SESSIONS_DIR.glob('*.md') if f.stem != 'Index'),
        key=sort_key,
    )


def format_digest_links(week_names: List[str]) -> str:
    return ', '.join(f'[[{w}]]' for w in week_names)


def update_session_navigation(session_file: Path, links: List[str], dry_run: bool = False) -> bool:
    """Insert or replace the Discord Discussions bullet in ## Session Navigation."""
    if not links:
        return False

    text = session_file.read_text(encoding='utf-8', errors='ignore')
    new_bullet = f'- Discord Discussions: {format_digest_links(links)}'

    # Check for existing Discord Discussions bullet anywhere in the file
    existing_re = re.compile(r'^- Discord Discussions:.*$', re.M)
    existing = existing_re.search(text)

    if existing:
        if existing.group(0) == new_bullet:
            return False  # already correct
        new_text = existing_re.sub(new_bullet, text, count=1)
    elif '## Session Navigation' in text:
        nav_start = text.find('## Session Navigation')
        # Find the next top-level section header (or end of file)
        next_sec = re.search(r'\n## ', text[nav_start + 1:])
        insert_at = nav_start + 1 + next_sec.start() if next_sec else len(text)
        nav_block = text[nav_start:insert_at]
        new_nav = nav_block.rstrip() + '\n' + new_bullet + '\n'
        new_text = text[:nav_start] + new_nav + text[insert_at:]
    else:
        new_text = text.rstrip() + f'\n\n## Session Navigation\n{new_bullet}\n'

    if dry_run:
        print(f"  [dry-run] would write: {new_bullet}")
        return True

    session_file.write_text(new_text, encoding='utf-8')
    return True


def process_session(
    session_file: Path,
    index_text: str,
    summaries: List[Dict],
    summary_weeks: set,
    dry_run: bool,
    endpoint: str,
    model: str,
) -> dict:
    print(f"\nProcessing: {session_file.name}", flush=True)

    # Pre-filter: if the session's date is after the last available summary, skip LLM.
    session_ym = extract_session_yearmonth(session_file)
    last_dates = sorted(s['date_end'] for s in summaries if s.get('date_end'))
    if session_ym and last_dates:
        last_ym = last_dates[-1][:7]  # YYYY-MM
        if session_ym > last_ym:
            print(f"  Session date {session_ym} is after last summary {last_ym} — no links available")
            return {'file': str(session_file), 'links': [], 'changed': False}

    session_content = session_file.read_text(encoding='utf-8', errors='ignore')
    prompt = LINK_PROMPT.format(index=index_text, session_content=session_content)

    try:
        raw = call_gemma(prompt, endpoint, model)
    except Exception as e:
        print(f"  LLM error: {e}")
        return {'file': str(session_file), 'error': str(e)}

    links = parse_links_from_response(raw)

    # Validate: only keep weeks that actually exist as files
    valid = [l for l in links if l in summary_weeks]
    dropped = [l for l in links if l not in summary_weeks]
    if dropped:
        print(f"  Dropped non-existent: {dropped}")

    print(f"  Links: {valid or '(none)'}")

    changed = update_session_navigation(session_file, valid, dry_run=dry_run)
    return {
        'file': str(session_file),
        'links': valid,
        'changed': changed,
    }


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(
        description='Link sessions to Discord weekly digests using Gemma.'
    )
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--session', help='Path to a specific session .md file')
    group.add_argument('--all', action='store_true', help='Process all session files')
    ap.add_argument('--dry-run', action='store_true', help='Print changes without writing files')
    ap.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    ap.add_argument('--model', default=DEFAULT_MODEL)
    args = ap.parse_args(argv)

    summaries = build_summary_index()
    if not summaries:
        print('No Discord Summary files found in vault/notes/', file=sys.stderr)
        sys.exit(1)

    index_text = format_index(summaries)
    summary_weeks = {s['week'] for s in summaries}

    targets = [Path(args.session)] if args.session else get_session_files()

    results = []
    for sf in targets:
        result = process_session(sf, index_text, summaries, summary_weeks, args.dry_run, args.endpoint, args.model)
        results.append(result)

    print('\n--- Summary ---')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
