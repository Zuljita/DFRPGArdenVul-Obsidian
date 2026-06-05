#!/usr/bin/env python3
"""
Conservative vault automation harness.

Most source discovery, validation, queueing, and application logic is
deterministic so scheduled runs stay bounded and auditable. Research lanes may
call the configured local LLM to propose and verify small sourced changes before
the deterministic applicator mutates vault Markdown.
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
import requests
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

import psycopg

try:
    import yaml  # type: ignore[import-not-found]
    YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    YAML_AVAILABLE = False


ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "vault"
AUTOMATION_DIR = ROOT / "data" / "automation"
LOCAL_SOURCES_CONFIG = ROOT / "config" / "local_sources.json"
CHANGELOG_PATH = AUTOMATION_DIR / "automation_changelog.md"
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
    "library": "Library Source",
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
    "library",
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
    source_excerpt: str = ""


@dataclass
class NewEntityCandidate:
    name: str
    kind: str
    canonical_target_dir: str
    mention_count: int
    sources: list[dict]
    rationale: str
    nearest_existing: str | None
    nearest_distance: float
    proposal_id: str = ""
    status: str = "needs-verification"


@dataclass
class ArticleEditProposal:
    article_path: str
    article_title: str
    article_kind: str
    article_score: int
    addition_type: str
    target_section: str
    proposed_text: str
    rationale: str
    sources: list[dict]
    status: str = "needs-verification"
    proposal_id: str = ""


@dataclass
class MetadataEditProposal:
    article_path: str
    article_title: str
    article_kind: str
    proposal_type: str
    value: str
    rationale: str
    sources: list[dict]
    status: str = "needs-verification"
    proposal_id: str = ""


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
        "rag_api_base_url": os.environ.get("ARDEN_RAG_API_BASE_URL") or config.get("rag_api_base_url", "http://127.0.0.1:8897"),
        "rag_api_key": os.environ.get("ARDEN_RAG_API_KEY") or config.get("rag_api_key"),
        "entity_link_verify_limit": int(config.get("entity_link_verify_limit", 0) or 0),
        "entity_link_apply_limit": int(config.get("entity_link_apply_limit", 0) or 0),
        "entity_link_catalog_refresh_sources": int(config.get("entity_link_catalog_refresh_sources", 1) or 1),
        "article_queue_limit": int(os.environ.get("ARDEN_ARTICLE_QUEUE_LIMIT") or config.get("article_queue_limit", 30) or 30),
        "media_queue_limit": int(os.environ.get("ARDEN_MEDIA_QUEUE_LIMIT") or config.get("media_queue_limit", 30) or 30),
        "media_edit_queue_top": int(config.get("media_edit_queue_top", 0) or 0),
        "vault_rag_embed_model": os.environ.get("ARDEN_VAULT_RAG_EMBED_MODEL") or config.get("vault_rag_embed_model", "bge-m3"),
        "vault_rag_embed_url": os.environ.get("ARDEN_VAULT_RAG_EMBED_URL") or config.get("vault_rag_embed_url", "http://127.0.0.1:11434/api/embeddings"),
        "article_edit_queue_top": int(config.get("article_edit_queue_top", 0) or 0),
        "article_edit_walk_step": int(config.get("article_edit_walk_step", 0) or 0),
        "article_edit_verify_limit": int(config.get("article_edit_verify_limit", 0) or 0),
        "article_edit_apply_limit": int(config.get("article_edit_apply_limit", 0) or 0),
        "metadata_edit_enabled": bool(config.get("metadata_edit_enabled", False)),
        "metadata_edit_queue_top": int(config.get("metadata_edit_queue_top", 5) or 5),
        "metadata_edit_verify_limit": int(config.get("metadata_edit_verify_limit", 0) or 0),
        "metadata_edit_apply_limit": int(config.get("metadata_edit_apply_limit", 0) or 0),
        "action_items_enabled": bool(config.get("action_items_enabled", False)),
        "action_items_apply": bool(config.get("action_items_apply", False)),
        "action_items_refresh_hours": int(config.get("action_items_refresh_hours", 24) or 24),
        "action_items_latest_sessions": int(config.get("action_items_latest_sessions", 8) or 8),
        "action_items_latest_discord_weeks": int(config.get("action_items_latest_discord_weeks", 4) or 4),
        "action_items_max_items": int(config.get("action_items_max_items", 200) or 200),
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
    # Match singular "Session 52a" or plural "Sessions 52b and 53" / "Sessions 8b and 9"
    plural = re.search(r"\bSessions\s+(\d+[a-z]?(?:\s+and\s+\d+[a-z]?)+)\b", title, re.IGNORECASE)
    if plural:
        return plural.group(1)
    singular = re.search(r"\bSession\s+(\d+[a-z]?)\b", title, re.IGNORECASE)
    return singular.group(1) if singular else None


def session_sort_key(session_id: str) -> tuple[int, str]:
    # Use the first numeric session in a compound id like "52b and 53" for sorting.
    match = re.match(r"(\d+)([a-z]?)", session_id)
    if not match:
        return (10_000, session_id)
    return (int(match.group(1)), match.group(2))


def session_display_title(title: str, session_id: str) -> str:
    # Strip the "DFRPG Arden Vul Session(s) <ids>:" prefix from the blog title.
    prefix_pat = r"^DFRPG\s+(?:Arden Vul\s+)?Sessions?\s+\S+(?:\s+and\s+\S+)*\s*:\s*"
    cleaned = re.sub(prefix_pat, "", title, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^Sessions?\s+\S+(?:\s+and\s+\S+)*\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
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


def import_discord_digests(apply: bool, changes: list[str], force_update: bool = False) -> set[Path]:
    """Import Discord digests into vault Discord Summary files.

    With force_update=True, existing summaries are overwritten when the source
    digest has changed (comparing body content, ignoring frontmatter).
    """
    created: set[Path] = set()
    for week_end, folder, digest in iter_external_digests():
        target = discord_summary_path_for_week_end(week_end)
        if target.exists() and not force_update:
            continue
        text = build_discord_summary_markdown(week_end, folder, digest)
        if target.exists():
            # Only update if the body (post-frontmatter) actually changed
            existing = read_text(target)
            existing_body = re.sub(r"^---\n.*?\n---\n", "", existing, flags=re.DOTALL).strip()
            new_body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()
            if existing_body == new_body:
                continue
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
        list_match = re.match(r"^\s*-\s+(.+)$", raw_line)
        if list_match and current_key:
            fields.setdefault(current_key, [])
            value = list_match.group(1).strip().strip("\"'")
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


PARTY_ARMORY_PATH = VAULT / "Party Armory.md"


def latest_canonical_sources(limit: int = 5) -> list[Path]:
    """Return canonical sources for entity proposal scanning.

    limit=0 means all sessions + all Discord summaries (full vault walk).
    """
    all_sessions = list_session_pages()
    all_summaries = all_discord_summary_paths()
    if limit <= 0:
        sessions = all_sessions
        summaries = all_summaries
    else:
        sessions = all_sessions[-limit:]
        summaries = all_summaries[-limit:]
    paths = [path for _sid, path in sessions] + summaries
    # Party Armory is ground-truth current inventory — always include it so items
    # the party currently holds but lack vault pages can be proposed.
    if PARTY_ARMORY_PATH.exists():
        paths.append(PARTY_ARMORY_PATH)
    return paths


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


def strip_frontmatter_only(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)


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


def entity_link_catalog(entities: list[EntityPage]) -> str:
    return "\n".join(
        f"{entity.kind} | {entity.path} | {entity.title} | aliases: {', '.join(entity.aliases) or '-'}"
        for entity in entities
    )


def entity_link_proposal_prompt(source_key: str, source_text: str, entities: list[EntityPage]) -> str:
    return (
        "Propose Obsidian wikilinks from one canonical Arden Vul campaign source to EXISTING vault entity pages.\n\n"
        "Use semantic judgment first. Do not perform naive substring matching. A surface word may be part of a "
        "different concept: for example, `Boots` inside `Boots of the North` is an item phrase and must not be "
        "linked to an NPC merely because an NPC page named Boots exists. Likewise, `Arden` inside `Arden Vul` "
        "must not be linked to an NPC unless the text actually refers to that person.\n\n"
        "Propose individual occurrences, not file-wide replacement rules. The same visible text can refer to different "
        "entities in different sentences. Return one entry per intended occurrence, with an exact source excerpt that "
        "uniquely identifies that occurrence.\n\n"
        "Only propose a link when:\n"
        "- the exact unlinked source phrase appears verbatim in SOURCE TEXT;\n"
        "- the phrase semantically refers to one specific page from EXISTING ENTITY CATALOG;\n"
        "- the catalog path is copied exactly; and\n"
        "- adding the link would improve navigation rather than link incidental words.\n\n"
        "Prefer named NPCs, PCs, locations, factions, and unique items. Skip generic nouns, partial-name matches, "
        "rules terms, ambiguous references, and phrases already written as wikilinks. Propose every useful high-confidence link.\n\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "links": [\n'
        "    {\n"
        '      "entity_path": "vault/npcs/Example.md",\n'
        '      "mention": "Exact source phrase",\n'
        '      "source_excerpt": "Exact unmodified sentence or short paragraph containing this occurrence",\n'
        '      "rationale": "One short sentence explaining why this phrase refers to that page."\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"SOURCE: {source_key}\n\n"
        "EXISTING ENTITY CATALOG:\n"
        f"{entity_link_catalog(entities)}\n\n"
        "SOURCE TEXT:\n"
        f"{source_text}"
    )


def llm_entity_link_proposals_for_source(
    source: Path,
    entities: list[EntityPage],
    limit_per_source: int | None,
) -> list[EntityLinkProposal]:
    source_key = source.relative_to(ROOT).as_posix()
    raw_text = strip_frontmatter_only(read_text(source))
    prompt = entity_link_proposal_prompt(source_key, raw_text, entities)
    try:
        response = llm_chat_json(prompt, timeout=180)
    except Exception:
        response = llm_chat_json(prompt + "\n\nIMPORTANT: Return syntactically valid strict JSON only.", timeout=180)
    raw_links = response.get("links") or []
    if not isinstance(raw_links, list):
        raise RuntimeError("LLM entity-link proposer returned non-list links")
    entities_by_path = {entity.path: entity for entity in entities}
    proposals: list[EntityLinkProposal] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw_links:
        if not isinstance(item, dict):
            continue
        entity_path = str(item.get("entity_path", "")).strip()
        mention = normalize_space(str(item.get("mention", "")))
        source_excerpt = str(item.get("source_excerpt", "")).strip()
        entity = entities_by_path.get(entity_path)
        pattern = mention_pattern(mention)
        if not entity or not pattern or not source_excerpt or raw_text.count(source_excerpt) != 1:
            continue
        excerpt_start = raw_text.index(source_excerpt)
        excerpt_matches = [
            candidate for candidate in pattern.finditer(source_excerpt)
            if not in_existing_wikilink(source_excerpt, candidate.start())
        ]
        if len(excerpt_matches) != 1:
            continue
        match = excerpt_matches[0]
        key = (entity_path, match.group(0).lower(), source_excerpt)
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
                context=context_excerpt(raw_text, excerpt_start + match.start(), excerpt_start + match.end()),
                status="needs-verification",
                source_excerpt=source_excerpt,
            )
        )
        if limit_per_source is not None and len(proposals) >= limit_per_source:
            break
    return proposals


def build_entity_link_proposals(limit_per_source: int | None = None) -> list[EntityLinkProposal]:
    entities = entity_pages()
    catalog_sha = hashlib.sha256(("occurrence-v1\n" + entity_link_catalog(entities)).encode("utf-8")).hexdigest()
    cache_path = AUTOMATION_DIR / "proposals" / "entity_link_proposal_cache.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    except Exception:
        cache = {}
    cached_sources = cache.get("sources")
    if not isinstance(cached_sources, dict):
        cached_sources = {}
    sources = [source for source in latest_canonical_sources() if source.exists()]
    refresh_state = cache.get("catalog_refresh")
    if not isinstance(refresh_state, dict) or refresh_state.get("target_sha") != catalog_sha:
        refresh_state = {
            "target_sha": catalog_sha,
            "pending_sources": [
                source.relative_to(ROOT).as_posix()
                for source in sources
            ] if cache.get("catalog_sha") != catalog_sha else [],
        }
    pending_refresh = [str(item) for item in refresh_state.get("pending_sources", [])]
    refresh_limit = max(1, int(load_local_sources().get("entity_link_catalog_refresh_sources", 1) or 1))
    dirty_sources = []
    for source in sources:
        source_key = source.relative_to(ROOT).as_posix()
        source_sha = hashlib.sha256(read_text(source).encode("utf-8")).hexdigest()
        cached = cached_sources.get(source_key) or {}
        if cached.get("sha256") != source_sha or not isinstance(cached.get("proposals"), list):
            dirty_sources.append(source_key)
    refresh_queue = list(dict.fromkeys(dirty_sources + pending_refresh))
    selected_refresh = set(refresh_queue[:refresh_limit])
    refreshed: set[str] = set()
    next_sources: dict[str, dict] = {}
    proposals: list[EntityLinkProposal] = []
    errors: list[dict[str, str]] = []
    for source in sources:
        source_key = source.relative_to(ROOT).as_posix()
        source_sha = hashlib.sha256(read_text(source).encode("utf-8")).hexdigest()
        cached = cached_sources.get(source_key) or {}
        raw_proposals: list[dict]
        cache_source = True
        if (
            source_key not in selected_refresh
            and cached.get("sha256") == source_sha
            and isinstance(cached.get("proposals"), list)
        ):
            raw_proposals = cached["proposals"]
        elif source_key not in selected_refresh:
            raw_proposals = []
            cache_source = False
            if cached:
                next_sources[source_key] = cached
        else:
            try:
                fresh = llm_entity_link_proposals_for_source(source, entities, limit_per_source)
                raw_proposals = [asdict(item) for item in fresh]
                refreshed.add(source_key)
            except Exception as exc:
                raw_proposals = []
                cache_source = False
                errors.append({"source": source_key, "error": str(exc)[:300]})
        if cache_source:
            next_sources[source_key] = {"sha256": source_sha, "proposals": raw_proposals}
        selected = raw_proposals if limit_per_source is None else raw_proposals[:limit_per_source]
        proposals.extend(EntityLinkProposal(**item) for item in selected)
    remaining_refresh = [source for source in pending_refresh if source not in refreshed]
    write_json(cache_path, {
        "catalog_sha": catalog_sha if not remaining_refresh else cache.get("catalog_sha"),
        "catalog_refresh": {
            "target_sha": catalog_sha,
            "pending_sources": remaining_refresh,
        },
        "sources": next_sources,
    })
    write_json(AUTOMATION_DIR / "proposals" / "entity_link_proposal_errors.json", errors)
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


def frontmatter_list(text: str, key: str) -> list[str]:
    raw = parse_frontmatter(text).get(key) or []
    if isinstance(raw, str):
        raw = [raw]
    return [normalize_space(item) for item in raw if isinstance(item, str) and item.strip()]


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


def build_article_queue_item(path: Path) -> ArticleQueueItem | None:
    """Build a queue item for one article path, regardless of score. Accepts either
    a relative repo path or an absolute one. Used for walk-cursor selections that
    may include strong articles outside the weakest-N queue."""
    abs_path = path if path.is_absolute() else (ROOT / path)
    if not abs_path.exists() or abs_path.stem.lower() in {"index", "readme"}:
        return None
    text = read_text(abs_path)
    score, reasons = score_article(abs_path, text)
    title = article_title(abs_path, text)
    aliases = article_aliases(text)
    tags = article_tags(text)
    return ArticleQueueItem(
        path=abs_path.relative_to(ROOT).as_posix(),
        title=title,
        kind=article_kind(abs_path),
        tags=tags,
        score=score,
        reasons=reasons,
        queries=article_queue_queries(title, article_kind(abs_path), aliases, tags),
    )


def build_article_queue(limit: int = 30) -> list[ArticleQueueItem]:
    items: list[ArticleQueueItem] = []
    for folder in ENTITY_DIRS:
        root = VAULT / folder
        if not root.exists():
            continue
        for path in sorted(root.glob("*.md")):
            item = build_article_queue_item(path)
            if item is None or item.score <= 0:
                continue
            items.append(item)
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
            article_item = build_article_queue_item(path)
            if article_item and curated_summary_literal_hits(article_item, max_hits=1):
                score += 100
                reasons = (*reasons, "curated Discord digest explicitly mentions work")
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
    text = strip_frontmatter_only(read_text(path))
    if proposal.source_excerpt and text.count(proposal.source_excerpt) == 1:
        start = text.index(proposal.source_excerpt)
        return context_window(text, start, start + len(proposal.source_excerpt))
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


def _parse_llm_json(content: str) -> dict:
    """Best-effort JSON parse for LLM output. Tries: raw, stripped of code fences,
    greedy {...} match, then bracket-counted slice. Raises if all fail."""
    if not content:
        raise ValueError("empty content")
    candidates: list[str] = [content]
    # Strip ```json ... ``` or ``` ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.S)
    if fence:
        candidates.append(fence.group(1))
    # Greedy first-{ ... last-} slice.
    first = content.find("{")
    last = content.rfind("}")
    if first != -1 and last > first:
        candidates.append(content[first:last + 1])
    # Bracket-counted slice starting at first {, ignoring brackets inside strings.
    if first != -1:
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i, ch in enumerate(content[first:], start=first):
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end > first:
            candidates.append(content[first:end + 1])
    last_err: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue
    if YAML_AVAILABLE:
        for cand in candidates:
            try:
                parsed = yaml.safe_load(cand)
                if isinstance(parsed, dict):
                    return parsed
            except Exception as exc:
                last_err = exc
                continue
    raise RuntimeError(f"could not parse LLM JSON: {last_err}; content head: {content[:200]!r}")


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
        "max_tokens": 16384,
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
    try:
        return _parse_llm_json(content)
    except Exception as exc:
        finish_reason = choice.get("finish_reason", "unknown")
        raise RuntimeError(f"LLM JSON parse failed; finish_reason={finish_reason}; err={exc}") from exc


def llm_chat_text(prompt: str, timeout: int = 90, system: str | None = None) -> str:
    """Like llm_chat_json but returns raw text instead of parsed JSON."""
    sources = load_local_sources()
    base_url = sources.get("llm_base_url")
    model = sources.get("llm_model")
    if not base_url or not model:
        raise RuntimeError("LLM is not configured")
    base = str(base_url).rstrip("/")
    url = base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 16384,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"].get("content") or ""


SCRATCH_PATH = ROOT / "SCRATCH.md"


def summarize_scratchpad() -> dict:
    if not SCRATCH_PATH.exists():
        return {"ok": False, "error": "SCRATCH.md not found"}
    text = SCRATCH_PATH.read_text(encoding="utf-8")
    if len(text) < 300:
        return {"ok": True, "skipped": True, "reason": f"only {len(text)} chars — nothing to condense"}
    prompt = f"""Condense this rolling session scratchpad for the Arden Vul vault automation project.

Preserve:
- All unresolved issues and open tasks
- Decisions made and how they were resolved
- Pipeline state: what ran, what is pending, what errored
- Named files, proposal IDs, and entity names still relevant
- Any line prefixed TODO, PENDING, ISSUE, or containing ⚠️

Drop:
- Completed tasks with no follow-up needed
- Resolved diagnostic output
- Repetitive narrative and status updates superseded by later entries

Return condensed markdown only — no preamble, no commentary. Target: under 400 lines.

---SCRATCHPAD---
{text}
---END SCRATCHPAD---"""
    condensed = llm_chat_text(prompt, timeout=600)
    header = f"<!-- summarized {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC -->\n\n"
    original_len = len(text)
    SCRATCH_PATH.write_text(header + condensed, encoding="utf-8")
    return {
        "ok": True,
        "original_chars": original_len,
        "condensed_chars": len(condensed),
        "path": str(SCRATCH_PATH),
    }


def cmd_summarize_scratchpad(args: argparse.Namespace) -> int:
    result = summarize_scratchpad()
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _entity_link_proposal_key(source: str, entity_path: str, mention: str, source_excerpt: str = "") -> str:
    return f"{source}|{entity_path}|{mention}|{source_excerpt}"


def verify_entity_link_proposals(limit: int | None = None) -> list[dict]:
    proposals_path = AUTOMATION_DIR / "proposals" / "entity_link_proposals.json"
    if proposals_path.exists():
        raw = json.loads(proposals_path.read_text(encoding="utf-8"))
        proposals = [EntityLinkProposal(**item) for item in raw]
    else:
        proposals = build_entity_link_proposals()
        write_entity_link_proposal_report(proposals)
    run_dir = AUTOMATION_DIR / "proposals"
    verifications_path = run_dir / "entity_link_verifications.json"
    # Load prior verifications and skip proposals already classified — otherwise
    # the scheduled runner re-verifies the same first-N proposals every cycle,
    # hammering the LLM with identical queries while later proposals never get
    # a turn.
    prior: list[dict] = []
    verified_keys: set[str] = set()
    if verifications_path.exists():
        try:
            prior = json.loads(verifications_path.read_text(encoding="utf-8"))
        except Exception:
            prior = []
        for v in prior:
            status = str(v.get("status", "")).lower()
            if status in {"supported", "contradicted", "ambiguous", "not_found"}:
                verified_keys.add(_entity_link_proposal_key(
                    str(v.get("source", "")),
                    str(v.get("entity_path", "")),
                    str(v.get("mention", "")),
                    str(v.get("source_excerpt", "")),
                ))
    pending = [
        p for p in proposals
        if _entity_link_proposal_key(p.source, p.entity_path, p.mention, p.source_excerpt) not in verified_keys
    ]
    fresh: list[dict] = []
    selected = pending if limit is None else pending[:limit]
    for proposal in selected:
        prompt = verification_prompt(proposal)
        try:
            result = llm_chat_json(prompt)
            status = str(result.get("status", "ambiguous")).lower()
            if status not in {"supported", "contradicted", "ambiguous", "not_found"}:
                status = "ambiguous"
            fresh.append({
                **asdict(proposal),
                "status": status,
                "verifier_rationale": str(result.get("rationale", "")),
                "verifier_evidence": str(result.get("evidence", "")),
            })
        except Exception as exc:
            fresh.append({
                **asdict(proposal),
                "status": "error",
                "verifier_rationale": f"verifier failed: {str(exc)[:200]}",
                "verifier_evidence": "",
            })
    combined = prior + fresh
    write_json(verifications_path, combined)
    lines = [
        "# Entity Link Verifications",
        "",
        "LLM verifier results for review-only entity link proposals. Accumulated across runs.",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Total verified: {len(combined)}  (this run: {len(fresh)} new, pending: {max(0, len(pending) - len(fresh))})",
        "",
        "| Entity | Mention | Status | Evidence | Rationale |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in combined:
        entity_link = f"[[{item['entity_path']}|{item['entity']}]]"
        lines.append(
            f"| {entity_link} | {item['mention']} | {item['status']} | "
            f"{normalize_space(item['verifier_evidence']).replace('|', '\\|')} | "
            f"{normalize_space(item['verifier_rationale']).replace('|', '\\|')} |"
        )
    (run_dir / "entity_link_verifications.md").write_text("\n".join(lines), encoding="utf-8")
    return fresh


def wikilink_target_from_repo_path(path: str) -> str:
    if path.startswith("vault/"):
        return path.removeprefix("vault/")
    return path


def in_existing_wikilink(text: str, index: int) -> bool:
    before_open = text.rfind("[[", 0, index)
    before_close = text.rfind("]]", 0, index)
    return before_open > before_close


def contextual_link_edit(text: str, mention: str, entity_path: str, source_excerpt: str) -> tuple[int, int, str] | None:
    pattern = mention_pattern(mention)
    if not pattern or not source_excerpt or text.count(source_excerpt) != 1:
        return None
    excerpt_start = text.index(source_excerpt)
    matches = [
        match for match in pattern.finditer(source_excerpt)
        if not in_existing_wikilink(source_excerpt, match.start())
    ]
    if len(matches) != 1:
        return None
    match = matches[0]
    target = wikilink_target_from_repo_path(entity_path)
    start = excerpt_start + match.start()
    end = excerpt_start + match.end()
    return start, end, f"[[{target}|{text[start:end]}]]"


def apply_verified_entity_links(apply: bool, limit: int | None = None) -> dict:
    verifications_path = AUTOMATION_DIR / "proposals" / "entity_link_verifications.json"
    if not verifications_path.exists():
        return {"ok": False, "error": "missing_verifications"}
    proposals_path = AUTOMATION_DIR / "proposals" / "entity_link_proposals.json"
    if not proposals_path.exists():
        return {"ok": False, "error": "missing_current_proposals"}
    verifications = json.loads(verifications_path.read_text(encoding="utf-8"))
    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))
    current_keys = {
        _entity_link_proposal_key(
            str(item.get("source", "")),
            str(item.get("entity_path", "")),
            str(item.get("mention", "")),
            str(item.get("source_excerpt", "")),
        )
        for item in proposals
    }
    candidates: list[dict] = []
    for item in verifications:
        if item.get("status") != "supported":
            continue
        key = _entity_link_proposal_key(
            str(item.get("source", "")),
            str(item.get("entity_path", "")),
            str(item.get("mention", "")),
            str(item.get("source_excerpt", "")),
        )
        if key not in current_keys:
            continue
        candidates.append(item)
    changes: list[str] = []
    applied = 0
    by_source: dict[str, list[dict]] = {}
    for item in candidates:
        by_source.setdefault(str(item.get("source", "")), []).append(item)
    for source_key, items in sorted(by_source.items()):
        if limit is not None and applied >= limit:
            break
        source = ROOT / source_key
        if not source.is_relative_to(VAULT) or not source.exists():
            continue
        text = read_text(source)
        edits: list[tuple[int, int, str, dict]] = []
        for item in items:
            edit = contextual_link_edit(text, item["mention"], item["entity_path"], item.get("source_excerpt", ""))
            if edit:
                edits.append((*edit, item))
        accepted: list[tuple[int, int, str, dict]] = []
        for edit in sorted(edits, key=lambda value: (value[0], -(value[1] - value[0]))):
            if accepted and edit[0] < accepted[-1][1]:
                continue
            accepted.append(edit)
        if limit is not None:
            accepted = accepted[:max(0, limit - applied)]
        if not accepted:
            continue
        updated = text
        for start, end, replacement, item in reversed(accepted):
            updated = updated[:start] + replacement + updated[end:]
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


def import_low_risk(apply: bool, blog_feed: str = BLOG_FEED_URL, force_discord_update: bool = False) -> dict:
    validation = validate_state()
    if not validation["ok"]:
        return {"ok": False, "error": "validation_failed", "validation": validation}

    changes: list[str] = []
    existing_discord = all_discord_summary_paths()
    existing_sessions = all_session_paths()
    created_discord = import_discord_digests(apply, changes, force_update=force_discord_update)
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


# ---- vault-rag (local Chroma) ----

VAULT_RAG_H2_SPLIT_RE = re.compile(r"^## (?!#)", re.MULTILINE)
VAULT_RAG_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n+", re.DOTALL)
VAULT_RAG_MAX_CHUNK_CHARS = 3000
VAULT_RAG_MIN_CHUNK_CHARS = 60
VAULT_RAG_SCHEMA_VERSION = 4  # bumped: chunk metadata now includes retrieval enrichment fields
VAULT_RAG_LABEL_SECTIONS = {
    "date",
    "weather",
    "player characters",
    "significant npcs",
    "the plan",
    "what happened",
    "gm's comments",
    "gm's notes",
    "achievements",
    "xp",
    "next week",
    "original source",
}


def vault_rag_embed(text: str) -> list[float]:
    sources = load_local_sources()
    url = sources["vault_rag_embed_url"]
    model = sources["vault_rag_embed_model"]
    body = None
    last_error: Exception | None = None
    for prompt in (
        text,
        text.rstrip() + "\n\n.",
        text.rstrip() + "\n\nAdditional context.",
        text.rstrip() + "\n\nThis is a vault note.",
    ):
        payload = json.dumps({"model": model, "prompt": prompt}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except Exception as exc:
            last_error = exc
    if body is None:
        raise RuntimeError(f"vault-rag embedding request failed: {last_error}")
    emb = body.get("embedding")
    if not emb:
        raise RuntimeError(f"vault-rag embedding returned no vector: {str(body)[:200]}")
    return emb


def rag_store_database_url() -> str:
    url = os.environ.get("RAG_STORE_DATABASE_URL", "").strip()
    if url:
        return url
    env_path = Path("/opt/brain/.env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("RAG_STORE_DATABASE_URL="):
                return line.partition("=")[2].strip()
    raise RuntimeError("RAG_STORE_DATABASE_URL is not set and could not be read from /opt/brain/.env")


def _split_oversized_chunk(text: str, max_chars: int) -> list[str]:
    """Split a long chunk at paragraph boundaries, packing up to max_chars per piece.
    Falls back to hard-splitting if a single paragraph still exceeds max_chars."""
    pieces: list[str] = []
    current: list[str] = []
    current_size = 0
    for para in text.split("\n\n"):
        para_size = len(para) + 2
        if current and current_size + para_size > max_chars:
            pieces.append("\n\n".join(current))
            current = [para]
            current_size = para_size
        else:
            current.append(para)
            current_size += para_size
    if current:
        pieces.append("\n\n".join(current))
    out: list[str] = []
    for piece in pieces:
        if len(piece) <= max_chars:
            out.append(piece)
        else:
            for i in range(0, len(piece), max_chars):
                out.append(piece[i:i + max_chars])
    return out


def _section_from_line(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("## ") and not stripped.startswith("### "):
        return stripped[3:].strip()
    bold = re.match(r"^\*\*(?P<label>[^*:\n]+):\*\*\s*$", stripped)
    if bold:
        label = bold.group("label").strip()
        if label.lower() in VAULT_RAG_LABEL_SECTIONS:
            return label
    bare = re.match(r"^(?P<label>[A-Za-z][A-Za-z0-9 '’&/-]{1,60}):(?P<rest>.*)$", stripped)
    if bare:
        label = bare.group("label").strip()
        if label.lower() in VAULT_RAG_LABEL_SECTIONS:
            return label
    return None


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split at H2s plus common imported recap labels.

    Many early imported sessions use plain labels such as "GM's Comments:" or
    "XP:" instead of H2 headings. If those are left inside the intro chunk, RAG
    metadata reports late-session material as `(intro)`.
    """
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_section = "(intro)"
    current_lines: list[str] = []
    for line in lines:
        section = _section_from_line(line)
        if section and current_lines:
            sections.append((current_section, current_lines))
            current_section = section
            current_lines = [line]
        elif section:
            current_section = section
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_section, current_lines))
    return [(section, "\n".join(lines).strip()) for section, lines in sections if "\n".join(lines).strip()]


