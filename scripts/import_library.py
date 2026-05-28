#!/usr/bin/env python3
"""
Create and enrich vault/library/ articles from the written-works JSON produced
by fetch_loot_sheet.py.

For each unique written work:
  1. Creates a stub in vault/library/<title>.md (skips if already exists, unless --update)
  2. Searches all session files for mentions of the title
  3. Calls the LLM to extract what players learned from each reading event
  4. Searches Discord summaries for relevant context excerpts
  5. Regenerates vault/library/Index.md

Usage:
  # First run: create stubs (no LLM enrichment)
  python3 scripts/import_library.py --dry-run
  python3 scripts/import_library.py

  # With enrichment (searches sessions + Discord for content)
  python3 scripts/import_library.py --enrich

  # Update existing articles too (re-run enrichment on already-written files)
  python3 scripts/import_library.py --enrich --update
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

DATA_DIR = Path("data")
BOOKS_JSON = DATA_DIR / "books.json"

VAULT = Path("vault")
LIBRARY_DIR = VAULT / "library"
SESSIONS_DIR = VAULT / "sessions"
DISCORD_DIR = VAULT / "notes"

DEFAULT_ENDPOINT = "http://100.76.165.94:1234"
DEFAULT_MODEL = "google/gemma-4-26b-a4b"

# Types that map to a human-readable label for the article header
TYPE_LABELS = {
    "book":        "Book",
    "spellbook":   "Spellbook",
    "ritual-text": "Ritual Text",
    "codex":       "Codex",
    "letter":      "Letter",
    "document":    "Document",
    "map":         "Map",
    "tablet":      "Tablet",
    "scroll":      "Lore Scroll",
    "notebook":    "Notebook",
    "diary":       "Diary",
    "data-crystal":"Data Crystal",
    "parchment":   "Parchment",
    "other":       "Written Work",
}

ENRICH_PROMPT = """/no_think
You are writing notes for an Obsidian knowledge vault about a DFRPG Arden Vul tabletop campaign.

A written work called "{title}" appeared in the campaign. Below are excerpts from session
recaps where this work was mentioned. Extract:
1. What the players LEARNED from reading or interacting with it (in-game information, lore, effects).
2. Any notable events involving it (who read it, what happened as a result).

Be concise. Write 2-5 bullet points under a "## Content" section and 1-3 sentences per reading
event under "## Reading Events". Use past tense. Do not speculate beyond what the excerpts say.
If the excerpts don't show the players actually reading the work, skip "## Content" and just note
the event under "## Reading Events".

Return ONLY the markdown sections, no preamble:

## Content
- ...

## Reading Events
- [[Session X]]: ...

