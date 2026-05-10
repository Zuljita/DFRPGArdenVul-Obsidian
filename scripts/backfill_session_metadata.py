#!/usr/bin/env python3
"""
Backfill source_url and session_date frontmatter into session files using
data scraped from dfwhiterock.blogspot.com.

Adds/updates two frontmatter fields for every session that has a known blog post:
  session_date: YYYY-MM-DD  (blog post date, one day after the Friday play date)
  source_url: https://dfwhiterock.blogspot.com/...

Also ensures a ## Source section exists in the file body.
Does NOT overwrite existing body content.

Usage:
  python3 scripts/backfill_session_metadata.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SESSIONS_DIR = Path('vault/sessions')

# Scraped from dfwhiterock.blogspot.com — exact post dates (Saturdays; play date is Friday before)
BLOG_DATA = [
    ("Session 1 - First Visit to the Ruins of Arden Vul.md",
     "2025-03-15", "https://dfwhiterock.blogspot.com/2025/03/dfrpg-session-1-first-visit-to-ruins-of.html"),
    ("Session 2 - Halfling Rent-Seekers.md",
     "2025-03-22", "https://dfwhiterock.blogspot.com/2025/03/dfrpg-session-2-halfling-rent-seekers.html"),
    ("Session 3 - Dragons and Baboons and Beastmen, Oh My!.md",
     "2025-03-29", "https://dfwhiterock.blogspot.com/2025/03/dfrpg-arden-vul-session-3-dragons-and.html"),
    ("Session 4 - Cheese and Crackers and Thoth and Demons.md",
     "2025-04-05", "https://dfwhiterock.blogspot.com/2025/04/dfrpg-arden-vul-session-4-cheese-and.html"),
    ("Session 5 - Parleys and The Great Cavern.md",
     "2025-04-12", "https://dfwhiterock.blogspot.com/2025/04/dfrpg-arden-vul-session-5-parleys-and.html"),
    ("Session 6 - Good Ghost, Bad Ghost.md",
     "2025-04-19", "https://dfwhiterock.blogspot.com/2025/04/dfrpg-arden-vul-session-6-good-ghost.html"),
    ("Session 7 - Why Did It Have to Be Plants.md",
     "2025-04-26", "https://dfwhiterock.blogspot.com/2025/04/dfrpg-session-7-why-did-it-have-to-be.html"),
    ("Session 8a - Never Trust a Scorpion.md",
     "2025-05-03", "https://dfwhiterock.blogspot.com/2025/05/dfrpg-arden-vul-session-8a-never-trust.html"),
    ("Session 8b and 9 - Muirasso's Tomb and the Broken Head.md",
     "2025-05-10", "https://dfwhiterock.blogspot.com/2025/05/dfrpg-arden-vul-sessions-8b-and-9.html"),
    ("Session 10 - Baboons, Ghouls, and a Mule.md",
     "2025-05-17", "https://dfwhiterock.blogspot.com/2025/05/dfrpg-arden-vul-session-10-baboons.html"),
    ("Session 11 - The Great Cavern Redux.md",
     "2025-05-24", "https://dfwhiterock.blogspot.com/2025/05/dfrpg-arden-vul-session-11-great-cavern.html"),
    ("Session 12 - First Encounter with the Cult of Set.md",
     "2025-05-31", "https://dfwhiterock.blogspot.com/2025/05/dfrpg-arden-vul-session-12-first.html"),
    ("Session 13 - Yrtol and the Turtle.md",
     "2025-06-07", "https://dfwhiterock.blogspot.com/2025/06/dfrpg-arden-vul-session-13-yrtol-and.html"),
    ("Session 14 - Behind the Waterfall Again.md",
     "2025-06-14", "https://dfwhiterock.blogspot.com/2025/06/dfrpg-arden-vul-session-14-behind.html"),
    ("Session 15 - The Great Cavern Re-Revisited.md",
     "2025-06-21", "https://dfwhiterock.blogspot.com/2025/06/dfrpg-arden-vul-session-15-great-cavern.html"),
    ("Session 16 - Random Scorpion Teleport to the Hall of Judgment.md",
     "2025-06-28", "https://dfwhiterock.blogspot.com/2025/06/dfrpg-arden-vul-session-15-random.html"),
("Session 17 - Cleaning Out the Vermin.md",
     "2025-07-05", "https://dfwhiterock.blogspot.com/2025/07/dfrpg-arden-vul-session-17-cleaning-out.html"),
    ("Session 18 - Back Down the Well of Light.md",
     "2025-07-12", "https://dfwhiterock.blogspot.com/2025/07/dfrpg-arden-vul-session-18-back-down.html"),
    ("Session 19 - The Pool of Donkey Ears.md",
     "2025-07-19", "https://dfwhiterock.blogspot.com/2025/07/df-whiterock-session-19-pool-of-donkey.html"),
    ("Session 20 - The Outer Caverns of Set.md",
     "2025-07-27", "https://dfwhiterock.blogspot.com/2025/07/df-whiterock-session-20-outer-caverns.html"),
    ("Session 21 - The Library of Thoth.md",
     "2025-08-02", "https://dfwhiterock.blogspot.com/2025/08/dfrpg-arden-vul-session-21-library-of.html"),
    ("Session 22 - The Oracle of Thoth and The Litany of Light.md",
     "2025-08-09", "https://dfwhiterock.blogspot.com/2025/08/dfrpg-arden-vul-session-22-oracle-of.html"),
    ("Session 22.5 Interlude - Bonus Downtime Recap.md",
     "2025-08-31", "https://dfwhiterock.blogspot.com/2025/08/dfrpg-bonus-downtime-recap-strange.html"),
    ("Session 23a - Gelatinous Cube and Slime Kraken.md",
     "2025-08-16", "https://dfwhiterock.blogspot.com/2025/08/dfrpg-arden-vul-session-23a-gelatinous.html"),
    ("Session 23b - Disrupting Services in the Temple of Set.md",
     "2025-08-23", "https://dfwhiterock.blogspot.com/2025/08/dfrpg-arden-vul-session-23b-disrupting.html"),
    ("Session 23c - Set Jailbreak and Down to Goblintown.md",
     "2025-08-30", "https://dfwhiterock.blogspot.com/2025/08/dfrpg-arden-vul-session-23c-set.html"),
    ("Session 24a - Revenge on the Set Cult.md",
     "2025-09-06", "https://dfwhiterock.blogspot.com/2025/09/dfrpg-arden-vul-session-24a-revenge-on.html"),
    ("Session 24b - The Set Cult Strikes Back, Larel's Stuff, and the Hall of Shrines.md",
     "2025-09-13", "https://dfwhiterock.blogspot.com/2025/09/dfrpg-arden-vul-session-24b-set-cult.html"),
    ("Session 25 - Looking for the Back Door to the Forum of Set.md",
     "2025-09-20", "https://dfwhiterock.blogspot.com/2025/09/dfrpg-arden-vul-session-25-looking-for.html"),
    ("Session 26 - The Scouring of the Shire.md",
     "2025-10-11", "https://dfwhiterock.blogspot.com/2025/10/dfrpg-arden-vul-session-26-scouring-of.html"),
    ("Session 27 - The Tomb of Ptoh-Ristus.md",
     "2025-10-18", "https://dfwhiterock.blogspot.com/2025/10/dfrpg-arden-vul-session-27-tomb-of-ptoh.html"),
    ("Session 28 - Teleport Rugs and Baboons.md",
     "2025-10-25", "https://dfwhiterock.blogspot.com/2025/10/dfrpg-session-28-teleport-rugs-and.html"),
    ("Session 29 - The Tower of Scrutiny.md",
     "2025-11-01", "https://dfwhiterock.blogspot.com/2025/11/dfrpg-session-29-tower-of-scrutiny.html"),
    ("Session 30 - The Tomb of Theskalon.md",
     "2025-11-08", "https://dfwhiterock.blogspot.com/2025/11/dfrpg-arden-vul-session-30-tomb-of.html"),
    ("Session 31 - I Want to Believe.md",
     "2025-11-15", "https://dfwhiterock.blogspot.com/2025/11/dfrpg-arden-vul-session-31-i-want-to.html"),
    ("Session 32 - Fast Exploration.md",
     "2025-11-22", "https://dfwhiterock.blogspot.com/2025/11/dfrpg-arden-vul-session-32-fast.html"),
    ("Session 33 - Nyema.md",
     "2025-11-29", "https://dfwhiterock.blogspot.com/2025/11/dfrpg-arden-vul-session-33-nyema.html"),
    ("Session 34a - Hunting the Thane.md",
     "2025-12-06", "https://dfwhiterock.blogspot.com/2025/12/dfrpg-session-34a-hunting-thane.html"),
    ("Session 34b - Tower of the Ape.md",
     "2025-12-13", "https://dfwhiterock.blogspot.com/2025/12/dfrpg-arden-vul-session-34b-tower-of-ape.html"),
    ("Session 34c - Burglary and Death.md",
     "2025-12-20", "https://dfwhiterock.blogspot.com/2025/12/dfrpg-arden-vul-session-34c-burglary.html"),
    ("Session 35 - The Scepter - Flute of the Goblins.md",
     "2025-12-27", "https://dfwhiterock.blogspot.com/2025/12/dfrpg-arden-vul-session-35-scepter.html"),
    ("Session 36 - Rescuing Deino's Kids.md",
     "2026-01-03", "https://dfwhiterock.blogspot.com/2026/01/dfrpg-arden-vul-session-36-rescuing.html"),
    ("Session 37 - Deino and the Eyeballs.md",
     "2026-01-10", "https://dfwhiterock.blogspot.com/2026/01/dfrpg-arden-vul-session-37-deino-and.html"),
    ("Session 38 - Another Attack on the Temple of Set.md",
     "2026-01-17", "https://dfwhiterock.blogspot.com/2026/01/dfrpg-arden-vul-session-38-another.html"),
    ("Session 39 - Diving for the Yellow Card.md",
     "2026-01-24", "https://dfwhiterock.blogspot.com/2026/01/dfrpg-arden-vul-session-39-diving-for.html"),
    ("Session 40 - Taking Command.md",
     "2026-01-31", "https://dfwhiterock.blogspot.com/2026/01/dfrpg-arden-vul-session-40-taking.html"),
    ("Session 41 - Theft and Counter-Theft.md",
     "2026-02-07", "https://dfwhiterock.blogspot.com/2026/02/dfrpg-session-41-theft-and-counter-theft.html"),
    ("Session 42a - Neferet.md",
     "2026-02-14", "https://dfwhiterock.blogspot.com/2026/02/dfrpg-arden-vul-session-42a-neferet.html"),
    ("Session 42b - Neferet and the Wraiths.md",
     "2026-02-21", "https://dfwhiterock.blogspot.com/2026/02/dfrpg-arden-vul-session-42b-neferet-and.html"),
    ("Session 43a - Alpha Strike on the Cult of Set.md",
     "2026-02-28", "https://dfwhiterock.blogspot.com/2026/02/dfrpg-arden-vul-session-43a-alpha.html"),
    ("Session 43b - Alpha Strike on the Cult of Set.md",
     "2026-03-07", "https://dfwhiterock.blogspot.com/2026/03/dfrpg-arden-vul-session-43b-alpha.html"),
    ("Session 43c - Looting the Cult of Set.md",
     "2026-03-14", "https://dfwhiterock.blogspot.com/2026/03/dfrpg-arden-vul-session-43c-looting.html"),
    ("Session 44 - Clearing the Goblin Forum.md",
     "2026-03-21", "https://dfwhiterock.blogspot.com/2026/03/dfrpg-arden-vul-session-44-clearing.html"),
    ("Session 45 - Purple Mist and the Drowned Canyon.md",
     "2026-03-28", "https://dfwhiterock.blogspot.com/2026/03/dfrpg-arden-vul-session-45-purple-mist.html"),
    ("Session 46 - The Arena Lord and the Inn of the Lost.md",
     "2026-04-04", "https://dfwhiterock.blogspot.com/2026/04/dfrpg-arden-vul-session-46-arena-lord.html"),
    ("Session 47 - The No Mana Zone.md",
     "2026-04-11", "https://dfwhiterock.blogspot.com/2026/04/dfrpg-arden-vul-session-47-no-mana-zone.html"),
    ("Session 48 - Thothian Teleportation Rings.md",
     "2026-04-18", "https://dfwhiterock.blogspot.com/2026/04/dfrpg-arden-vul-session-48-thothian.html"),
    ("Session 49 - Demons and Mummies.md",
     "2026-04-25", "https://dfwhiterock.blogspot.com/2026/04/dfrpg-arden-vul-session-48-demons-and.html"),
    ("Session 50 - The Iron Circlet of Ghanor.md",
     "2026-05-02", "https://dfwhiterock.blogspot.com/2026/05/dfrpg-arden-vul-session-50-iron-circlet.html"),
]


def set_frontmatter_field(text: str, key: str, value: str) -> str:
    """Add or replace a key in YAML frontmatter. Assumes frontmatter starts at line 1."""
    fm_re = re.compile(r'^(---\n)(.*?)(\n---)', re.S)
    m = fm_re.match(text)
    if not m:
        # No frontmatter — prepend minimal one
        return f'---\n{key}: {value}\n---\n\n' + text

    fm_body = m.group(2)
    rest = text[m.end():]

    key_re = re.compile(rf'^{re.escape(key)}:.*$', re.M)
    if key_re.search(fm_body):
        fm_body = key_re.sub(f'{key}: {value}', fm_body)
    else:
        fm_body = fm_body.rstrip('\n') + f'\n{key}: {value}'

    return m.group(1) + fm_body + m.group(3) + rest


def ensure_source_section(text: str, url: str) -> str:
    """Add a ## Source section before ## Session Navigation if one isn't already present."""
    if re.search(r'https://dfwhiterock\.blogspot\.com', text):
        return text  # URL already in file somewhere

    source_block = f'\n## Source\n- {url}\n'
    if '## Session Navigation' in text:
        idx = text.find('## Session Navigation')
        return text[:idx] + source_block + '\n' + text[idx:]
    return text.rstrip() + source_block