def chunk_markdown_for_rag(text: str) -> list[tuple[str, str]]:
    """Split markdown by sections; sub-split large sections at paragraph breaks."""
    text = strip_frontmatter(text).strip()
    if not text:
        return []
    raw_chunks: list[tuple[str, str]] = []
    for section, body in _split_markdown_sections(text):
        raw_chunks.append((section, body))
    chunks: list[tuple[str, str]] = []
    for section, body in raw_chunks:
        if len(body) <= VAULT_RAG_MAX_CHUNK_CHARS:
            chunks.append((section, body))
        else:
            for sub in _split_oversized_chunk(body, VAULT_RAG_MAX_CHUNK_CHARS):
                chunks.append((section, sub))
    return [(s, c) for s, c in chunks if len(c.strip()) >= VAULT_RAG_MIN_CHUNK_CHARS]


def vault_rag_chunk_kind(base_kind: str, section: str) -> str:
    if section.strip().lower() == "session navigation":
        return "navigation"
    return base_kind


VAULT_RAG_SKIP_DIRS = {"templates", "quartz", "attachments", ".obsidian"}
VAULT_RAG_FOLDER_TO_KIND = {
    "sessions": "session",
    "notes": "note",
    "lore": "lore",
    "npcs": "npc",
    "pcs": "pc",
    "locations": "location",
    "factions": "faction",
    "items": "item",
    "library": "library",
    "monsters": "monster",
    "spells": "spell",
    "concepts": "concept",
}


def vault_rag_kind_for_path(path: Path) -> str:
    try:
        rel = path.relative_to(VAULT)
    except ValueError:
        return "external"
    parts = rel.parts
    if not parts:
        return "vault"
    top = parts[0]
    if top == "notes" and path.stem.startswith("Discord Summary"):
        return "summary"
    return VAULT_RAG_FOLDER_TO_KIND.get(top, "vault")


def vault_rag_source_paths() -> list[tuple[Path, str]]:
    """Return (path, kind) pairs for content to ingest into the vault RAG Postgres database.
    Indexes the entire vault (skipping templates/quartz/attachments), plus the spreadsheet snapshot if present.

    Do not index raw Discord weekly rollup channel files here. Those files preserve
    near-verbatim chat logs; player-facing RAG should only see curated vault pages
    such as Discord Summary notes.
    """
    items: list[tuple[Path, str]] = []
    if VAULT.exists():
        for p in sorted(VAULT.rglob("*.md")):
            rel_parts = p.relative_to(VAULT).parts
            # Skip files inside any excluded directory at any depth.
            if any(part in VAULT_RAG_SKIP_DIRS for part in rel_parts[:-1]):
                continue
            frontmatter = parse_frontmatter(read_text(p))
            if str(frontmatter.get("status") or "").strip().lower() == "redirect":
                continue
            items.append((p, vault_rag_kind_for_path(p)))
    snapshot = AUTOMATION_DIR / "sources" / "group_spreadsheet_snapshot.md"
    if snapshot.exists():
        items.append((snapshot, "spreadsheet"))
    return items


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in values) + "]"


def vault_rag_upsert_file(conn: "psycopg.Connection", path: Path, kind: str) -> dict:
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = str(path)
    text = read_text(path)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT metadata->>'sha256', metadata->>'schema_version', count(*) "
            "FROM rag_chunks WHERE database='arden' AND metadata->>'path'=%s GROUP BY 1,2 LIMIT 1",
            (rel,),
        )
        row = cur.fetchone()
    if row and row[0] == sha and row[1] == str(VAULT_RAG_SCHEMA_VERSION):
        return {"path": rel, "action": "unchanged", "chunk_count": int(row[2])}

    with conn.cursor() as cur:
        cur.execute("DELETE FROM rag_chunks WHERE database='arden' AND metadata->>'path'=%s", (rel,))

    chunks = chunk_markdown_for_rag(text)
    if not chunks:
        conn.commit()
        return {"path": rel, "action": "empty", "chunk_count": 0}

    try:
        fm = parse_frontmatter(text)
    except Exception:
        fm = {}
    fm_status = str(fm.get("status") or "").strip().lower() or None
    fm_aliases_raw = fm.get("aliases") or []
    if isinstance(fm_aliases_raw, str):
        fm_aliases_raw = [a.strip() for a in fm_aliases_raw.split(",") if a.strip()]
    fm_aliases = ", ".join(str(a) for a in fm_aliases_raw if str(a).strip()) or None
    fm_tags = ", ".join(frontmatter_list(text, "tags")) or None
    fm_related_entities = ", ".join(frontmatter_list(text, "related_entities")) or None
    fm_identity_hints = ", ".join(frontmatter_list(text, "identity_hints")) or None

    rows: list[tuple] = []
    skipped: list[dict] = []
    for i, (section, chunk_text) in enumerate(chunks):
        try:
            emb = vault_rag_embed(chunk_text)
        except Exception as exc:
            skipped.append({"chunk_index": i, "section": section, "char_count": len(chunk_text), "error": str(exc)[:200]})
            continue
        chunk_id = f"{rel}#{i}:{hashlib.sha1(chunk_text.encode('utf-8')).hexdigest()[:8]}"
        chunk_meta: dict = {
            "path": rel,
            "kind": vault_rag_chunk_kind(kind, section),
            "source_kind": kind,
            "section": section,
            "title": path.stem,
            "sha256": sha,
            "schema_version": VAULT_RAG_SCHEMA_VERSION,
            "chunk_index": i,
            "char_count": len(chunk_text),
        }
        if fm_status:
            chunk_meta["status"] = fm_status
        if fm_aliases:
            chunk_meta["aliases"] = fm_aliases
        if fm_tags:
            chunk_meta["tags"] = fm_tags
        if fm_related_entities:
            chunk_meta["related_entities"] = fm_related_entities
        if fm_identity_hints:
            chunk_meta["identity_hints"] = fm_identity_hints
        rows.append((chunk_id, chunk_text, json.dumps(chunk_meta), _vector_literal(emb)))

    if not rows:
        conn.commit()
        return {"path": rel, "action": "error", "chunk_count": 0, "error": "all chunks failed to embed", "skipped": skipped}

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO rag_chunks (database, chunk_id, document, metadata, embedding) "
            "VALUES ('arden', %s, %s, %s::jsonb, %s::vector)",
            rows,
        )
    conn.commit()
    result: dict = {"path": rel, "action": "upserted", "chunk_count": len(rows)}
    if skipped:
        result["skipped_chunks"] = skipped
    return result


def vault_rag_ingest_all(reset: bool = False, limit: int | None = None) -> dict:
    db_url = rag_store_database_url()
    paths = vault_rag_source_paths()
    if limit:
        paths = paths[:limit]
    results: list[dict] = []
    with psycopg.connect(db_url) as conn:
        if reset:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rag_chunks WHERE database='arden'")
            conn.commit()
        for p, kind in paths:
            try:
                results.append(vault_rag_upsert_file(conn, p, kind))
            except Exception as exc:
                try:
                    rel = p.relative_to(ROOT).as_posix()
                except ValueError:
                    rel = str(p)
                results.append({"path": rel, "action": "error", "error": str(exc)})
        with conn.cursor() as cur:
            cur.execute("ANALYZE rag_chunks")
            cur.execute("SELECT count(*) FROM rag_chunks WHERE database='arden'")
            collection_size = cur.fetchone()[0]
        conn.commit()
    counts: dict[str, int] = {}
    for r in results:
        counts[r.get("action", "?")] = counts.get(r.get("action", "?"), 0) + 1
    return {
        "ok": counts.get("error", 0) == 0,
        "total_files": len(paths),
        "actions": counts,
        "collection_size": collection_size,
        "results": results,
    }


def local_rag_api_key() -> str:
    configured = str(load_local_sources().get("rag_api_key") or "").strip()
    if configured:
        return configured
    env_path = Path("/opt/brain/.env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("RAG_API_KEYS="):
                return line.partition("=")[2].split(",", 1)[0].strip()
    return ""


def pgvector_rag_search(query: str, top_k: int = 5, kind: str | None = None) -> list[dict]:
    """Query the published local pgvector RAG API."""
    sources = load_local_sources()
    base_url = str(sources.get("rag_api_base_url") or "").rstrip("/")
    api_key = local_rag_api_key()
    if not base_url or not api_key:
        return []
    payload: dict = {
        "query": query,
        "top_k": top_k,
        "include_text": True,
        "max_text_chars": 4000,
    }
    if kind:
        payload["kind"] = kind
    request = urllib.request.Request(
        base_url + "/search/arden",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    return [
        {
            "path": hit.get("path"),
            "section": hit.get("section"),
            "kind": hit.get("kind"),
            "title": hit.get("title"),
            "distance": hit.get("distance"),
            "text": hit.get("text"),
            "match_type": hit.get("match_type"),
        }
        for hit in body.get("hits", [])
    ]


def vault_rag_search(query: str, top_k: int = 5, kind: str | None = None) -> list[dict]:
    return pgvector_rag_search(query, top_k=top_k, kind=kind)


def _format_mechanics_hit(doc, meta, dist, match_type) -> dict:
    meta = meta or {}
    return {
        "book": meta.get("book", "?"),
        "printed_page": meta.get("printed_page", "?"),
        "section": meta.get("section", "?"),
        "source_pdf": meta.get("source", "?"),
        "distance": dist,
        "match_type": match_type,
        "text": doc,
    }


def mechanics_rag_search(query: str, top_k: int = 3) -> list[dict]:
    """Hybrid search of the DFRPG rules MechanicsVault Chroma collection.

    bge-m3 embeddings rank thematically-similar chunks (e.g. searching for
    "Wall of Lightning" returns Weather Spells intro and Lightning Missiles
    entries before the actual Wall of Lightning spell). To compensate, we
    also do a literal $contains scan for the candidate name and prefer those
    hits — if the rulebook text contains the verbatim name, that's a much
    stronger signal that it's a rulebook entry than semantic similarity.

    Returns up to top_k hits; literal-match hits come first, then embedding-
    based hits, with duplicates collapsed by (book, page, section).
    """
    base_url, api_key = _load_rag_api_config()
    if not api_key:
        return []
    hits = _rag_search(base_url, api_key, "mechanics", query, top_k=top_k * 2)
    seen: set[tuple] = set()
    out: list[dict] = []
    for h in hits:
        key = (h.get("book"), h.get("printed_page"), h.get("section"))
        if key in seen:
            continue
        seen.add(key)
        out.append(_format_mechanics_hit(
            h.get("text", ""),
            {"book": h.get("book"), "printed_page": h.get("printed_page"),
             "section": h.get("section"), "source": h.get("source_pdf")},
            h.get("distance", 0.0),
            h.get("match_type", "embedding"),
        ))
        if len(out) >= top_k * 2:
            break
    return out


# ---- new-entity proposal lane (item 6: IAC/ACE) ----

IAC_KIND_TO_DIR = {
    "NPC": "npcs",
    "PC": "pcs",
    "Location": "locations",
    "Faction": "factions",
    "Item": "items",
    "Monster": "monsters",
    "Spell": "spells",
    "Concept": "concepts",
    "Media": "items",  # Media items live in items/ with media/<subtype> tags
}
IAC_KIND_EXTRA_TAGS = {
    "Media": ("media/general",),  # Verifier may upgrade to media/book, media/map, etc.
}
IAC_CANDIDATE_PROMPT = (
    "You are extracting named entities from a recap of a Dungeon Fantasy RPG (DFRPG/GURPS) "
    "tabletop campaign set in the Halls of Arden Vul. Recaps come from blog session writeups, "
    "weekly Discord digests, raw Discord channel rollups, lore notes, and spreadsheet snapshots.\n\n"
    "List entity candidates from the text grouped by type:\n"
    "- NPC: named non-player characters (people, sentient creatures with proper names).\n"
    "- PC: a named player character (e.g. Vael, Ioannes, Vallium, Uvash). PC names are listed "
    "in \"Player Characters\" sections of session recaps.\n"
    "- Location: named places (regions, halls, named rooms like \"Goblin Forum\", landmarks). "
    "Skip generic rooms (\"the hallway\", \"a chamber\") and door labels.\n"
    "- Faction: named groups, cults, organizations, militaries, races/cultures used as groups "
    "(e.g. \"Cult of Set\", \"Sortians\", \"Sun-Scarred Knights\").\n"
    "- Item: named magical or significant non-media items (weapons, armor, artifacts, devices).\n"
    "- Monster: named creatures or distinct creature types appearing as encounters "
    "(e.g. \"Behir\", \"Surgical Construct\", \"Ancient Wyrm of the Chasm\"). Skip generic "
    "common monsters (ghoul, goblin, skeleton) unless they appear as named individuals — "
    "those are NPCs instead.\n"
    "- Spell: named spells, magical effects, or supernatural abilities used in-fiction "
    "(e.g. \"Seeker\", \"Apportation\", \"Recover Energy\"). Not generic verbs.\n"
    "- Concept: named in-world concepts that aren't a person/place/group/item (e.g. "
    "\"Apophidian Calendar\", \"Litany of Light\", named rituals or eras).\n"
    "- Media: named books, scrolls, maps, data crystals, libraries, journals, or catalogs "
    "(e.g. \"Book of Priors\", \"On the Location of Priscus Pulcher\", \"The Archontean "
    "Empire\"). These are items, but flagged separately so they get the right media tags.\n\n"
    "Rules:\n"
    "- Title Case only. Use the canonical proper name, not a sentence fragment.\n"
    "- Exclude generics, scaffolding words (we, they, that, this, date, session, summary), "
    "and pronouns.\n"
    "- Do not invent. Only list names actually present in the text.\n"
    "- Do not map to existing pages — that's a separate step.\n\n"
    "Return strict JSON only:\n"
    "{\n"
    '  "NPC": ["..."],\n'
    '  "PC": ["..."],\n'
    '  "Location": ["..."],\n'
    '  "Faction": ["..."],\n'
    '  "Item": ["..."],\n'
    '  "Monster": ["..."],\n'
    '  "Spell": ["..."],\n'
    '  "Concept": ["..."],\n'
    '  "Media": ["..."]\n'
    "}\n"
    "Empty arrays for kinds with no candidates."
)
NEW_ENTITY_MIN_MENTIONS = 2
NEW_ENTITY_FUZZY_THRESHOLD = 0.88
NEW_ENTITY_SCAFFOLDING = {
    "the", "a", "an", "that", "this", "they", "we", "i", "you", "also", "however",
    "finally", "first", "second", "third", "next", "previous", "again", "great",
    "over", "under", "ahead", "before", "after", "date", "session", "summary",
    "page", "note", "tbd", "todo", "however,", "but", "and", "or",
}
NEW_ENTITY_SCAFFOLDING_SUFFIXES = {
    "date", "over", "we", "that", "this", "again", "finally", "however",
    "before", "after", "they", "you", "i",
}


def load_entity_filters() -> dict:
    p = ROOT / "config" / "entity_filters.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_ace_ignore_npcs() -> set[str]:
    p = ROOT / "config" / "ace_ignore_npcs.txt"
    if not p.exists():
        return set()
    out: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line.lower())
    return out


def is_candidate_rejected(name: str, kind: str, filters: dict, ignore_npcs: set[str]) -> tuple[bool, str]:
    if not name:
        return True, "empty"
    n = name.strip()
    if n.startswith("[[") and n.endswith("]]"):
        n = n[2:-2].split("|")[-1]
    if len(n) < 3:
        return True, "too short"
    if any(c in n for c in (":", ";", "?", "!", "\n", "\t")):
        return True, "punctuation suggests fragment"
    nl = n.lower()
    if nl in NEW_ENTITY_SCAFFOLDING:
        return True, "scaffolding word"
    if " " not in n and n.isupper():
        return True, "all-caps single token (likely acronym/header)"
    if " " not in n and len(n) <= 4 and n[0].isupper():
        return True, "single short title-case word (likely generic)"
    stop_key = {"NPC": "stop_npcs", "Location": "stop_location", "Faction": "stop_factions", "Item": "stop_items", "Concept": "stop_concepts", "Spell": "spells", "Media": "stop_items"}.get(kind)
    if stop_key:
        # Spells in the stop list may have difficulty suffixes like " (VH)" or " (H)" that
        # the LLM extractor omits. Strip them before comparing so "Blink Other" matches
        # "Blink Other (VH)".
        _DIFF_SUFFIX = re.compile(r"\s+\([VH]+\)\s*$", re.IGNORECASE)
        for stop in filters.get(stop_key, []):
            stop_norm = _DIFF_SUFFIX.sub("", str(stop)).lower().strip()
            if nl == stop_norm or nl == str(stop).lower():
                return True, f"in {stop_key}"
    if kind == "Item":
        for commodity in filters.get("commodity_items", []):
            if nl == str(commodity).lower():
                return True, "commodity item"
    if kind == "NPC" and nl in ignore_npcs:
        return True, "in ace_ignore_npcs"
    last = n.split()[-1].lower()
    if last in NEW_ENTITY_SCAFFOLDING_SUFFIXES:
        return True, f"trailing scaffolding word '{last}'"
    return False, ""


_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)


def _entity_name_overlap(a: str, b: str) -> bool:
    """Word-level subset check: True if names share enough words to be the same entity.
    Catches cases like 'Vael Sunshadow' vs 'Vaelethron Vael Sunshadow', 'The Beacon' vs 'Beacon',
    'Lady Alexia' vs 'Lady Alexia Basileon'."""
    aw = {w for w in _WORD_RE.findall(a.lower()) if len(w) > 1}
    bw = {w for w in _WORD_RE.findall(b.lower()) if len(w) > 1}
    if not aw or not bw:
        return False
    common = aw & bw
    if len(common) >= 2:
        return True
    if common and (aw.issubset(bw) or bw.issubset(aw)):
        return True
    return False


def find_nearest_existing_entity(name: str, kind: str, entity_index: dict[str, list[EntityPage]]) -> tuple[str | None, float]:
    # NPC and PC candidates need to be checked against each other — player characters
    # are people too and should never be added as NPC pages. Media items live in
    # items/ alongside non-media items so dedup needs to scan there.
    kind_to_dirs = {
        "NPC": ["npcs", "pcs"],
        "PC": ["pcs", "npcs"],
        "Location": ["locations"],
        "Faction": ["factions"],
        "Item": ["items"],
        "Monster": ["monsters"],
        "Spell": ["spells"],
        "Concept": ["concepts"],
        "Media": ["items"],
    }
    dirs = kind_to_dirs.get(kind)
    if not dirs:
        return None, 0.0
    best_path: str | None = None
    best_sim = 0.0
    nl = name.lower()
    for dir_name in dirs:
        for ent in entity_index.get(dir_name, []):
            names_to_check = [ent.title.lower()] + [a.lower() for a in ent.aliases]
            for cand_name in names_to_check:
                if not cand_name:
                    continue
                if _entity_name_overlap(nl, cand_name):
                    return ent.path, 1.0
                sim = difflib.SequenceMatcher(None, nl, cand_name).ratio()
                if sim > best_sim:
                    best_sim = sim
                    best_path = ent.path
    # Cross-directory dedup: entities can legitimately live in a different directory
    # than the proposed kind (e.g. a merchant guild proposed as Location but filed
    # under factions/). A high-confidence name match anywhere in the vault is enough
    # to treat it as already covered.
    CROSS_DIR_THRESHOLD = 0.92
    if best_sim < CROSS_DIR_THRESHOLD:
        for dir_name, pages in entity_index.items():
            if dir_name in dirs:
                continue
            for ent in pages:
                names_to_check = [ent.title.lower()] + [a.lower() for a in ent.aliases]
                for cand_name in names_to_check:
                    if not cand_name:
                        continue
                    if _entity_name_overlap(nl, cand_name):
                        return ent.path, 1.0
                    sim = difflib.SequenceMatcher(None, nl, cand_name).ratio()
                    if sim > best_sim:
                        best_sim = sim
                        best_path = ent.path
    return best_path, best_sim


