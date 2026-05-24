#!/usr/bin/env python3
"""
Deterministic vault automation harness.

This script is intentionally conservative. It does not call an LLM and does not
edit vault Markdown. The first job is to make source discovery and guardrail
validation boring enough that scheduled automation can safely report proposals
instead of mutating the vault directly.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "vault"
AUTOMATION_DIR = ROOT / "data" / "automation"
LOCAL_SOURCES_CONFIG = ROOT / "config" / "local_sources.json"
CHANGELOG_PATH = ROOT / "docs" / "AUTOMATION_CHANGELOG.md"
CAMPAIGN_CONTEXT_PATH = ROOT / "docs" / "CAMPAIGN_CONTEXT.md"
BLOG_FEED_URL = "https://dfwhiterock.blogspot.com/feeds/posts/default?alt=json&max-results=50"
CENTRAL = ZoneInfo("America/Chicago")

ENTITY_DIRS = {
    "npcs": "NPC",
    "pcs": "PC",
    "locations": "Location",
    "factions": "Faction",
    "items": "Item",
}

MEDIA_DIRS = {
    "notes": "Media Note",
    "lore": "Lore Source",
    "items": "Media Item",
    "locations": "Repository",
}

MEDIA_TITLE_PATTERNS = re.compile(
    r"\b(book|books|journal|scroll|codex|treatise|manuscript|litany|map|cartographic|crystal|library|bookstore|archive|catalog)\b",
    flags=re.IGNORECASE,
)

MEDIA_TAGS = {
    "book",
    "books",
    "journal",
    "scroll",
    "codex",
    "manuscript",
    "map",
    "maps",
    "cartography",
    "catalog",
    "library",
    "written-sources",
    "media",
    "data-crystal",
    "lore-source",
}

FORBIDDEN_VAULT_DIRS = {
    "Entities",
    "Factions",
    "Items",
    "Locations",
    "NPCs",
    "PCs",
    "Sessions",
    "Spells",
    "Weekly Discord Digests",
}

CANONICAL_VAULT_DIRS = {
    "attachments",
    "concepts",
    "factions",
    "items",
    "locations",
    "lore",
    "monsters",
    "notes",
    "npcs",
    "pcs",
    "sessions",
    "spells",
    "templates",
}


@dataclass
class SourceRecord:
    source_id: str
    source_type: str
    path: str
    mtime: float
    size: int
    sha256: str
    status: str = "discovered"


@dataclass
class BlogPostRecord:
    source_id: str
    title: str
    url: str
    published: str
    updated: str
    labels: list[str]
    status: str = "discovered"


@dataclass
class BlogEntry:
    record: BlogPostRecord
    content_html: str


@dataclass
class SpreadsheetSnapshot:
    source_id: str
    row_count: int
    column_count: int
    non_empty_cells: int
    sha256: str
    headers: list[str]
    status: str = "discovered"


@dataclass(frozen=True)
class SpreadsheetRowClassification:
    row_number: int
    label: str
    category: str
    route: str
    subjects: tuple[str, ...]
    non_empty_cells: int
    confidence: str
    notes: str


@dataclass(frozen=True)
class LootDispositionEvidence:
    source: str
    line_number: int
    disposition: str
    excerpt: str
    status: str


@dataclass(frozen=True)
class LootReconciliationMatch:
    source: str
    line_number: int
    disposition: str
    evidence_excerpt: str
    matched_vault_items: tuple[str, ...]
    extracted_item_phrases: tuple[str, ...]
    matched_spreadsheet_rows: tuple[str, ...]
    confidence: str
    review_note: str


@dataclass(frozen=True)
class EntityPage:
    title: str
    kind: str
    path: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class EntityLinkProposal:
    source: str
    entity: str
    entity_path: str
    kind: str
    mention: str
    context: str
    status: str


@dataclass(frozen=True)
class ArticleQueueItem:
    path: str
    title: str
    kind: str
    tags: tuple[str, ...]
    score: int
    reasons: tuple[str, ...]
    queries: tuple[str, ...]


@dataclass(frozen=True)
class MediaQueueItem:
    path: str
    title: str
    kind: str
    tags: tuple[str, ...]
    score: int
    reasons: tuple[str, ...]
    queries: tuple[str, ...]


def load_local_sources() -> dict:
    config: dict = {}
    if LOCAL_SOURCES_CONFIG.exists():
        config = json.loads(LOCAL_SOURCES_CONFIG.read_text(encoding="utf-8"))

    digest_root = os.environ.get("ARDEN_DISCORD_DIGEST_ROOT") or config.get("discord_digest_root")
    rollup_root = os.environ.get("ARDEN_DISCORD_ROLLUP_ROOT") or config.get("discord_rollup_root")
    spreadsheet_url = os.environ.get("ARDEN_GROUP_SPREADSHEET_URL") or config.get("group_spreadsheet_url")
    spreadsheet_gid = os.environ.get("ARDEN_GROUP_SPREADSHEET_GID") or config.get("group_spreadsheet_gid")
    return {
        "discord_digest_root": Path(digest_root).expanduser() if digest_root else None,
        "discord_rollup_root": Path(rollup_root).expanduser() if rollup_root else None,
        "group_spreadsheet_url": spreadsheet_url,
        "group_spreadsheet_gid": str(spreadsheet_gid) if spreadsheet_gid is not None else None,
        "llm_base_url": os.environ.get("ARDEN_LLM_BASE_URL") or config.get("llm_base_url"),
        "llm_model": os.environ.get("ARDEN_LLM_MODEL") or config.get("llm_model"),
        "entity_link_verify_limit": int(config.get("entity_link_verify_limit", 0) or 0),
        "entity_link_apply_limit": int(config.get("entity_link_apply_limit", 0) or 0),
        "article_queue_limit": int(os.environ.get("ARDEN_ARTICLE_QUEUE_LIMIT") or config.get("article_queue_limit", 30) or 30),
        "media_queue_limit": int(os.environ.get("ARDEN_MEDIA_QUEUE_LIMIT") or config.get("media_queue_limit", 30) or 30),
    }


def source_roots() -> dict[str, list[Path]]:
    sources = load_local_sources()
    roots = {"session": [VAULT / "sessions"]}
    if sources["discord_digest_root"]:
        roots["discord_digest"] = [sources["discord_digest_root"]]
    return roots


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_markdown_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        parts = set(path.parts)
        if "node_modules" in parts or "quartz" in parts:
            continue
        yield path


def discover_sources() -> list[SourceRecord]:
    records: list[SourceRecord] = []
    seen: set[Path] = set()
    for source_type, roots in source_roots().items():
        for root in roots:
            for path in iter_markdown_files(root):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                stat = path.stat()
                rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
                records.append(
                    SourceRecord(
                        source_id=hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:16],
                        source_type=source_type,
                        path=rel,
                        mtime=stat.st_mtime,
                        size=stat.st_size,
                        sha256=sha256_file(path),
                    )
                )
    records.sort(key=lambda r: (r.source_type, r.path))
    return records


def fetch_blog_posts(feed_url: str = BLOG_FEED_URL) -> list[BlogPostRecord]:
    return [entry.record for entry in fetch_blog_entries(feed_url)]


def fetch_blog_entries(feed_url: str = BLOG_FEED_URL) -> list[BlogEntry]:
    with urllib.request.urlopen(feed_url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    entries: list[BlogEntry] = []
    for entry in payload.get("feed", {}).get("entry", []):
        title = entry.get("title", {}).get("$t", "").strip()
        links = entry.get("link", [])
        url = next((link.get("href", "") for link in links if link.get("rel") == "alternate"), "")
        if not title or not url:
            continue
        labels = [cat.get("term", "") for cat in entry.get("category", []) if cat.get("term")]
        if "Arden Vul" not in labels and "arden vul" not in title.lower():
            continue
        record = BlogPostRecord(
                source_id=hashlib.sha1(url.encode("utf-8")).hexdigest()[:16],
                title=title,
                url=url,
                published=entry.get("published", {}).get("$t", ""),
                updated=entry.get("updated", {}).get("$t", ""),
                labels=labels,
            )
        entries.append(
            BlogEntry(
                record=record,
                content_html=entry.get("content", {}).get("$t", ""),
            )
        )
    entries.sort(key=lambda item: (item.record.published, item.record.title))
    return entries


def spreadsheet_csv_url(url: str, gid: str | None = None) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.path.endswith("/export"):
        query = urllib.parse.parse_qs(parsed.query)
        query["format"] = ["csv"]
        if gid:
            query["gid"] = [gid]
        return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))
    match = re.search(r"/spreadsheets/d/([^/]+)", parsed.path)
    if not match:
        raise ValueError("not a Google Sheets URL")
    sheet_id = match.group(1)
    query = urllib.parse.parse_qs(parsed.query)
    gid_value = gid or (query.get("gid") or ["0"])[0]
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid_value}"


def fetch_spreadsheet_rows(url: str, gid: str | None = None) -> tuple[str, list[list[str]]]:
    csv_url = spreadsheet_csv_url(url, gid)
    with urllib.request.urlopen(csv_url, timeout=30) as response:
        text = response.read().decode("utf-8-sig", errors="replace")
    rows = [row for row in csv.reader(io.StringIO(text))]
    return text, rows


def spreadsheet_snapshot(url: str, gid: str | None = None) -> tuple[SpreadsheetSnapshot, list[list[str]]]:
    text, rows = fetch_spreadsheet_rows(url, gid)
    column_count = max((len(row) for row in rows), default=0)
    non_empty = sum(1 for row in rows for cell in row if cell.strip())
    headers = next((row for row in rows if any(cell.strip() for cell in row)), [])
    source_key = spreadsheet_csv_url(url, gid)
    snapshot = SpreadsheetSnapshot(
        source_id=hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:16],
        row_count=len(rows),
        column_count=column_count,
        non_empty_cells=non_empty,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        headers=[cell.strip() for cell in headers[:25]],
    )
    return snapshot, rows


def configured_spreadsheet_snapshot() -> dict:
    sources = load_local_sources()
    url = sources.get("group_spreadsheet_url")
    if not url:
        return {"configured": False}
    try:
        snapshot, _rows = spreadsheet_snapshot(str(url), sources.get("group_spreadsheet_gid"))
    except Exception as exc:
        return {"configured": True, "ok": False, "error": str(exc)}
    payload = asdict(snapshot)
    payload["configured"] = True
    payload["ok"] = True
    return payload


def write_spreadsheet_snapshot_report(snapshot: SpreadsheetSnapshot, rows: list[list[str]]) -> None:
    run_dir = AUTOMATION_DIR / "sources"
    payload = {
        **asdict(snapshot),
        "generated": datetime.now(timezone.utc).isoformat(),
        "preview_rows": rows[:20],
    }
    write_json(run_dir / "group_spreadsheet_snapshot.json", payload)
    lines = [
        "# Group Spreadsheet Snapshot",
        "",
        "Ignored operational snapshot of the shared structured campaign sheet.",
        "Use this as source material for review-gated proposals; do not treat spreadsheet cells as final narrative claims without verification when they affect lore.",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Rows: {snapshot.row_count}",
        f"Columns: {snapshot.column_count}",
        f"Non-empty cells: {snapshot.non_empty_cells}",
        f"Content SHA-256: `{snapshot.sha256}`",
        "",
        "## First Non-Empty Row",
        "",
        "| Column | Value |",
        "| ---: | --- |",
    ]
    for idx, value in enumerate(snapshot.headers, start=1):
        lines.append(f"| {idx} | {value.replace('|', '\\|')} |")
    lines.extend(["", "## Preview", ""])
    max_cols = min(snapshot.column_count, 16)
    lines.append("| " + " | ".join(str(i) for i in range(1, max_cols + 1)) + " |")
    lines.append("| " + " | ".join("---" for _ in range(max_cols)) + " |")
    for row in rows[:12]:
        cells = [(row[i] if i < len(row) else "").replace("|", "\\|") for i in range(max_cols)]
        lines.append("| " + " | ".join(cells) + " |")
    (run_dir / "group_spreadsheet_snapshot.md").write_text("\n".join(lines), encoding="utf-8")


def spreadsheet_header_row(rows: list[list[str]]) -> tuple[int, list[str]]:
    best_idx = 0
    best_row: list[str] = []
    best_score = -1
    for idx, row in enumerate(rows[:10]):
        score = sum(1 for cell in row[2:] if cell.strip())
        if score > best_score:
            best_idx = idx
            best_row = row
            best_score = score
    return best_idx, best_row


def spreadsheet_row_label(row: list[str]) -> str:
    for cell in row[:2]:
        if cell.strip():
            return normalize_space(cell)
    return ""


def classify_spreadsheet_label(label: str, current_section: str) -> tuple[str, str, str, str]:
    lower = label.lower()
    section = current_section.lower()
    if not label:
        return "blank", "ignore", "low", "blank separator row"
    exact = lower.strip()
    if any(term in lower for term in {"book", "scroll", "crystal", "library", "map", "catalog"}):
        return "media-library", "media queue", "medium", "media or library row"
    if any(term in lower for term in {"spell", "share energy", "bless", "affect spirits", "breathe water"}):
        return "party-spells", "PC/spell proposal queue", "high", "party spell capability row"
    if exact == "swim" and "party spells" in section:
        return "party-spells", "PC/spell proposal queue", "high", "party spell capability row"
    if any(term in lower for term in {"dodge", "parry", "block", "defense", "physical stun", "mental stun", "fright"}):
        return "pc-defense", "PC sheet proposal queue", "high", "defense/resistance row"
    if exact == "dr" or lower.startswith("dr "):
        return "pc-defense", "PC sheet proposal queue", "high", "defense/resistance row"
    if any(term in lower for term in {"melee", "damage", "close combat", "grappling", "ranged", "distance", "rof", "shots", "throwing", "backup"}):
        return "pc-combat", "PC sheet proposal queue", "high", "combat capability row"
    if any(term in lower for term in {"stealth", "climbing", "swimming", "gesture", "alchemy"}):
        return "pc-skills", "PC sheet proposal queue", "high", "skill row"
    if any(term in lower for term in {"loot", "treasure", "selling", "power item", "backpack"}):
        return "loot-inventory", "PC/item proposal queue", "medium", "inventory, carrying, selling, or resource row"
    if exact in {"enc", "bl"}:
        return "loot-inventory", "PC/item proposal queue", "medium", "inventory, carrying, selling, or resource row"
    if exact in {"st", "dx", "iq", "ht", "hp", "fp", "er", "will", "per", "speed", "base move", "combat move", "luck", "recovery", "striking", "lifting"}:
        return "pc-mechanics", "PC sheet proposal queue", "high", "character mechanical/stat row"
    if any(lower.startswith(prefix) for prefix in {"st ", "dx ", "iq ", "ht ", "hp ", "fp ", "er ", "will ", "per "}):
        return "pc-mechanics", "PC sheet proposal queue", "high", "character mechanical/stat row"
    if "base skill" in lower:
        return "pc-mechanics", "PC sheet proposal queue", "high", "character mechanical/stat row"
    if "defense" in section:
        return "pc-defense", "PC sheet proposal queue", "medium", "row inherited from defense section"
    if "melee" in section or "ranged" in section:
        return "pc-combat", "PC sheet proposal queue", "medium", "row inherited from combat section"
    if "party spells" in section:
        return "party-spells", "PC/spell proposal queue", "medium", "row inherited from party spell section"
    return "unknown-structured", "spreadsheet review", "low", "structured row needs review"


def classify_spreadsheet_rows(rows: list[list[str]]) -> list[SpreadsheetRowClassification]:
    header_idx, header = spreadsheet_header_row(rows)
    subjects_by_col = {idx: normalize_space(name) for idx, name in enumerate(header) if idx >= 2 and name.strip()}
    classifications: list[SpreadsheetRowClassification] = []
    current_section = ""
    for idx, row in enumerate(rows, start=1):
        label = spreadsheet_row_label(row)
        non_empty = sum(1 for cell in row if cell.strip())
        if idx == header_idx + 1:
            classifications.append(
                SpreadsheetRowClassification(
                    row_number=idx,
                    label="character headers",
                    category="pc-roster",
                    route="PC roster mapping",
                    subjects=tuple(subjects_by_col.values()),
                    non_empty_cells=non_empty,
                    confidence="high",
                    notes="header row maps spreadsheet columns to player characters and companions",
                )
            )
            continue
        if idx == header_idx + 2 and non_empty:
            subjects = tuple(
                subjects_by_col[col]
                for col, cell in enumerate(row)
                if col in subjects_by_col and cell.strip()
            )
            classifications.append(
                SpreadsheetRowClassification(
                    row_number=idx,
                    label="ancestry/species row",
                    category="pc-roster",
                    route="PC roster mapping",
                    subjects=subjects,
                    non_empty_cells=non_empty,
                    confidence="medium",
                    notes="unlabeled row directly below character headers appears to describe ancestry/species",
                )
            )
            continue
        if label and row[0].strip() and not row[1].strip():
            current_section = label
        subjects = tuple(
            subjects_by_col[col]
            for col, cell in enumerate(row)
            if col in subjects_by_col and cell.strip()
        )
        category, route, confidence, notes = classify_spreadsheet_label(label, current_section)
        if category == "blank" and non_empty == 0:
            continue
        if category == "blank":
            continue
        classifications.append(
            SpreadsheetRowClassification(
                row_number=idx,
                label=label or "(unlabeled row)",
                category=category,
                route=route,
                subjects=subjects,
                non_empty_cells=non_empty,
                confidence=confidence,
                notes=notes,
            )
        )
    return classifications


def write_spreadsheet_classification_report(snapshot: SpreadsheetSnapshot, rows: list[list[str]]) -> list[SpreadsheetRowClassification]:
    run_dir = AUTOMATION_DIR / "sources"
    classifications = classify_spreadsheet_rows(rows)
    write_json(
        run_dir / "group_spreadsheet_classification.json",
        {
            "source_id": snapshot.source_id,
            "sha256": snapshot.sha256,
            "generated": datetime.now(timezone.utc).isoformat(),
            "classification_count": len(classifications),
            "rows": [asdict(item) for item in classifications],
        },
    )
    counts: dict[str, int] = {}
    for item in classifications:
        counts[item.category] = counts.get(item.category, 0) + 1
    lines = [
        "# Group Spreadsheet Classification",
        "",
        "Review-first interpretation of the shared structured sheet.",
        "Rows are routed to proposal queues; no vault pages are edited by this report.",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Source ID: `{snapshot.source_id}`",
        f"Content SHA-256: `{snapshot.sha256}`",
        "",
        "## Category Counts",
        "",
        "| Category | Rows |",
        "| --- | ---: |",
    ]
    for category, count in sorted(counts.items()):
        lines.append(f"| {category} | {count} |")
    lines.extend(
        [
            "",
            "## Routed Rows",
            "",
            "| Row | Label | Category | Route | Subjects | Confidence | Notes |",
            "| ---: | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in classifications:
        subjects = ", ".join(item.subjects[:8])
        if len(item.subjects) > 8:
            subjects += f", +{len(item.subjects) - 8} more"
        lines.append(
            f"| {item.row_number} | {item.label.replace('|', '\\|')} | {item.category} | "
            f"{item.route} | {subjects.replace('|', '\\|')} | {item.confidence} | {item.notes.replace('|', '\\|')} |"
        )
    (run_dir / "group_spreadsheet_classification.md").write_text("\n".join(lines), encoding="utf-8")
    return classifications


LOOT_DISPOSITION_PATTERNS = {
    "destroyed": re.compile(r"\b(destroyed|shattered|smashed|disintegrated|burned up|burnt up|ruined)\b", re.I),
    "consumed": re.compile(r"\b(consumed|drank|drunk|used up|spent|expended|cast from|activated)\b", re.I),
    "lost": re.compile(r"\b(lost|dropped|left behind|abandoned|misplaced|fell into|fell down)\b", re.I),
    "sold": re.compile(r"\b(sold|fenced|converted to cash|cashed out|liquidated)\b", re.I),
    "broken": re.compile(r"\b(broken|cracked|damaged|fragile)\b", re.I),
}


def disposition_for_text(text: str) -> str | None:
    matches = [name for name, pattern in LOOT_DISPOSITION_PATTERNS.items() if pattern.search(text)]
    if not matches:
        return None
    priority = ["destroyed", "consumed", "lost", "sold", "broken"]
    return next(name for name in priority if name in matches)


def is_loot_disposition_noise(text: str) -> bool:
    lower = text.lower()
    noise_patterns = [
        r"broken (speaking|written|writing)",
        r"ruined by excessive xp",
        r"xp for .*treasure",
        r"sell stuff anonymously",
        r"loot xp",
        r"2 xp loot session",
        r"loot appears",
    ]
    return any(re.search(pattern, lower) for pattern in noise_patterns)


def find_loot_disposition_evidence() -> list[LootDispositionEvidence]:
    evidence: list[LootDispositionEvidence] = []
    sources = all_discord_summary_paths()
    for path in sources:
        rel = path.relative_to(ROOT).as_posix()
        lines = read_text(path).splitlines()
        for idx, line in enumerate(lines, start=1):
            if not re.search(r"\b(item|loot|treasure|potion|scroll|book|map|crystal|ring|armor|weapon|shield|wand|rod|staff|rug|card|plaque|key|gem|coin|gold|silver)\b", line, flags=re.I):
                continue
            if is_loot_disposition_noise(line):
                continue
            disposition = disposition_for_text(line)
            if not disposition:
                continue
            excerpt = normalize_space(line)
            evidence.append(
                LootDispositionEvidence(
                    source=rel,
                    line_number=idx,
                    disposition=disposition,
                    excerpt=excerpt[:500],
                    status="needs-review",
                )
            )
    evidence.sort(key=lambda item: (item.source, item.line_number, item.disposition))
    return evidence


def current_spreadsheet_loot_rows() -> list[dict]:
    path = AUTOMATION_DIR / "sources" / "group_spreadsheet_classification.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in payload.get("rows", []) if row.get("category") == "loot-inventory"]


def loot_target_pages() -> list[EntityPage]:
    pages = [page for page in entity_pages() if page.kind == "Item"]
    for folder, kind in {"notes": "Note", "lore": "Lore"}.items():
        root = VAULT / folder
        if not root.exists():
            continue
        for path in sorted(root.glob("*.md")):
            if path.stem.lower() in {"index", "readme"}:
                continue
            text = read_text(path)
            title = article_title(path, text)
            if not MEDIA_TITLE_PATTERNS.search(title) and not MEDIA_TITLE_PATTERNS.search(path.stem):
                continue
            aliases = tuple(article_aliases(text))
            pages.append(
                EntityPage(
                    title=title,
                    kind=kind,
                    path=path.relative_to(ROOT).as_posix(),
                    aliases=aliases,
                )
            )
    return pages


def normalized_for_match(value: str) -> str:
    value = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"\[\[([^\]]+)\]\]", lambda m: Path(m.group(1)).stem, value)
    value = re.sub(r"[*_`\"']", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return normalize_space(value)


def exact_loot_page_matches(excerpt: str, pages: list[EntityPage]) -> list[str]:
    norm_excerpt = " " + normalized_for_match(excerpt) + " "
    matches: list[str] = []
    for page in pages:
        names = (page.title, *page.aliases, Path(page.path).stem)
        for name in names:
            norm_name = normalized_for_match(name)
            if len(norm_name) < 4:
                continue
            if f" {norm_name} " in norm_excerpt:
                matches.append(page.path)
                break
    return sorted(set(matches))


def extract_item_phrases(excerpt: str) -> list[str]:
    text = re.sub(r"\[[^\]]+\]", "", excerpt)
    text = re.sub(r"\([^)]*\)", "", text)
    patterns = [
        r"\b(?:Potion|Book|Map|Gauntlet|Javelin|Key|Keys|Plaque|Card|Ring|Rug|Scroll|Crystal|Disc|Power Supply|Black Sand|Teleportation Squares?|Magical Eyes?)\b(?:\s+of\s+[A-Z][A-Za-z'-]+|\s+[A-Z][A-Za-z0-9'-]+){0,5}",
        r"\b[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,4}\s+(?:Potion|Book|Map|Gauntlet|Javelin|Key|Plaque|Card|Ring|Rug|Scroll|Crystal|Disc)\b",
    ]
    phrases: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            phrase = normalize_space(match.group(0).strip(" -:;,."))
            if len(phrase) < 4:
                continue
            if phrase.lower() in {"key copies", "power item"}:
                continue
            phrases.append(phrase)
    # Split comma lists inside parentheticals that have already contributed useful names.
    for chunk in re.split(r"[;,]", excerpt):
        if re.search(r"\b(map|eyes|squares|sand|supply|plaque|potion|javelin|gauntlet|book)\b", chunk, re.I):
            cleaned = normalize_space(re.sub(r"[*_`\"()\[\]]", "", chunk))
            cleaned = re.sub(r"^[-: A-Za-z0-9]*?(Temrin map|magical eyes|teleportation squares|black sand|power supply|Brown Oval Plaque|Potion of Chaotic Sweat|Returning Javelin|Gauntlet of Flaming Fury|Book of Night Maneuvers).*", r"\1", cleaned, flags=re.I)
            if 4 <= len(cleaned) <= 80:
                phrases.append(cleaned)
    out: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        key = normalized_for_match(phrase)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(phrase)
    return out[:8]


def fuzzy_loot_page_matches(phrases: list[str], pages: list[EntityPage]) -> list[str]:
    matches: set[str] = set()
    choices: list[tuple[str, str]] = []
    for page in pages:
        for name in (page.title, *page.aliases, Path(page.path).stem):
            norm = normalized_for_match(name)
            if len(norm) >= 5:
                choices.append((norm, page.path))
    for phrase in phrases:
        norm_phrase = normalized_for_match(phrase)
        if len(norm_phrase) < 5:
            continue
        for norm_name, path in choices:
            ratio = difflib.SequenceMatcher(None, norm_phrase, norm_name).ratio()
            if ratio >= 0.88:
                matches.add(path)
    return sorted(matches)


def spreadsheet_row_matches_for_evidence(excerpt: str, loot_rows: list[dict]) -> list[str]:
    lower = excerpt.lower()
    matches: list[str] = []
    for row in loot_rows:
        label = str(row.get("label", ""))
        label_lower = label.lower()
        if label_lower and label_lower in lower:
            matches.append(f"row {row.get('row_number')}: {label}")
            continue
        if label == "Power Item" and re.search(r"\b(power item|power supply|power disc)\b", lower):
            matches.append(f"row {row.get('row_number')}: {label}")
        elif label == "Selling" and re.search(r"\b(sell|sold|selling|cash|contribute)\b", lower):
            matches.append(f"row {row.get('row_number')}: {label}")
        elif label == "Selling" and re.search(r"\b(spent|cost)\b", lower) and re.search(r"\b(gear|item|map|eyes|squares|sand|supply|plaque|party members)\b", lower):
            matches.append(f"row {row.get('row_number')}: {label}")
        elif label in {"BL", "Enc", "Backpack Move (4+)"} and re.search(r"\b(weight|lbs|encumbrance|carrying|backpack|abandoned due to weight)\b", lower):
            matches.append(f"row {row.get('row_number')}: {label}")
    return sorted(set(matches))


def build_loot_reconciliation_matches(evidence: list[LootDispositionEvidence], loot_rows: list[dict]) -> list[LootReconciliationMatch]:
    pages = loot_target_pages()
    matches: list[LootReconciliationMatch] = []
    for item in evidence:
        exact = exact_loot_page_matches(item.excerpt, pages)
        phrases = extract_item_phrases(item.excerpt)
        fuzzy = [path for path in fuzzy_loot_page_matches(phrases, pages) if path not in exact]
        vault_matches = tuple(sorted(set(exact + fuzzy)))
        row_matches = tuple(spreadsheet_row_matches_for_evidence(item.excerpt, loot_rows))
        if vault_matches and row_matches:
            confidence = "high"
            note = "matched an existing vault item/media page and a relevant spreadsheet row"
        elif vault_matches:
            confidence = "medium"
            note = "matched an existing vault item/media page; spreadsheet row impact needs review"
        elif phrases and row_matches:
            confidence = "medium"
            note = "found item-like phrases and a spreadsheet row, but no existing vault page match"
        elif phrases:
            confidence = "low"
            note = "found item-like phrases with no existing vault page or spreadsheet row match"
        else:
            confidence = "low"
            note = "no specific item phrase found; keep as disposition evidence only"
        matches.append(
            LootReconciliationMatch(
                source=item.source,
                line_number=item.line_number,
                disposition=item.disposition,
                evidence_excerpt=item.excerpt,
                matched_vault_items=vault_matches,
                extracted_item_phrases=tuple(phrases),
                matched_spreadsheet_rows=row_matches,
                confidence=confidence,
                review_note=note,
            )
        )
    return matches


def write_loot_reconciliation_report() -> dict:
    run_dir = AUTOMATION_DIR / "proposals"
    evidence = find_loot_disposition_evidence()
    loot_rows = current_spreadsheet_loot_rows()
    matches = build_loot_reconciliation_matches(evidence, loot_rows)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "spreadsheet_loot_row_count": len(loot_rows),
        "discord_disposition_evidence_count": len(evidence),
        "match_count": len(matches),
        "spreadsheet_loot_rows": loot_rows,
        "discord_disposition_evidence": [asdict(item) for item in evidence],
        "matches": [asdict(item) for item in matches],
    }
    write_json(run_dir / "loot_reconciliation.json", payload)
    lines = [
        "# Loot Reconciliation",
        "",
        "Review-first report for balancing shared spreadsheet inventory/loot rows against Discord summary evidence for destroyed, consumed, lost, sold, or broken items.",
        "This report does not edit vault pages. Spreadsheet inventory should not be promoted as current until disposition evidence has been reviewed.",
        "",
        f"Generated: {payload['generated']}",
        f"Spreadsheet loot/inventory rows: {len(loot_rows)}",
        f"Discord disposition evidence rows: {len(evidence)}",
        "",
        "## Spreadsheet Loot / Inventory Rows",
        "",
        "| Row | Label | Subjects | Notes |",
        "| ---: | --- | --- | --- |",
    ]
    for row in loot_rows:
        subjects = ", ".join(row.get("subjects", [])[:10])
        if len(row.get("subjects", [])) > 10:
            subjects += f", +{len(row['subjects']) - 10} more"
        lines.append(
            f"| {row.get('row_number')} | {str(row.get('label', '')).replace('|', '\\|')} | "
            f"{subjects.replace('|', '\\|')} | {str(row.get('notes', '')).replace('|', '\\|')} |"
        )
    lines.extend(
        [
            "",
            "## Candidate Matches",
            "",
            "| Source | Line | Disposition | Confidence | Vault Matches | Spreadsheet Rows | Extracted Phrases | Review Note |",
            "| --- | ---: | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for match in matches:
        vault_matches = "<br>".join(f"[[{wikilink_target_from_repo_path(path)}]]" for path in match.matched_vault_items)
        row_matches = "<br>".join(match.matched_spreadsheet_rows)
        phrases = "<br>".join(match.extracted_item_phrases)
        lines.append(
            f"| {match.source} | {match.line_number} | {match.disposition} | {match.confidence} | "
            f"{vault_matches.replace('|', '\\|')} | {row_matches.replace('|', '\\|')} | "
            f"{phrases.replace('|', '\\|')} | {match.review_note.replace('|', '\\|')} |"
        )
    lines.extend(
        [
            "",
            "## Discord Disposition Evidence",
            "",
            "| Source | Line | Disposition | Status | Excerpt |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for item in evidence:
        lines.append(
            f"| {item.source} | {item.line_number} | {item.disposition} | {item.status} | {item.excerpt.replace('|', '\\|')} |"
        )
    (run_dir / "loot_reconciliation.md").write_text("\n".join(lines), encoding="utf-8")
    return payload


def git_status() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    return [line for line in result.stdout.splitlines() if line.strip()]


def validate_state() -> dict:
    status = git_status()
    tracked_deletions = [line for line in status if line[:2].strip() == "D" or line.startswith(" D")]
    untracked = [line for line in status if line.startswith("?? ")]
    modified = [line for line in status if line and not line.startswith("?? ") and line not in tracked_deletions]

    forbidden_existing = sorted(
        d.name for d in VAULT.iterdir() if d.is_dir() and d.name in FORBIDDEN_VAULT_DIRS
    )
    canonical_missing = sorted(d for d in CANONICAL_VAULT_DIRS if not (VAULT / d).exists())

    failures = []
    if tracked_deletions:
        failures.append("tracked_deletions_present")
    if forbidden_existing:
        failures.append("forbidden_duplicate_dirs_present")
    if not VAULT.exists():
        failures.append("canonical_vault_missing")

    return {
        "ok": not failures,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo": str(ROOT),
        "vault": str(VAULT),
        "failures": failures,
        "git": {
            "status_count": len(status),
            "tracked_deletions": len(tracked_deletions),
            "modified": len(modified),
            "untracked": len(untracked),
        },
        "forbidden_existing_dirs": forbidden_existing,
        "canonical_missing_dirs": canonical_missing,
    }


def discord_status() -> dict:
    sources = load_local_sources()
    rollups_dir = sources["discord_rollup_root"]
    digests_dir = sources["discord_digest_root"]
    if not digests_dir:
        return {
            "configured": False,
            "rollup_count": 0,
            "digest_count": 0,
            "latest_rollup": None,
            "latest_digest": None,
        }
    rollups = sorted(p for p in rollups_dir.glob("week-ending-*-2300-central") if p.is_dir()) if rollups_dir else []
    digests = sorted(p for p in digests_dir.glob("week-ending-*-2300-central") if p.is_dir())
    digest_files = []
    for folder in digests:
        preferred = folder / "revised-digest.md"
        fallback = folder / "digest.md"
        if preferred.exists():
            digest_files.append(preferred)
        elif fallback.exists():
            digest_files.append(fallback)

    return {
        "configured": True,
        "rollup_count": len(rollups),
        "digest_count": len(digest_files),
        "latest_rollup": rollups[-1].name if rollups else None,
        "latest_digest": digest_files[-1].parent.name if digest_files else None,
    }


def parse_week_end_from_folder(path: Path) -> datetime | None:
    match = re.search(r"week-ending-(\d{4}-\d{2}-\d{2})-2300-central$", path.name)
    if not match:
        return None
    return datetime.fromisoformat(match.group(1) + "T23:00:00").replace(tzinfo=CENTRAL)


def week_key_from_date(dt: datetime) -> str:
    return dt.astimezone(CENTRAL).strftime("%Y-W%W")


def discord_summary_path_for_week_end(week_end: datetime) -> Path:
    return VAULT / "notes" / f"Discord Summary {week_key_from_date(week_end)}.md"


def digest_source_for_folder(folder: Path) -> Path | None:
    revised = folder / "revised-digest.md"
    digest = folder / "digest.md"
    if revised.exists():
        return revised
    if digest.exists():
        return digest
    return None


def iter_external_digests() -> list[tuple[datetime, Path, Path]]:
    items: list[tuple[datetime, Path, Path]] = []
    digests_dir = load_local_sources()["discord_digest_root"]
    if not digests_dir:
        return items
    for folder in sorted(digests_dir.glob("week-ending-*-2300-central")):
        if not folder.is_dir():
            continue
        week_end = parse_week_end_from_folder(folder)
        digest = digest_source_for_folder(folder)
        if week_end and digest:
            items.append((week_end, folder, digest))
    return sorted(items, key=lambda item: item[0])


def markdown_escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_discord_summary_markdown(week_end: datetime, source_folder: Path, digest_path: Path) -> str:
    week_key = week_key_from_date(week_end)
    title = f"Discord Summary {week_key}"
    body = digest_path.read_text(encoding="utf-8", errors="ignore").strip()
    return "\n".join(
        [
            "---",
            f'title: "{markdown_escape_yaml(title)}"',
            "tags:",
            "  - discord-summary",
            "  - canonical-source",
            f"week_ending: {week_end.date().isoformat()}",
            "source_type: private-discord-weekly-digest",
            f"source_week: {source_folder.name}",
            "---",
            "",
            f"# {title}",
            "",
            "## Source",
            "- Private Discord weekly digest",
            f"- Week ending: {week_end.date().isoformat()}",
            "",
            "## Navigation",
            "<!-- BEGIN AUTO NAV -->",
            "<!-- END AUTO NAV -->",
            "",
            body,
            "",
        ]
    )


class BlogHTMLToMarkdown(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.link_stack: list[str] = []

    def emit(self, text: str) -> None:
        if text:
            self.parts.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k: v or "" for k, v in attrs}
        if tag in {"h1", "h2", "h3", "h4"}:
            self.emit("\n\n## ")
        elif tag in {"div", "p"}:
            self.emit("\n\n")
        elif tag == "br":
            self.emit("\n")
        elif tag in {"ul", "ol"}:
            self.emit("\n")
        elif tag == "li":
            self.emit("\n- ")
        elif tag == "a":
            self.link_stack.append(attrs_dict.get("href", ""))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "p", "div", "ul", "ol"}:
            self.emit("\n")
        elif tag == "a" and self.link_stack:
            self.link_stack.pop()

    def handle_data(self, data: str) -> None:
        text = html.unescape(data).replace("\xa0", " ")
        if not text.strip():
            return
        if self.link_stack and self.link_stack[-1]:
            self.emit(f"[{text}]({self.link_stack[-1]})")
        else:
            self.emit(text)

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(?m)^##\s*$", "", text)
        return text.strip()


def html_to_markdown(content_html: str) -> str:
    parser = BlogHTMLToMarkdown()
    parser.feed(content_html)
    return parser.markdown()


def parse_session_id(title: str) -> str | None:
    match = re.search(r"\bSession\s+(\d+[a-z]?)\b", title, re.IGNORECASE)
    return match.group(1) if match else None


def session_sort_key(session_id: str) -> tuple[int, str]:
    match = re.match(r"(\d+)([a-z]?)$", session_id)
    if not match:
        return (10_000, session_id)
    return (int(match.group(1)), match.group(2))


def session_display_title(title: str, session_id: str) -> str:
    cleaned = re.sub(r"^DFRPG\s+(?:Arden Vul\s+)?Session\s+\S+\s*:\s*", "", title, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^Session\s+\S+\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned or title


def session_path_for_blog_title(title: str) -> Path | None:
    session_id = parse_session_id(title)
    if not session_id:
        return None
    display = session_display_title(title, session_id)
    safe = re.sub(r'[\\/*?:"<>|]', "", display).strip()
    return VAULT / "sessions" / f"Session {session_id} - {safe}.md"


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(CENTRAL)
    except ValueError:
        return None


def preceding_friday(dt: datetime) -> datetime:
    dt = dt.astimezone(CENTRAL)
    days_since_friday = (dt.weekday() - 4) % 7
    friday = (dt - timedelta(days=days_since_friday)).replace(hour=23, minute=0, second=0, microsecond=0)
    if friday > dt:
        friday -= timedelta(days=7)
    return friday


def following_friday(dt: datetime) -> datetime:
    prev = preceding_friday(dt)
    if prev.date() == dt.date() and dt.hour < 23:
        return prev
    return prev + timedelta(days=7)


def wikilink(path: Path, label: str | None = None) -> str:
    rel = path.relative_to(VAULT).as_posix()
    display = label or path.stem
    return f"[[{rel}|{display}]]"


def build_session_markdown(entry: BlogEntry) -> str | None:
    session_id = parse_session_id(entry.record.title)
    path = session_path_for_blog_title(entry.record.title)
    if not session_id or not path:
        return None
    display = session_display_title(entry.record.title, session_id)
    post_dt = parse_datetime(entry.record.published)
    body = html_to_markdown(entry.content_html)
    lines = [
        "---",
        f'title: "{markdown_escape_yaml(session_id + ": " + display)}"',
        "tags:",
        "  - session",
        "  - recap",
        "  - canonical-source",
        f"source_url: {entry.record.url}",
        f"blog_published: {entry.record.published}",
        f"blog_updated: {entry.record.updated}",
        "---",
        "",
        f"# {session_id}: {display}",
        "",
        body,
        "",
        "## Source",
        f"- {entry.record.url}",
        "",
        "## Session Navigation",
        "",
        "<!-- BEGIN AUTO NAV -->",
        "- Previous Session: (pending)",
        "- Next Session: (pending)",
        "- Previous Discord Summary: (pending)",
        "- Next Discord Summary: (pending)",
        "<!-- END AUTO NAV -->",
        "",
    ]
    if post_dt:
        lines.insert(-6, f"<!-- blog-published-local: {post_dt.isoformat()} -->")
    return "\n".join(lines)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text_if_changed(path: Path, text: str, apply: bool, changes: list[str]) -> None:
    current = read_text(path) if path.exists() else None
    if current == text:
        return
    changes.append(("update " if path.exists() else "create ") + path.relative_to(ROOT).as_posix())
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def list_session_pages() -> list[tuple[str, Path]]:
    sessions: list[tuple[str, Path]] = []
    for path in (VAULT / "sessions").glob("Session *.md"):
        match = re.match(r"Session\s+(\d+[a-z]?)\b", path.stem, re.IGNORECASE)
        if match:
            sessions.append((match.group(1), path))
    return sorted(sessions, key=lambda item: session_sort_key(item[0]))


def replace_auto_nav(text: str, bullets: list[str]) -> str:
    block = "<!-- BEGIN AUTO NAV -->\n" + "\n".join(bullets) + "\n<!-- END AUTO NAV -->"
    if "<!-- BEGIN AUTO NAV -->" in text and "<!-- END AUTO NAV -->" in text:
        heading_match = re.search(
            r"(?ms)^## (Session Navigation|Navigation)\s*\n.*?<!-- BEGIN AUTO NAV -->.*?<!-- END AUTO NAV -->",
            text,
        )
        if heading_match:
            heading = heading_match.group(1)
            return text[: heading_match.start()] + f"## {heading}\n\n{block}" + text[heading_match.end():]
        return re.sub(r"<!-- BEGIN AUTO NAV -->.*?<!-- END AUTO NAV -->", block, text, flags=re.S)
    if "## Session Navigation" in text:
        return re.sub(r"(?ms)^## Session Navigation\s*\n.*\Z", "## Session Navigation\n\n" + block + "\n", text.rstrip())
    return text.rstrip() + "\n\n## Session Navigation\n\n" + block + "\n"


def update_session_navigation(apply: bool, changes: list[str], target_paths: set[Path] | None = None) -> None:
    sessions = list_session_pages()
    blog_dates_by_url: dict[str, datetime] = {}
    try:
        for post in fetch_blog_posts():
            post_dt = parse_datetime(post.published)
            if post_dt:
                blog_dates_by_url[post.url] = post_dt
    except Exception:
        blog_dates_by_url = {}
    for idx, (sid, path) in enumerate(sessions):
        if target_paths is not None and path not in target_paths:
            continue
        text = read_text(path)
        published_match = re.search(r"^blog_published:\s*(.+)$", text, flags=re.M)
        source_match = re.search(r"^source_url:\s*(.+)$", text, flags=re.M)
        post_dt = parse_datetime(published_match.group(1).strip()) if published_match else None
        if not post_dt and source_match:
            post_dt = blog_dates_by_url.get(source_match.group(1).strip())
        prev_path = sessions[idx - 1][1] if idx > 0 else None
        next_path = sessions[idx + 1][1] if idx + 1 < len(sessions) else None
        prev_summary = next_summary = None
        if post_dt:
            prev_summary = discord_summary_path_for_week_end(preceding_friday(post_dt))
            next_summary = discord_summary_path_for_week_end(following_friday(post_dt))
        bullets = [
            f"- Previous Session: {wikilink(prev_path, prev_path.stem) if prev_path else '(none)'}",
            f"- Next Session: {wikilink(next_path, next_path.stem) if next_path else '(none)'}",
        ]
        if prev_summary and prev_summary.exists():
            bullets.append(f"- Previous Discord Summary: {wikilink(prev_summary, prev_summary.stem)}")
        if next_summary and next_summary.exists():
            bullets.append(f"- Next Discord Summary: {wikilink(next_summary, next_summary.stem)}")
        if source_match:
            bullets.append(f"- Original Source: {source_match.group(1).strip()}")
        updated = replace_auto_nav(text, bullets)
        write_text_if_changed(path, updated, apply, changes)


def update_discord_navigation(apply: bool, changes: list[str], target_paths: set[Path] | None = None) -> None:
    summaries: list[tuple[str, Path]] = []
    for path in (VAULT / "notes").glob("Discord Summary *.md"):
        match = re.search(r"Discord Summary (\d{4}-W\d{2})", path.stem)
        if match:
            summaries.append((match.group(1), path))
    summaries.sort()
    for idx, (_week, path) in enumerate(summaries):
        if target_paths is not None and path not in target_paths:
            continue
        text = read_text(path)
        bullets = [
            f"- Previous Discord Summary: {wikilink(summaries[idx - 1][1], summaries[idx - 1][1].stem) if idx > 0 else '(none)'}",
            f"- Next Discord Summary: {wikilink(summaries[idx + 1][1], summaries[idx + 1][1].stem) if idx + 1 < len(summaries) else '(none)'}",
        ]
        updated = replace_auto_nav(text, bullets)
        write_text_if_changed(path, updated, apply, changes)


def sanitize_discord_summary_sources(apply: bool, changes: list[str]) -> None:
    for path in all_discord_summary_paths():
        text = read_text(path)
        updated = re.sub(r"(?m)^source_(digest|rollup): .*\n", "", text)
        if "source_type: private-discord-weekly-digest" not in updated:
            week_match = re.search(r"^week_ending:\s*(.+)$", updated, flags=re.M)
            insert_after = week_match.end() if week_match else None
            source_type = "\nsource_type: private-discord-weekly-digest"
            if insert_after is not None:
                updated = updated[:insert_after] + source_type + updated[insert_after:]
        week_match = re.search(r"^week_ending:\s*(.+)$", updated, flags=re.M)
        week_ending = week_match.group(1).strip() if week_match else "unknown"
        source_section = (
            "## Source\n"
            "- Private Discord weekly digest\n"
            f"- Week ending: {week_ending}\n"
        )
        if "## Source" in updated and "## Navigation" in updated:
            updated = re.sub(r"(?ms)^## Source\n.*?(?=^## Navigation)", source_section + "\n", updated)
        write_text_if_changed(path, updated, apply, changes)


def adjacent_paths(sorted_paths: list[Path], selected: set[Path]) -> set[Path]:
    out: set[Path] = set()
    for path in selected:
        if path not in sorted_paths:
            continue
        idx = sorted_paths.index(path)
        out.add(path)
        if idx > 0:
            out.add(sorted_paths[idx - 1])
        if idx + 1 < len(sorted_paths):
            out.add(sorted_paths[idx + 1])
    return out


def import_discord_digests(apply: bool, changes: list[str]) -> set[Path]:
    created: set[Path] = set()
    for week_end, folder, digest in iter_external_digests():
        target = discord_summary_path_for_week_end(week_end)
        if target.exists():
            continue
        text = build_discord_summary_markdown(week_end, folder, digest)
        write_text_if_changed(target, text, apply, changes)
        created.add(target)
    return created


def import_blog_sessions(apply: bool, changes: list[str], feed_url: str) -> set[Path]:
    created: set[Path] = set()
    existing_session_ids = {sid for sid, _path in list_session_pages()}
    for entry in fetch_blog_entries(feed_url):
        session_id = parse_session_id(entry.record.title)
        target = session_path_for_blog_title(entry.record.title)
        if not session_id or not target:
            continue
        if session_id in existing_session_ids:
            continue
        if target.exists():
            continue
        text = build_session_markdown(entry)
        if text:
            write_text_if_changed(target, text, apply, changes)
            created.add(target)
            existing_session_ids.add(session_id)
    return created


def all_discord_summary_paths() -> list[Path]:
    paths = []
    for path in (VAULT / "notes").glob("Discord Summary *.md"):
        if re.search(r"Discord Summary \d{4}-W\d{2}", path.stem):
            paths.append(path)
    return sorted(paths)


def all_session_paths() -> list[Path]:
    return [path for _sid, path in list_session_pages()]


def parse_frontmatter(text: str) -> dict[str, object]:
    match = re.match(r"---\n(.*?)\n---", text, flags=re.S)
    if not match:
        return {}
    fields: dict[str, object] = {}
    current_key: str | None = None
    for raw_line in match.group(1).splitlines():
        if raw_line.startswith("  - ") and current_key:
            fields.setdefault(current_key, [])
            value = raw_line[4:].strip().strip('"')
            if value:
                assert isinstance(fields[current_key], list)
                fields[current_key].append(value)
            continue
        current_key = None
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"')
        if value.startswith("[") and value.endswith("]"):
            fields[key] = [
                item.strip().strip('"').strip("'")
                for item in value[1:-1].split(",")
                if item.strip()
            ]
        elif value:
            fields[key] = value
        else:
            fields[key] = []
            current_key = key
    return fields


def entity_pages() -> list[EntityPage]:
    raw_pages: list[EntityPage] = []
    for folder, kind in ENTITY_DIRS.items():
        root = VAULT / folder
        if not root.exists():
            continue
        for path in sorted(root.glob("*.md")):
            if path.stem.lower() in {"index", "readme"}:
                continue
            text = read_text(path)
            frontmatter = parse_frontmatter(text)
            title = str(frontmatter.get("title") or path.stem).strip()
            aliases_raw = frontmatter.get("aliases") or []
            aliases = tuple(a for a in aliases_raw if isinstance(a, str))
            if len(title) < 4:
                continue
            raw_pages.append(
                EntityPage(
                    title=title,
                    kind=kind,
                    path=path.relative_to(ROOT).as_posix(),
                    aliases=aliases,
                )
            )
    title_owner = {normalize_space(page.title).lower(): page.path for page in raw_pages}
    pages: list[EntityPage] = []
    for page in raw_pages:
        safe_aliases = []
        for alias in page.aliases:
            alias = normalize_space(alias)
            if not alias or "," in alias or "(" in alias or ")" in alias:
                continue
            if len(alias.split()) > 4:
                continue
            owner = title_owner.get(alias.lower())
            if owner and owner != page.path:
                continue
            safe_aliases.append(alias)
        pages.append(EntityPage(page.title, page.kind, page.path, tuple(safe_aliases)))
    return pages


def latest_canonical_sources(limit: int = 5) -> list[Path]:
    sessions = list_session_pages()[-limit:]
    summaries = all_discord_summary_paths()[-limit:]
    return [path for _sid, path in sessions] + summaries


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_frontmatter(text: str) -> str:
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    def visible_wikilink(match: re.Match[str]) -> str:
        body = match.group(1)
        if "|" in body:
            return body.rsplit("|", 1)[1]
        return Path(body).stem

    return re.sub(r"\[\[([^\]]+)\]\]", visible_wikilink, text)


def context_excerpt(text: str, start: int, end: int, width: int = 220) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    excerpt = normalize_space(text[left:right])
    return excerpt.replace("|", "\\|")


def context_window(text: str, start: int, end: int, width: int = 1600) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    return normalize_space(text[left:right])


def mention_pattern(mention: str) -> re.Pattern[str] | None:
    mention = normalize_space(mention)
    if len(mention) < 4:
        return None
    if mention.lower() in {"session", "summary", "source", "notes", "index"}:
        return None
    parts = [re.escape(part) for part in mention.split()]
    return re.compile(r"(?<![\w/])" + r"\s+".join(parts) + r"(?![\w.-])", flags=re.IGNORECASE)


def build_entity_link_proposals(limit_per_source: int = 40) -> list[EntityLinkProposal]:
    entities = entity_pages()
    proposals: list[EntityLinkProposal] = []
    seen: set[tuple[str, str, str]] = set()
    counts_by_source: dict[str, int] = {}
    for source in latest_canonical_sources():
        if not source.exists():
            continue
        raw_text = strip_frontmatter(read_text(source))
        source_key = source.relative_to(ROOT).as_posix()
        for entity in entities:
            mentions = (entity.title, *entity.aliases)
            for mention in mentions:
                pattern = mention_pattern(mention)
                if not pattern:
                    continue
                for match in pattern.finditer(raw_text):
                    if raw_text[max(0, match.start() - 2):match.start()] == "[[":
                        continue
                    key = (source_key, entity.path, match.group(0).lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    proposals.append(
                        EntityLinkProposal(
                            source=source_key,
                            entity=entity.title,
                            entity_path=entity.path,
                            kind=entity.kind,
                            mention=match.group(0),
                            context=context_excerpt(raw_text, match.start(), match.end()),
                            status="needs-verification",
                        )
                    )
                    counts_by_source[source_key] = counts_by_source.get(source_key, 0) + 1
                    break
            if counts_by_source.get(source_key, 0) >= limit_per_source:
                break
    proposals.sort(key=lambda p: (p.source, p.kind, p.entity.lower(), p.mention.lower()))
    return proposals


def article_kind(path: Path) -> str:
    return ENTITY_DIRS.get(path.parent.name, path.parent.name.rstrip("s").title())


def article_title(path: Path, text: str) -> str:
    frontmatter = parse_frontmatter(text)
    title = str(frontmatter.get("title") or "").strip()
    return title or path.stem


def article_aliases(text: str) -> list[str]:
    frontmatter = parse_frontmatter(text)
    raw = frontmatter.get("aliases") or []
    return [item for item in raw if isinstance(item, str) and item.strip()]


def article_tags(text: str) -> tuple[str, ...]:
    frontmatter = parse_frontmatter(text)
    raw = frontmatter.get("tags") or []
    tags = [normalize_space(item) for item in raw if isinstance(item, str) and item.strip()]
    return tuple(dict.fromkeys(tags))


def count_wikilinks(text: str) -> int:
    return len(re.findall(r"\[\[[^\]]+\]\]", text))


def readable_tag(tag: str) -> str:
    if "/" in tag:
        _namespace, value = tag.split("/", 1)
        return value.replace("-", " ")
    return tag.replace("-", " ")


def article_queue_queries(title: str, kind: str, aliases: list[str], tags: tuple[str, ...]) -> tuple[str, ...]:
    candidates = [
        title,
        f"{title} {kind}",
        f"{title} Arden Vul",
        f"{title} session recap",
        f"{title} Discord summary",
    ]
    for alias in aliases[:3]:
        candidates.extend([alias, f"{alias} {kind}"])
    identity_tags = [
        tag for tag in tags
        if "/" in tag and not tag.endswith("/unknown")
    ][:6]
    for tag in identity_tags:
        candidates.append(f"{title} {readable_tag(tag)}")
    if identity_tags:
        candidates.append(f"{title} {' '.join(readable_tag(tag) for tag in identity_tags[:3])}")
    queries: list[str] = []
    seen: set[str] = set()
    for query in candidates:
        query = normalize_space(query)
        if not query or query.lower() in seen:
            continue
        seen.add(query.lower())
        queries.append(query)
    return tuple(queries)


def score_article(path: Path, text: str) -> tuple[int, tuple[str, ...]]:
    body = strip_frontmatter(text)
    line_count = len([line for line in body.splitlines() if line.strip()])
    word_count = len(re.findall(r"\b\w+\b", body))
    links = count_wikilinks(body)
    lower = body.lower()
    score = 0
    reasons: list[str] = []
    if line_count <= 12:
        score += 35
        reasons.append(f"very short body ({line_count} nonblank lines)")
    elif line_count <= 24:
        score += 20
        reasons.append(f"short body ({line_count} nonblank lines)")
    if word_count <= 120:
        score += 20
        reasons.append(f"low word count ({word_count} words)")
    if re.search(r"\b(tbd|todo|placeholder)\b", lower):
        score += 30
        reasons.append("contains TBD/TODO/placeholder text")
    if re.search(r"\bunknown\b", lower):
        score += 10
        reasons.append("contains unknown markers")
    if links == 0:
        score += 15
        reasons.append("has no wikilinks")
    elif links <= 2:
        score += 8
        reasons.append(f"few wikilinks ({links})")
    if not re.search(r"(?m)^##\s+(source|sources|appears in|sessions?)\b", body, flags=re.I):
        score += 12
        reasons.append("missing explicit source/session section")
    if not re.search(r"(?m)^##\s+(summary|overview|description)\b", body, flags=re.I):
        score += 8
        reasons.append("missing summary/overview section")
    if path.parent.name == "items" and re.search(r"\bunknown\b|\btbd\b", lower):
        score += 5
        reasons.append("item has unresolved function or identity")
    return score, tuple(reasons)


def build_article_queue(limit: int = 30) -> list[ArticleQueueItem]:
    items: list[ArticleQueueItem] = []
    for folder in ENTITY_DIRS:
        root = VAULT / folder
        if not root.exists():
            continue
        for path in sorted(root.glob("*.md")):
            if path.stem.lower() in {"index", "readme"}:
                continue
            text = read_text(path)
            score, reasons = score_article(path, text)
            if score <= 0:
                continue
            title = article_title(path, text)
            aliases = article_aliases(text)
            tags = article_tags(text)
            items.append(
                ArticleQueueItem(
                    path=path.relative_to(ROOT).as_posix(),
                    title=title,
                    kind=article_kind(path),
                    tags=tags,
                    score=score,
                    reasons=reasons,
                    queries=article_queue_queries(title, article_kind(path), aliases, tags),
                )
            )
    items.sort(key=lambda item: (-item.score, item.kind, item.title.lower(), item.path))
    return items[:limit]


def write_article_queue_report(items: list[ArticleQueueItem]) -> None:
    run_dir = AUTOMATION_DIR / "proposals"
    write_json(run_dir / "article_improvement_queue.json", [asdict(item) for item in items])
    lines = [
        "# Article Improvement Queue",
        "",
        "Deterministic queue of promoted entity pages that need source-grounded improvement.",
        "Use the listed queries for private RAG retrieval, then require source evidence before any article edit.",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Queued articles: {len(items)}",
        "",
        "| Score | Article | Kind | Tags | Reasons | RAG Queries |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for item in items:
        link = f"[[{wikilink_target_from_repo_path(item.path)}|{item.title}]]"
        tags = ", ".join(f"`{tag}`" for tag in item.tags).replace("|", "\\|")
        reasons = "; ".join(item.reasons).replace("|", "\\|")
        queries = "<br>".join(item.queries).replace("|", "\\|")
        lines.append(f"| {item.score} | {link} | {item.kind} | {tags} | {reasons} | {queries} |")
    (run_dir / "article_improvement_queue.md").write_text("\n".join(lines), encoding="utf-8")


def media_kind(path: Path, title: str, tags: tuple[str, ...]) -> str:
    lowered = " ".join((path.stem, title, " ".join(tags))).lower()
    if "map" in lowered or "cartograph" in lowered:
        return "Map"
    if "crystal" in lowered:
        return "Data Crystal"
    if "library" in lowered or "bookstore" in lowered or "archive" in lowered:
        return "Repository"
    if "scroll" in lowered:
        return "Scroll"
    if "journal" in lowered:
        return "Journal"
    if "catalog" in lowered:
        return "Catalog"
    return "Written Source"


def is_media_page(path: Path, text: str) -> bool:
    title = article_title(path, text)
    tags = set(article_tags(text))
    if tags & MEDIA_TAGS:
        return True
    if MEDIA_TITLE_PATTERNS.search(title) or MEDIA_TITLE_PATTERNS.search(path.stem):
        return True
    if path.parent.name == "lore" and MEDIA_TITLE_PATTERNS.search(strip_frontmatter(text)[:500]):
        return True
    return False


def score_media_page(path: Path, text: str) -> tuple[int, tuple[str, ...]]:
    body = strip_frontmatter(text)
    lower = body.lower()
    score = 0
    reasons: list[str] = []
    if re.search(r"\b(todo|tbd|unknown|untranslated|partial|unlinked|candidate merge|duplicate)\b", lower):
        score += 30
        reasons.append("contains unresolved media/catalog markers")
    if not re.search(r"(?m)^##\s+(source|sources|sessions?|found in|discord insights)\b", body, flags=re.I):
        score += 25
        reasons.append("missing explicit source/session provenance")
    if not re.search(r"(?m)^##\s+(summary|contents|known contents|reading status|translation status|discoveries)\b", body, flags=re.I):
        score += 20
        reasons.append("missing contents or reading/translation status section")
    if "data crystal" in lower and "transcription" not in lower and "contents" not in lower:
        score += 15
        reasons.append("data crystal lacks captured contents")
    if "map" in lower and "image" not in lower and "![" not in body:
        score += 10
        reasons.append("map lacks linked image/artifact reference")
    if len([line for line in body.splitlines() if line.strip()]) <= 12:
        score += 10
        reasons.append("short media page")
    return score, tuple(reasons)


def media_queue_queries(title: str, kind: str, tags: tuple[str, ...]) -> tuple[str, ...]:
    candidates = [
        title,
        f"{title} {kind}",
        f"{title} downtime reading",
        f"{title} read contents",
        f"{title} Arden Vul",
        f"{title} Discord summary",
    ]
    for tag in tags[:6]:
        if tag in {"catalog", "written-sources", "media"}:
            continue
        candidates.append(f"{title} {readable_tag(tag)}")
    queries: list[str] = []
    seen: set[str] = set()
    for query in candidates:
        query = normalize_space(query)
        if not query or query.lower() in seen:
            continue
        seen.add(query.lower())
        queries.append(query)
    return tuple(queries)


def build_media_queue(limit: int = 30) -> list[MediaQueueItem]:
    items: list[MediaQueueItem] = []
    for folder in MEDIA_DIRS:
        root = VAULT / folder
        if not root.exists():
            continue
        for path in sorted(root.glob("*.md")):
            if path.stem.lower() in {"index", "readme"}:
                continue
            text = read_text(path)
            if not is_media_page(path, text):
                continue
            score, reasons = score_media_page(path, text)
            if score <= 0:
                continue
            title = article_title(path, text)
            tags = article_tags(text)
            kind = media_kind(path, title, tags)
            items.append(
                MediaQueueItem(
                    path=path.relative_to(ROOT).as_posix(),
                    title=title,
                    kind=kind,
                    tags=tags,
                    score=score,
                    reasons=reasons,
                    queries=media_queue_queries(title, kind, tags),
                )
            )
    items.sort(key=lambda item: (-item.score, item.kind, item.title.lower(), item.path))
    return items[:limit]


def write_media_queue_report(items: list[MediaQueueItem]) -> None:
    run_dir = AUTOMATION_DIR / "proposals"
    write_json(run_dir / "media_improvement_queue.json", [asdict(item) for item in items])
    lines = [
        "# Media Improvement Queue",
        "",
        "Review-first queue for books, scrolls, maps, data crystals, libraries, and catalog pages.",
        "Use this queue to turn downtime reading into sourced library/media updates without importing raw chat.",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Queued media pages: {len(items)}",
        "",
        "| Score | Page | Kind | Tags | Reasons | RAG Queries |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for item in items:
        link = f"[[{wikilink_target_from_repo_path(item.path)}|{item.title}]]"
        tags = ", ".join(f"`{tag}`" for tag in item.tags).replace("|", "\\|")
        reasons = "; ".join(item.reasons).replace("|", "\\|")
        queries = "<br>".join(item.queries).replace("|", "\\|")
        lines.append(f"| {item.score} | {link} | {item.kind} | {tags} | {reasons} | {queries} |")
    (run_dir / "media_improvement_queue.md").write_text("\n".join(lines), encoding="utf-8")


def write_entity_link_proposal_report(proposals: list[EntityLinkProposal]) -> None:
    run_dir = AUTOMATION_DIR / "proposals"
    write_json(run_dir / "entity_link_proposals.json", [asdict(p) for p in proposals])
    lines = [
        "# Entity Link Proposals",
        "",
        "Review-first report for linking already-promoted entity pages from canonical sources.",
        "Every proposal still requires source-grounded verification before automatic page edits are allowed.",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Proposal count: {len(proposals)}",
        "",
    ]
    by_source: dict[str, list[EntityLinkProposal]] = {}
    for proposal in proposals:
        by_source.setdefault(proposal.source, []).append(proposal)
    for source, items in by_source.items():
        lines.extend([f"## {source}", ""])
        lines.append("| Entity | Kind | Mention | Status | Context |")
        lines.append("| --- | --- | --- | --- | --- |")
        for item in items:
            entity_link = f"[[{item.entity_path}|{item.entity}]]"
            lines.append(f"| {entity_link} | {item.kind} | {item.mention} | {item.status} | {item.context} |")
        lines.append("")
    (run_dir / "entity_link_proposals.md").write_text("\n".join(lines), encoding="utf-8")


def campaign_context() -> str:
    if not CAMPAIGN_CONTEXT_PATH.exists():
        return ""
    return CAMPAIGN_CONTEXT_PATH.read_text(encoding="utf-8", errors="ignore").strip()


def entity_page_context(entity_path: str, max_chars: int = 1800) -> str:
    path = ROOT / entity_path
    if not path.exists() or not path.is_relative_to(VAULT):
        return ""
    text = strip_frontmatter(read_text(path))
    return normalize_space(text[:max_chars])


def source_context_for_proposal(proposal: EntityLinkProposal) -> str:
    path = ROOT / proposal.source
    if not path.exists() or not path.is_relative_to(VAULT):
        return proposal.context
    text = strip_frontmatter(read_text(path))
    pattern = mention_pattern(proposal.mention)
    if not pattern:
        return proposal.context
    for match in pattern.finditer(text):
        if in_existing_wikilink(text, match.start()):
            continue
        return context_window(text, match.start(), match.end())
    return proposal.context


def verification_prompt(proposal: EntityLinkProposal) -> str:
    return "\n".join(
        [
            "Classify whether the mention refers to the proposed existing entity.",
            "Use the campaign context, entity context, and source window together.",
            "",
            "Allowed statuses: supported, contradicted, ambiguous, not_found.",
            "Return JSON with keys: status, rationale, evidence.",
            "The evidence must be a short quote from the source window.",
            "",
            "CAMPAIGN CONTEXT:",
            campaign_context(),
            "",
            "PROPOSED ENTITY:",
            f"Name: {proposal.entity}",
            f"Kind: {proposal.kind}",
            f"Path: {proposal.entity_path}",
            "",
            "ENTITY PAGE CONTEXT:",
            entity_page_context(proposal.entity_path),
            "",
            "SOURCE WINDOW:",
            f"Source: {proposal.source}",
            f"Mention: {proposal.mention}",
            source_context_for_proposal(proposal),
        ]
    )


def llm_chat_json(prompt: str, timeout: int = 90) -> dict:
    sources = load_local_sources()
    base_url = sources.get("llm_base_url")
    model = sources.get("llm_model")
    if not base_url or not model:
        raise RuntimeError("LLM verifier is not configured")
    base = str(base_url).rstrip("/")
    url = base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You verify Obsidian vault automation proposals. "
                    "Use only the provided context. Return strict JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    choice = body["choices"][0]
    content = choice["message"].get("content") or ""
    match = re.search(r"\{.*\}", content, flags=re.S)
    if not match:
        finish_reason = choice.get("finish_reason", "unknown")
        raise RuntimeError(f"LLM verifier did not return JSON; finish_reason={finish_reason}; content={content[:200]}")
    return json.loads(match.group(0))


def verify_entity_link_proposals(limit: int = 25) -> list[dict]:
    proposals_path = AUTOMATION_DIR / "proposals" / "entity_link_proposals.json"
    if proposals_path.exists():
        raw = json.loads(proposals_path.read_text(encoding="utf-8"))
        proposals = [EntityLinkProposal(**item) for item in raw]
    else:
        proposals = build_entity_link_proposals(limit_per_source=20)
        write_entity_link_proposal_report(proposals)
    verified: list[dict] = []
    for proposal in proposals[:limit]:
        prompt = verification_prompt(proposal)
        result = llm_chat_json(prompt)
        status = str(result.get("status", "ambiguous")).lower()
        if status not in {"supported", "contradicted", "ambiguous", "not_found"}:
            status = "ambiguous"
        verified.append(
            {
                **asdict(proposal),
                "status": status,
                "verifier_rationale": str(result.get("rationale", "")),
                "verifier_evidence": str(result.get("evidence", "")),
            }
        )
    run_dir = AUTOMATION_DIR / "proposals"
    write_json(run_dir / "entity_link_verifications.json", verified)
    lines = [
        "# Entity Link Verifications",
        "",
        "LLM verifier results for review-only entity link proposals.",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Verified count: {len(verified)}",
        "",
        "| Entity | Mention | Status | Evidence | Rationale |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in verified:
        entity_link = f"[[{item['entity_path']}|{item['entity']}]]"
        lines.append(
            f"| {entity_link} | {item['mention']} | {item['status']} | "
            f"{normalize_space(item['verifier_evidence']).replace('|', '\\|')} | "
            f"{normalize_space(item['verifier_rationale']).replace('|', '\\|')} |"
        )
    (run_dir / "entity_link_verifications.md").write_text("\n".join(lines), encoding="utf-8")
    return verified


def wikilink_target_from_repo_path(path: str) -> str:
    if path.startswith("vault/"):
        return path.removeprefix("vault/")
    return path


def in_existing_wikilink(text: str, index: int) -> bool:
    before_open = text.rfind("[[", 0, index)
    before_close = text.rfind("]]", 0, index)
    return before_open > before_close


def link_first_unlinked_mention(text: str, mention: str, entity_path: str) -> tuple[str, bool]:
    pattern = mention_pattern(mention)
    if not pattern:
        return text, False
    target = wikilink_target_from_repo_path(entity_path)
    for match in pattern.finditer(text):
        if in_existing_wikilink(text, match.start()):
            continue
        link = f"[[{target}|{match.group(0)}]]"
        return text[: match.start()] + link + text[match.end():], True
    return text, False


def apply_verified_entity_links(apply: bool, limit: int | None = None) -> dict:
    verifications_path = AUTOMATION_DIR / "proposals" / "entity_link_verifications.json"
    if not verifications_path.exists():
        return {"ok": False, "error": "missing_verifications"}
    verifications = json.loads(verifications_path.read_text(encoding="utf-8"))
    changes: list[str] = []
    applied = 0
    for item in verifications:
        if limit is not None and applied >= limit:
            break
        if item.get("status") != "supported":
            continue
        source = ROOT / item["source"]
        if not source.is_relative_to(VAULT) or not source.exists():
            continue
        text = read_text(source)
        updated, changed = link_first_unlinked_mention(text, item["mention"], item["entity_path"])
        if not changed:
            continue
        changes.append(f"link {item['mention']} -> {item['entity_path']} in {item['source']}")
        applied += 1
        if apply:
            source.write_text(updated, encoding="utf-8")
    return {
        "ok": True,
        "mode": "apply" if apply else "dry-run",
        "change_count": len(changes),
        "changes": changes,
    }


def paths_with_auto_nav(paths: Iterable[Path]) -> set[Path]:
    out: set[Path] = set()
    for path in paths:
        if path.exists() and "<!-- BEGIN AUTO NAV -->" in read_text(path):
            out.add(path)
    return out


def planned_discord_paths(existing: list[Path], created: set[Path]) -> list[Path]:
    return sorted(set(existing) | created)


def planned_session_paths(existing: list[Path], created: set[Path]) -> list[Path]:
    return sorted(set(existing) | created, key=lambda p: session_sort_key(re.match(r"Session\s+(\d+[a-z]?)", p.stem, re.I).group(1)) if re.match(r"Session\s+(\d+[a-z]?)", p.stem, re.I) else (10_000, p.name))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def build_source_manifest(feed_url: str = BLOG_FEED_URL) -> dict:
    records = discover_sources()
    blog_posts = fetch_blog_posts(feed_url)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo": str(ROOT),
        "vault": str(VAULT),
        "source_count": len(records),
        "blog_post_count": len(blog_posts),
        "discord": discord_status(),
        "spreadsheet": configured_spreadsheet_snapshot(),
        "sources": [asdict(r) for r in records],
        "blog_posts": [asdict(r) for r in blog_posts],
    }


def import_low_risk(apply: bool, blog_feed: str = BLOG_FEED_URL) -> dict:
    validation = validate_state()
    if not validation["ok"]:
        return {"ok": False, "error": "validation_failed", "validation": validation}

    changes: list[str] = []
    existing_discord = all_discord_summary_paths()
    existing_sessions = all_session_paths()
    created_discord = import_discord_digests(apply, changes)
    created_sessions = import_blog_sessions(apply, changes, blog_feed)
    sanitize_discord_summary_sources(apply, changes)

    planned_discord = planned_discord_paths(existing_discord, created_discord)
    planned_sessions = planned_session_paths(existing_sessions, created_sessions)
    discord_nav_targets = adjacent_paths(planned_discord, created_discord) | paths_with_auto_nav(planned_discord)
    session_nav_targets = adjacent_paths(planned_sessions, created_sessions) | paths_with_auto_nav(planned_sessions)
    update_discord_navigation(apply, changes, discord_nav_targets)
    update_session_navigation(apply, changes, session_nav_targets)
    return {
        "ok": True,
        "mode": "apply" if apply else "dry-run",
        "change_count": len(changes),
        "changes": changes,
    }


def append_changelog(run_id: str, import_result: dict) -> None:
    changes = import_result.get("changes") or []
    if not changes:
        return
    if not CHANGELOG_PATH.exists():
        CHANGELOG_PATH.write_text(
            "# Automation Changelog\n\n"
            "Public log of deterministic vault automation changes. Entries avoid private local source paths.\n",
            encoding="utf-8",
        )
    lines = [
        "",
        f"## {datetime.now(CENTRAL).strftime('%Y-%m-%d %H:%M %Z')} - {run_id}",
        "",
    ]
    for change in changes:
        lines.append(f"- {change}")
    with CHANGELOG_PATH.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def cmd_discover(args: argparse.Namespace) -> int:
    payload = build_source_manifest(args.blog_feed)
    if args.write:
        write_json(AUTOMATION_DIR / "source_manifest.json", payload)
    summary_keys = ("timestamp", "repo", "vault", "source_count", "blog_post_count", "discord")
    print(json.dumps(payload if args.verbose else {k: payload[k] for k in summary_keys}, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    payload = validate_state()
    if args.write:
        write_json(AUTOMATION_DIR / "last_validation.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 2


def cmd_status(_: argparse.Namespace) -> int:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_validation": validate_state(),
        "discord": discord_status(),
        "spreadsheet": configured_spreadsheet_snapshot(),
        "blog_latest": [asdict(post) for post in fetch_blog_posts()[-5:]],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["repo_validation"]["ok"] else 2


def cmd_propose(_: argparse.Namespace) -> int:
    print(
        json.dumps(
            {
                "ok": False,
                "error": "proposal_generation_not_implemented",
                "message": "Implement IAC/ACE/LCE proposal generation only after discover and validate are stable.",
            },
            indent=2,
        )
    )
    return 2


def cmd_propose_entity_links(args: argparse.Namespace) -> int:
    proposals = build_entity_link_proposals(args.limit_per_source)
    write_entity_link_proposal_report(proposals)
    payload = {
        "ok": True,
        "proposal_count": len(proposals),
        "json": str(AUTOMATION_DIR / "proposals" / "entity_link_proposals.json"),
        "markdown": str(AUTOMATION_DIR / "proposals" / "entity_link_proposals.md"),
        "note": "Review-only. No vault pages were edited.",
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_verify_entity_links(args: argparse.Namespace) -> int:
    try:
        verified = verify_entity_link_proposals(args.limit)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    counts: dict[str, int] = {}
    for item in verified:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    payload = {
        "ok": True,
        "verified_count": len(verified),
        "status_counts": counts,
        "json": str(AUTOMATION_DIR / "proposals" / "entity_link_verifications.json"),
        "markdown": str(AUTOMATION_DIR / "proposals" / "entity_link_verifications.md"),
        "note": "Review-only. No vault pages were edited.",
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_apply_verified_entity_links(args: argparse.Namespace) -> int:
    result = apply_verified_entity_links(args.apply, args.limit)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


def cmd_build_article_queue(args: argparse.Namespace) -> int:
    items = build_article_queue(args.limit)
    write_article_queue_report(items)
    payload = {
        "ok": True,
        "queued_count": len(items),
        "json": str(AUTOMATION_DIR / "proposals" / "article_improvement_queue.json"),
        "markdown": str(AUTOMATION_DIR / "proposals" / "article_improvement_queue.md"),
        "note": "Review/research queue only. No vault pages were edited.",
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_build_media_queue(args: argparse.Namespace) -> int:
    items = build_media_queue(args.limit)
    write_media_queue_report(items)
    payload = {
        "ok": True,
        "queued_count": len(items),
        "json": str(AUTOMATION_DIR / "proposals" / "media_improvement_queue.json"),
        "markdown": str(AUTOMATION_DIR / "proposals" / "media_improvement_queue.md"),
        "note": "Review/research queue only. No vault pages were edited.",
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_ingest_spreadsheet(args: argparse.Namespace) -> int:
    sources = load_local_sources()
    url = args.url or sources.get("group_spreadsheet_url")
    gid = args.gid or sources.get("group_spreadsheet_gid")
    if not url:
        print(json.dumps({"ok": False, "error": "spreadsheet_url_not_configured"}, indent=2))
        return 2
    try:
        snapshot, rows = spreadsheet_snapshot(str(url), gid)
        if args.write:
            write_spreadsheet_snapshot_report(snapshot, rows)
            if args.classify:
                write_spreadsheet_classification_report(snapshot, rows)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    payload = {
        "ok": True,
        **asdict(snapshot),
        "written": bool(args.write),
        "json": str(AUTOMATION_DIR / "sources" / "group_spreadsheet_snapshot.json") if args.write else None,
        "markdown": str(AUTOMATION_DIR / "sources" / "group_spreadsheet_snapshot.md") if args.write else None,
        "classification_json": str(AUTOMATION_DIR / "sources" / "group_spreadsheet_classification.json") if args.write and args.classify else None,
        "classification_markdown": str(AUTOMATION_DIR / "sources" / "group_spreadsheet_classification.md") if args.write and args.classify else None,
        "note": "Snapshot/report only. No vault pages were edited.",
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_classify_spreadsheet(args: argparse.Namespace) -> int:
    sources = load_local_sources()
    url = args.url or sources.get("group_spreadsheet_url")
    gid = args.gid or sources.get("group_spreadsheet_gid")
    if not url:
        print(json.dumps({"ok": False, "error": "spreadsheet_url_not_configured"}, indent=2))
        return 2
    try:
        snapshot, rows = spreadsheet_snapshot(str(url), gid)
        classifications = write_spreadsheet_classification_report(snapshot, rows) if args.write else classify_spreadsheet_rows(rows)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    counts: dict[str, int] = {}
    for item in classifications:
        counts[item.category] = counts.get(item.category, 0) + 1
    payload = {
        "ok": True,
        "source_id": snapshot.source_id,
        "sha256": snapshot.sha256,
        "classification_count": len(classifications),
        "category_counts": counts,
        "written": bool(args.write),
        "json": str(AUTOMATION_DIR / "sources" / "group_spreadsheet_classification.json") if args.write else None,
        "markdown": str(AUTOMATION_DIR / "sources" / "group_spreadsheet_classification.md") if args.write else None,
        "note": "Classification/report only. No vault pages were edited.",
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_reconcile_loot(_: argparse.Namespace) -> int:
    payload = write_loot_reconciliation_report()
    result = {
        "ok": True,
        "spreadsheet_loot_row_count": payload["spreadsheet_loot_row_count"],
        "discord_disposition_evidence_count": payload["discord_disposition_evidence_count"],
        "json": str(AUTOMATION_DIR / "proposals" / "loot_reconciliation.json"),
        "markdown": str(AUTOMATION_DIR / "proposals" / "loot_reconciliation.md"),
        "note": "Review-only. No vault pages were edited.",
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    payload = import_low_risk(args.apply, args.blog_feed)
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 2


def cmd_run_low_risk(args: argparse.Namespace) -> int:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = AUTOMATION_DIR / "runs" / run_id
    manifest = build_source_manifest(args.blog_feed)
    before = validate_state()
    import_result = import_low_risk(True, args.blog_feed) if before["ok"] else {
        "ok": False,
        "error": "pre_validation_failed",
    }
    proposals: list[EntityLinkProposal] = []
    verification_result: dict = {"enabled": False}
    link_apply_result: dict = {"enabled": False}
    article_queue: list[ArticleQueueItem] = []
    media_queue: list[MediaQueueItem] = []
    if before["ok"]:
        proposals = build_entity_link_proposals(limit_per_source=20)
        write_entity_link_proposal_report(proposals)
        sources = load_local_sources()
        article_queue = build_article_queue(int(sources.get("article_queue_limit", 30)))
        write_article_queue_report(article_queue)
        media_queue = build_media_queue(int(sources.get("media_queue_limit", 30)))
        write_media_queue_report(media_queue)
        spreadsheet_result = configured_spreadsheet_snapshot()
        if spreadsheet_result.get("ok"):
            try:
                snapshot, rows = spreadsheet_snapshot(str(sources.get("group_spreadsheet_url")), sources.get("group_spreadsheet_gid"))
                write_spreadsheet_snapshot_report(snapshot, rows)
                classifications = write_spreadsheet_classification_report(snapshot, rows)
                spreadsheet_result["classification_count"] = len(classifications)
            except Exception as exc:
                spreadsheet_result = {"configured": True, "ok": False, "error": str(exc)}
        loot_reconciliation = write_loot_reconciliation_report()
        verify_limit = sources.get("entity_link_verify_limit", 0)
        apply_limit = sources.get("entity_link_apply_limit", 0)
        if verify_limit and sources.get("llm_base_url") and sources.get("llm_model"):
            try:
                verified = verify_entity_link_proposals(int(verify_limit))
                counts: dict[str, int] = {}
                for item in verified:
                    status = str(item.get("status", "unknown"))
                    counts[status] = counts.get(status, 0) + 1
                verification_result = {
                    "enabled": True,
                    "verified_count": len(verified),
                    "status_counts": counts,
                    "markdown": str(AUTOMATION_DIR / "proposals" / "entity_link_verifications.md"),
                }
                if apply_limit:
                    link_apply_result = {
                        "enabled": True,
                        **apply_verified_entity_links(True, int(apply_limit)),
                    }
            except Exception as exc:
                verification_result = {"enabled": True, "ok": False, "error": str(exc)}
    after = validate_state()
    payload = {
        "ok": before["ok"] and import_result["ok"] and after["ok"],
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "scheduled-low-risk",
        "manifest": {
            "source_count": manifest["source_count"],
            "blog_post_count": manifest["blog_post_count"],
            "discord": manifest["discord"],
            "spreadsheet": manifest["spreadsheet"],
        },
        "before_validation": before,
        "import": import_result,
        "entity_link_proposals": {
            "count": len(proposals),
            "markdown": str(AUTOMATION_DIR / "proposals" / "entity_link_proposals.md"),
        },
        "entity_link_verification": verification_result,
        "entity_link_apply": link_apply_result,
        "article_improvement_queue": {
            "count": len(article_queue),
            "markdown": str(AUTOMATION_DIR / "proposals" / "article_improvement_queue.md"),
        },
        "media_improvement_queue": {
            "count": len(media_queue),
            "markdown": str(AUTOMATION_DIR / "proposals" / "media_improvement_queue.md"),
        },
        "loot_reconciliation": {
            "spreadsheet_loot_row_count": loot_reconciliation["spreadsheet_loot_row_count"] if before["ok"] else 0,
            "discord_disposition_evidence_count": loot_reconciliation["discord_disposition_evidence_count"] if before["ok"] else 0,
            "markdown": str(AUTOMATION_DIR / "proposals" / "loot_reconciliation.md"),
        },
        "after_validation": after,
    }
    write_json(AUTOMATION_DIR / "source_manifest.json", manifest)
    write_json(AUTOMATION_DIR / "last_validation.json", after)
    write_json(run_dir / "run.json", payload)
    if payload["ok"]:
        append_changelog(run_id, import_result)
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Conservative Arden Vault automation harness")
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="Discover source files and optionally write a manifest")
    discover.add_argument("--write", action="store_true", help="Write data/automation/source_manifest.json")
    discover.add_argument("--verbose", action="store_true", help="Print every discovered source")
    discover.add_argument("--blog-feed", default=BLOG_FEED_URL, help="Blogger JSON feed URL")
    discover.set_defaults(func=cmd_discover)

    validate = sub.add_parser("validate", help="Run guardrail checks against the current repo")
    validate.add_argument("--write", action="store_true", help="Write data/automation/last_validation.json")
    validate.set_defaults(func=cmd_validate)

    propose = sub.add_parser("propose", help="Reserved for future dry-run proposal generation")
    propose.set_defaults(func=cmd_propose)

    entity_links = sub.add_parser("propose-entity-links", help="Write review-only entity link proposals")
    entity_links.add_argument("--limit-per-source", type=int, default=40, help="Maximum proposals per source file")
    entity_links.set_defaults(func=cmd_propose_entity_links)

    verify_links = sub.add_parser("verify-entity-links", help="LLM-verify review-only entity link proposals")
    verify_links.add_argument("--limit", type=int, default=25, help="Maximum proposals to verify")
    verify_links.set_defaults(func=cmd_verify_entity_links)

    apply_links = sub.add_parser("apply-verified-entity-links", help="Apply supported verified entity links")
    apply_links.add_argument("--apply", action="store_true", help="Write changes. Omit for dry-run.")
    apply_links.add_argument("--limit", type=int, default=None, help="Maximum supported links to apply")
    apply_links.set_defaults(func=cmd_apply_verified_entity_links)

    article_queue = sub.add_parser("build-article-queue", help="Write a review-only article improvement queue")
    article_queue.add_argument("--limit", type=int, default=30, help="Maximum articles to queue")
    article_queue.set_defaults(func=cmd_build_article_queue)

    media_queue = sub.add_parser("build-media-queue", help="Write a review-only media/library improvement queue")
    media_queue.add_argument("--limit", type=int, default=30, help="Maximum media pages to queue")
    media_queue.set_defaults(func=cmd_build_media_queue)

    spreadsheet = sub.add_parser("ingest-spreadsheet", help="Snapshot a configured shared Google Sheet as a structured source")
    spreadsheet.add_argument("--url", help="Google Sheets URL. Omit to use ignored local config.")
    spreadsheet.add_argument("--gid", help="Worksheet gid. Omit to use URL/config/default.")
    spreadsheet.add_argument("--write", action="store_true", help="Write ignored snapshot artifacts under data/automation/sources/")
    spreadsheet.add_argument("--classify", action="store_true", help="Also write row classification artifacts")
    spreadsheet.set_defaults(func=cmd_ingest_spreadsheet)

    classify_sheet = sub.add_parser("classify-spreadsheet", help="Classify configured spreadsheet rows into proposal lanes")
    classify_sheet.add_argument("--url", help="Google Sheets URL. Omit to use ignored local config.")
    classify_sheet.add_argument("--gid", help="Worksheet gid. Omit to use URL/config/default.")
    classify_sheet.add_argument("--write", action="store_true", help="Write ignored classification artifacts under data/automation/sources/")
    classify_sheet.set_defaults(func=cmd_classify_spreadsheet)

    loot_reconcile = sub.add_parser("reconcile-loot", help="Write a review-only loot inventory reconciliation report")
    loot_reconcile.set_defaults(func=cmd_reconcile_loot)

    status = sub.add_parser("status", help="Summarize repo, Discord, and Blogspot source state")
    status.set_defaults(func=cmd_status)

    importer = sub.add_parser("import-low-risk", help="Import canonical Blogspot recaps and external Discord digests")
    importer.add_argument("--apply", action="store_true", help="Write changes. Omit for dry-run.")
    importer.add_argument("--blog-feed", default=BLOG_FEED_URL, help="Blogger JSON feed URL")
    importer.set_defaults(func=cmd_import)

    scheduled = sub.add_parser("run-low-risk", help="Scheduled low-risk vault maintenance entry point")
    scheduled.add_argument("--blog-feed", default=BLOG_FEED_URL, help="Blogger JSON feed URL")
    scheduled.set_defaults(func=cmd_run_low_risk)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