def process_file(path: Path, date: str, url: str, dry_run: bool) -> dict:
    text = path.read_text(encoding='utf-8', errors='ignore')
    original = text

    text = set_frontmatter_field(text, 'session_date', date)
    text = set_frontmatter_field(text, 'source_url', url)
    text = ensure_source_section(text, url)

    changed = text != original
    if dry_run:
        status = 'would update' if changed else 'no change'
    else:
        if changed:
            path.write_text(text, encoding='utf-8')
        status = 'updated' if changed else 'no change'

    return {'file': path.name, 'status': status, 'date': date}


def main() -> None:
    ap = argparse.ArgumentParser(description='Backfill session_date and source_url into session files.')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    missing = []
    results = []
    for filename, date, url in BLOG_DATA:
        path = SESSIONS_DIR / filename
        if not path.exists():
            missing.append(filename)
            continue
        result = process_file(path, date, url, args.dry_run)
        results.append(result)
        print(f"  {result['status']:12s} {result['file']}  ({result['date']})")

    if missing:
        print(f'\nFiles not found in vault ({len(missing)}):')
        for f in missing:
            print(f'  {f}')

    changed = sum(1 for r in results if r['status'] in ('updated', 'would update'))
    print(f'\n{"[dry-run] " if args.dry_run else ""}Updated {changed}/{len(results)} files.')


if __name__ == '__main__':
    main()