def build_entity_index() -> dict[str, list[EntityPage]]:
    out: dict[str, list[EntityPage]] = {}
    for p in entity_pages():
        parts = p.path.split("/")
        key = None
        if parts and parts[0] == "vault" and len(parts) >= 2:
            key = parts[1]
        elif parts:
            key = parts[0]
        if key:
            out.setdefault(key, []).append(p)
    return out


def iac_extract_candidates_from_chunk(chunk_text: str) -> dict[str, list[str]]:
    prompt = IAC_CANDIDATE_PROMPT + "\n\nTEXT:\n" + chunk_text[:3000]
    try:
        response = llm_chat_json(prompt, timeout=120)
    except Exception:
        return {}
    out: dict[str, list[str]] = {}
    for kind in IAC_KIND_TO_DIR.keys():
        values = response.get(kind) or []
        if isinstance(values, list):
            cleaned = []
            for v in values:
                if isinstance(v, (str, int, float)):
                    s = str(v).strip()
                    if s:
                        cleaned.append(s)
            out[kind] = cleaned
    return out


def extract_candidate_evidence(name: str, source_paths: list[Path]) -> list[dict]:
    evidence: list[dict] = []
    pattern = re.compile(re.escape(name), re.IGNORECASE)
    section_pat = re.compile(r"^## (?!#)([^\n]+)", re.MULTILINE)
    for sp in source_paths:
        try:
            text = read_text(sp)
        except Exception:
            continue
        m = pattern.search(text)
        if not m:
            continue
        section = "(intro)"
        for sec_m in section_pat.finditer(text[:m.start()]):
            section = sec_m.group(1).strip()
        start = max(0, m.start() - 150)
        end = min(len(text), m.end() + 200)
        excerpt = normalize_space(text[start:end])
        try:
            rel = sp.relative_to(ROOT).as_posix()
        except ValueError:
            rel = str(sp)
        evidence.append({"path": rel, "section": section, "excerpt": excerpt[:400]})
    return evidence


def build_new_entity_proposals(source_limit: int = 10, candidate_limit: int = 50) -> list[NewEntityCandidate]:
    canonical_sources = latest_canonical_sources(limit=source_limit)
    if not canonical_sources:
        return []
    filters = load_entity_filters()
    ignore_npcs = load_ace_ignore_npcs()
    entity_index = build_entity_index()
    raw_by_kind: dict[str, dict[str, list[Path]]] = {k: {} for k in IAC_KIND_TO_DIR.keys()}
    for sp in canonical_sources:
        try:
            text = read_text(sp)
        except Exception:
            continue
        # For the Party Armory, normalize table cell names before extraction:
        # strip comma-separated descriptions (e.g. "pale green horn, with a broad spiral")
        # so the LLM sees "Pale Green Horn" as a clean proper noun.
        if sp == PARTY_ARMORY_PATH:
            # Normalize the first (item-name) cell of each armory table row:
            # strip comma-separated physical descriptions so the LLM sees clean
            # proper nouns (e.g. "pale green horn, with..." → "Pale Green Horn").
            def _normalize_armory_name_cell(m: re.Match) -> str:
                cell = m.group(1).strip()
                # Only normalize cells that start lowercase — these are descriptive
                # names the LLM won't recognise as proper nouns (e.g. "pale green horn,
                # with a broad spiral..."). Properly-cased entries are left unchanged.
                if cell and cell[0].islower():
                    cell = cell.split(",")[0].strip().title()
                return f"| {cell} |{m.group(2)}"
            text = re.sub(r"^\|\s*([^|\n]{4,}?)\s*\|(\s*\d)", _normalize_armory_name_cell, text, flags=re.MULTILINE)
        for i in range(0, len(text), 3000):
            chunk = text[i:i + 3000]
            if len(chunk.strip()) < 80:
                continue
            extracted = iac_extract_candidates_from_chunk(chunk)
            for kind, names in extracted.items():
                for name in names:
                    raw_by_kind[kind].setdefault(name, []).append(sp)
    out: list[NewEntityCandidate] = []
    for kind, by_name in raw_by_kind.items():
        for name, sources_seen in by_name.items():
            rejected, _ = is_candidate_rejected(name, kind, filters, ignore_npcs)
            if rejected:
                continue
            unique_sources = list({str(p): p for p in sources_seen}.values())
            if len(unique_sources) < NEW_ENTITY_MIN_MENTIONS and len(sources_seen) < NEW_ENTITY_MIN_MENTIONS:
                continue
            nearest_path, nearest_sim = find_nearest_existing_entity(name, kind, entity_index)
            if nearest_sim >= NEW_ENTITY_FUZZY_THRESHOLD:
                continue
            ev = extract_candidate_evidence(name, unique_sources[:5])
            from_armory = any(str(s.get("path", "")) == str(PARTY_ARMORY_PATH.relative_to(ROOT)) or
                               str(s.get("path", "")).endswith("Party Armory.md")
                               for s in ev)
            min_mentions = 1 if from_armory else NEW_ENTITY_MIN_MENTIONS
            if len(ev) < min_mentions:
                continue
            proposal_id = hashlib.sha1(f"{kind}|{name}".encode("utf-8")).hexdigest()[:12]
            rationale = (
                f"Listed in Party Armory (current inventory); "
                f"no existing vault/{IAC_KIND_TO_DIR[kind]}/ page found "
                f"(nearest match similarity={nearest_sim:.2f})."
            ) if from_armory else (
                f"Mentioned across {len(ev)} canonical sources; "
                f"not found in existing vault/{IAC_KIND_TO_DIR[kind]}/ pages "
                f"(nearest match similarity={nearest_sim:.2f})."
            )
            out.append(NewEntityCandidate(
                name=name,
                kind=kind,
                canonical_target_dir=IAC_KIND_TO_DIR[kind],
                mention_count=len(ev),
                sources=ev,
                rationale=rationale,
                nearest_existing=nearest_path,
                nearest_distance=nearest_sim,
                proposal_id=proposal_id,
                status="needs-verification",
            ))
    out.sort(key=lambda c: (-c.mention_count, c.kind, c.name))
    out = out[:candidate_limit]

    # Post-proposal RAG filter: suppress rulebook items and existing vault pages;
    # route entities whose matching page lacks evidence content to update suggestions.
    kept, suppressed_by_rag, update_suggestions = rag_filter_new_entity_proposals(out)
    proposals_dir = AUTOMATION_DIR / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    if suppressed_by_rag or update_suggestions:
        write_json(proposals_dir / "new_entity_rag_filter.json", {
            "suppressed": suppressed_by_rag,
            "update_suggestions": update_suggestions,
        })
    return kept


def _load_rag_api_config() -> tuple[str, str | None]:
    """Return (base_url, api_key) for the postgres RAG API."""
    sources = load_local_sources()
    base_url = str(sources.get("rag_api_url") or "http://localhost:8897").rstrip("/")
    api_key = str(sources.get("rag_api_key")) if sources.get("rag_api_key") else None
    if not api_key:
        env_path = Path("/opt/brain/.env")
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("RAG_API_KEYS="):
                    api_key = line.split("=", 1)[1].strip().split(",")[0].strip()
                    break
    return base_url, api_key


def _rag_search(base_url: str, api_key: str, database: str, query: str, top_k: int = 3) -> list[dict]:
    try:
        resp = requests.post(
            f"{base_url}/search/{database}",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"query": query, "top_k": top_k, "include_text": True, "max_text_chars": 500},
            timeout=12,
        )
        resp.raise_for_status()
        return resp.json().get("hits", [])
    except Exception:
        return []


def _llm_judge_update_candidate(
    name: str,
    kind: str,
    existing_text: str,
    evidence_sources: list[dict],
) -> dict:
    """Ask the configured LLM whether evidence adds new facts to an existing vault page.

    Returns {"verdict": "UPDATE"|"SKIP", "reason": "..."}. Falls back to SKIP on error
    so a broken LLM call never causes spurious update proposals.
    """
    evidence_blocks = []
    for s in evidence_sources[:4]:
        excerpt = (s.get("excerpt") or "").strip()
        if excerpt:
            evidence_blocks.append(
                f"Source: {s.get('path','')} §{s.get('section','')}\n{excerpt[:400]}"
            )
    if not evidence_blocks:
        return {"verdict": "SKIP", "reason": "no evidence excerpts"}

    # If the existing page is a definition stub (no Sessions/Appearances section),
    # any in-world evidence almost certainly adds new lore worth documenting.
    is_stub = not re.search(r"^##\s+(session|appears in|appearances|discovered|found in|lore)", existing_text, re.IGNORECASE | re.MULTILINE)
    stub_hint = (
        "\nNOTE: The existing page has no Sessions or Appearances section, so it is "
        "a definition stub. Any evidence of the entity being discovered in-world "
        "(found as a scroll, in a book, used by an NPC, acquired by the party) "
        "qualifies as new information worth documenting even if the definition is complete.\n"
    ) if is_stub else ""

    prompt = (
        f"You are auditing whether campaign evidence warrants updating a vault page.\n\n"
        f"ENTITY: [{kind}] {name}\n\n"
        f"EXISTING PAGE (truncated):\n{existing_text[:1500]}\n\n"
        f"EVIDENCE FROM SESSIONS/SUMMARIES:\n"
        + "\n\n---\n\n".join(evidence_blocks)
        + f"\n\n{stub_hint}"
        + "Does the evidence contain NEW FACTUAL INFORMATION about this specific entity "
        f"that is NOT already in the existing page? "
        f"New facts = abilities, history, relationships, appearances, game rulings, "
        f"or in-world discoveries (finding a scroll, a book, an NPC using the spell, "
        f"or the party acquiring it). "
        f"Do NOT count: tactical plans mentioning the entity, session player lists, "
        f"or incidental references where the entity is not the subject.\n\n"
        f'Return strict JSON: {{"verdict": "UPDATE", "reason": "one sentence"}} '
        f'or {{"verdict": "SKIP", "reason": "one sentence"}}'
    )
    try:
        result = llm_chat_json(prompt, timeout=60)
        verdict = str(result.get("verdict", "SKIP")).upper()
        if verdict not in ("UPDATE", "SKIP"):
            verdict = "SKIP"
        return {"verdict": verdict, "reason": str(result.get("reason", ""))}
    except Exception as exc:
        return {"verdict": "SKIP", "reason": f"llm error: {str(exc)[:80]}"}


def rag_filter_new_entity_proposals(
    proposals: list[NewEntityCandidate],
) -> tuple[list[NewEntityCandidate], list[dict], list[dict]]:
    """Post-proposal filter using both RAG databases.

    Three passes per candidate:
    1. Mechanics RAG — if the candidate name appears as a bold rulebook entry, it's a
       standard rules item; suppress it.
    2. Arden RAG — if a dedicated vault page already covers this candidate (title
       similarity ≥ 0.88), check whether the candidate's evidence adds new information
       not present in the existing page.
       - Fully covered → suppress.
       - Existing page missing key evidence content → route to update_candidates.
    3. Neither match → keep for new-page creation.

    Returns (kept, suppressed, update_candidates).
    update_candidates entries have: name, kind, existing_path, missing_excerpts.
    """
    base_url, api_key = _load_rag_api_config()
    if not api_key:
        return proposals, [], []

    kept: list[NewEntityCandidate] = []
    suppressed: list[dict] = []
    update_candidates: list[dict] = []

    for p in proposals:
        nl = p.name.lower()
        outcome: str | None = None  # "suppress" | "update" | None=keep
        suppress_reason: str | None = None
        update_info: dict = {}

        # --- Pass 1: mechanics RAG ---
        if p.kind in ("Item", "Spell", "Monster", "Concept", "Media"):
            hits = _rag_search(base_url, api_key, "mechanics", p.name, top_k=1)
            if hits:
                text = hits[0].get("text", "").lower()
                if f"**{nl}" in text or f"**{nl} (" in text:
                    outcome = "suppress"
                    suppress_reason = f"rulebook item — mechanics RAG: '{hits[0].get('title','')}'"

        # --- Pass 2: Arden RAG ---
        # Only dedicated entity pages count as existing coverage; session notes and
        # Discord summaries merely *mention* entities and are not authoritative pages.
        # Also enforce kind compatibility: a Spell should only match spell pages, a Media
        # candidate should only match library pages, etc. Prevents library book entries
        # (which contain spell names in their titles) from suppressing spell proposals.
        _ENTITY_PAGE_KINDS = {"npc", "pc", "location", "faction", "item", "monster", "spell", "concept", "lore", "library"}
        _KIND_COMPATIBLE_PAGE_KINDS: dict[str, set[str]] = {
            "Spell": {"spell"},
            "NPC": {"npc", "pc"},
            "PC": {"npc", "pc"},
            "Monster": {"monster"},
            "Item": {"item"},
            "Faction": {"faction"},
            "Location": {"location"},
            "Media": {"library", "note", "summary"},  # Discord Summaries index as kind=summary
            "Concept": {"concept", "lore", "npc", "faction", "location"},
        }
        compatible_page_kinds = _KIND_COMPATIBLE_PAGE_KINDS.get(p.kind, _ENTITY_PAGE_KINDS)
        _BOILERPLATE = {"auto nav", "navigation", "weekly knowledge base", "begin auto nav", "end auto nav", "canonical-source"}
        if not outcome:
            hits = _rag_search(base_url, api_key, "arden", p.name, top_k=8)
            for hit in hits:
                hit_kind = hit.get("kind", "")
                if hit_kind not in _ENTITY_PAGE_KINDS:
                    continue  # skip session recaps, Discord summaries, nav chunks
                if hit_kind not in compatible_page_kinds:
                    continue  # skip kind-incompatible pages (e.g. library entry for a Spell)
                title = hit.get("title", "").lower()
                sim = difflib.SequenceMatcher(None, nl, title).ratio()
                # Require either strong similarity OR multi-word overlap; single shared
                # word (e.g. "Chrysalis" inside "Lasselanta Chrysalis Ashcroft") is not
                # enough unless similarity is also high.
                overlap = _entity_name_overlap(nl, title)
                if sim < 0.88 and not overlap:
                    continue
                if sim < 0.60 and overlap:
                    # Overlap fired but names are very different — likely a coincidence
                    aw = set(re.findall(r"[a-z]{3,}", nl))
                    bw = set(re.findall(r"[a-z]{3,}", title))
                    if len(aw & bw) < 2:
                        continue
                existing_path = VAULT / hit["path"].removeprefix("vault/")
                existing_text = read_text(existing_path).lower() if existing_path.exists() else ""

                # Check each evidence excerpt against the existing page content.
                # An excerpt qualifies as "missing content" only if:
                #   1. It actually mentions the entity name (not just retrieved by proximity)
                #   2. It isn't boilerplate (nav, headers, Party Armory table rows)
                #   3. Less than half its substantive words appear in the existing page
                missing: list[str] = []
                name_words = set(re.findall(r"[a-z]{3,}", nl))
                for ev in p.sources:
                    excerpt = ev.get("excerpt", "")
                    if not excerpt:
                        continue
                    el = excerpt.lower()
                    if any(b in el for b in _BOILERPLATE):
                        continue
                    # Skip Party Armory table rows (pipes + numbers pattern)
                    if el.count("|") > 3 and re.search(r"\|\s*\$?\d", el):
                        continue
                    # Skip session/recap header metadata
                    if re.search(r"blog_published|blog_updated|source_url|tags:.*session", el):
                        continue
                    # Must mention the entity name (at least one name word present)
                    if not any(w in el for w in name_words if len(w) >= 4):
                        continue
                    # For near-perfect page matches, skip plan/list mentions that don't
                    # add factual content (e.g. "plan to visit X" or "X is required")
                    if sim >= 0.95:
                        if re.search(r"\b(plan|planning|intend|utilize|proceed|explore|deliver|prioritize)\b", el):
                            continue
                    words = [w for w in re.findall(r"[a-z]{4,}", el) if w not in NEW_ENTITY_SCAFFOLDING]
                    if len(words) < 4:
                        continue
                    present = sum(1 for w in words if w in existing_text)
                    if present / len(words) < 0.5:
                        missing.append(excerpt[:200])

                if missing:
                    # LLM second opinion: word-overlap fires on incidental mentions.
                    # Ask the configured model whether the evidence genuinely adds new
                    # facts about this entity that the existing page lacks.
                    llm_verdict = _llm_judge_update_candidate(
                        name=p.name,
                        kind=p.kind,
                        existing_text=existing_text,
                        evidence_sources=p.sources,
                    )
                    if llm_verdict.get("verdict", "SKIP").upper() == "UPDATE":
                        outcome = "update"
                        update_info = {
                            "name": p.name,
                            "kind": p.kind,
                            "existing_path": hit["path"],
                            "existing_title": hit["title"],
                            "arden_sim": round(sim, 2),
                            "missing_excerpts": missing,
                            "llm_reason": llm_verdict.get("reason", ""),
                            "sources": p.sources,
                        }
                    else:
                        outcome = "suppress"
                        suppress_reason = (
                            f"arden page exists, llm confirmed covered — "
                            f"'{hit['title']}' ({hit['path']}, sim={sim:.2f}): "
                            f"{llm_verdict.get('reason', '')}"
                        )
                else:
                    outcome = "suppress"
                    suppress_reason = (
                        f"arden page exists, fully covered — "
                        f"'{hit['title']}' ({hit['path']}, sim={sim:.2f})"
                    )
                break

        if outcome == "suppress":
            suppressed.append({"name": p.name, "kind": p.kind, "reason": suppress_reason})
        elif outcome == "update":
            update_candidates.append(update_info)
        else:
            kept.append(p)

    return kept, suppressed, update_candidates


def write_new_entity_proposal_report(proposals: list[NewEntityCandidate]) -> None:
    proposals_dir = AUTOMATION_DIR / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    write_json(proposals_dir / "new_entity_proposals.json", [asdict(p) for p in proposals])
    lines: list[str] = ["# New Entity Proposals", ""]
    by_kind: dict[str, list[NewEntityCandidate]] = {}
    for p in proposals:
        by_kind.setdefault(p.kind, []).append(p)
    for kind in IAC_KIND_TO_DIR.keys():
        ps = by_kind.get(kind, [])
        if not ps:
            continue
        lines.append(f"## {kind} ({len(ps)})")
        lines.append("")
        for p in ps:
            lines.append(f"### {p.proposal_id} — {p.name}")
            lines.append(f"**Mentions**: {p.mention_count}")
            if p.nearest_existing:
                lines.append(f"**Nearest existing**: `{p.nearest_existing}` (similarity {p.nearest_distance:.2f})")
            lines.append(f"**Rationale**: {p.rationale}")
            lines.append("**Evidence**:")
            for s in p.sources[:3]:
                ex = (s.get("excerpt", "") or "").replace("|", "\\|").replace("\n", " ")
                lines.append(f"- `{s.get('path','')}` §{s.get('section','')}: > {ex}")
            lines.append("")
    # Append RAG filter results if available
    rag_filter_path = proposals_dir / "new_entity_rag_filter.json"
    if rag_filter_path.exists():
        try:
            rf = json.loads(rag_filter_path.read_text(encoding="utf-8"))
            suppressed = rf.get("suppressed", [])
            update_sug = rf.get("update_suggestions", [])
            if suppressed or update_sug:
                lines.append("---")
                lines.append("")
                if suppressed:
                    lines.append(f"## Suppressed by RAG filter ({len(suppressed)})")
                    lines.append("")
                    for s in suppressed:
                        lines.append(f"- **[{s['kind']}] {s['name']}** — {s['reason']}")
                    lines.append("")
                if update_sug:
                    lines.append(f"## Update suggestions from RAG filter ({len(update_sug)})")
                    lines.append("")
                    for u in update_sug:
                        lines.append(f"### [{u['kind']}] {u['name']}")
                        lines.append(f"**Existing page**: `{u['existing_path']}` (sim={u['arden_sim']})")
                        lines.append("**Missing content from evidence**:")
                        for ex in u.get("missing_excerpts", [])[:2]:
                            lines.append(f"> {ex[:180].replace(chr(10), ' ')}")
                        lines.append("")
        except Exception:
            pass
    (proposals_dir / "new_entity_proposals.md").write_text("\n".join(lines), encoding="utf-8")


def new_entity_verifier_prompt(candidate: NewEntityCandidate) -> str:
    sources_text = "\n\n---\n\n".join(
        f"[{s.get('path','')} §{s.get('section','?')}]\n{s.get('excerpt','')}"
        for s in candidate.sources[:5]
    )
    # Cross-reference the candidate name against the existing vault via vault-rag.
    # This catches concept-duplicates that name-overlap dedup misses — e.g. the
    # candidate has a different surface name but the vault already covers it
    # under an alias or in a related page.
    rag_block = ""
    try:
        rag_hits = vault_rag_search(candidate.name, top_k=4)
        # Drop hits from the candidate's intended target folder if they're the
        # nearest_existing (already cited above), to keep the prompt focused.
        kept: list[dict] = []
        for h in rag_hits:
            if h.get("path") == candidate.nearest_existing:
                continue
            kept.append(h)
        if kept:
            rag_block = "\n\nVAULT CROSS-REFERENCE (vault-rag hits for the candidate name in the wider vault):\n\n" + "\n\n---\n\n".join(
                f"[{h.get('path','?')} §{h.get('section','?')} kind={h.get('kind','?')}]\n{(h.get('text') or '')[:600]}"
                for h in kept[:4]
            )
    except Exception:
        pass
    # Cross-reference the candidate name against the DFRPG MechanicsVault rules
    # collection. If the candidate is a rulebook entry (e.g. the spell "Awaken",
    # the potion "Paut", a monster stat block from DF_Monsters), we don't want
    # to create a campaign-specific stub for it. The verifier should mark it
    # as "rulebook_entry" instead.
    rules_block = ""
    try:
        rules_hits = mechanics_rag_search(candidate.name, top_k=3)
        if rules_hits:
            literal_count = sum(1 for h in rules_hits if h.get("match_type") == "literal")
            header = "\n\nDFRPG RULES CROSS-REFERENCE (MechanicsVault hits):"
            if literal_count > 0:
                header += (
                    f" {literal_count} LITERAL match(es) — the candidate name appears VERBATIM "
                    "in rulebook text below. This is strong evidence the candidate is a "
                    "rulebook_entry, not a campaign-specific entity."
                )
            rules_block = header + "\n\n" + "\n\n---\n\n".join(
                f"[{h.get('book','?')} p.{h.get('printed_page','?')} §{h.get('section','?')} match={h.get('match_type','?')}]\n{(h.get('text') or '')[:500]}"
                for h in rules_hits[:5]
            )
    except Exception:
        pass
    # Check whether the candidate name matches any unique_item_patterns from entity_filters.
    # These patterns identify generic DFRPG magic item vocabulary (Amulet, Wand, Ring, etc.)
    # that frequently signals a rulebook entry. When matched, inject an explicit warning so
    # the verifier doesn't need a literal mechanics-RAG hit to flag it.
    generic_item_warning = ""
    if candidate.kind in ("Item", "Spell"):
        try:
            filters = load_entity_filters()
            for pat_str in filters.get("unique_item_patterns", []):
                if re.search(pat_str, candidate.name):
                    generic_item_warning = (
                        "\n\n⚠️  GENERIC MAGIC ITEM PATTERN MATCH: The candidate name matches a "
                        "pattern associated with standard DFRPG magic item vocabulary "
                        f"(matched pattern: `{pat_str}`). "
                        "Standard named items of this form — 'Amulet of X', 'Wand of X', "
                        "'Ring of X', 'Potion of X', or items whose entire identity is a "
                        "mechanical benefit (fire resistance, poison immunity, haste, stealth) "
                        "with no campaign-specific history — are rulebook_entry. "
                        "Only confirm if the evidence shows this item has a CAMPAIGN-UNIQUE name "
                        "or history beyond its mechanical function (e.g. 'Iron Circlet of Ghanor' "
                        "with documented campaign lore). When in doubt, rulebook_entry."
                    )
                    break
        except Exception:
            pass

    nearest_line = (
        f"\nNearest existing entity in vault/{candidate.canonical_target_dir}/: "
        f"`{candidate.nearest_existing}` (similarity {candidate.nearest_distance:.2f}).\n"
        if candidate.nearest_existing else ""
    )
    return (
        f"You are auditing a proposed new {candidate.kind} entity for the Arden Vul DFRPG/GURPS tabletop campaign vault.\n\n"
        f"Candidate name: \"{candidate.name}\"\n"
        f"Proposed entity kind: {candidate.kind}\n"
        f"Target vault folder: vault/{candidate.canonical_target_dir}/\n"
        f"{nearest_line}\n"
        "EVIDENCE EXCERPTS FROM CANONICAL VAULT SOURCES (Blogspot session recaps, weekly Discord digests, "
        "raw Discord channel rollups, lore notes, and ignored spreadsheet snapshots):\n\n"
        f"{sources_text}"
        f"{rag_block}"
        f"{rules_block}"
        f"{generic_item_warning}\n\n"
        "Decide one of:\n"
        "- \"confirmed\": evidence clearly establishes this as a named CAMPAIGN-SPECIFIC entity of the proposed kind, with no obvious duplicate. The vault cross-reference did not surface this entity under another name AND the rules cross-reference did not show this is a rulebook entry.\n"
        "- \"rulebook_entry\": the DFRPG rules cross-reference clearly shows this is a generic rulebook entry (a published spell like Awaken or Detect Magic; a generic potion like Paut; a monster stat block from DF_Monsters; an Adventurer power). We do NOT create lore-style vault pages for rulebook entries — those are already covered by the rules. Cite the book/page in rationale.\n"
        "- \"wrong_kind\": evidence supports a real entity but the proposed kind is wrong (e.g. it is a Location, not an NPC; or it is a Monster, not an Item; or a Media item, not a plain Item). Set suggested_kind to the correct one.\n"
        "- \"duplicate\": evidence (including the vault cross-reference) indicates this is the same entity as an already-known vault page, possibly under a different surface name. Cite which path in rationale.\n"
        "- \"not_an_entity\": this is a generic noun, scaffolding word, sentence fragment, room/door label, generic monster type, or term that should not become a vault page.\n"
        "- \"ambiguous\": evidence is too thin or contradictory to decide.\n\n"
        "CRITICAL RULE FOR RULEBOOK ENTRIES:\n"
        "If the rules cross-reference contains ANY hit with match=literal that shows the actual "
        "rulebook entry for the candidate name (e.g. an `### Apportation` spell entry, an "
        "`## Salamander Amulet` item entry, a monster stat block header), the candidate is a "
        "rulebook_entry — even if session recaps and Discord rollups document characters using or "
        "discussing it. Routine campaign use of a published spell, item, or monster is NOT enough "
        "to make it campaign-specific:\n"
        "- Vael casting Dispel Magic in Session 50 -> Dispel Magic stays rulebook_entry.\n"
        "- The party brewing a Salamander Amulet -> Salamander Amulet stays rulebook_entry.\n"
        "- A delver fighting a generic ghoul -> Ghoul stays rulebook_entry / not_an_entity.\n"
        "Only mark as confirmed when the campaign introduces a UNIQUELY-NAMED variant or a "
        "substantively different version that the rulebook doesn't cover. Examples that DO warrant "
        "confirmed status:\n"
        "- A behir named \"Korthax the Coiled\" appearing as a recurring antagonist (campaign NPC).\n"
        "- A custom spell \"Scry Gate of Beacon\" with campaign-specific mechanics not in the rules.\n"
        "- A unique magical item like \"The Iron Circlet of Ghanor\" with a campaign-rooted name and history.\n\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "status": "confirmed|rulebook_entry|wrong_kind|duplicate|not_an_entity|ambiguous",\n'
        '  "rationale": "<one sentence grounded in the cited evidence and/or vault cross-reference>",\n'
        '  "suggested_kind": "<NPC|PC|Location|Faction|Item|Monster|Spell|Concept|Media if status=wrong_kind, else empty string>",\n'
        '  "suggested_media_subtype": "<book|map|scroll|data-crystal|library|catalog|journal|inscription if kind=Media and status=confirmed, else empty string>",\n'
        '  "summary": "<one factual sentence suitable for the stub page if status=confirmed, else empty string>"\n'
        "}"
    )