SESSION EXCERPTS:
{excerpts}
"""


# ── Utilities ──────────────────────────────────────────────────────────────────

def safe_filename(title: str) -> str:
    """Convert a title to a safe filename, preserving most characters."""
    s = re.sub(r'[<>:"/\\|?*]', '-', title)
    s = re.sub(r'\s+', ' ', s).strip()
    s = s[:120]  # cap length
    return s


def normalize_for_search(title: str) -> str:
    s = title.lower()
    s = re.sub(r'^(the|a|an)\s+', '', s)
    s = re.sub(r'[^\w\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def significant_words(title: str) -> List[str]:
    stops = {'that', 'this', 'with', 'from', 'have', 'will', 'been', 'were',
             'they', 'some', 'into', 'more', 'also', 'each', 'than', 'then',
             'when', 'what', 'which', 'your', 'their', 'there', 'about'}
    return [w for w in re.findall(r'[A-Za-z]{4,}', title) if w.lower() not in stops]


def build_search_pattern(title: str) -> Optional[re.Pattern]:
    """Build a search regex for a title. Returns None if title is too generic."""
    sig = significant_words(title)
    if not sig:
        return None
    # Require 2+ significant words for pattern matching; single words are too noisy
    if len(sig) < 2:
        return None
    # Try exact phrase first
    return re.compile(re.escape(title), re.I)


def build_proximity_pattern(title: str) -> Optional[re.Pattern]:
    """Fallback: any significant word from the title."""
    sig = significant_words(title)
    if len(sig) < 2:
        return None
    # Match if the two most distinctive words appear within 300 chars of each other
    # Use the two longest words as they're most distinctive
    sig_sorted = sorted(sig, key=len, reverse=True)[:2]
    return sig_sorted  # return word list for proximity check


# ── Session searching ──────────────────────────────────────────────────────────

def load_sessions() -> List[Dict]:
    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.md")):
        if f.stem == "Index":
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'^session_date:\s*(\d{4}-\d{2}-\d{2})', text, re.M)
        sessions.append({
            "path": f,
            "stem": f.stem,
            "date": m.group(1) if m else None,
            "text": text,
        })
    return sessions


def find_in_sessions(title: str, sessions: List[Dict]) -> List[Dict]:
    """
    Return list of {session, excerpts} for sessions that mention the title.
    Extracts up to 3 context windows of ±350 chars around each match.
    """
    exact_pat = build_search_pattern(title)
    prox_words = build_proximity_pattern(title)

    hits = []
    for sess in sessions:
        text = sess["text"]
        excerpts = []
        seen_ranges = []

        def _add_excerpt(start: int, end: int) -> None:
            lo = max(0, start - 350)
            hi = min(len(text), end + 350)
            # Avoid overlapping windows
            for (a, b) in seen_ranges:
                if lo < b and hi > a:
                    return
            seen_ranges.append((lo, hi))
            excerpts.append(text[lo:hi].strip())

        if exact_pat:
            for m in exact_pat.finditer(text):
                if len(excerpts) >= 3:
                    break
                _add_excerpt(m.start(), m.end())

        # Proximity fallback if no exact matches
        if not excerpts and prox_words:
            w0_pat = re.compile(re.escape(prox_words[0]), re.I)
            w1_pat = re.compile(re.escape(prox_words[1]), re.I)
            for m in w0_pat.finditer(text):
                window_start = max(0, m.start() - 50)
                window_end = min(len(text), m.end() + 300)
                window = text[window_start:window_end]
                if w1_pat.search(window):
                    _add_excerpt(m.start(), m.end())
                    if len(excerpts) >= 3:
                        break

        if excerpts:
            hits.append({"session": sess, "excerpts": excerpts})
    return hits


# ── Discord excerpts ───────────────────────────────────────────────────────────

def load_discord_summaries() -> List[Dict]:
    summaries = []
    for f in sorted(DISCORD_DIR.glob("Discord Summary *.md")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        summaries.append({"week": f.stem, "text": text, "path": f})
    return summaries


def get_discord_excerpt(title: str, week: str, summaries: List[Dict]) -> Optional[str]:
    """Find the paragraph(s) in a Discord summary that mention the title."""
    target = next((s for s in summaries if s["week"] == week), None)
    if not target:
        return None
    # Strip YAML frontmatter before searching
    text = re.sub(r'^---\n.*?\n---\n', '', target["text"], flags=re.S)
    exact_pat = re.compile(re.escape(title), re.I)
    for m in exact_pat.finditer(text):
        lo = max(0, m.start() - 150)
        hi = min(len(text), m.end() + 250)
        excerpt = text[lo:hi].strip()
        # Trim to sentence boundaries to avoid mid-sentence cuts
        # Find last period/newline before the window start
        lead = text[lo:m.start()]
        bound = max(lead.rfind('. '), lead.rfind('\n'))
        if bound > 0:
            excerpt = text[lo + bound + 1: hi].strip()
        # Don't let it run past a section header
        header_m = re.search(r'\n#+\s', excerpt)
        if header_m:
            excerpt = excerpt[:header_m.start()].strip()
        return excerpt[:400]
    return None


# ── LLM enrichment ────────────────────────────────────────────────────────────

def call_llm(prompt: str, endpoint: str, model: str, timeout: int = 180) -> str:
    url = endpoint.rstrip("/") + "/v1/chat/completions"
    resp = requests.post(url, json={
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.15,
        "max_tokens": 1200,
        "stream": False,
        "reasoning_effort": "none",
        "enable_thinking": False,
    }, timeout=timeout)
    resp.raise_for_status()
    msg = resp.json()["choices"][0]["message"]
    return (msg.get("content") or msg.get("reasoning_content") or "").strip()


def enrich_with_llm(title: str, session_hits: List[Dict],
                    endpoint: str, model: str) -> str:
    """Call LLM to extract content/reading-event markdown from session excerpts."""
    parts = []
    for hit in session_hits:
        sess_label = hit["session"]["stem"]
        for exc in hit["excerpts"]:
            parts.append(f"=== {sess_label} ===\n{exc}")
    excerpts_text = "\n\n".join(parts)
    prompt = ENRICH_PROMPT.format(title=title, excerpts=excerpts_text)
    try:
        return call_llm(prompt, endpoint, model)
    except Exception as e:
        return f"<!-- LLM enrichment failed: {e} -->"


# ── Article generation ─────────────────────────────────────────────────────────

def extract_preserved_sections(existing_text: str) -> Dict[str, str]:
    """
    Pull out ## Content and ## Reading Events from an existing article.
    Returns empty strings for sections that still have TODO placeholders.
    """
    result = {"content": "", "reading_events": ""}
    # Match each section up to the next ## heading or end of file
    sec_re = re.compile(r'^(## (?:Content|Reading Events|Summary))(.*?)(?=^## |\Z)',
                        re.M | re.S)
    for m in sec_re.finditer(existing_text):
        header = m.group(1).strip()
        body   = m.group(2).strip()
        if "TODO" in body or not body:
            continue
        if header == "## Content":
            result["content"] = body
        elif header == "## Reading Events":
            result["reading_events"] = body
    return result


def session_wikilink(stem: str) -> str:
    return f"[[sessions/{stem}|{stem}]]"


def format_acquisitions_table(acquisitions: List[Dict]) -> str:
    lines = ["| Date | Page | Value | Qty | Sold | Owner |",
             "|------|------|-------|-----|------|-------|"]
    for a in acquisitions:
        page  = f"p.{int(a['page'])}" if isinstance(a['page'], float) else (a['page'] or "—")
        value = f"${int(a['value'])}" if isinstance(a['value'], (int, float)) else "—"
        qty   = str(int(a['qty'])) if isinstance(a['qty'], float) else (str(a['qty']) if a['qty'] else "1")
        sold  = a.get("sold") or "—"
        owner = a.get("owner") or "—"
        lines.append(f"| {a['date']} | {page} | {value} | {qty} | {sold} | {owner} |")
    return "\n".join(lines)


def make_stub(book: Dict, session_hits: List[Dict], discord_summaries: List[Dict],
              enriched_md: str = "", preserved: Optional[Dict] = None) -> str:
    title = book["title"]
    btype = book.get("type", "other")
    type_label = TYPE_LABELS.get(btype, "Written Work")
    aliases: List[str] = []
    # Add alias without leading "The"
    if title.lower().startswith("the "):
        aliases.append(title[4:])

    fm_lines = [
        "---",
        f'title: "{title}"',
        f"type: {btype}",
        "tags:",
        "  - library",
        f"  - {btype}",
    ]
    if aliases:
        fm_lines.append("aliases:")
        for a in aliases:
            fm_lines.append(f'  - "{a}"')
    fm_lines.append("---")

    acq_table = format_acquisitions_table(book["acquisitions"])

    # Build session reading links
    session_links = []
    for hit in session_hits:
        session_links.append(f"- {session_wikilink(hit['session']['stem'])}")

    # Build discord section
    discord_lines = []
    for week in book.get("discord_mentions", []):
        exc = get_discord_excerpt(title, week, discord_summaries)
        if exc:
            discord_lines.append(f"- **[[{week}]]**: {exc[:300].strip()}")
        else:
            discord_lines.append(f"- [[{week}]]")

    body_parts = [
        "\n".join(fm_lines),
        f"# {title}",
        f"*{type_label}*",
        "",
        "## Summary",
        "TODO: Add description.",
        "",
        "## Acquisitions",
        acq_table,
    ]

    # Determine content/reading-events text, in priority order:
    #  1. Fresh LLM enrichment (--enrich run)
    #  2. Preserved sections from existing article (--update without --enrich)
    #  3. TODO placeholders with session link list for manual fill-in
    p = preserved or {}
    if enriched_md:
        body_parts.append("")
        body_parts.append(enriched_md)
    elif p.get("content") or p.get("reading_events"):
        if p.get("content"):
            body_parts += ["", "## Content", p["content"]]
        else:
            body_parts += ["", "## Content",
                           "TODO: What the work contains (GM-provided information)."]
        if p.get("reading_events"):
            body_parts += ["", "## Reading Events", p["reading_events"]]
        else:
            body_parts += ["", "## Reading Events",
                           "TODO: Sessions where players read or interacted with this work."]
            if session_links:
                body_parts += ["", "### Sessions mentioning this work"] + session_links
    else:
        body_parts += [
            "",
            "## Content",
            "TODO: What the work contains (GM-provided information).",
            "",
            "## Reading Events",
            "TODO: Sessions where players read or interacted with this work.",
        ]
        if session_links:
            body_parts += ["", "### Sessions mentioning this work"] + session_links

    if discord_lines:
        body_parts += ["", "## Discord Discussions"] + discord_lines

    return "\n".join(body_parts) + "\n"


PLURAL_EXCEPTIONS = {
    "Codex": "Codices",
    "Diary": "Diaries",
    "Lore Scroll": "Lore Scrolls",
    "Written Work": "Written Works",
    "Data Crystal": "Data Crystals",
    "Ritual Text": "Ritual Texts",
}


def _plural(label: str) -> str:
    return PLURAL_EXCEPTIONS.get(label, label + "s")


def _is_enriched(book: Dict) -> bool:
    """Check if the article on disk has non-TODO Content."""
    fname = safe_filename(book["title"]) + ".md"
    dest = LIBRARY_DIR / fname
    if not dest.exists():
        return False
    text = dest.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'^## Content\n(.*?)(?=^##|\Z)', text, re.M | re.S)
    if not m:
        return False
    return "TODO" not in m.group(1) and m.group(1).strip() != ""


def generate_index(books: List[Dict]) -> str:
    by_type: Dict[str, List[Dict]] = {}
    for b in books:
        t = TYPE_LABELS.get(b.get("type", "other"), "Other")
        by_type.setdefault(t, []).append(b)

    total = len(books)
    party = sum(1 for b in books if any(a.get("owner") == "Party" for a in b["acquisitions"]))
    discord_ct = sum(1 for b in books if b.get("discord_mentions"))

    lines = [
        "# Library Index",
        "",
        f"*{total} written works catalogued · {party} currently held by the party · "
        f"{discord_ct} discussed on Discord*",
        "",
        "| Symbol | Meaning |",
        "|--------|---------|",
        "| 📖 | Content extracted from sessions |",
        "| 💬 | Discussed on Discord |",
        "| ✅ | Party holds this item |",
        "",
    ]

    for type_label in sorted(by_type):
        section_books = sorted(by_type[type_label], key=lambda x: x["title"].lstrip('"').lower())
        lines.append(f"## {_plural(type_label)}")
        for b in section_books:
            fname = safe_filename(b["title"])
            first_acq = b["acquisitions"][0]["date"] if b["acquisitions"] else "?"
            party_held = any(a.get("owner") == "Party" for a in b["acquisitions"])
            enriched   = _is_enriched(b)

            flags = ""
            if enriched:    flags += " 📖"
            if b.get("discord_mentions"): flags += " 💬"
            if party_held:  flags += " ✅"

            discord_links = ""
            if b.get("discord_mentions"):
                discord_links = " — " + ", ".join(f"[[{w}]]" for w in b["discord_mentions"])

            lines.append(
                f"- [[library/{fname}|{b['title']}]]{flags} *(found: {first_acq})*{discord_links}"
            )
        lines.append("")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Import written-works JSON into vault/library/ articles."
    )
    ap.add_argument("--input",    default=str(BOOKS_JSON),
                    help=f"Source JSON (default: {BOOKS_JSON})")
    ap.add_argument("--enrich",   action="store_true",
                    help="Call LLM to extract reading events from session files")
    ap.add_argument("--update",   action="store_true",
                    help="Overwrite existing library articles (default: skip)")
    ap.add_argument("--dry-run",  action="store_true",
                    help="Print what would be done without writing files")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--model",    default=DEFAULT_MODEL)
    args = ap.parse_args(argv)

    books = json.loads(Path(args.input).read_text(encoding="utf-8"))
    print(f"Loaded {len(books)} written works from {args.input}", file=sys.stderr)

    sessions = load_sessions()
    discord_summaries = load_discord_summaries()
    print(f"Loaded {len(sessions)} sessions, {len(discord_summaries)} Discord summaries",
          file=sys.stderr)

    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

    created = updated = skipped = 0
    for book in books:
        title = book["title"]
        fname = safe_filename(title) + ".md"
        dest  = LIBRARY_DIR / fname

        exists = dest.exists()
        if exists and not args.update:
            skipped += 1
            continue

        # Preserve existing enriched sections when updating without --enrich
        preserved: Optional[Dict] = None
        if exists and not args.enrich:
            preserved = extract_preserved_sections(dest.read_text(encoding="utf-8"))

        # Search sessions for mentions
        session_hits = find_in_sessions(title, sessions)
        if session_hits:
            print(f"  '{title[:50]}': found in {len(session_hits)} session(s)", file=sys.stderr)

        # Optionally enrich via LLM
        enriched_md = ""
        if args.enrich and session_hits:
            print(f"    → enriching with LLM …", file=sys.stderr)
            enriched_md = enrich_with_llm(title, session_hits, args.endpoint, args.model)

        content = make_stub(book, session_hits, discord_summaries, enriched_md, preserved)

        if args.dry_run:
            action = "would update" if exists else "would create"
            sess_note = f" ({len(session_hits)} session hits)" if session_hits else ""
            print(f"  {action}: {dest}{sess_note}")
            continue

        dest.write_text(content, encoding="utf-8")
        if exists:
            updated += 1
        else:
            created += 1

    # Index
    index_path = LIBRARY_DIR / "Index.md"
    index_content = generate_index(books)
    if not args.dry_run:
        index_path.write_text(index_content, encoding="utf-8")
        print(f"\nWrote {index_path}", file=sys.stderr)
    else:
        print(f"\n[dry-run] would write {index_path}")

    print(f"\nDone: {created} created, {updated} updated, {skipped} skipped", file=sys.stderr)


if __name__ == "__main__":
    main()