def verify_new_entity_proposals(limit: int = -1) -> list[dict]:
    """Verify new entity proposals with the configured LLM.

    limit=-1 (default) processes all unverified proposals.
    Existing verifications are preserved; only unverified proposals are processed.
    """
    proposals_path = AUTOMATION_DIR / "proposals" / "new_entity_proposals.json"
    if not proposals_path.exists():
        raise RuntimeError("new_entity_proposals.json not found; run propose-new-entities first")
    raw = json.loads(proposals_path.read_text(encoding="utf-8"))
    proposals = [NewEntityCandidate(**r) for r in raw]

    # Load existing verifications so we can skip already-processed proposals
    # and append new results rather than overwriting.
    verifications_path = AUTOMATION_DIR / "proposals" / "new_entity_verifications.json"
    existing: list[dict] = []
    already_verified_ids: set[str] = set()
    if verifications_path.exists():
        try:
            existing = json.loads(verifications_path.read_text(encoding="utf-8"))
            already_verified_ids = {e["proposal_id"] for e in existing}
        except Exception:
            existing = []

    # Only process proposals not yet verified; limit=-1 means all
    pending = [p for p in proposals if p.proposal_id not in already_verified_ids]
    batch = pending if limit < 0 else pending[:limit]

    out: list[dict] = list(existing)
    for p in batch:
        try:
            response = llm_chat_json(new_entity_verifier_prompt(p), timeout=120)
            status = str(response.get("status", "unknown"))
            rationale = str(response.get("rationale", ""))
            suggested_kind = str(response.get("suggested_kind", ""))
            summary = str(response.get("summary", ""))
            media_subtype = str(response.get("suggested_media_subtype", "")).strip().lower()
        except Exception as exc:
            status = "error"
            rationale = str(exc)[:200]
            suggested_kind = ""
            summary = ""
            media_subtype = ""
        result = asdict(p)
        result["verifier_status"] = status
        result["verifier_rationale"] = rationale
        result["verifier_suggested_kind"] = suggested_kind
        result["verifier_summary"] = summary
        result["verifier_media_subtype"] = media_subtype
        out.append(result)
    proposals_dir = AUTOMATION_DIR / "proposals"
    write_json(proposals_dir / "new_entity_verifications.json", out)
    lines: list[str] = ["# New Entity Verifications", ""]
    by_status: dict[str, list[dict]] = {}
    for r in out:
        by_status.setdefault(r["verifier_status"], []).append(r)
    for status in ["confirmed", "rulebook_entry", "wrong_kind", "duplicate", "ambiguous", "not_an_entity", "error", "unknown"]:
        items = by_status.get(status, [])
        if not items:
            continue
        lines.append(f"## {status} ({len(items)})")
        lines.append("")
        for r in items:
            lines.append(f"### {r['proposal_id']} — {r['name']} ({r['kind']})")
            lines.append(f"**Verifier**: {r.get('verifier_rationale','')}")
            if r.get("verifier_summary"):
                lines.append(f"**Suggested summary**: {r['verifier_summary']}")
            if r.get("verifier_suggested_kind"):
                lines.append(f"**Suggested kind**: {r['verifier_suggested_kind']}")
            lines.append("")
    (proposals_dir / "new_entity_verifications.md").write_text("\n".join(lines), encoding="utf-8")
    return out


def slugify_entity_name(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def build_new_entity_stub(name: str, kind: str, summary: str, sources: list[dict], media_subtype: str = "") -> str:
    tag_map = {
        "NPC": "npc",
        "PC": "pc",
        "Location": "location",
        "Faction": "faction",
        "Item": "item",
        "Monster": "monster",
        "Spell": "spell",
        "Concept": "concept",
        "Media": "item",  # Media lives in items/ alongside non-media items
    }
    tag = tag_map.get(kind, kind.lower())
    tags = [tag]
    if kind == "Media":
        # media/<subtype> tag (book/map/scroll/data-crystal/library/catalog/journal/inscription).
        allowed_media = {"book", "map", "scroll", "data-crystal", "library", "catalog", "journal", "inscription"}
        subtype = media_subtype if media_subtype in allowed_media else "general"
        tags.append(f"media/{subtype}")
    tags.append("identity/uncertain")
    lines = ["---", "tags:"]
    for t in tags:
        lines.append(f"  - {t}")
    lines.extend([
        "status: stub",
        "---",
        "",
        f"# {name}",
        "",
    ])
    if summary:
        lines.extend(["## Summary", summary, ""])
    lines.append("## Sources")
    seen: set[str] = set()
    for s in sources:
        path = s.get("path", "")
        if not path or path in seen:
            continue
        seen.add(path)
        # Vault-relative wikilink form (no leading "vault/") matches the
        # convention used elsewhere in the vault.
        wiki_path = path[len("vault/"):] if path.startswith("vault/") else path
        label = Path(path).stem
        lines.append(f"- [[{wiki_path}|{label}]]")
    lines.append("")
    return "\n".join(lines)


def apply_verified_new_entities(apply_changes: bool, limit: int | None = None) -> dict:
    ver_path = AUTOMATION_DIR / "proposals" / "new_entity_verifications.json"
    if not ver_path.exists():
        return {"ok": False, "error": "verifications_not_found", "hint": "Run verify-new-entities first"}
    verifications = json.loads(ver_path.read_text(encoding="utf-8"))
    confirmed = [v for v in verifications if v.get("verifier_status") == "confirmed"]
    if limit is not None:
        confirmed = confirmed[:limit]
    rulebook_count = sum(1 for v in verifications if v.get("verifier_status") == "rulebook_entry")
    results: list[dict] = []
    created: list[str] = []
    for v in confirmed:
        name = v.get("name", "")
        kind = v.get("kind", "")
        # PC pages are maintained by players; never auto-create them. Log so we
        # know the proposer hit one, but don't write to disk.
        if kind == "PC":
            results.append({"name": name, "kind": kind, "action": "skipped", "reason": "PC pages must be created manually"})
            continue
        target_dir_name = IAC_KIND_TO_DIR.get(kind, "")
        if not target_dir_name:
            results.append({"name": name, "kind": kind, "action": "error", "reason": "unsupported kind"})
            continue
        target_dir = VAULT / target_dir_name
        if not target_dir.exists():
            results.append({"name": name, "kind": kind, "action": "error", "reason": f"vault/{target_dir_name}/ missing"})
            continue
        slug = slugify_entity_name(name)
        if not slug:
            results.append({"name": name, "kind": kind, "action": "error", "reason": "name slugified to empty"})
            continue
        target_path = target_dir / f"{slug}.md"
        rel_path = target_path.relative_to(ROOT).as_posix()
        if target_path.exists():
            results.append({"name": name, "kind": kind, "action": "skipped", "reason": "page already exists", "path": rel_path})
            continue
        # Also check every other vault subdirectory — a page may already exist
        # under a different kind folder (e.g. Discord Summaries live in notes/).
        existing_elsewhere = next(
            (p for p in VAULT.rglob(f"{slug}.md") if p != target_path), None
        )
        if existing_elsewhere:
            alt_rel = existing_elsewhere.relative_to(ROOT).as_posix()
            results.append({"name": name, "kind": kind, "action": "skipped", "reason": "page exists elsewhere", "path": alt_rel})
            continue
        content = build_new_entity_stub(
            name, kind, v.get("verifier_summary", ""), v.get("sources", []),
            media_subtype=v.get("verifier_media_subtype", ""),
        )
        if apply_changes:
            target_path.write_text(content, encoding="utf-8")
            created.append(rel_path)
            results.append({"name": name, "kind": kind, "action": "created", "path": rel_path})
        else:
            results.append({
                "name": name, "kind": kind, "action": "would_create", "path": rel_path,
                "preview": content[:300],
            })
    payload: dict = {
        "ok": True,
        "mode": "apply" if apply_changes else "dry-run",
        "confirmed_count": len(confirmed),
        "rulebook_filtered_count": rulebook_count,
        "created_count": len(created),
        "skipped_count": sum(1 for r in results if r["action"] in ("skipped", "error")),
        "results": results,
    }
    if apply_changes and created:
        payload["vault_rag_refresh"] = refresh_vault_rag_safely()
    return payload


def cmd_propose_new_entities(args: argparse.Namespace) -> int:
    source_limit = 0 if getattr(args, "all_sources", False) else args.source_limit
    proposals = build_new_entity_proposals(source_limit=source_limit, candidate_limit=args.limit)
    write_new_entity_proposal_report(proposals)
    by_kind: dict[str, int] = {}
    for p in proposals:
        by_kind[p.kind] = by_kind.get(p.kind, 0) + 1
    summary = {
        "ok": True,
        "proposal_count": len(proposals),
        "by_kind": by_kind,
        "markdown": str(AUTOMATION_DIR / "proposals" / "new_entity_proposals.md"),
        "json": str(AUTOMATION_DIR / "proposals" / "new_entity_proposals.json"),
    }
    print(json.dumps(summary, indent=2))
    return 0


def cmd_verify_new_entities(args: argparse.Namespace) -> int:
    try:
        verifications = verify_new_entity_proposals(limit=args.limit)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    counts: dict[str, int] = {}
    for v in verifications:
        st = v.get("verifier_status", "unknown")
        counts[st] = counts.get(st, 0) + 1
    summary = {
        "ok": True,
        "verified_count": len(verifications),
        "status_counts": counts,
        "markdown": str(AUTOMATION_DIR / "proposals" / "new_entity_verifications.md"),
        "json": str(AUTOMATION_DIR / "proposals" / "new_entity_verifications.json"),
    }
    print(json.dumps(summary, indent=2))
    return 0


def cmd_apply_verified_new_entities(args: argparse.Namespace) -> int:
    result = apply_verified_new_entities(apply_changes=args.apply, limit=args.limit)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


# ---- vault walk cursor (rotates through every article over time) ----

VAULT_WALK_CURSOR_PATH = AUTOMATION_DIR / "vault_walk_cursor.json"
VAULT_WALK_DIRS = ("npcs", "pcs", "locations", "factions", "items", "monsters", "spells")


def vault_walk_eligible_articles() -> list[str]:
    """Sorted repo-relative paths of every walkable article."""
    paths: list[str] = []
    for sub in VAULT_WALK_DIRS:
        root = VAULT / sub
        if not root.exists():
            continue
        for p in sorted(root.glob("*.md")):
            if p.stem.lower() in {"index", "readme"}:
                continue
            paths.append(p.relative_to(ROOT).as_posix())
    return paths


def vault_walk_load_cursor() -> dict:
    if not VAULT_WALK_CURSOR_PATH.exists():
        return {"last_path": "", "wraps": 0, "started_at": datetime.now(timezone.utc).isoformat()}
    try:
        return json.loads(VAULT_WALK_CURSOR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"last_path": "", "wraps": 0, "started_at": datetime.now(timezone.utc).isoformat()}


def vault_walk_save_cursor(cursor: dict) -> None:
    VAULT_WALK_CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    cursor["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(VAULT_WALK_CURSOR_PATH, cursor)


def vault_walk_next(n: int, save: bool = True) -> list[str]:
    """Return the next n article paths after the cursor and (optionally) advance the cursor."""
    if n <= 0:
        return []
    paths = vault_walk_eligible_articles()
    if not paths:
        return []
    cursor = vault_walk_load_cursor()
    last = cursor.get("last_path", "")
    start_idx = 0
    if last:
        try:
            start_idx = paths.index(last) + 1
        except ValueError:
            start_idx = 0
    selected: list[str] = []
    wraps = int(cursor.get("wraps", 0))
    idx = start_idx
    for _ in range(min(n, len(paths))):
        if idx >= len(paths):
            idx = 0
            wraps += 1
        selected.append(paths[idx])
        idx += 1
    if save and selected:
        cursor["last_path"] = selected[-1]
        cursor["wraps"] = wraps
        cursor["total_articles"] = len(paths)
        vault_walk_save_cursor(cursor)
    return selected


def cmd_vault_walk_status(_: argparse.Namespace) -> int:
    paths = vault_walk_eligible_articles()
    cursor = vault_walk_load_cursor()
    last = cursor.get("last_path", "")
    pos = (paths.index(last) + 1) if last and last in paths else 0
    print(json.dumps({
        "ok": True,
        "total_articles": len(paths),
        "cursor_position": pos,
        "last_path": last,
        "wraps_completed": cursor.get("wraps", 0),
        "started_at": cursor.get("started_at"),
        "updated_at": cursor.get("updated_at"),
    }, indent=2))
    return 0


# ---- metadata enrichment lane ----

METADATA_EDIT_TYPES = {"add_tag", "add_related_entity", "add_identity_hint", "add_alias"}
METADATA_TAG_PATTERN = re.compile(
    r"^(?:type|status|title|faction|culture|site|session|identity)/[a-z0-9][a-z0-9-]*$"
)
METADATA_IDENTITY_TAGS = {"identity/uncertain", "identity/possible-alias", "identity/possible-duplicate"}


def metadata_edit_proposer_prompt(item: ArticleQueueItem, article_text: str, source_chunks: list[dict]) -> str:
    evidence = "\n\n---\n\n".join(
        f"[{chunk.get('path','?')} §{chunk.get('section','?')}]\n{(chunk.get('text') or '')[:1400]}"
        for chunk in source_chunks
    )
    return (
        "You maintain retrieval metadata for one canonical Obsidian page in an Arden Vul campaign vault.\n\n"
        f"PAGE: {item.path}\nTITLE: {item.title}\nKIND: {item.kind}\n\n"
        f"CURRENT PAGE:\n---\n{article_text[:4000]}\n---\n\n"
        f"CITABLE VAULT EVIDENCE:\n{evidence}\n\n"
        "Propose only small metadata additions that make related campaign evidence easier to retrieve. "
        "Every proposal must be supported by the current page or cited vault evidence. Tags and relationships are "
        "retrieval hints, not proof of identity. Never merge pages and never infer that two entities are identical merely "
        "because they share a type or location.\n\n"
        "Allowed proposal types:\n"
        "- add_tag: one namespaced tag using type/<slug>, status/<slug>, title/<slug>, faction/<slug>, culture/<slug>, "
        "site/<slug>, session/<id>, or one of identity/uncertain, identity/possible-alias, identity/possible-duplicate. "
        "Use type/ghost for a ghost. Apply culture tags only to the page subject's supported culture, not the era or "
        "culture of a related site.\n"
        "- add_related_entity: one existing canonical vault target as an explicit wikilink, such as "
        "[[npcs/Nyema.md|Nyema]]. Use only relationships supported by evidence.\n"
        "- add_identity_hint: one evidence-scoped descriptive phrase used before a canonical identity was known, such as "
        "angry scary ghost. This is searchable metadata, not a global alias and not proof of identity.\n"
        "- add_alias: one verified alternate proper name, epithet, or spelling for this exact canonical entity. Do not use "
        "generic descriptions or path-like values as aliases; use add_identity_hint for generic historical descriptions.\n\n"
        "Avoid duplicate values already present in the page. Return at most 6 proposals. Every proposal must cite a short "
        "verbatim excerpt from a vault path. Return strict JSON only:\n"
        "{\n"
        '  "proposals": [\n'
        '    {"proposal_type":"add_tag","value":"type/ghost","rationale":"<why>",'
        '"sources":[{"path":"vault/npcs/Example.md","section":"Summary","excerpt":"<verbatim quote>"}]}\n'
        "  ]\n"
        "}\n"
    )


def normalize_related_entity(value: str) -> str | None:
    match = re.fullmatch(r"\[\[([^|\]]+?)(?:\|([^\]]+))?\]\]", value.strip())
    if not match:
        return None
    target = match.group(1).strip()
    if target.startswith("vault/"):
        target = target[len("vault/"):]
    if not target.endswith(".md"):
        target += ".md"
    if not (VAULT / target).exists():
        return None
    label = normalize_space(match.group(2) or Path(target).stem)
    return f"[[{target}|{label}]]"


def metadata_proposal_value(proposal_type: str, value: str) -> str | None:
    value = normalize_space(value)
    if not value or len(value) > 120:
        return None
    if proposal_type == "add_tag":
        value = value.lower()
        if not METADATA_TAG_PATTERN.fullmatch(value):
            return None
        if value.startswith("identity/") and value not in METADATA_IDENTITY_TAGS:
            return None
        return value
    if proposal_type == "add_related_entity":
        return normalize_related_entity(value)
    if proposal_type == "add_identity_hint":
        return value if len(value) >= 4 and "[[" not in value and "]]" not in value else None
    if proposal_type == "add_alias":
        if "/" in value or "[[" in value or "]]" in value or len(value.split()) > 8:
            return None
        return value
    return None


def metadata_edit_key(proposal: MetadataEditProposal) -> str:
    return hashlib.sha256(
        f"{proposal.article_path}|{proposal.proposal_type}|{proposal.value}".encode("utf-8")
    ).hexdigest()[:12]


def build_metadata_edit_proposals(
    article_paths: list[Path] | None = None,
    limit: int = 5,
    top_k_per_query: int = 3,
) -> list[MetadataEditProposal]:
    if article_paths:
        items = [build_article_queue_item(path) for path in article_paths]
        selected = [item for item in items if item is not None]
    else:
        selected = build_article_queue(limit=limit)
    proposals: list[MetadataEditProposal] = []
    for item in selected:
        path = ROOT / item.path
        article_text = read_text(path)
        chunks = [{
            "path": item.path,
            "section": "current canonical page",
            "text": strip_frontmatter_only(article_text),
        }]
        chunks.extend(gather_article_research_chunks(item, top_k_per_query=top_k_per_query, max_chunks=8))
        try:
            response = llm_chat_json(metadata_edit_proposer_prompt(item, article_text, chunks), timeout=180)
        except Exception:
            continue
        for raw in (response.get("proposals") or [])[:6]:
            if not isinstance(raw, dict):
                continue
            proposal_type = str(raw.get("proposal_type", "")).strip()
            if proposal_type not in METADATA_EDIT_TYPES:
                continue
            value = metadata_proposal_value(proposal_type, str(raw.get("value", "")))
            if not value:
                continue
            sources = []
            for src in raw.get("sources") or []:
                if isinstance(src, dict) and is_citable_article_source(str(src.get("path", ""))):
                    sources.append({
                        "path": str(src.get("path", "")),
                        "section": str(src.get("section", "")),
                        "excerpt": str(src.get("excerpt", ""))[:500],
                    })
            if not sources:
                continue
            proposal = MetadataEditProposal(
                article_path=item.path,
                article_title=item.title,
                article_kind=item.kind,
                proposal_type=proposal_type,
                value=value,
                rationale=str(raw.get("rationale", "")).strip(),
                sources=sources,
            )
            proposal.proposal_id = metadata_edit_key(proposal)
            proposals.append(proposal)
    unique: dict[tuple[str, str, str], MetadataEditProposal] = {}
    for proposal in proposals:
        unique[(proposal.article_path, proposal.proposal_type, proposal.value.lower())] = proposal
    return sorted(unique.values(), key=lambda item: (item.article_path, item.proposal_type, item.value.lower()))


def write_metadata_edit_report(proposals: list[MetadataEditProposal]) -> None:
    out = AUTOMATION_DIR / "proposals"
    write_json(out / "metadata_edit_proposals.json", [asdict(item) for item in proposals])
    lines = ["# Metadata Edit Proposals", ""]
    for item in proposals:
        lines.extend([
            f"## {item.proposal_id} - {item.article_path}",
            f"- Type: `{item.proposal_type}`",
            f"- Value: `{item.value}`",
            f"- Rationale: {item.rationale}",
            "",
        ])
    (out / "metadata_edit_proposals.md").write_text("\n".join(lines), encoding="utf-8")


def metadata_edit_verifier_prompt(proposal: MetadataEditProposal) -> str:
    blocks = []
    for src in proposal.sources:
        path = ROOT / src["path"]
        text = read_text(path) if path.exists() else ""
        needle = src.get("excerpt", "")
        index = text.find(needle) if needle else -1
        window = text[max(0, index - 500):index + len(needle) + 900] if index >= 0 else text[:2200]
        blocks.append(f"[{src['path']} §{src.get('section','?')}]\n{window}")
    return (
        "Verify one retrieval-metadata proposal for a canonical Arden Vul vault page. Use only the cited source windows. "
        "Tags, related entities, aliases, and identity hints must be supported by evidence. A generic historical "
        "description belongs in add_identity_hint, not add_alias. A shared type or site does not prove two entities are "
        "identical. Return strict JSON only.\n\n"
        f"PAGE: {proposal.article_path}\nTYPE: {proposal.proposal_type}\nVALUE: {proposal.value}\n"
        f"RATIONALE: {proposal.rationale}\n\nSOURCES:\n" + "\n\n---\n\n".join(blocks) + "\n\n"
        '{"status":"supported|contradicted|ambiguous|not_found","rationale":"<one sentence>",'
        '"evidence":"<short verbatim quote if supported, else empty>"}'
    )


def verify_metadata_edit_proposals(limit: int | None = None) -> list[dict]:
    path = AUTOMATION_DIR / "proposals" / "metadata_edit_proposals.json"
    if not path.exists():
        raise RuntimeError("metadata_edit_proposals.json not found; run propose-metadata-edits first")
    proposals = [MetadataEditProposal(**item) for item in json.loads(path.read_text(encoding="utf-8"))]
    selected = proposals if limit is None else proposals[:limit]
    out = []
    for proposal in selected:
        try:
            response = llm_chat_json(metadata_edit_verifier_prompt(proposal), timeout=180)
            status = str(response.get("status", "unknown"))
            rationale = str(response.get("rationale", ""))
            evidence = str(response.get("evidence", ""))
        except Exception as exc:
            status, rationale, evidence = "error", str(exc)[:200], ""
        item = asdict(proposal)
        item.update(verifier_status=status, verifier_rationale=rationale, verifier_evidence=evidence)
        out.append(item)
    proposals_dir = AUTOMATION_DIR / "proposals"
    write_json(proposals_dir / "metadata_edit_verifications.json", out)
    lines = ["# Metadata Edit Verifications", ""]
    for item in out:
        lines.extend([
            f"## {item['proposal_id']} - {item['article_path']}",
            f"- Status: `{item['verifier_status']}`",
            f"- Type: `{item['proposal_type']}`",
            f"- Value: `{item['value']}`",
            f"- Verifier: {item['verifier_rationale']}",
            "",
        ])
    (proposals_dir / "metadata_edit_verifications.md").write_text("\n".join(lines), encoding="utf-8")
    return out


def add_frontmatter_list_item(text: str, key: str, value: str) -> tuple[str, bool, str]:
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm_match:
        return text, False, "no frontmatter"
    if value.lower() in {item.lower() for item in frontmatter_list(text, key)}:
        return text, False, "already present"
    fm = fm_match.group(1)
    rest = text[fm_match.end():]
    match = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$", fm, re.MULTILINE)
    if match:
        line = match.group(0)
        inline = match.group(1).strip()
        if inline in {"", "[]"}:
            remainder = fm[match.end():]
            following_list = re.match(r"\n(?P<indent>\s*)-\s+", remainder)
            indent = following_list.group("indent") if following_list else "  "
            replacement = f"{key}:\n{indent}- {value}"
        elif inline.startswith("[") and inline.endswith("]"):
            items = [part.strip() for part in inline[1:-1].split(",") if part.strip()]
            replacement = f"{key}: [{', '.join(items + [value])}]"
        else:
            replacement = line + f"\n  - {value}"
        fm = fm.replace(line, replacement, 1)
    else:
        fm = fm.rstrip() + f"\n{key}:\n  - {value}"
    return "---\n" + fm + "\n---\n" + rest, True, f"added {key}"


def apply_verified_metadata_edits(apply_changes: bool, limit: int | None = None) -> dict:
    path = AUTOMATION_DIR / "proposals" / "metadata_edit_verifications.json"
    if not path.exists():
        return {"ok": False, "error": "verifications_not_found"}
    supported = [item for item in json.loads(path.read_text(encoding="utf-8")) if item.get("verifier_status") == "supported"]
    if limit is not None:
        supported = supported[:limit]
    key_by_type = {
        "add_tag": "tags",
        "add_related_entity": "related_entities",
        "add_identity_hint": "identity_hints",
        "add_alias": "aliases",
    }
    by_article: dict[str, list[dict]] = {}
    for item in supported:
        by_article.setdefault(item["article_path"], []).append(item)
    results = []
    for article_path, edits in by_article.items():
        full_path = ROOT / article_path
        if not full_path.exists():
            results.append({"article_path": article_path, "applied": 0, "error": "file_not_found"})
            continue
        text = read_text(full_path)
        applied = 0
        for item in edits:
            key = key_by_type.get(item.get("proposal_type", ""))
            value = metadata_proposal_value(str(item.get("proposal_type", "")), str(item.get("value", "")))
            if not key or not value:
                continue
            text, changed, _reason = add_frontmatter_list_item(text, key, value)
            if changed:
                applied += 1
        if applied and apply_changes:
            full_path.write_text(text, encoding="utf-8")
        results.append({"article_path": article_path, "applied": applied})
    payload = {
        "ok": True,
        "mode": "apply" if apply_changes else "dry-run",
        "supported_count": len(supported),
        "articles_touched": len(by_article),
        "total_applied": sum(item["applied"] for item in results),
        "results": results,
    }
    if apply_changes and payload["total_applied"]:
        payload["vault_rag_refresh"] = refresh_vault_rag_safely()
    return payload


# ---- article-edit research lane ----

ARTICLE_EDIT_ADDITION_TYPES = {"append_bullet_to_section", "add_alias", "extend_summary"}


def article_edit_proposer_prompt(
    article_text: str,
    source_chunks: list[dict],
    private_hints: list[dict],
    article_path: str,
    article_title: str,
    article_kind: str,
) -> str:
    article_excerpt = article_text[:2000]
    blocks = []
    for c in source_chunks:
        blocks.append(
            f"[{c.get('path','?')} §{c.get('section','?')} kind={c.get('kind','?')}]\n{(c.get('text') or '')[:900]}"
        )
    sources_text = "\n\n---\n\n".join(blocks)
    hint_blocks = []
    for hint in private_hints:
        hint_blocks.append(
            f"[PRIVATE AUTOMATION HINT: {hint.get('path','?')}]\n{(hint.get('text') or '')[:1200]}"
        )
    hints_text = "\n\n---\n\n".join(hint_blocks) or "(none)"
    return (
        "You are an Obsidian vault research assistant for the Arden Vul DFRPG tabletop campaign.\n\n"
        f"CURRENT ARTICLE PAGE: {article_path}\n"
        f"Title: {article_title}\n"
        f"Kind: {article_kind}\n"
        "Content:\n---\n"
        f"{article_excerpt}\n"
        "---\n\n"
        "SOURCE EVIDENCE retrieved from canonical vault sources (Blogspot recaps in vault/sessions/, "
        "weekly Discord digests in vault/notes/, lore docs in vault/lore/, and ignored spreadsheet snapshots):\n\n"
        f"{sources_text}\n\n"
        "YOUR TASK: Propose at most 3 small, sourced additions to the article based ONLY on the source evidence above. "
        "Be conservative: do not invent facts, do not paraphrase loosely, do not propose changes already present in the article.\n\n"
        "For library and media pages, prioritize recent citable evidence that explicitly names the current work. If the "
        "page has TODO placeholders in `Content` or `Reading Events`, propose concise bullets for those sections from an "
        "explicitly named reading result before exploring loosely related works or older similarly named research. A raw "
        "private hint may help locate the curated digest, but the proposed bullet must cite the curated digest. When a "
        "curated digest explicitly states that the work was read and gives its result, do not return an empty proposal "
        "list: add a `Content` bullet summarizing the revealed information and a `Reading Events` bullet linking the "
        "digest. Use this form where practical: `- [[notes/Discord Summary YYYY-WNN.md|Discord Summary YYYY-WNN]] - ...`.\n\n"
        "Allowed addition types:\n"
        "- \"append_bullet_to_section\": Add ONE sourced bullet to an existing H2 section (e.g. \"Sessions\", "
        "\"Appears In\", \"Notes\", \"Connections\", \"Content\", \"Reading Events\"). Include relevant wikilinks. "
        "target_section must match an existing H2 heading in the article. "
        "PREFER THIS TYPE over extend_summary when adding a new fact.\n"
        "- \"add_alias\": Add ONE alternate name to the frontmatter aliases list. target_section must be \"aliases\".\n"
        "- \"extend_summary\": Add ONE short factual sentence to the Summary section. target_section must be \"Summary\". "
        "Use only when strongly supported AND the new sentence introduces information that is not already in the Summary. "
        "Do NOT propose extend_summary text whose words substantially overlap with the existing Summary content — that "
        "produces a near-duplicate restatement and adds noise. If the fact is new but could go elsewhere, prefer "
        "append_bullet_to_section in Notes/History/Appears In.\n\n"
        "Every proposal MUST cite a specific source excerpt by path and section. The excerpt should be a short verbatim "
        "quote from the source content, not a paraphrase.\n\n"
        "PRIVATE AUTOMATION HINTS below come from raw local Discord rollups. They may help you identify a topic or ask "
        "for better retrieval, but they are NOT publishable evidence. Never cite them. Never propose a factual addition "
        "supported only by a private hint. A proposed fact must also appear in the citable SOURCE EVIDENCE above.\n\n"
        f"{hints_text}\n\n"
        "If this evidence bundle is incomplete, return up to 3 focused `research_queries`. The caller will search the "
        "campaign RAG again and ask you to reconsider with expanded evidence. Use an empty list when no follow-up "
        "retrieval is needed.\n\n"
        "Return strict JSON only. No commentary, no markdown fences, no preamble. Schema:\n"
        "{\n"
        '  "research_queries": ["optional focused RAG query"],\n'
        '  "context_sessions": [],\n'
        '  "proposals": [\n'
        "    {\n"
        '      "addition_type": "append_bullet_to_section",\n'
        '      "target_section": "Sessions",\n'
        '      "proposed_text": "- [[sessions/Session 27 - Tomb of Ptoh-Ristus.md|Session 27 - Tomb of Ptoh-Ristus]]",\n'
        '      "rationale": "Article mentions Ptoh-Ristus but lacks the canonical session reference.",\n'
        '      "sources": [\n'
        '        {"path": "vault/sessions/Session 27 - Tomb of Ptoh-Ristus.md", "section": "Full Recap", "excerpt": "<short verbatim quote>"}\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "context_sessions: If the evidence is insufficient because the article needs a SPECIFIC session's full text "
        "(not just RAG chunks), list the exact session file names here (e.g. 'Session 27 - The Tomb of Ptoh-Ristus'). "
        "This flags the article for a targeted --from-session run. Only populate when you can identify a specific "
        "named session that would provide the missing context. Leave empty otherwise.\n\n"
        "Return {\"research_queries\": [], \"context_sessions\": [], \"proposals\": []} if the evidence does not support any addition."
    )


def media_article_edit_proposer_prompt(
    article_text: str,
    source_chunks: list[dict],
    private_hints: list[dict],
    article_path: str,
    article_title: str,
) -> str:
    evidence = "\n\n---\n\n".join(
        f"[{chunk.get('path','?')} §{chunk.get('section','?')}]\n{(chunk.get('text') or '')[:1400]}"
        for chunk in source_chunks
    )
    hints = "\n\n---\n\n".join(
        f"[PRIVATE AUTOMATION HINT: {hint.get('path','?')}]\n{(hint.get('text') or '')[:900]}"
        for hint in private_hints
    ) or "(none)"
    return (
        "You maintain one library/media page in an Obsidian campaign vault.\n\n"
        f"PAGE: {article_path}\nTITLE: {article_title}\n\n"
        f"CURRENT PAGE:\n---\n{article_text[:2200]}\n---\n\n"
        "CITABLE CURATED EVIDENCE:\n"
        f"{evidence}\n\n"
        "PRIVATE AUTOMATION HINTS (local raw Discord; never cite these and never publish a fact supported only here):\n"
        f"{hints}\n\n"
        "Extract improvements for this exact named work. When curated evidence says this work was read and states the "
        "result, propose both:\n"
        "1. one concise `Content` bullet describing the revealed information; and\n"
        "2. one `Reading Events` bullet linking the curated digest and stating that the work was read.\n\n"
        "Use only existing H2 sections. Do not return an empty list when CITABLE CURATED EVIDENCE explicitly names this "
        "work and gives its reading result. Do not cite private hints. For `Reading Events`, link the digest with its own "
        "title as the label, for example `- [[notes/Discord Summary 2026-W21.md|Discord Summary 2026-W21]] - Vael read "
        "this work.` Return strict JSON only:\n"
        "{\n"
        '  "research_queries": [],\n'
        '  "proposals": [\n'
        "    {\n"
        '      "addition_type": "append_bullet_to_section",\n'
        '      "target_section": "Content",\n'
        '      "proposed_text": "- <concise sourced fact>",\n'
        '      "rationale": "<short reason>",\n'
        '      "sources": [{"path": "vault/notes/Discord Summary YYYY-WNN.md", "section": "<section label>", "excerpt": "<short verbatim quote>"}]\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def extract_session_article_paths(session_path: Path) -> list[Path]:
    """Return deduplicated vault paths for every location/npc/item/faction wikilinked in a session file."""
    text = read_text(session_path)
    entity_dirs = {"locations", "npcs", "items", "factions"}
    pattern = re.compile(r"\[\[(" + "|".join(entity_dirs) + r")/([^\]|]+?)(?:\.md)?(?:\|[^\]]+)?\]\]")
    seen: set[str] = set()
    paths: list[Path] = []
    for m in pattern.finditer(text):
        folder, name = m.group(1), m.group(2)
        key = f"{folder}/{name}"
        if key in seen:
            continue
        seen.add(key)
        candidate = VAULT / folder / f"{name}.md"
        if candidate.exists():
            paths.append(candidate)
    return paths


def gather_article_research_chunks(
    item: ArticleQueueItem,
    top_k_per_query: int = 5,
    max_chunks: int = 12,
    sessions_only: bool = False,
) -> list[dict]:
    """Collect candidate research chunks from vault-rag for an article.
    Reorders results so chunks that literally mention the article title come first,
    since multi-topic chunks often bury the most relevant evidence below pure name-similarity.
    When sessions_only=True, Discord summary chunks are skipped and only vault/sessions/ chunks
    are returned — use this for session-first enrichment to avoid Discord contamination."""
    seen: set[tuple] = set()
    if sessions_only:
        chunks = []
    else:
        chunks = curated_summary_literal_hits(item)
    for hit in chunks:
        seen.add((hit.get("path"), hit.get("section")))
    for q in list(item.queries)[:6]:
        try:
            hits = vault_rag_search(q, top_k=max(top_k_per_query * 3, 9))
        except Exception:
            continue
        for h in hits:
            if h.get("path") == item.path:
                continue
            if sessions_only and not (h.get("path") or "").startswith("vault/sessions/"):
                continue
            key = (h.get("path"), h.get("section"))
            if key in seen:
                continue
            seen.add(key)
            chunks.append(h)
            if len(chunks) >= max_chunks:
                break
        if len(chunks) >= max_chunks:
            break
    # Boost chunks that literally contain the article title.
    title_l = item.title.lower()
    def _key(h: dict) -> tuple[int, float]:
        text = (h.get("text") or "").lower()
        has_title = 0 if title_l in text else 1
        return (has_title, h.get("distance") if h.get("distance") is not None else 1.0)
    chunks.sort(key=_key)
    return chunks


def article_literal_phrases(item: ArticleQueueItem) -> list[str]:
    candidates = [item.title]
    if item.title.lower().startswith("the "):
        candidates.append(item.title[4:])
    candidates.extend(re.findall(r"\(([^)]+)\)", item.title))
    phrases: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        phrase = normalize_space(candidate)
        if len(phrase) < 5 or phrase.lower() in seen:
            continue
        seen.add(phrase.lower())
        phrases.append(phrase)
    return phrases


def curated_summary_literal_hits(item: ArticleQueueItem, max_hits: int = 4, width: int = 900) -> list[dict]:
    """Surface exact title-bearing digest excerpts before semantic retrieval."""
    hits: list[dict] = []
    for path in reversed(all_discord_summary_paths()):
        text = read_text(path)
        lower = text.lower()
        for phrase in article_literal_phrases(item):
            index = lower.find(phrase.lower())
            if index < 0:
                continue
            start = max(0, index - width)
            end = min(len(text), index + width)
            hits.append({
                "path": path.relative_to(ROOT).as_posix(),
                "section": "curated Discord summary literal match",
                "kind": "summary",
                "title": path.stem,
                "distance": -1.0,
                "match_type": "literal-local-curated",
                "text": text[start:end],
            })
            break
        if len(hits) >= max_hits:
            break
    return hits


PRIVATE_HINT_STOPWORDS = {
    "arden", "book", "campaign", "contents", "discord", "downtime", "read", "source", "summary", "the", "vul",
}


def private_discord_hint_search(query: str, max_hits: int = 4, width: int = 900) -> list[dict]:
    """Retrieve local-only Discord context for Heavy. These hints are never citable."""
    rollup_root = load_local_sources().get("discord_rollup_root")
    if not rollup_root or not Path(rollup_root).exists():
        return []
    terms = [
        term.lower()
        for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]{2,}", query)
        if term.lower() not in PRIVATE_HINT_STOPWORDS
    ]
    if not terms:
        return []
    hits: list[dict] = []
    for path in sorted(Path(rollup_root).glob("week-ending-*/channels/*.md"), reverse=True):
        text = read_text(path)
        lower = text.lower()
        matched = [term for term in terms if term in lower]
        if not matched:
            continue
        score = len(matched)
        phrase = normalize_space(query).lower()
        if phrase and phrase in lower:
            score += 10
            index = lower.index(phrase)
        else:
            index = min(lower.index(term) for term in matched)
        start = max(0, index - width)
        end = min(len(text), index + width)
        hits.append({
            "path": str(path),
            "score": score,
            "text": text[start:end],
        })
    hits.sort(key=lambda hit: (-int(hit["score"]), str(hit["path"])), reverse=False)
    return hits[:max_hits]


def gather_private_discord_hints(item: ArticleQueueItem, max_hits: int = 6) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    hints: list[dict] = []
    for query in list(item.queries)[:4]:
        for hit in private_discord_hint_search(query):
            key = (str(hit.get("path", "")), str(hit.get("text", "")))
            if key in seen:
                continue
            seen.add(key)
            hints.append(hit)
            if len(hints) >= max_hits:
                return hints
    return hints


def is_citable_article_source(path: str) -> bool:
    if path.startswith("vault/"):
        full_path = ROOT / path
        return full_path.exists() and full_path.is_relative_to(VAULT)
    return path == "data/automation/sources/group_spreadsheet_snapshot.md" and (ROOT / path).exists()


def normalize_vault_wikilinks(text: str) -> str:
    return text.replace("[[vault/", "[[")


def remove_section_todo(text: str, target_section: str) -> str:
    pattern = re.compile(
        rf"(^## {re.escape(target_section)}\s*$)(.*?)(?=^## |\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return text
    body = re.sub(r"(?m)^TODO:.*\n?", "", match.group(2))
    return text[:match.start(2)] + body + text[match.end(2):]


def expand_article_research_chunks(chunks: list[dict], queries: list[str], top_k_per_query: int, max_chunks: int = 20) -> list[dict]:
    seen = {(hit.get("path"), hit.get("section"), hit.get("text")) for hit in chunks}
    expanded = list(chunks)
    for query in queries[:3]:
        query = normalize_space(query)
        if not query:
            continue
        try:
            hits = vault_rag_search(query, top_k=max(top_k_per_query * 3, 9))
        except Exception:
            continue
        for hit in hits:
            key = (hit.get("path"), hit.get("section"), hit.get("text"))
            if key in seen:
                continue
            seen.add(key)
            expanded.append(hit)
            if len(expanded) >= max_chunks:
                return expanded
    return expanded


def build_article_edit_proposals(
    article_paths: list[Path] | None = None,
    limit: int = 5,
    max_additions_per_article: int = 3,
    top_k_per_query: int = 5,
    sessions_only: bool = False,
) -> list[ArticleEditProposal]:
    queue = build_article_queue(limit=200)
    if article_paths:
        wanted_paths: list[str] = []
        for p in article_paths:
            try:
                wanted_paths.append(p.relative_to(ROOT).as_posix() if p.is_absolute() else p.as_posix())
            except ValueError:
                wanted_paths.append(p.as_posix())
        # Preserve caller order; fall back to building a queue item for paths
        # that are outside the weakest-N queue so walk-cursor articles still process.
        by_path = {it.path: it for it in queue}
        items = []
        for rel in wanted_paths:
            if rel in by_path:
                items.append(by_path[rel])
                continue
            built = build_article_queue_item(ROOT / rel)
            if built is not None:
                items.append(built)
    else:
        items = queue[:limit]
    proposals: list[ArticleEditProposal] = []
    for item in items:
        path = ROOT / item.path
        if not path.exists():
            continue
        article_text = read_text(path)
        chunks = gather_article_research_chunks(item, top_k_per_query=top_k_per_query, sessions_only=sessions_only)
        private_hints = [] if sessions_only else gather_private_discord_hints(item)
        exact_digest_hits: list[dict] = []
        if path.parent.name == "library":
            exact_digest_hits = curated_summary_literal_hits(item)
            if exact_digest_hits:
                exact_keys = {(hit.get("path"), hit.get("section"), hit.get("text")) for hit in exact_digest_hits}
                supplemental = [
                    hit for hit in chunks
                    if (hit.get("path"), hit.get("section"), hit.get("text")) not in exact_keys
                ]
                chunks = exact_digest_hits + supplemental[:4]
                private_hints = private_hints[:2]
        if not chunks:
            continue
        prompt = (
            media_article_edit_proposer_prompt(article_text, chunks, private_hints, item.path, item.title)
            if path.parent.name == "library" and exact_digest_hits
            else article_edit_proposer_prompt(article_text, chunks, private_hints, item.path, item.title, item.kind)
        )
        try:
            response = llm_chat_json(prompt, timeout=120)
        except Exception:
            continue
        research_queries = response.get("research_queries") or []
        if isinstance(research_queries, list) and research_queries:
            expanded_chunks = expand_article_research_chunks(
                chunks,
                [str(query) for query in research_queries],
                top_k_per_query=top_k_per_query,
            )
            if len(expanded_chunks) > len(chunks):
                try:
                    response = llm_chat_json(
                        article_edit_proposer_prompt(article_text, expanded_chunks, private_hints, item.path, item.title, item.kind),
                        timeout=120,
                    )
                except Exception:
                    continue
        # If LLM flagged specific sessions needed and produced no proposals, write context_needed marker.
        context_sessions = [str(s) for s in (response.get("context_sessions") or []) if s]
        raw_proposals = response.get("proposals") or []
        if context_sessions and not raw_proposals:
            _write_context_needed(path, context_sessions)
        for raw in raw_proposals[:max_additions_per_article]:
            if not isinstance(raw, dict):
                continue
            addition_type = str(raw.get("addition_type", "")).strip()
            if addition_type not in ARTICLE_EDIT_ADDITION_TYPES:
                continue
            target_section = str(raw.get("target_section", "")).strip()
            proposed_text = normalize_vault_wikilinks(str(raw.get("proposed_text", "")).strip())
            rationale = str(raw.get("rationale", "")).strip()
            sources: list[dict] = []
            for src in (raw.get("sources") or []):
                if isinstance(src, dict) and is_citable_article_source(str(src.get("path", ""))):
                    sources.append({
                        "path": str(src.get("path", "")),
                        "section": str(src.get("section", "")),
                        "excerpt": str(src.get("excerpt", ""))[:400],
                    })
            if not sources or not proposed_text or not target_section:
                continue
            proposal_id = hashlib.sha1(
                f"{item.path}|{addition_type}|{target_section}|{proposed_text}".encode("utf-8")
            ).hexdigest()[:12]
            proposals.append(ArticleEditProposal(
                article_path=item.path,
                article_title=item.title,
                article_kind=item.kind,
                article_score=item.score,
                addition_type=addition_type,
                target_section=target_section,
                proposed_text=proposed_text,
                rationale=rationale,
                sources=sources,
                status="needs-verification",
                proposal_id=proposal_id,
            ))
    return proposals


def write_article_edit_proposal_report(proposals: list[ArticleEditProposal]) -> None:
    proposals_dir = AUTOMATION_DIR / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    write_json(proposals_dir / "article_edit_proposals.json", [asdict(p) for p in proposals])
    lines: list[str] = ["# Article Edit Proposals", ""]
    by_article: dict[str, list[ArticleEditProposal]] = {}
    for p in proposals:
        by_article.setdefault(p.article_path, []).append(p)
    for article_path, props in sorted(by_article.items()):
        lines.append(f"## {article_path}")
        first = props[0]
        lines.append(f"score={first.article_score} kind={first.article_kind}")
        lines.append("")
        for p in props:
            lines.append(f"### {p.proposal_id} — `{p.addition_type}` → `{p.target_section}`")
            lines.append(f"**Proposed**: {p.proposed_text}")
            lines.append(f"**Rationale**: {p.rationale}")
            if p.sources:
                lines.append("**Sources**:")
                for s in p.sources:
                    excerpt = (s.get("excerpt", "") or "").replace("|", "\\|").replace("\n", " ")
                    lines.append(f"- `{s.get('path','')}` §{s.get('section','')}: > {excerpt}")
            lines.append("")
    (proposals_dir / "article_edit_proposals.md").write_text("\n".join(lines), encoding="utf-8")


def merge_article_edit_proposals(new_proposals: list[ArticleEditProposal]) -> tuple[int, int]:
    """Merge new proposals into the existing article_edit_proposals.json, deduplicating by proposal_id.

    Returns (added_count, total_count).
    """
    proposals_dir = AUTOMATION_DIR / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    json_path = proposals_dir / "article_edit_proposals.json"
    existing: list[dict] = []
    if json_path.exists():
        try:
            existing = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing_ids = {e.get("proposal_id") for e in existing if e.get("proposal_id")}
    added = 0
    for p in new_proposals:
        if p.proposal_id and p.proposal_id in existing_ids:
            continue
        existing.append(asdict(p))
        existing_ids.add(p.proposal_id)
        added += 1
    write_json(json_path, existing)
    return added, len(existing)


def research_agent_round_prompt(
    article_text: str,
    chunks: list[dict],
    private_hints: list[dict],
    article_path: str,
    article_title: str,
    article_kind: str,
    round_num: int,
    max_rounds: int,
    max_additions: int,
) -> str:
    article_excerpt = article_text[:2500]
    evidence_blocks = []
    for c in chunks:
        evidence_blocks.append(
            f"[{c.get('path','?')} §{c.get('section','?')} kind={c.get('kind','?')}]\n{(c.get('text') or '')[:1600]}"
        )
    evidence_text = "\n\n---\n\n".join(evidence_blocks) or "(none yet)"
    hint_blocks = []
    for h in private_hints:
        hint_blocks.append(
            f"[PRIVATE HINT: {h.get('path','?')}]\n{(h.get('text') or '')[:1000]}"
        )
    hints_text = "\n\n---\n\n".join(hint_blocks) or "(none)"
    rounds_left = max_rounds - round_num - 1
    return (
        "You are a research agent for the Arden Vul DFRPG campaign vault.\n\n"
        f"ARTICLE: {article_path}\nTitle: {article_title}\nKind: {article_kind}\n"
        f"Round {round_num + 1} of {max_rounds} ({rounds_left} search rounds remaining after this).\n\n"
        "ARTICLE CONTENT:\n---\n"
        f"{article_excerpt}\n"
        "---\n\n"
        "ACCUMULATED EVIDENCE from vault RAG searches:\n\n"
        f"{evidence_text}\n\n"
        "PRIVATE AUTOMATION HINTS (non-citable raw Discord; never cite these directly):\n\n"
        f"{hints_text}\n\n"
        "YOUR TASK:\n"
        "1. If you need more evidence, return up to 3 focused `research_queries` for the next RAG search round.\n"
        "2. Return any `proposals` supported by the EVIDENCE above (not hints alone).\n"
        "   You may return both queries and proposals in the same response.\n"
        f"   Propose at most {max_additions} additions total across all rounds.\n"
        "   If the evidence is sufficient, return an empty `research_queries` list.\n\n"
        "Allowed addition types:\n"
        "- append_bullet_to_section: add a sourced bullet to an existing H2 section. "
        "If the article is a stub with no body sections yet, use target_section='Notes' "
        "or target_section='Summary' to seed it with factual content.\n"
        "- add_alias: add an alternate name to the frontmatter aliases list (target_section='aliases').\n"
        "- extend_summary: add one factual sentence to the Summary section (target_section='Summary').\n\n"
        "Every proposal MUST cite a specific source excerpt verbatim from the EVIDENCE above.\n"
        "Do not invent facts, do not paraphrase loosely, do not propose changes already in the article.\n\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "research_queries": ["focused query string", ...],\n'
        '  "proposals": [\n'
        "    {\n"
        '      "addition_type": "append_bullet_to_section",\n'
        '      "target_section": "Sessions",\n'
        '      "proposed_text": "- [[sessions/Session 27.md|Session 27]]",\n'
        '      "rationale": "one sentence",\n'
        '      "sources": [{"path": "vault/sessions/...", "section": "...", "excerpt": "<verbatim quote>"}]\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def research_article_agent(
    article_path: Path,
    max_rounds: int = 5,
    top_k_per_query: int = 8,
    max_additions: int = 5,
) -> list[ArticleEditProposal]:
    """Iterative research agent: searches the RAG in multiple rounds to build evidence before proposing edits."""
    rel_path = article_path.relative_to(ROOT).as_posix()
    article_text = read_text(article_path)
    item = build_article_queue_item(article_path)
    if item is None:
        # Build a minimal queue item for paths not in the scored queue
        title = article_path.stem
        kind = vault_rag_kind_for_path(article_path)
        item = ArticleQueueItem(
            path=rel_path, title=title, kind=kind, tags=(),
            score=0, reasons=(), queries=(title,),
        )

    all_chunks = gather_article_research_chunks(item, top_k_per_query=top_k_per_query)
    private_hints = gather_private_discord_hints(item)

    accumulated_proposals: list[dict] = []
    rounds_run = 0

    for round_num in range(max_rounds):
        rounds_run += 1
        prompt = research_agent_round_prompt(
            article_text, all_chunks, private_hints,
            rel_path, item.title, item.kind,
            round_num, max_rounds, max_additions,
        )
        try:
            response = llm_chat_json(prompt, timeout=300)
        except Exception as exc:
            print(f"  round {round_num + 1} LLM error: {exc}", file=sys.stderr)
            break

        new_queries = [
            q.strip() for q in (response.get("research_queries") or [])
            if isinstance(q, str) and q.strip()
        ]
        for raw in (response.get("proposals") or []):
            if isinstance(raw, dict):
                accumulated_proposals.append(raw)

        print(
            f"  round {round_num + 1}: {len(new_queries)} new queries, "
            f"{len(response.get('proposals') or [])} proposals",
            file=sys.stderr,
        )

        if not new_queries or round_num == max_rounds - 1:
            break
        all_chunks = expand_article_research_chunks(all_chunks, new_queries, top_k_per_query, max_chunks=40)

    # Parse accumulated proposals into ArticleEditProposal objects
    results: list[ArticleEditProposal] = []
    seen_ids: set[str] = set()
    for raw in accumulated_proposals:
        addition_type = str(raw.get("addition_type", "")).strip()
        if addition_type not in ARTICLE_EDIT_ADDITION_TYPES:
            continue
        target_section = str(raw.get("target_section", "")).strip()
        proposed_text = normalize_vault_wikilinks(str(raw.get("proposed_text", "")).strip())
        rationale = str(raw.get("rationale", "")).strip()
        sources: list[dict] = []
        for src in (raw.get("sources") or []):
            if isinstance(src, dict) and is_citable_article_source(str(src.get("path", ""))):
                sources.append({
                    "path": str(src.get("path", "")),
                    "section": str(src.get("section", "")),
                    "excerpt": str(src.get("excerpt", ""))[:400],
                })
        if not sources or not proposed_text or not target_section:
            continue
        proposal_id = hashlib.sha1(
            f"{rel_path}|{addition_type}|{target_section}|{proposed_text}".encode("utf-8")
        ).hexdigest()[:12]
        if proposal_id in seen_ids:
            continue
        seen_ids.add(proposal_id)
        results.append(ArticleEditProposal(
            article_path=rel_path,
            article_title=item.title,
            article_kind=item.kind,
            article_score=item.score,
            addition_type=addition_type,
            target_section=target_section,
            proposed_text=proposed_text,
            rationale=rationale,
            sources=sources,
            status="needs-verification",
            proposal_id=proposal_id,
        ))
        if len(results) >= max_additions:
            break

    return results


def cmd_research_article(args: argparse.Namespace) -> int:
    article_path = ROOT / args.article
    if not article_path.exists():
        print(json.dumps({"ok": False, "error": f"file not found: {args.article}"}), file=sys.stderr)
        return 1
    print(f"Researching {args.article} (max_rounds={args.max_rounds}, top_k={args.top_k}) ...", file=sys.stderr)
    proposals = research_article_agent(
        article_path,
        max_rounds=args.max_rounds,
        top_k_per_query=args.top_k,
        max_additions=args.max_additions,
    )
    added, total = merge_article_edit_proposals(proposals)
    print(json.dumps({
        "ok": True,
        "article": args.article,
        "proposals_generated": len(proposals),
        "proposals_added_to_queue": added,
        "total_in_queue": total,
        "next_step": "python3 scripts/vault_automation.py verify-article-edits",
    }, indent=2))
    return 0


def article_edit_verifier_prompt(proposal: ArticleEditProposal) -> str:
    article_full_path = ROOT / proposal.article_path
    article_text = read_text(article_full_path)[:1800] if article_full_path.exists() else ""
    source_blocks: list[str] = []
    for src in proposal.sources:
        src_path_str = src.get("path", "")
        src_path = Path(src_path_str) if src_path_str.startswith("/") else ROOT / src_path_str
        if not src_path.exists():
            source_blocks.append(f"[{src_path_str} §{src.get('section','?')}]\nSOURCE FILE NOT FOUND")
            continue
        src_text = read_text(src_path)
        section = src.get("section", "")
        excerpt = (src.get("excerpt", "") or "").strip()
        window = ""
        # Prefer to center the window on the cited excerpt if we can find it verbatim.
        needle = excerpt[:80].strip() if excerpt else ""
        excerpt_idx = src_text.find(needle) if needle else -1
        excerpt_found_mechanically = bool(needle and excerpt_idx >= 0)
        if excerpt_idx >= 0:
            start = max(0, excerpt_idx - 1200)
            end = min(len(src_text), excerpt_idx + 2000)
            window = src_text[start:end]
        # Fallback: full section bounded by next H2.
        if not window and section:
            sec_pat = re.compile(rf"^## {re.escape(section)}\s*$", re.MULTILINE)
            m = sec_pat.search(src_text)
            if m:
                end_search = re.search(r"^## ", src_text[m.end():], re.MULTILINE)
                end = m.end() + end_search.start() if end_search else len(src_text)
                # Allow up to 6000 chars so multi-paragraph sections aren't truncated.
                window = src_text[m.start():min(end, m.start() + 6000)]
        # Last resort: the start of the file.
        if not window:
            window = src_text[:3000]
        mech_label = "EXCERPT FOUND MECHANICALLY" if excerpt_found_mechanically else "EXCERPT NOT FOUND MECHANICALLY"
        source_blocks.append(f"[{src.get('path','')} §{section or '?'}] [{mech_label}]\n{window}")
    sources_text = "\n\n---\n\n".join(source_blocks)
    return (
        "Verify whether the proposed article addition is supported by the cited canonical sources.\n\n"
        "PROPOSED ADDITION:\n"
        f"- For article: {proposal.article_path}\n"
        f"- Article title: {proposal.article_title}\n"
        f"- Article kind: {proposal.article_kind}\n"
        f"- Addition type: {proposal.addition_type}\n"
        f"- Target section: {proposal.target_section}\n"
        f"- Proposed text: {proposal.proposed_text}\n"
        f"- Proposer rationale: {proposal.rationale}\n\n"
        "CURRENT ARTICLE CONTENT (for awareness only — verification is against the cited sources, not the article):\n"
        "---\n"
        f"{article_text}\n"
        "---\n\n"
        "CITED SOURCES (verbatim from disk):\n"
        "Each source header shows [EXCERPT FOUND MECHANICALLY] or [EXCERPT NOT FOUND MECHANICALLY].\n"
        "If a source shows EXCERPT NOT FOUND MECHANICALLY, the proposer likely cited the wrong source\n"
        "or fabricated the excerpt. Treat such sources with strong skepticism: return 'not_found' unless\n"
        "the proposed claim is stated word-for-word elsewhere in the source window pasted below.\n\n"
        f"{sources_text}\n\n"
        "Classify the proposed addition strictly:\n"
        "- \"supported\": the source window explicitly and clearly supports this content; excerpt found mechanically OR claim is stated verbatim in the window.\n"
        "- \"contradicted\": cited sources contain evidence against this content.\n"
        "- \"ambiguous\": sources mention the topic but do not clearly support the specific claim.\n"
        "- \"not_found\": the source does not contain this information, OR excerpt was NOT FOUND MECHANICALLY and the claim is not verbatim in the window.\n\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "status": "supported|contradicted|ambiguous|not_found",\n'
        '  "rationale": "<one sentence grounded in the cited source content>",\n'
        '  "evidence": "<short verbatim quote from one cited source if status=supported, else empty string>"\n'
        "}"
    )


def verify_article_edit_proposals(limit: int | None = None) -> list[dict]:
    proposals_path = AUTOMATION_DIR / "proposals" / "article_edit_proposals.json"
    if not proposals_path.exists():
        raise RuntimeError("article_edit_proposals.json not found; run propose-article-edits first")
    raw = json.loads(proposals_path.read_text(encoding="utf-8"))
    proposals = [ArticleEditProposal(**r) for r in raw]

    # Load existing verifications and skip already-processed proposals (cursor behaviour).
    verifications_path = AUTOMATION_DIR / "proposals" / "article_edit_verifications.json"
    existing: list[dict] = []
    already_verified_ids: set[str] = set()
    if verifications_path.exists():
        try:
            existing = json.loads(verifications_path.read_text(encoding="utf-8"))
            already_verified_ids = {e["proposal_id"] for e in existing if e.get("proposal_id")}
        except Exception:
            existing = []

    pending = [p for p in proposals if p.proposal_id not in already_verified_ids]
    # limit=None or limit<0 means all pending
    if limit is not None and limit >= 0:
        pending = pending[:limit]

    out: list[dict] = list(existing)
    for p in pending:
        try:
            response = llm_chat_json(article_edit_verifier_prompt(p), timeout=120)
            status = str(response.get("status", "unknown"))
            rationale = str(response.get("rationale", ""))
            evidence = str(response.get("evidence", ""))
        except Exception as exc:
            status = "error"
            rationale = str(exc)[:200]
            evidence = ""
        result = asdict(p)
        result["verifier_status"] = status
        result["verifier_rationale"] = rationale
        result["verifier_evidence"] = evidence
        out.append(result)
    proposals_dir = AUTOMATION_DIR / "proposals"
    write_json(proposals_dir / "article_edit_verifications.json", out)
    lines: list[str] = ["# Article Edit Verifications", ""]
    by_status: dict[str, list[dict]] = {}
    for r in out:
        by_status.setdefault(r["verifier_status"], []).append(r)
    for status in ["supported", "contradicted", "ambiguous", "not_found", "error", "unknown"]:
        items = by_status.get(status, [])
        if not items:
            continue
        lines.append(f"## {status} ({len(items)})")
        lines.append("")
        for r in items:
            lines.append(f"### {r['proposal_id']} — {r['article_path']}")
            lines.append(f"**Type**: `{r['addition_type']}` → `{r['target_section']}`")
            lines.append(f"**Proposed**: {r['proposed_text']}")
            lines.append(f"**Verifier**: {r['verifier_rationale']}")
            ev = (r.get("verifier_evidence") or "").replace("|", "\\|").replace("\n", " ")
            if ev:
                lines.append(f"**Evidence**: > {ev}")
            lines.append("")
    (proposals_dir / "article_edit_verifications.md").write_text("\n".join(lines), encoding="utf-8")
    return out


def retire_proposals_for_path(article_rel_path: str) -> int:
    """Mark all supported proposals for a given article as already_applied.
    Call this after manually rewriting a page so the apply pipeline won't
    re-add old verified proposals on top of the clean content."""
    vers_path = AUTOMATION_DIR / "proposals" / "article_edit_verifications.json"
    if not vers_path.exists():
        return 0
    vers = json.loads(vers_path.read_text(encoding="utf-8"))
    retired = 0
    for v in vers:
        if v.get("article_path") == article_rel_path and v.get("verifier_status") == "supported":
            v["verifier_status"] = "already_applied"
            v["verifier_rationale"] = "Page manually rewritten; old proposals superseded."
            retired += 1
    if retired:
        write_json(vers_path, vers)
    return retired


def apply_article_edit_to_text(text: str, edit: dict) -> tuple[str, bool, str]:
    addition_type = edit.get("addition_type", "")
    target_section = edit.get("target_section", "")
    proposed_text = (edit.get("proposed_text", "") or "").rstrip()
    if not proposed_text:
        return text, False, "empty proposed_text"
    if proposed_text in text:
        return text, False, "already present"
    # Near-duplicate check: if any existing bullet shares the first 25 chars (after
    # stripping trailing plural 's') with the proposed bullet, treat it as already present.
    # Uses 25 chars (not 40) to catch "stair"/"stairs" and similar word-boundary variants
    # that diverge just past a stem.
    if addition_type == "append_bullet_to_section":
        def _dedup_key(s: str) -> str:
            # Strip wikilinks to plain text first
            s = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", s)
            s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
            s = re.sub(r"\s+", " ", s.lstrip("- ").strip()).lower()
            # Normalize punctuation and plural-s so variants compare equally
            s = re.sub(r"[,;:.!?]", "", s)
            s = re.sub(r"s\b", "", s)
            return s[:20]  # 20 chars after normalization catches most variants
        needle = _dedup_key(proposed_text)
        if needle and len(needle) >= 12:
            for existing in re.findall(r"^- (.+)", text, re.MULTILINE):
                if _dedup_key(existing) == needle:
                    return text, False, "near-duplicate bullet already present"
    if addition_type == "append_bullet_to_section":
        pat = re.compile(rf"^## {re.escape(target_section)}\s*$", re.MULTILINE)
        m = pat.search(text)
        if not m:
            return text, False, f"section '{target_section}' not found"
        rest_start = m.end()
        next_h2 = re.search(r"^## ", text[rest_start:], re.MULTILINE)
        if next_h2:
            insert_at = rest_start + next_h2.start()
            before = text[:insert_at].rstrip()
            after = text[insert_at:]
            new = before + "\n" + proposed_text + "\n\n" + after
        else:
            new = text.rstrip() + "\n" + proposed_text + "\n"
        return remove_section_todo(new, target_section), True, "appended bullet"
    if addition_type == "add_alias":
        fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not fm_match:
            return text, False, "no frontmatter"
        alias_text = proposed_text.strip()
        fm = fm_match.group(1)
        rest = text[fm_match.end():]
        if re.search(rf"(^|\s){re.escape(alias_text)}(\s|$)", fm):
            return text, False, "alias already present"
        # Reject aliases that look like sub-entities (e.g. "Tasha's Tailor Shop" aliased to "Gosterwick"):
        # if the proposed alias is longer than the article title, it's likely a sub-location name.
        h1_match = re.search(r"^#\s+(.+)$", rest, re.MULTILINE)
        article_title = h1_match.group(1).strip() if h1_match else ""
        title_plain = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", article_title).strip()
        if title_plain and len(alias_text) > len(title_plain) + 10:
            return text, False, f"alias '{alias_text}' looks like a sub-entity of '{title_plain}' — skipped"
        am = re.search(r"^aliases:[ \t]*(.*)$", fm, re.MULTILINE)
        if am:
            line = am.group(0)
            value = am.group(1).strip()
            if value in ("", "[]"):
                new_line = f"aliases:\n  - {alias_text}"
                new_fm = fm.replace(line, new_line, 1)
            elif value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                items = [s.strip() for s in inner.split(",") if s.strip()] if inner else []
                items.append(alias_text)
                new_line = f"aliases: [{', '.join(items)}]"
                new_fm = fm.replace(line, new_line, 1)
            else:
                new_line = line + f"\n  - {alias_text}"
                new_fm = fm.replace(line, new_line, 1)
        else:
            new_fm = fm.rstrip() + f"\naliases:\n  - {alias_text}"
        return "---\n" + new_fm + "\n---\n" + rest, True, "added alias"
    if addition_type == "extend_summary":
        pat = re.compile(r"^## Summary\s*$", re.MULTILINE)
        m = pat.search(text)
        if not m:
            return text, False, "no Summary section"
        rest_start = m.end()
        next_h2 = re.search(r"^## ", text[rest_start:], re.MULTILINE)
        end = rest_start + next_h2.start() if next_h2 else len(text)
        before = text[:end].rstrip()
        after = text[end:]
        new = before + "\n\n" + proposed_text + "\n\n" + after
        return new, True, "extended summary"
    return text, False, f"unsupported addition_type: {addition_type}"


# ---- action-item lane ----

ACTION_ITEMS_PATH = VAULT / "notes" / "Active Action Items.md"
ACTION_ITEM_LEGACY_PATHS = [
    VAULT / "notes" / "Unfinished Plotlines and Tasks.md",
    VAULT / "notes" / "Open Threads - Post Session 35.md",
]
ACTION_ITEM_CATEGORIES = {
    "Active Quests",
    "Open Mysteries",
    "Watch List",
    "Completed / Resolved",
}
ACTION_ITEM_STATUS_TO_CATEGORY = {
    "active": "Active Quests",
    "open": "Open Mysteries",
    "watch": "Watch List",
    "completed": "Completed / Resolved",
    "resolved": "Completed / Resolved",
}


def _truncate_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head - 80
    return text[:head].rstrip() + "\n\n...[truncated]...\n\n" + text[-tail:].lstrip()


def latest_session_pages(limit: int) -> list[Path]:
    sessions = [path for _sid, path in list_session_pages()]
    return sessions[-limit:] if limit > 0 else []


def latest_discord_summary_pages(limit: int) -> list[Path]:
    pattern = re.compile(r"^Discord Summary (\d{4}-W\d{2})\.md$")
    notes_dir = VAULT / "notes"
    matches = [(m.group(1), p) for p in notes_dir.glob("Discord Summary *.md") if (m := pattern.match(p.name))]
    matches.sort(key=lambda x: x[0])
    return [p for _, p in matches[-limit:]] if limit > 0 else []


def discord_summary_action_excerpt(text: str, max_chars: int = 4000) -> str:
    """Extract Unresolved Threads, Tactical Planning, and Item Intelligence from a Discord summary.

    Handles both ## numbered-heading format (older summaries) and **Bold** standalone-line
    format (newer summaries).
    """
    wanted = {"unresolved threads", "tactical planning", "item intelligence"}
    parts: list[str] = []

    # Try ## heading extraction (strips leading "N. " from numbered headings)
    heading_matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    for idx, match in enumerate(heading_matches):
        heading = re.sub(r"^\d+\.\s+", "", match.group(1)).strip().lower()
        if heading not in wanted:
            continue
        end = heading_matches[idx + 1].start() if idx + 1 < len(heading_matches) else len(text)
        parts.append(text[match.start():end].strip())

    if parts:
        return _truncate_middle("\n\n".join(parts), max_chars)

    # Fall back to **Bold** standalone-line section headers
    bold_matches = list(re.finditer(
        r"^\*\*(" + "|".join(re.escape(h.title()) for h in wanted) + r")\*\*\s*$",
        text, flags=re.MULTILINE | re.IGNORECASE,
    ))
    for idx, match in enumerate(bold_matches):
        end = bold_matches[idx + 1].start() if idx + 1 < len(bold_matches) else len(text)
        parts.append(text[match.start():end].strip())

    if parts:
        return _truncate_middle("\n\n".join(parts), max_chars)

    # No structured sections found — return truncated full text
    return _truncate_middle(text, max_chars)


def markdown_section_excerpt(text: str, headings: set[str], max_chars: int = 5000) -> str:
    parts: list[str] = []
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    for idx, match in enumerate(matches):
        heading = match.group(1).strip().rstrip(":").lower()
        if heading not in headings:
            continue
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        parts.append(text[match.start():end].strip())
    if not parts:
        return _truncate_middle(text, max_chars)
    return _truncate_middle("\n\n".join(parts), max_chars)


def action_item_context(latest_session_count: int, latest_discord_weeks: int = 4) -> str:
    blocks: list[str] = []
    if ACTION_ITEMS_PATH.exists():
        blocks.append(
            f"## CURRENT CANONICAL ACTION NOTE: {ACTION_ITEMS_PATH.relative_to(ROOT).as_posix()}\n"
            + _truncate_middle(read_text(ACTION_ITEMS_PATH), 10000)
        )
    post35 = VAULT / "notes" / "Open Threads - Post Session 35.md"
    if post35.exists():
        blocks.append(
            f"## LEGACY THREAD NOTE: {post35.relative_to(ROOT).as_posix()}\n"
            + _truncate_middle(read_text(post35), 10000)
        )
    unfinished = VAULT / "notes" / "Unfinished Plotlines and Tasks.md"
    if unfinished.exists():
        text = read_text(unfinished)
        session_30 = re.search(r"^## Session 30\b", text, flags=re.MULTILINE)
        if session_30:
            text = text[session_30.start():]
        blocks.append(
            f"## LEGACY THREAD NOTE EXCERPT: {unfinished.relative_to(ROOT).as_posix()}\n"
            + _truncate_middle(text, 18000)
        )
    wanted = {"what happened", "next week", "gm's comments", "resolved/updated", "open threads", "achievements"}
    for path in latest_session_pages(latest_session_count):
        text = markdown_section_excerpt(read_text(path), wanted, max_chars=6000)
        blocks.append(
            f"## RECENT SESSION: {path.relative_to(ROOT).as_posix()}\n"
            + text
        )
    for path in latest_discord_summary_pages(latest_discord_weeks):
        excerpt = discord_summary_action_excerpt(read_text(path), max_chars=3000)
        if excerpt.strip():
            blocks.append(
                f"## RECENT DISCORD SUMMARY (Unresolved Threads / Tactical Planning / Item Intelligence): "
                f"{path.relative_to(ROOT).as_posix()}\n"
                + excerpt
            )
    return "\n\n---\n\n".join(blocks)


def action_item_prompt(latest_session_count: int, max_items: int, latest_discord_weeks: int = 4) -> str:
    context = action_item_context(latest_session_count, latest_discord_weeks)
    return (
        "You maintain an Obsidian campaign note named vault/notes/Active Action Items.md for an Arden Vul DFRPG campaign.\n\n"
        "Use ONLY the provided source context. The older thread notes are useful historical inventories, but recent session "
        "recaps are stronger evidence for current status. Prefer concrete party obligations, next-session plans, unresolved "
        "promises, live threats, and actionable leads over broad lore questions. Do not include spoilers or facts not present "
        "in the context. Do NOT treat a session's pre-session 'The Plan' section as proof that something is still active; "
        "the later What Happened / GM's Comments / Next Week / Resolved sections supersede it.\n\n"
        "Your task is to produce a clean current action-item inventory. Treat the current canonical action note as a prior "
        "hypothesis to reconcile, not evidence that an item is still active. Merge duplicates. Keep an active or watch item "
        "only when the supplied timeline still supports future work. When a later recap shows that an older plan was carried "
        "out, retire it from the active list and include it as completed only when it remains useful historical context. Mark "
        "items completed/resolved only when the provided context explicitly says they were completed, resolved, found, "
        "rescued, or otherwise closed. Prefer the newest decisive citation for each status. Keep uncertain lore as Open "
        "Mysteries or Watch List rather than Active Quests.\n\n"
        "Discord summary excerpts (labeled RECENT DISCORD SUMMARY) are also valid sources. They appear in the context "
        "under 'Unresolved Threads', 'Tactical Planning', and 'Item Intelligence' sections. Treat items listed under "
        "'Unresolved Threads' in a Discord summary as open threads eligible for the Watch List or Open Mysteries "
        "unless a later session explicitly resolves them. Items listed under 'Tactical Planning' or 'Item Intelligence' "
        "that describe an explicit party obligation or pending decision are eligible for Active Quests.\n\n"
        "Each item must cite at least one source path and a short verbatim excerpt from that source. Use repo-relative paths "
        "like vault/sessions/Session 52b and 53 - Behir, Varumani, and the Surgical Construct.md or "
        "vault/notes/Discord Summary 2026-W05.md.\n\n"
        f"Return no more than {max_items} items. Return strict JSON only, no markdown fences:\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "id": "short-stable-slug",\n'
        '      "title": "Recover or resolve X",\n'
        '      "status": "active|open|watch|completed",\n'
        '      "category": "Active Quests|Open Mysteries|Watch List|Completed / Resolved",\n'
        '      "summary": "One concise campaign-facing sentence.",\n'
        '      "next_step": "Concrete next step, or empty string for completed items.",\n'
        '      "related": ["[[npcs/Example.md|Example]]"],\n'
        '      "sources": [{"path": "vault/sessions/Session 52b and 53 - Behir, Varumani, and the Surgical Construct.md", "excerpt": "short verbatim quote"}]\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "SOURCE CONTEXT:\n"
        "---\n"
        f"{context}\n"
        "---"
    )


def _normalized_contains(haystack: str, needle: str) -> bool:
    h = re.sub(r"\s+", " ", haystack).strip().lower()
    n = re.sub(r"\s+", " ", needle).strip().lower()
    if not n:
        return False
    return n in h


def clean_action_item(raw: dict) -> dict | None:
    title = str(raw.get("title", "")).strip()
    summary = str(raw.get("summary", "")).strip()
    if not title or not summary:
        return None
    status = str(raw.get("status", "open")).strip().lower()
    if status == "resolved":
        status = "completed"
    if status not in {"active", "open", "watch", "completed"}:
        status = "open"
    category = str(raw.get("category", "")).strip() or ACTION_ITEM_STATUS_TO_CATEGORY[status]
    if category not in ACTION_ITEM_CATEGORIES:
        category = ACTION_ITEM_STATUS_TO_CATEGORY[status]
    slug = str(raw.get("id", "")).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug or title.lower()).strip("-")[:64]
    if not slug:
        slug = hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]
    related_raw = raw.get("related") or []
    related = [str(v).strip() for v in related_raw if str(v).strip()][:8] if isinstance(related_raw, list) else []
    sources: list[dict] = []
    for src in raw.get("sources") or []:
        if not isinstance(src, dict):
            continue
        path = str(src.get("path", "")).strip()
        excerpt = str(src.get("excerpt", "")).strip()
        if path and excerpt:
            sources.append({"path": path, "excerpt": excerpt[:500]})
    if not sources:
        return None
    return {
        "id": slug,
        "title": title[:160],
        "status": status,
        "category": category,
        "summary": summary[:500],
        "next_step": str(raw.get("next_step", "")).strip()[:300],
        "related": related,
        "sources": sources[:4],
    }


def source_excerpt_supported(src: dict) -> bool:
    path_str = str(src.get("path", "")).strip()
    excerpt = str(src.get("excerpt", "")).strip()
    if not path_str or not excerpt:
        return False
    path = Path(path_str) if path_str.startswith("/") else ROOT / path_str
    if not path.exists() or not path.is_file():
        return False
    return _normalized_contains(read_text(path), excerpt)


def verify_action_item_inventory(items: list[dict]) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    rejected: list[dict] = []
    seen: set[str] = set()
    for item in items:
        clean = clean_action_item(item)
        if not clean:
            rejected.append({"item": item, "reason": "missing required fields"})
            continue
        if clean["id"] in seen:
            rejected.append({"item": clean, "reason": "duplicate id"})
            continue
        supported_sources = [src for src in clean["sources"] if source_excerpt_supported(src)]
        if not supported_sources:
            rejected.append({"item": clean, "reason": "no cited excerpt found in source files"})
            continue
        clean["sources"] = supported_sources
        seen.add(clean["id"])
        accepted.append(clean)
    return accepted, rejected


def action_item_llm_json(prompt: str) -> dict:
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            return llm_chat_json(prompt, timeout=1800)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"action item LLM failed after 3 attempts: {last_error}")


def build_action_item_inventory(latest_sessions: int = 8, max_items: int = 50, latest_discord_weeks: int = 4) -> dict:
    response = action_item_llm_json(action_item_prompt(latest_sessions, max_items, latest_discord_weeks))
    raw_items = response.get("items") or []
    if not isinstance(raw_items, list):
        raw_items = []
    accepted, rejected = verify_action_item_inventory(raw_items[:max_items])
    payload = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_sessions": latest_sessions,
        "max_items": max_items,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "items": accepted,
        "rejected": rejected,
    }
    proposals_dir = AUTOMATION_DIR / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    write_json(proposals_dir / "action_item_inventory.json", payload)
    write_action_item_inventory_report(payload)
    return payload


def write_action_item_inventory_report(payload: dict) -> None:
    lines = ["# Action Item Inventory Proposal", ""]
    lines.append(f"Accepted: {payload.get('accepted_count', 0)}")
    lines.append(f"Rejected: {payload.get('rejected_count', 0)}")
    lines.append("")
    for category in ["Active Quests", "Open Mysteries", "Watch List", "Completed / Resolved"]:
        items = [it for it in payload.get("items", []) if it.get("category") == category]
        if not items:
            continue
        lines.append(f"## {category}")
        lines.append("")
        for item in items:
            mark = "x" if item.get("status") == "completed" else " "
            lines.append(f"- [{mark}] **{item['title']}**")
            lines.append(f"  - Status: {item['status']}")
            lines.append(f"  - Summary: {item['summary']}")
            if item.get("next_step"):
                lines.append(f"  - Next step: {item['next_step']}")
            for src in item.get("sources", []):
                lines.append(f"  - Evidence: [[{src['path']}]] — \"{src['excerpt']}\"")
            lines.append("")
    rejected = payload.get("rejected") or []
    if rejected:
        lines.append("## Rejected")
        lines.append("")
        for r in rejected[:20]:
            title = ((r.get("item") or {}).get("title") if isinstance(r.get("item"), dict) else "") or "(untitled)"
            lines.append(f"- {title}: {r.get('reason')}")
    (AUTOMATION_DIR / "proposals" / "action_item_inventory.md").write_text("\n".join(lines), encoding="utf-8")


def render_action_items_note(items: list[dict]) -> str:
    lines: list[str] = [
        "---",
        "tags:",
        "  - note",
        "  - action-items",
        "  - open-threads",
        "generated_by: vault_automation.py action-items",
        f"updated: {datetime.now(timezone.utc).isoformat()}",
        "---",
        "",
        "# Active Action Items",
        "",
        "This note is maintained by the vault automation. It merges current quests, unresolved mysteries, watch items, and completed items from cited session and campaign notes.",
        "",
        "## Sources",
        "- [[notes/Unfinished Plotlines and Tasks.md|Unfinished Plotlines and Tasks]]",
        "- [[notes/Open Threads - Post Session 35.md|Open Threads - Post Session 35]]",
        "- Recent session recaps",
        "",
    ]
    for category in ["Active Quests", "Open Mysteries", "Watch List", "Completed / Resolved"]:
        category_items = [it for it in items if it.get("category") == category]
        lines.append(f"## {category}")
        lines.append("")
        if not category_items:
            lines.append("_No current items._")
            lines.append("")
            continue
        for item in category_items:
            mark = "x" if item.get("status") == "completed" else " "
            lines.append(f"- [{mark}] **{item['title']}**")
            lines.append(f"  - ID: `{item['id']}`")
            lines.append(f"  - Status: {item['status']}")
            lines.append(f"  - Summary: {item['summary']}")
            if item.get("next_step"):
                lines.append(f"  - Next step: {item['next_step']}")
            if item.get("related"):
                related = [link for link in (normalize_vault_wikilink(v) for v in item["related"]) if link]
                if related:
                    lines.append(f"  - Related: {', '.join(related)}")
            lines.append("  - Evidence:")
            for src in item.get("sources", []):
                path = src["path"]
                link_path = path.removeprefix("vault/")
                label = Path(path).stem
                excerpt = src["excerpt"].replace('"', "'")
                lines.append(f"    - [[{link_path}|{label}]] — \"{excerpt}\"")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def apply_action_item_inventory(apply_changes: bool = False) -> dict:
    inv_path = AUTOMATION_DIR / "proposals" / "action_item_inventory.json"
    if not inv_path.exists():
        return {"ok": False, "error": "action_item_inventory_not_found", "hint": "Run build-action-items first"}
    payload = json.loads(inv_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    if not items:
        return {"ok": False, "error": "action_item_inventory_empty"}
    new_text = render_action_items_note(items)
    old_text = read_text(ACTION_ITEMS_PATH) if ACTION_ITEMS_PATH.exists() else ""
    changed = old_text != new_text
    if changed and apply_changes:
        ACTION_ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ACTION_ITEMS_PATH.write_text(new_text, encoding="utf-8")
    return {
        "ok": True,
        "mode": "apply" if apply_changes else "dry-run",
        "path": ACTION_ITEMS_PATH.relative_to(ROOT).as_posix(),
        "changed": changed,
        "item_count": len(items),
        "active_count": sum(1 for it in items if it.get("status") == "active"),
        "open_count": sum(1 for it in items if it.get("status") == "open"),
        "watch_count": sum(1 for it in items if it.get("status") == "watch"),
        "completed_count": sum(1 for it in items if it.get("status") == "completed"),
    }


def normalize_vault_wikilink(link: str) -> str | None:
    match = re.match(r"^\[\[([^|\]]+)(?:\|([^\]]+))?\]\]$", link.strip())
    if not match:
        return None
    target = match.group(1).removeprefix("vault/")
    label = match.group(2)
    path = VAULT / target
    if not path.exists():
        stem_target = target.replace("-", " ")
        path = VAULT / stem_target
        if path.exists():
            target = stem_target
    if not path.exists():
        return None
    return f"[[{target}|{label or Path(target).stem}]]"


def update_action_items_safely(apply_changes: bool, latest_sessions: int, max_items: int, latest_discord_weeks: int = 4) -> dict:
    try:
        inventory = build_action_item_inventory(latest_sessions=latest_sessions, max_items=max_items, latest_discord_weeks=latest_discord_weeks)
        applied = apply_action_item_inventory(apply_changes=apply_changes)
        return {
            "enabled": True,
            "ok": bool(inventory.get("ok") and applied.get("ok")),
            "accepted_count": inventory.get("accepted_count", 0),
            "rejected_count": inventory.get("rejected_count", 0),
            "applied": applied,
            "markdown": str(AUTOMATION_DIR / "proposals" / "action_item_inventory.md"),
            "json": str(AUTOMATION_DIR / "proposals" / "action_item_inventory.json"),
        }
    except Exception as exc:
        return {"enabled": True, "ok": False, "error": str(exc)[:300]}


def action_items_refresh_due(import_result: dict, refresh_hours: int) -> tuple[bool, str]:
    if int(import_result.get("change_count", 0) or 0) > 0:
        return True, "canonical_sources_changed"
    inventory_path = AUTOMATION_DIR / "proposals" / "action_item_inventory.json"
    if not inventory_path.exists():
        return True, "inventory_missing"
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(inventory_path.stat().st_mtime, timezone.utc)
    if age >= timedelta(hours=max(1, refresh_hours)):
        return True, "periodic_refresh_due"
    return False, "no_source_changes_and_periodic_refresh_not_due"


def cmd_build_action_items(args: argparse.Namespace) -> int:
    try:
        payload = build_action_item_inventory(latest_sessions=args.latest_sessions, max_items=args.max_items, latest_discord_weeks=args.latest_discord_weeks)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({
        "ok": True,
        "accepted_count": payload.get("accepted_count", 0),
        "rejected_count": payload.get("rejected_count", 0),
        "markdown": str(AUTOMATION_DIR / "proposals" / "action_item_inventory.md"),
        "json": str(AUTOMATION_DIR / "proposals" / "action_item_inventory.json"),
    }, indent=2))
    return 0


def cmd_apply_action_items(args: argparse.Namespace) -> int:
    result = apply_action_item_inventory(apply_changes=args.apply)
    if result.get("ok") and args.apply and result.get("changed"):
        result["vault_rag_refresh"] = refresh_vault_rag_safely()
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


def refresh_vault_rag_safely() -> dict:
    """Refresh vault-rag, swallowing setup errors so the caller stays robust.
    Returns a small status dict suitable for inclusion in run/apply reports."""
    try:
        result = vault_rag_ingest_all(reset=False, limit=None)
    except Exception as exc:
        return {"ok": False, "skipped": True, "reason": str(exc)[:200]}
    return {
        "ok": result.get("ok", False),
        "actions": result.get("actions", {}),
        "collection_size": result.get("collection_size"),
    }


def apply_verified_article_edits(apply_changes: bool, limit: int | None = None) -> dict:
    ver_path = AUTOMATION_DIR / "proposals" / "article_edit_verifications.json"
    if not ver_path.exists():
        return {"ok": False, "error": "verifications_not_found", "hint": "Run verify-article-edits first"}
    verifications = json.loads(ver_path.read_text(encoding="utf-8"))
    supported = [v for v in verifications if v.get("verifier_status") == "supported"]
    if limit is not None:
        supported = supported[:limit]
    by_article: dict[str, list[dict]] = {}
    for v in supported:
        by_article.setdefault(v["article_path"], []).append(v)
    results: list[dict] = []
    for article_path, edits in by_article.items():
        full_path = ROOT / article_path
        if not full_path.exists():
            results.append({"article_path": article_path, "applied": 0, "skipped": len(edits), "error": "file_not_found"})
            continue
        text = read_text(full_path)
        applied = 0
        per_edit: list[dict] = []
        for v in edits:
            new_text, changed, reason = apply_article_edit_to_text(text, v)
            per_edit.append({
                "proposal_id": v.get("proposal_id"),
                "addition_type": v.get("addition_type"),
                "target_section": v.get("target_section"),
                "changed": changed,
                "reason": reason,
            })
            if changed:
                text = new_text
                applied += 1
        if applied and apply_changes:
            full_path.write_text(text, encoding="utf-8")
        results.append({
            "article_path": article_path,
            "applied": applied,
            "skipped": len(edits) - applied,
            "edits": per_edit,
        })
    payload: dict = {
        "ok": True,
        "mode": "apply" if apply_changes else "dry-run",
        "supported_count": len(supported),
        "articles_touched": len(by_article),
        "total_applied": sum(r["applied"] for r in results),
        "results": results,
    }
    if apply_changes and payload["total_applied"] > 0:
        payload["vault_rag_refresh"] = refresh_vault_rag_safely()
    return payload


def _write_context_needed(article_path: Path, session_names: list[str]) -> None:
    """Append context_needed: frontmatter to an article when the LLM identifies specific
    sessions it needs but couldn't get from RAG chunks alone."""
    try:
        text = article_path.read_text(encoding="utf-8")
    except Exception:
        return
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm_match:
        return
    fm = fm_match.group(1)
    rest = text[fm_match.end():]
    # Resolve partial session names to vault paths
    session_paths: list[str] = []
    sessions_dir = VAULT / "sessions"
    for name in session_names:
        name_clean = name.strip()
        # Try exact match first, then prefix match
        exact = sessions_dir / f"{name_clean}.md"
        if exact.exists():
            session_paths.append(f"vault/sessions/{name_clean}.md")
            continue
        # Prefix/substring match
        matches = [p for p in sessions_dir.glob("*.md") if name_clean.lower() in p.stem.lower()]
        if matches:
            session_paths.append(matches[0].relative_to(ROOT).as_posix())
        else:
            session_paths.append(name_clean)  # store raw name if can't resolve
    if not session_paths:
        return
    # Don't duplicate existing entries
    existing = re.findall(r"context_needed:\s*\n((?:  - .+\n)*)", fm)
    already = set()
    if existing:
        already = set(re.findall(r"  - (.+)", existing[0]))
    new_paths = [p for p in session_paths if p not in already]
    if not new_paths:
        return
    # Write or extend context_needed block
    cn_match = re.search(r"^context_needed:\s*\n((?:  - .+\n)*)", fm, re.MULTILINE)
    if cn_match:
        insertion = cn_match.group(0) + "".join(f"  - {p}\n" for p in new_paths)
        new_fm = fm.replace(cn_match.group(0), insertion, 1)
    else:
        new_fm = fm.rstrip() + "\ncontext_needed:\n" + "".join(f"  - {p}\n" for p in new_paths)
    article_path.write_text(f"---\n{new_fm}\n---\n{rest}", encoding="utf-8")


def _clear_context_needed(article_path: Path) -> None:
    """Remove context_needed: frontmatter after a successful context run."""
    try:
        text = article_path.read_text(encoding="utf-8")
    except Exception:
        return
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm_match:
        return
    fm = fm_match.group(1)
    rest = text[fm_match.end():]
    new_fm = re.sub(r"context_needed:\s*\n(?:  - .+\n)*", "", fm, flags=re.MULTILINE)
    if new_fm != fm:
        article_path.write_text(f"---\n{new_fm.rstrip()}\n---\n{rest}", encoding="utf-8")


def cmd_run_context_needed(args: argparse.Namespace) -> int:
    """Find vault pages flagged with context_needed: frontmatter and run targeted
    --from-session --sessions-only passes for each referenced session, then clear the marker."""
    skip_dirs = {".obsidian", "attachments", "templates"}
    cn_re = re.compile(r"^context_needed:\s*\n((?:  - .+\n)+)", re.MULTILINE)

    # Collect: {session_path -> [article_paths]}
    session_to_articles: dict[str, list[Path]] = {}
    flagged_articles: list[Path] = []

    for md_path in sorted(VAULT.rglob("*.md")):
        if any(part in skip_dirs for part in md_path.parts):
            continue
        try:
            text = md_path.read_text(encoding="utf-8")
        except Exception:
            continue
        m = cn_re.search(text[:1000])
        if not m:
            continue
        session_refs = re.findall(r"  - (.+)", m.group(1))
        flagged_articles.append(md_path)
        for ref in session_refs:
            session_path = ref.strip()
            session_to_articles.setdefault(session_path, []).append(md_path)

    if not flagged_articles:
        print("No articles flagged with context_needed.")
        return 0

    print(f"Found {len(flagged_articles)} flagged article(s) across {len(session_to_articles)} session(s).")
    for session_path, articles in sorted(session_to_articles.items()):
        full_session = ROOT / session_path if not session_path.startswith("/") else Path(session_path)
        if not full_session.exists():
            print(f"  SKIP (not found): {session_path}", file=sys.stderr)
            continue
        article_names = [a.stem for a in articles]
        print(f"  Running --from-session {session_path} → covers: {', '.join(article_names[:4])}"
              + (f" +{len(article_names)-4} more" if len(article_names) > 4 else ""))
        if not args.dry_run:
            # Use the flagged articles directly (--article mode) rather than extracting
            # session wikilinks — the flagged pages may not be wikilinked in the session
            # even though the session contains relevant content.
            entity_paths = articles
            proposals = build_article_edit_proposals(
                article_paths=entity_paths,
                limit=-1,
                max_additions_per_article=3,
                top_k_per_query=6,
                sessions_only=True,
            )
            if proposals:
                added, total = merge_article_edit_proposals(proposals)
                print(f"    → {added} new proposals merged (total queue: {total})")
            else:
                print(f"    → No new proposals generated")

    if not args.dry_run:
        # Clear context_needed from all successfully processed articles
        for md_path in flagged_articles:
            _clear_context_needed(md_path)
        print(f"\nCleared context_needed from {len(flagged_articles)} article(s).")
        print("Next step: python3 scripts/vault_automation.py verify-article-edits")

    return 0


def cmd_check_title_integrity(args: argparse.Namespace) -> int:
    """Check that every vault page's H1 heading matches its frontmatter title (or filename stem).
    Also flags any H1 that contains a wikilink, which is always a content error."""
    issues: list[dict] = []
    h1_re = re.compile(r"^#\s+(.+)$", re.MULTILINE)
    wikilink_re = re.compile(r"\[\[")
    frontmatter_title_re = re.compile(r"(?m)^title:\s*[\"']?(.+?)[\"']?\s*$")

    skip_dirs = {".obsidian", "attachments", "templates"}
    skip_stems = {"index", "readme"}
    # Session files use "DFRPG Arden Vul Session N: {title}" as H1 while frontmatter title is
    # "N: {title}". This is a known intentional convention — don't flag them.
    # Also handles "Sessions N and M:" (plural) and plain "NN - title" / "NN: title" prefixes.
    session_h1_prefix_re = re.compile(
        r"^(?:DFRPG\s+Arden\s+Vul\s+Sessions?\s+[\w\s]+[:–-]|[\d]+[a-z]?\s+[-:/])",
        re.IGNORECASE
    )
    # Intentional subtitle differences in notes/lore — skip these paths.
    skip_subtitle_paths = {
        "vault/notes/Books Title Concordance.md",
        "vault/notes/Discord Summary 2025-W52.md",
        "vault/notes/Gedrick() Malachite.md",
        "vault/notes/Rumors.md",
        "vault/notes/Session 34-35-42b-43 QA Mining.md",
        "vault/notes/Weekly Summary Generation Log.md",
        "vault/lore/Announcing DFRPG Arden Vul.md",
        "vault/lore/Arden Vul Character Creation Rules.md",
        "vault/lore/Winding Stair.md",
        "vault/items/Gold Signet Ring with Gregor inscribed.md",
    }
    for md_path in sorted(VAULT.rglob("*.md")):
        if any(part in skip_dirs for part in md_path.parts):
            continue
        if md_path.stem.lower() in skip_stems:
            continue
        text = read_text(md_path)
        rel = md_path.relative_to(ROOT).as_posix()
        if rel in skip_subtitle_paths:
            continue

        # Extract frontmatter title if present.
        fm_match = frontmatter_title_re.search(text[:800])
        fm_title = fm_match.group(1).strip() if fm_match else None

        # Extract first H1.
        h1_match = h1_re.search(text)
        if not h1_match:
            continue
        h1_raw = h1_match.group(1).strip()

        # Strip wikilinks to get plain H1 text for comparison.
        h1_plain = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", h1_raw).strip()
        h1_plain = re.sub(r"\[\[([^\]]+)\]\]", r"\1", h1_plain).strip()

        # Skip session files — their H1 prefix "DFRPG Arden Vul Session N:" is intentional.
        if session_h1_prefix_re.match(h1_plain):
            continue

        has_wikilink = bool(wikilink_re.search(h1_raw))
        stem = md_path.stem

        mismatches: list[str] = []
        if fm_title and fm_title.lower() != h1_plain.lower():
            mismatches.append(f"H1 '{h1_plain}' ≠ frontmatter title '{fm_title}'")
        elif not fm_title and stem.lower() != h1_plain.lower():
            mismatches.append(f"H1 '{h1_plain}' ≠ filename stem '{stem}'")
        # Allow H1 to be a superset of the frontmatter title — e.g. "Tresti Iredell" is fine
        # when frontmatter title is "Tresti", because the H1 is simply the full name expansion.
        if mismatches and fm_title and fm_title.lower() in h1_plain.lower():
            mismatches = []
        # Only flag a wikilink-in-H1 as a distinct error when the plain text also mismatches.
        # Wikilinks in headings that correctly name the page (e.g. "# Ebon Spear of [[Arden]]") are style, not errors.
        if has_wikilink and mismatches:
            mismatches.insert(0, f"H1 contains wikilink and plain text mismatches: '{h1_raw}'")

        if mismatches:
            issues.append({"path": rel, "h1": h1_raw, "fm_title": fm_title or "", "stem": stem, "issues": mismatches})

    if args.json:
        print(json.dumps({"ok": True, "issue_count": len(issues), "issues": issues}, indent=2))
    else:
        if not issues:
            print("No title integrity issues found.")
        else:
            print(f"{len(issues)} title integrity issue(s):\n")
            for item in issues:
                print(f"  {item['path']}")
                for msg in item["issues"]:
                    print(f"    - {msg}")
    return 0 if not issues else 1


def audit_extract_uncited_claims(text: str, sections: list[str]) -> list[tuple[str, str]]:
    """Extract (section, claim) pairs from named H2 sections where the claim has no wikilink citation."""
    results: list[tuple[str, str]] = []
    h2_split = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    # h2_split alternates: [preamble, heading, body, heading, body, ...]
    for i in range(1, len(h2_split) - 1, 2):
        heading = h2_split[i].strip()
        if sections and heading not in sections:
            continue
        body = h2_split[i + 1]
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip leading bullet markers
            claim = re.sub(r"^[-*]\s+", "", line).strip()
            if not claim or len(claim) < 15:
                continue
            # Skip lines that already have a parenthetical citation ([[...]])
            if re.search(r"\(\[\[", claim):
                continue
            # Skip lines that cite a session or source inline (wikilink in the text)
            if re.search(r"\[\[sessions/|\[\[notes/Discord Summary|\[\[lore/Found Notes", claim):
                continue
            # Skip lines that are pure wikilinks (session/source lists)
            if re.match(r"^\[\[", claim) and claim.count("[[") == 1:
                continue
            # Skip pure speculative/annotative language — flag separately but don't audit against RAG
            if re.search(r"\bsuggests?\b|\bpresumably?\b|\blikely\b|\bmay be\b|\bpossibly\b", claim, re.IGNORECASE):
                continue
            results.append((heading, claim))
    return results


def cmd_audit_content_claims(args: argparse.Namespace) -> int:
    """Audit existing vault page content for claims that can't be verified against the RAG.

    For each uncited bullet in the target sections, searches the vault RAG and checks
    whether the claim appears in any result. Outputs a report of suspicious claims.
    """
    target_kinds = {k.strip().lower() for k in args.kinds.split(",")} if args.kinds else None
    target_sections = [s.strip() for s in args.sections.split(",")] if args.sections else ["Summary", "Notes", "Description"]
    limit = args.limit if args.limit and args.limit > 0 else None

    entity_dirs_map = {
        "npc": "npcs", "npcs": "npcs",
        "location": "locations", "locations": "locations",
        "faction": "factions", "factions": "factions",
        "item": "items", "items": "items",
        "monster": "monsters", "monsters": "monsters",
    }

    paths: list[Path] = []
    if args.article:
        p = ROOT / args.article
        if p.exists():
            paths = [p]
    else:
        dirs_to_scan = set()
        for k, d in entity_dirs_map.items():
            if target_kinds is None or k in target_kinds:
                dirs_to_scan.add(d)
        for d in sorted(dirs_to_scan):
            paths.extend(sorted((VAULT / d).glob("*.md")))

    if limit:
        paths = paths[:limit]

    suspicious: list[dict] = []
    supported_count = 0
    checked_count = 0

    for path in paths:
        text = read_text(path)
        rel = path.relative_to(ROOT).as_posix()
        title = article_title(path, text)
        claims = audit_extract_uncited_claims(text, target_sections)
        if not claims:
            continue

        for section, claim in claims:
            checked_count += 1
            # Search the RAG for the claim
            try:
                hits = vault_rag_search(claim[:120], top_k=3)
            except Exception:
                hits = []

            # Check if claim text appears in any hit (fuzzy: first 40 chars)
            needle = claim[:40].lower()
            found = any(needle in (h.get("text") or "").lower() for h in hits)

            if found:
                supported_count += 1
            else:
                # Secondary check: search by title + claim keywords
                try:
                    hits2 = vault_rag_search(f"{title} {claim[:60]}", top_k=3)
                    found2 = any(needle in (h.get("text") or "").lower() for h in hits2)
                except Exception:
                    found2 = False

                if found2:
                    supported_count += 1
                else:
                    suspicious.append({
                        "path": rel,
                        "title": title,
                        "section": section,
                        "claim": claim,
                        "top_hit": hits[0].get("path", "") if hits else "",
                    })

    report_lines = [
        "# Content Audit Report",
        f"",
        f"Checked {checked_count} uncited claims across {len(paths)} pages.",
        f"Supported by RAG: {supported_count} | Suspicious: {len(suspicious)}",
        "",
    ]
    for item in suspicious:
        report_lines.append(f"## {item['path']}")
        report_lines.append(f"**Section:** {item['section']}")
        report_lines.append(f"**Claim:** {item['claim']}")
        if item["top_hit"]:
            report_lines.append(f"**Closest RAG hit:** {item['top_hit']}")
        report_lines.append("")

    report_path = AUTOMATION_DIR / "proposals" / "content_audit_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    if args.json:
        print(json.dumps({
            "ok": True,
            "checked": checked_count,
            "supported": supported_count,
            "suspicious": len(suspicious),
            "report": str(report_path),
            "items": suspicious,
        }, indent=2))
    else:
        print(f"Checked {checked_count} uncited claims. Suspicious: {len(suspicious)}")
        print(f"Report: {report_path}")
        for item in suspicious[:20]:
            print(f"  [{item['path'].split('/')[-1]}] §{item['section']}: {item['claim'][:80]}")
        if len(suspicious) > 20:
            print(f"  ... and {len(suspicious) - 20} more. See report for full list.")
    return 0


def cmd_propose_article_edits(args: argparse.Namespace) -> int:
    sessions_only: bool = getattr(args, "sessions_only", False)
    from_session: str | None = getattr(args, "from_session", None)

    article_paths: list[Path] | None = None
    if from_session:
        session_path = ROOT / from_session
        if not session_path.exists():
            print(json.dumps({"ok": False, "error": f"session file not found: {from_session}"}), file=sys.stderr)
            return 1
        article_paths = extract_session_article_paths(session_path)
        if not article_paths:
            print(json.dumps({"ok": False, "error": f"no wikilinked entity pages found in {from_session}"}), file=sys.stderr)
            return 1
        print(f"Session-first mode: queued {len(article_paths)} article(s) from {from_session}", file=sys.stderr)
    elif args.article:
        article_paths = [Path(args.article)]

    proposals = build_article_edit_proposals(
        article_paths=article_paths,
        limit=args.limit,
        max_additions_per_article=args.max_additions_per_article,
        top_k_per_query=args.top_k_per_query,
        sessions_only=sessions_only,
    )
    # When processing a specific session or article, merge into the existing queue
    # so multiple --from-session runs accumulate without overwriting each other.
    if from_session or args.article:
        added, total = merge_article_edit_proposals(proposals)
        # Re-read merged JSON and regenerate the markdown report.
        merged_path = AUTOMATION_DIR / "proposals" / "article_edit_proposals.json"
        merged_proposals = [ArticleEditProposal(**r) for r in json.loads(merged_path.read_text(encoding="utf-8"))]
        write_article_edit_proposal_report(merged_proposals)
    else:
        added, total = len(proposals), len(proposals)
        write_article_edit_proposal_report(proposals)
    summary = {
        "ok": True,
        "proposals_new": added,
        "proposals_total": total,
        "articles_with_proposals": len({p.article_path for p in proposals}),
        "sessions_only": sessions_only,
        "from_session": from_session,
        "markdown": str(AUTOMATION_DIR / "proposals" / "article_edit_proposals.md"),
        "json": str(AUTOMATION_DIR / "proposals" / "article_edit_proposals.json"),
    }
    print(json.dumps(summary, indent=2))
    return 0


def cmd_verify_article_edits(args: argparse.Namespace) -> int:
    try:
        verifications = verify_article_edit_proposals(limit=args.limit)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    counts: dict[str, int] = {}
    for v in verifications:
        st = v.get("verifier_status", "unknown")
        counts[st] = counts.get(st, 0) + 1
    summary = {
        "ok": True,
        "verified_count": len(verifications),
        "status_counts": counts,
        "markdown": str(AUTOMATION_DIR / "proposals" / "article_edit_verifications.md"),
        "json": str(AUTOMATION_DIR / "proposals" / "article_edit_verifications.json"),
    }
    print(json.dumps(summary, indent=2))
    return 0


def cmd_apply_verified_article_edits(args: argparse.Namespace) -> int:
    result = apply_verified_article_edits(apply_changes=args.apply, limit=args.limit)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


def cmd_propose_metadata_edits(args: argparse.Namespace) -> int:
    article_paths = [Path(args.article)] if args.article else None
    proposals = build_metadata_edit_proposals(
        article_paths=article_paths,
        limit=args.limit,
        top_k_per_query=args.top_k_per_query,
    )
    write_metadata_edit_report(proposals)
    print(json.dumps({
        "ok": True,
        "proposal_count": len(proposals),
        "articles_with_proposals": len({item.article_path for item in proposals}),
        "markdown": str(AUTOMATION_DIR / "proposals" / "metadata_edit_proposals.md"),
        "json": str(AUTOMATION_DIR / "proposals" / "metadata_edit_proposals.json"),
    }, indent=2))
    return 0


def cmd_verify_metadata_edits(args: argparse.Namespace) -> int:
    try:
        verifications = verify_metadata_edit_proposals(limit=args.limit)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    counts: dict[str, int] = {}
    for item in verifications:
        status = str(item.get("verifier_status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps({
        "ok": True,
        "verified_count": len(verifications),
        "status_counts": counts,
        "markdown": str(AUTOMATION_DIR / "proposals" / "metadata_edit_verifications.md"),
        "json": str(AUTOMATION_DIR / "proposals" / "metadata_edit_verifications.json"),
    }, indent=2))
    return 0


def cmd_apply_verified_metadata_edits(args: argparse.Namespace) -> int:
    result = apply_verified_metadata_edits(apply_changes=args.apply, limit=args.limit)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


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
                "message": "Implement IAC/ACE proposal generation only after discover and validate are stable.",
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


def cmd_ingest_vault_rag(args: argparse.Namespace) -> int:
    try:
        result = vault_rag_ingest_all(reset=args.reset, limit=args.limit)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    if not args.verbose:
        result.pop("results", None)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


def cmd_refresh_vault_rag(args: argparse.Namespace) -> int:
    try:
        result = vault_rag_ingest_all(reset=False, limit=args.limit)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    if not args.verbose:
        result.pop("results", None)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


def cmd_vault_rag_search(args: argparse.Namespace) -> int:
    try:
        hits = vault_rag_search(args.query, top_k=args.top_k, kind=args.kind)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    output: list[dict] = []
    for hit in hits:
        item = {**hit}
        if not args.full and item.get("text"):
            item["text"] = item["text"][:300]
        output.append(item)
    print(json.dumps(
        {"ok": True, "query": args.query, "top_k": args.top_k, "kind": args.kind, "hits": output},
        indent=2,
    ))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    payload = import_low_risk(args.apply, args.blog_feed, force_discord_update=getattr(args, "force_discord_update", False))
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 2


def cmd_run_low_risk(args: argparse.Namespace) -> int:
    started_at = time.monotonic()
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
        proposals = build_entity_link_proposals()
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
                verified = verify_entity_link_proposals(None if int(verify_limit) < 0 else int(verify_limit))
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
                        **apply_verified_entity_links(True, None if int(apply_limit) < 0 else int(apply_limit)),
                    }
            except Exception as exc:
                verification_result = {"enabled": True, "ok": False, "error": str(exc)}
    article_edit_result: dict = {"enabled": False}
    selected_paths: list[Path] = []
    if before["ok"]:
        try:
            sources_cfg = load_local_sources()
            queue_top = int(sources_cfg.get("article_edit_queue_top", 0) or 0)
            media_queue_top = int(sources_cfg.get("media_edit_queue_top", 0) or 0)
            walk_step = int(sources_cfg.get("article_edit_walk_step", 0) or 0)
            ae_verify_limit = int(sources_cfg.get("article_edit_verify_limit", 0) or 0)
            ae_apply_limit = int(sources_cfg.get("article_edit_apply_limit", 0) or 0)
            ae_verify_limit_arg = None if ae_verify_limit < 0 else ae_verify_limit
            ae_apply_limit_arg = None if ae_apply_limit < 0 else ae_apply_limit
            if (queue_top or media_queue_top or walk_step) and sources_cfg.get("llm_base_url") and sources_cfg.get("llm_model"):
                seen: set[str] = set()
                if queue_top and article_queue:
                    for it in article_queue[:queue_top]:
                        if it.path not in seen:
                            seen.add(it.path)
                            selected_paths.append(Path(it.path))
                if media_queue_top and media_queue:
                    for it in media_queue[:media_queue_top]:
                        if it.path not in seen:
                            seen.add(it.path)
                            selected_paths.append(Path(it.path))
                walk_selection: list[str] = []
                if walk_step:
                    walk_selection = vault_walk_next(walk_step, save=True)
                    for wp in walk_selection:
                        if wp not in seen:
                            seen.add(wp)
                            selected_paths.append(Path(wp))
                article_edit_proposals = build_article_edit_proposals(
                    article_paths=selected_paths,
                    max_additions_per_article=3,
                    top_k_per_query=3,
                )
                write_article_edit_proposal_report(article_edit_proposals)
                article_edit_result = {
                    "enabled": True,
                    "queue_top": queue_top,
                    "media_queue_top": media_queue_top,
                    "walk_step": walk_step,
                    "walk_selection": walk_selection,
                    "articles_processed": len(selected_paths),
                    "proposal_count": len(article_edit_proposals),
                }
                if ae_verify_limit and article_edit_proposals:
                    verified = verify_article_edit_proposals(limit=ae_verify_limit_arg)
                    vcounts: dict[str, int] = {}
                    for v in verified:
                        st = str(v.get("verifier_status", "unknown"))
                        vcounts[st] = vcounts.get(st, 0) + 1
                    article_edit_result["verifier_status_counts"] = vcounts
                    if ae_apply_limit:
                        apply_result = apply_verified_article_edits(apply_changes=True, limit=ae_apply_limit_arg)
                        article_edit_result["applied"] = {
                            "supported_count": apply_result.get("supported_count", 0),
                            "articles_touched": apply_result.get("articles_touched", 0),
                            "total_applied": apply_result.get("total_applied", 0),
                            "files": [
                                r.get("article_path")
                                for r in apply_result.get("results", [])
                                if r.get("applied", 0) > 0
                            ],
                        }
        except Exception as exc:
            article_edit_result = {"enabled": True, "ok": False, "error": str(exc)[:200]}
    metadata_edit_result: dict = {"enabled": False}
    if before["ok"]:
        try:
            sources_cfg = load_local_sources()
            if sources_cfg.get("metadata_edit_enabled") and sources_cfg.get("llm_base_url") and sources_cfg.get("llm_model"):
                metadata_paths = selected_paths
                if not metadata_paths:
                    metadata_paths = [
                        item.path for item in build_article_queue(limit=sources_cfg["metadata_edit_queue_top"])
                    ]
                proposals = build_metadata_edit_proposals(article_paths=metadata_paths)
                write_metadata_edit_report(proposals)
                metadata_edit_result = {
                    "enabled": True,
                    "articles_processed": len(metadata_paths),
                    "proposal_count": len(proposals),
                }
                verify_limit = int(sources_cfg.get("metadata_edit_verify_limit", 0) or 0)
                apply_limit = int(sources_cfg.get("metadata_edit_apply_limit", 0) or 0)
                if verify_limit and proposals:
                    verified = verify_metadata_edit_proposals(None if verify_limit < 0 else verify_limit)
                    counts: dict[str, int] = {}
                    for item in verified:
                        status = str(item.get("verifier_status", "unknown"))
                        counts[status] = counts.get(status, 0) + 1
                    metadata_edit_result["verifier_status_counts"] = counts
                    if apply_limit:
                        metadata_edit_result["applied"] = apply_verified_metadata_edits(
                            apply_changes=True,
                            limit=None if apply_limit < 0 else apply_limit,
                        )
        except Exception as exc:
            metadata_edit_result = {"enabled": True, "ok": False, "error": str(exc)[:200]}
    action_items_result: dict = {"enabled": False}
    if before["ok"]:
        try:
            sources_cfg = load_local_sources()
            if sources_cfg.get("action_items_enabled") and sources_cfg.get("llm_base_url") and sources_cfg.get("llm_model"):
                refresh_due, refresh_reason = action_items_refresh_due(
                    import_result,
                    int(sources_cfg.get("action_items_refresh_hours", 24) or 24),
                )
                if refresh_due:
                    action_items_result = update_action_items_safely(
                        apply_changes=bool(sources_cfg.get("action_items_apply")),
                        latest_sessions=int(sources_cfg.get("action_items_latest_sessions", 8) or 8),
                        latest_discord_weeks=int(sources_cfg.get("action_items_latest_discord_weeks", 4) or 4),
                        max_items=int(sources_cfg.get("action_items_max_items", 50) or 50),
                    )
                    action_items_result["refresh_reason"] = refresh_reason
                else:
                    action_items_result = {
                        "enabled": True,
                        "ok": True,
                        "skipped": True,
                        "reason": refresh_reason,
                    }
        except Exception as exc:
            action_items_result = {"enabled": True, "ok": False, "error": str(exc)[:200]}
    vault_rag_refresh = refresh_vault_rag_safely() if before["ok"] else {"ok": False, "skipped": True, "reason": "pre_validation_failed"}
    after = validate_state()
    payload = {
        "ok": before["ok"] and import_result["ok"] and after["ok"],
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
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
        "article_edit": article_edit_result,
        "metadata_edit": metadata_edit_result,
        "action_items": action_items_result,
        "vault_rag_refresh": vault_rag_refresh,
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
    entity_links.add_argument("--limit-per-source", type=int, default=None, help="Optional maximum proposals per source file")
    entity_links.set_defaults(func=cmd_propose_entity_links)

    verify_links = sub.add_parser("verify-entity-links", help="LLM-verify review-only entity link proposals")
    verify_links.add_argument("--limit", type=int, default=None, help="Optional maximum proposals to verify")
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

    ingest_vault_rag = sub.add_parser("ingest-vault-rag", help="Ingest vault sessions/summaries/lore into the local Chroma vault-rag collection")
    ingest_vault_rag.add_argument("--reset", action="store_true", help="Delete the existing collection first and rebuild from scratch")
    ingest_vault_rag.add_argument("--limit", type=int, default=None, help="Maximum number of files to process (for testing)")
    ingest_vault_rag.add_argument("--verbose", action="store_true", help="Include per-file results in the JSON output")
    ingest_vault_rag.set_defaults(func=cmd_ingest_vault_rag)

    refresh_vault_rag = sub.add_parser("refresh-vault-rag", help="Refresh the vault-rag collection (sha256-gated; only changed files get re-embedded)")
    refresh_vault_rag.add_argument("--limit", type=int, default=None, help="Maximum number of files to process (for testing)")
    refresh_vault_rag.add_argument("--verbose", action="store_true", help="Include per-file results in the JSON output")
    refresh_vault_rag.set_defaults(func=cmd_refresh_vault_rag)

    search_vault_rag = sub.add_parser("vault-rag-search", help="Query the vault-rag Chroma collection")
    search_vault_rag.add_argument("query", help="Natural-language query")
    search_vault_rag.add_argument("--top-k", type=int, default=5, help="Number of results to return (default 5)")
    search_vault_rag.add_argument(
        "--kind",
        choices=["session", "summary", "note", "lore", "npc", "pc", "location", "faction", "item", "monster", "spell", "concept", "rollup", "spreadsheet"],
        default=None,
        help="Filter by chunk kind",
    )
    search_vault_rag.add_argument("--full", action="store_true", help="Print full chunk text instead of a 300-char preview")
    search_vault_rag.set_defaults(func=cmd_vault_rag_search)

    run_context = sub.add_parser("run-context-needed", help="Find context_needed: flagged articles and run targeted --from-session passes, then clear markers")
    run_context.add_argument("--dry-run", action="store_true", help="List flagged articles without running proposals or clearing markers")
    run_context.set_defaults(func=cmd_run_context_needed)

    audit_claims = sub.add_parser("audit-content-claims", help="Audit uncited bullets in vault pages against the RAG — surfaces potential fabrications")
    audit_claims.add_argument("--kinds", default=None, help="Comma-separated entity kinds to audit (npc,location,faction,item,monster). Default: all.")
    audit_claims.add_argument("--sections", default=None, help="Comma-separated H2 sections to check. Default: Summary,Notes,Description.")
    audit_claims.add_argument("--article", default=None, help="Audit a single article by repo-relative path.")
    audit_claims.add_argument("--limit", type=int, default=None, help="Max pages to audit.")
    audit_claims.add_argument("--json", action="store_true", help="Output results as JSON.")
    audit_claims.set_defaults(func=cmd_audit_content_claims)

    check_title = sub.add_parser("check-title-integrity", help="Report vault pages whose H1 heading mismatches their frontmatter title or filename")
    check_title.add_argument("--json", action="store_true", help="Output results as JSON")
    check_title.set_defaults(func=cmd_check_title_integrity)

    propose_article = sub.add_parser("propose-article-edits", help="Generate sourced article edit proposals via vault-rag + LLM")
    propose_article.add_argument("--limit", type=int, default=-1, help="Number of queue articles to process (-1 = all, default; ignored when --article is set)")
    propose_article.add_argument("--article", default=None, help="Process a single article by repo-relative path (e.g. vault/npcs/Pelteon.md)")
    propose_article.add_argument("--max-additions-per-article", type=int, default=3, help="Maximum proposals to keep per article (default 3)")
    propose_article.add_argument("--top-k-per-query", type=int, default=3, help="vault-rag top_k per generated research query (default 3)")
    propose_article.add_argument("--sessions-only", action="store_true", help="Restrict research context to session recap chunks only (no Discord summaries or hints)")
    propose_article.add_argument("--from-session", default=None, metavar="RELPATH", help="Queue locations/NPCs/items/factions wikilinked from a session file (e.g. vault/sessions/Session 55.md)")
    propose_article.set_defaults(func=cmd_propose_article_edits)

    verify_article = sub.add_parser("verify-article-edits", help="LLM-verify article edit proposals against canonical sources")
    verify_article.add_argument("--limit", type=int, default=-1, help="Maximum proposals to verify (-1 = all, default)")
    verify_article.set_defaults(func=cmd_verify_article_edits)

    apply_article = sub.add_parser("apply-verified-article-edits", help="Apply supported article edits to vault files")
    apply_article.add_argument("--apply", action="store_true", help="Write changes to vault files; omit for dry-run")
    apply_article.add_argument("--limit", type=int, default=None, help="Maximum supported edits to consider")
    apply_article.set_defaults(func=cmd_apply_verified_article_edits)

    propose_metadata = sub.add_parser("propose-metadata-edits", help="Generate sourced retrieval-metadata proposals via vault-rag + LLM")
    propose_metadata.add_argument("--limit", type=int, default=-1, help="Number of queue articles to process (-1 = all, default)")
    propose_metadata.add_argument("--article", default=None, help="Process a single article by repo-relative path")
    propose_metadata.add_argument("--top-k-per-query", type=int, default=3, help="vault-rag top_k per generated research query")
    propose_metadata.set_defaults(func=cmd_propose_metadata_edits)

    verify_metadata = sub.add_parser("verify-metadata-edits", help="LLM-verify retrieval-metadata proposals against cited sources")
    verify_metadata.add_argument("--limit", type=int, default=None, help="Maximum proposals to verify")
    verify_metadata.set_defaults(func=cmd_verify_metadata_edits)

    apply_metadata = sub.add_parser("apply-verified-metadata-edits", help="Apply supported retrieval-metadata edits to vault files")
    apply_metadata.add_argument("--apply", action="store_true", help="Write changes to vault files; omit for dry-run")
    apply_metadata.add_argument("--limit", type=int, default=None, help="Maximum supported edits to consider")
    apply_metadata.set_defaults(func=cmd_apply_verified_metadata_edits)

    build_actions = sub.add_parser("build-action-items", help="Generate a cited current action-item inventory")
    build_actions.add_argument("--latest-sessions", type=int, default=8, help="Recent session files to include as current-status evidence")
    build_actions.add_argument("--latest-discord-weeks", type=int, default=4, help="Recent Discord summary weeks to include as supplementary context")
    build_actions.add_argument("--max-items", type=int, default=200, help="Maximum action items to keep")
    build_actions.set_defaults(func=cmd_build_action_items)

    apply_actions = sub.add_parser("apply-action-items", help="Apply the generated action-item inventory to the canonical note")
    apply_actions.add_argument("--apply", action="store_true", help="Write vault/notes/Active Action Items.md; omit for dry-run")
    apply_actions.set_defaults(func=cmd_apply_action_items)

    propose_new = sub.add_parser("propose-new-entities", help="Extract new entity candidates from canonical sources via IAC + filters")
    propose_new.add_argument("--source-limit", type=int, default=10, help="Latest canonical sources to scan (default 10)")
    propose_new.add_argument("--all-sources", action="store_true", help="Scan every session and Discord summary (full vault walk, ~17 min)")
    propose_new.add_argument("--limit", type=int, default=500, help="Maximum candidates to keep after filtering (default 500)")
    propose_new.set_defaults(func=cmd_propose_new_entities)

    verify_new = sub.add_parser("verify-new-entities", help="LLM-verify new entity candidates against canonical source evidence")
    verify_new.add_argument("--limit", type=int, default=-1, help="Maximum candidates to verify (-1 = all unverified, default)")
    verify_new.set_defaults(func=cmd_verify_new_entities)

    apply_new = sub.add_parser("apply-verified-new-entities", help="Create stub vault pages for confirmed new entity candidates")
    apply_new.add_argument("--apply", action="store_true", help="Write stub files; omit for dry-run")
    apply_new.add_argument("--limit", type=int, default=None, help="Maximum confirmed candidates to apply (default unlimited)")
    apply_new.set_defaults(func=cmd_apply_verified_new_entities)

    walk_status = sub.add_parser("vault-walk-status", help="Show the vault walk cursor's current position")
    walk_status.set_defaults(func=cmd_vault_walk_status)

    status = sub.add_parser("status", help="Summarize repo, Discord, and Blogspot source state")
    status.set_defaults(func=cmd_status)

    importer = sub.add_parser("import-low-risk", help="Import canonical Blogspot recaps and external Discord digests")
    importer.add_argument("--apply", action="store_true", help="Write changes. Omit for dry-run.")
    importer.add_argument("--blog-feed", default=BLOG_FEED_URL, help="Blogger JSON feed URL")
    importer.add_argument("--force-discord-update", action="store_true", help="Overwrite existing Discord Summaries when revised-digest.md has changed")
    importer.set_defaults(func=cmd_import)

    scheduled = sub.add_parser("run-low-risk", help="Scheduled low-risk vault maintenance entry point")
    scheduled.add_argument("--blog-feed", default=BLOG_FEED_URL, help="Blogger JSON feed URL")
    scheduled.set_defaults(func=cmd_run_low_risk)

    summarize_scratch = sub.add_parser("summarize-scratchpad", help="Condense SCRATCH.md using the configured LLM")
    summarize_scratch.set_defaults(func=cmd_summarize_scratchpad)

    research = sub.add_parser("research-article", help="Run an iterative RAG research agent to propose edits for a vault article")
    research.add_argument("--article", required=True, help="Repo-relative path to the article (e.g. vault/items/Pale Green Horn.md)")
    research.add_argument("--max-rounds", type=int, default=5, help="Maximum RAG search rounds (default 5)")
    research.add_argument("--top-k", type=int, default=8, help="RAG results per query per round (default 8)")
    research.add_argument("--max-additions", type=int, default=5, help="Maximum proposals to generate (default 5)")
    research.set_defaults(func=cmd_research_article)

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
