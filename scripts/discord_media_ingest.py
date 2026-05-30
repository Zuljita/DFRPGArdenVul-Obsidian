#!/usr/bin/env python3
"""Ingest downloaded Discord media into the vault.

Walks /home/kyle/discord-chat-explorer/media/manifest.jsonl, classifies each
file (rule-based for character sheets / data files; Gemma-4 vision for images),
proposes a target vault page and section, and writes proposals to
data/automation/proposals/media_ingestion_proposals.{json,md}.

Apply step copies the file into vault/attachments/discord/<channel>/<file> and
injects a reference (`![[…]]` for images, `[[…]]` for binaries) into the
target vault page.

Subcommands:
  propose-media-ingestion   classify + write proposals (no writes to vault)
  apply-media-ingestion     copy files + inject references (gated --apply)
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import vault_automation as va  # type: ignore

VAULT = va.VAULT
ROOT = va.ROOT
PROPOSALS_DIR = va.AUTOMATION_DIR / "proposals"
PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

EXPLORER_ROOT = Path("/home/kyle/discord-chat-explorer")
MEDIA_MANIFEST = EXPLORER_ROOT / "media" / "manifest.jsonl"
ROLLUPS_ROOT = EXPLORER_ROOT / "weekly-rollups"

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}
VIDEO_EXTS = {"mp4", "webm", "mov"}
SHEET_EXTS = {"gcs", "eqp"}
DOC_EXTS = {"pdf", "txt", "md"}

# Channel hints used by the classifier as priors.
CHANNEL_DEFAULT_KIND = {
    "character-sheets": "pc-character-sheet",
    "new-spells": "spell-attachment",
    "monster-cards": "monster",
    "handouts": "handout",
    "loot": "item",
    "worldbuilding": "lore",
    "worldbuilding-the-book-of-priors": "lore",
    "general-rumor-sharing": "lore",
}


# ---------- helpers ----------

def load_manifest_ok() -> list[dict]:
    """Return manifest entries with status=ok (file downloaded successfully).

    De-dupes by (stream_id, message_id, attachment_id) keeping the latest
    successful entry (manifest appends as we re-run)."""
    if not MEDIA_MANIFEST.exists():
        return []
    by_key: dict[tuple, dict] = {}
    with MEDIA_MANIFEST.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") != "ok":
                continue
            key = (rec.get("stream_id", ""), rec.get("message_id", ""), rec.get("attachment_id", ""))
            by_key[key] = rec
    return list(by_key.values())


def pc_inventory() -> list[dict]:
    """Return PC entity records: {path, title, aliases, tokens}.

    Includes top-level pcs/ and the grudge-brigade subfolder so character
    sheets that name "Thronebreaker" still match."""
    out = []
    for md in list((VAULT / "pcs").glob("*.md")) + list((VAULT / "pcs" / "grudge-brigade").glob("*.md")):
        if md.stem.lower() in {"index", "readme"}:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = md.read_text(encoding="latin-1")
        fm = va.parse_frontmatter(text)
        aliases = fm.get("aliases") if isinstance(fm, dict) else []
        if isinstance(aliases, str):
            aliases = [aliases]
        aliases = [str(a) for a in (aliases or []) if a]
        title_match = re.search(r"^# (.+)$", text, flags=re.M)
        title = (title_match.group(1).strip() if title_match else md.stem).strip()
        all_names = {title.lower(), md.stem.lower()} | {a.lower() for a in aliases}
        tokens: set[str] = set()
        for n in all_names:
            tokens |= set(re.findall(r"[a-z0-9]+", n))
        out.append({
            "path": str(md.relative_to(ROOT)),
            "title": title,
            "aliases": aliases,
            "all_names": all_names,
            "tokens": tokens,
        })
    return out


def match_pc_from_filename(filename: str, pcs: list[dict]) -> tuple[dict | None, str]:
    """Greedy fuzzy match of a filename like 'Vael_Sunshadow.gcs' to a PC.

    Returns (pc_record_or_None, reason).
    """
    stem = re.sub(r"\.[^.]+$", "", filename)
    stem_tokens = set(re.findall(r"[a-z0-9]+", stem.lower()))
    if not stem_tokens:
        return None, "empty filename stem"

    # Direct alias hit: filename stem contains a PC alias as substring
    for pc in pcs:
        for name in pc["all_names"]:
            if not name:
                continue
            name_compact = re.sub(r"[^a-z0-9]+", "", name)
            stem_compact = re.sub(r"[^a-z0-9]+", "", stem.lower())
            if len(name_compact) >= 4 and name_compact in stem_compact:
                return pc, f"alias '{name}' matched in filename stem"

    # Token overlap fallback
    best_pc, best_overlap = None, 0
    for pc in pcs:
        overlap = len(stem_tokens & pc["tokens"])
        if overlap > best_overlap and overlap >= 2:
            best_pc, best_overlap = pc, overlap
    if best_pc:
        return best_pc, f"token overlap = {best_overlap} ({sorted(stem_tokens & best_pc['tokens'])})"
    return None, "no PC name overlap"


def find_stream_context(channel_id: str, message_id: str, window_hours: float = 24) -> str:
    """Return surrounding messages from the raw stream JSONL within a time window.

    Uses a ±window_hours window around the target message's timestamp rather
    than a fixed message count, so threads that span many hours stay connected
    while very busy channels don't balloon the context.

    Reads directly from the stream file — not dependent on rollups existing.
    """
    from datetime import datetime, timezone, timedelta
    stream_glob = list({
        p for pattern in [
            f"guilds/*/streams/*-{channel_id}.jsonl",
            f"guilds/*/streams/*{channel_id}*.jsonl",
        ]
        for p in EXPLORER_ROOT.glob(pattern)
    })
    if not stream_glob:
        return ""
    records: list[tuple[datetime, int, str, str]] = []  # (ts, mid, author, body)
    seen_mids: set[int] = set()
    for jsonl in stream_glob:
        with jsonl.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message") or {}
                mid_str = msg.get("id") or ""
                if not mid_str:
                    continue
                try:
                    mid = int(mid_str)
                except ValueError:
                    continue
                if mid in seen_mids:
                    continue
                seen_mids.add(mid)
                ts_str = msg.get("timestamp") or ""
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except ValueError:
                    continue
                author = (msg.get("author") or {}).get("global_name") or \
                         (msg.get("author") or {}).get("username") or "?"
                content = (msg.get("content") or "").strip()
                atts = msg.get("attachments") or []
                att_notes = " ".join(
                    f"[attachment: {a.get('filename', '')}]" for a in atts
                )
                body = " ".join(filter(None, [content, att_notes]))
                records.append((ts, mid, author, body))
    if not records:
        return ""
    records.sort(key=lambda x: x[0])
    target_mid = int(message_id) if message_id.isdigit() else 0
    target_ts = next((r[0] for r in records if r[1] == target_mid), None)
    if target_ts is None:
        return ""
    cutoff = timedelta(hours=window_hours)
    lines = []
    for ts, mid, author, body in records:
        if abs((ts - target_ts).total_seconds()) <= cutoff.total_seconds():
            marker = " ◀ THIS MESSAGE" if mid == target_mid else ""
            lines.append(f"[{ts.strftime('%Y-%m-%d %H:%M')}] {author}: {body[:400]}{marker}")
    return "\n".join(lines)


def find_rollup_context(channel_id: str, message_id: str, window_hours: float = 24) -> str:
    """Return surrounding context for an image message.

    Tries the raw stream JSONL first (time-based ±window_hours window).
    Falls back to weekly rollup markdown if the stream file can't be found.
    """
    ctx = find_stream_context(channel_id, message_id, window_hours=window_hours)
    if ctx:
        return ctx
    # Fallback: scan rollup markdown files with a fixed ±8 message window.
    target = int(message_id) if message_id.isdigit() else 0
    found = []
    for rollup_md in sorted(ROLLUPS_ROOT.glob("*/channels/*.md")):
        text = rollup_md.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(
            r"^## (?P<dt>\d{4}-\d{2}-\d{2}[^\n-]*) - (?P<author>[^\n-]+) - (?P<mid>\d+)\s*\n+(?P<body>.+?)(?=^## \d{4}-\d{2}-\d{2}|\Z)",
            text, flags=re.M | re.S,
        ):
            mid = int(m.group("mid"))
            found.append((mid, m.group("dt").strip(), m.group("author").strip(),
                          m.group("body").strip()))
    if not found:
        return ""
    found.sort(key=lambda x: x[0])
    idx = next((i for i, f in enumerate(found) if f[0] == target), None)
    if idx is None:
        return ""
    lo = max(0, idx - 8)
    hi = min(len(found), idx + 9)
    lines = []
    for i in range(lo, hi):
        mid, dt, author, body = found[i]
        marker = " ◀ THIS MESSAGE" if i == idx else ""
        lines.append(f"[{dt}] {author}: {body[:400]}{marker}")
    return "\n".join(lines)


# ---------- vision classifier ----------

VISION_SYSTEM = """You are classifying images posted to a private Discord server for an Arden Vul DFRPG campaign. For each image, decide:
  1. What kind of image it is (portrait, map, character-sheet-screenshot, item-photo, monster-stat-block, group-art, meme, chat-screenshot, off-topic).
  2. Whether it belongs in the campaign vault knowledge-base.
  3. If yes, which vault entity it is about (NPC name, PC name, location name, item name, monster name, or just "general lore").

Classification rules:
- INCLUDE: AI-generated or hand-drawn portraits of named campaign NPCs or PCs, even if posted casually in #off-topic. Use surrounding Discord context to identify the character — if messages nearby ask "which looks most like [Name]?" or name the character, that IS the entity.
- INCLUDE: Maps, handouts, monster stat blocks, item art, and group faction art relevant to the campaign.
- INCLUDE: Images from #screenshots are almost always dungeon maps, battle grids, or in-session reference images — include them and classify as "map" unless obviously off-topic.
- INCLUDE: Images from #character-sheets that are portraits, character art, or illustrated character reference images.
- INCLUDE: Images from #pc-notes, #ooc-planning, #general that show campaign maps, handouts, or character art; skip personal/off-topic content in those channels.
- INCLUDE: Images from loot channels (channel name starts with "Loot") are likely item photos or loot-sheet screenshots — include as "item".
- SKIP: Screenshots of wiki/Obsidian vault pages (dark background, structured sections like Summary/Background/Properties with wikilinks). These are screenshots of data that already exists as text in the vault.
- SKIP: Screenshots of AI chat interfaces (ChatGPT/Claude/Gemini UI chrome) where the content is reasoning, planning, or text generation — NOT a portrait. Exception: if the AI output IS a portrait image embedded in the screenshot, classify by the portrait content.
- SKIP: Memes, real-world photos, weather screenshots, food photos, and other off-topic personal content.
- SKIP: LLM "thinking" traces or internal reasoning dumps (walls of small text, no images).

Output JSON exactly:
{"kind":"...","include":true|false,"entity":"<title or empty>","entity_kind":"npc|pc|location|item|monster|lore|skip","caption":"<one short sentence>","reason":"<why include/skip>"}
"""


_MAX_IMAGE_BYTES = 3 * 1024 * 1024   # 3 MB encoded; resize if larger
_MAX_IMAGE_DIM   = 1536              # max width or height after resize


def _prepare_image_data_url(image_path: Path) -> str:
    """Return a base64 data URL for the image, resizing if necessary.

    Large images and webp files cause HTTP 400 errors from LM Studio.
    Resizes anything over _MAX_IMAGE_DIM on its longest side and converts
    webp/gif to JPEG so the payload stays within limits.
    """
    from PIL import Image
    import io
    with Image.open(image_path) as img:
        # Convert palette/transparency modes that JPEG can't handle
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        # Resize if either dimension exceeds the limit
        w, h = img.size
        if max(w, h) > _MAX_IMAGE_DIM:
            scale = _MAX_IMAGE_DIM / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        # Encode as JPEG (universally supported, good compression)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        raw = buf.getvalue()
    # If still too large, re-encode at lower quality
    if len(raw) > _MAX_IMAGE_BYTES:
        buf = io.BytesIO()
        with Image.open(image_path) as img:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            w, h = img.size
            scale = min(1.0, (_MAX_IMAGE_DIM * 0.75) / max(w, h))
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            img.save(buf, format="JPEG", quality=70)
        raw = buf.getvalue()
    return f"data:image/jpeg;base64,{base64.b64encode(raw).decode()}"


def vision_classify(image_path: Path, context: str, channel: str, filename: str) -> dict:
    sources = va.load_local_sources()
    base_url = sources.get("llm_base_url") or "http://100.76.165.94:1234/v1"
    model = sources.get("llm_model") or "google/gemma-4-26b-a4b"
    try:
        data_url = _prepare_image_data_url(image_path)
    except Exception as e:
        raise RuntimeError(f"image prep failed: {e}") from e
    user_text = (
        f"Channel: #{channel}\n"
        f"Filename: {filename}\n\n"
        f"Surrounding Discord context:\n{context or '(none captured)'}\n\n"
        "Classify per your instructions. Respond with JSON only."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": VISION_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
        "max_tokens": 4096,
        "temperature": 0.1,
        "stream": False,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        body = json.loads(r.read().decode("utf-8"))
    content = (body["choices"][0]["message"].get("content") or "").strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```\s*$", "", content)
    m = re.search(r"\{.*\}", content, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {"kind": "parse_error", "include": False, "raw": content[:500]}
    return {"kind": "parse_error", "include": False, "raw": content[:500]}


def match_vault_page(entity: str, entity_kind: str) -> tuple[str | None, str]:
    """Resolve a classifier-suggested entity name to an existing vault page."""
    if not entity or entity_kind == "skip":
        return None, "no entity"
    folder_map = {"npc": "npcs", "pc": "pcs", "location": "locations",
                  "item": "items", "monster": "monsters", "lore": "lore"}
    folder = folder_map.get(entity_kind)
    if not folder:
        return None, f"unknown entity_kind '{entity_kind}'"
    name_lower = entity.lower().strip()
    # Direct stem match
    for md in (VAULT / folder).rglob("*.md"):
        if md.stem.lower() == name_lower:
            return str(md.relative_to(ROOT)), "stem match"
    # Alias match — scan all pages in that folder
    for md in (VAULT / folder).rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        fm = va.parse_frontmatter(text)
        aliases = fm.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        for a in aliases:
            if str(a).lower() == name_lower:
                return str(md.relative_to(ROOT)), f"alias '{a}'"
    # Fuzzy substring
    for md in (VAULT / folder).rglob("*.md"):
        if name_lower in md.stem.lower() or md.stem.lower() in name_lower:
            return str(md.relative_to(ROOT)), "substring match"
    return None, f"no match in vault/{folder}/"


# ---------- propose lane ----------

def propose_media_ingestion(args: argparse.Namespace) -> int:
    manifest = load_manifest_ok()
    print(f"manifest entries with status=ok: {len(manifest)}", file=sys.stderr)
    if args.limit:
        manifest = manifest[: args.limit]

    pcs = pc_inventory()
    print(f"PC index built: {len(pcs)} characters", file=sys.stderr)

    # Skip files already proposed (idempotent)
    existing_proposals: dict[str, dict] = {}
    out_json = PROPOSALS_DIR / "media_ingestion_proposals.json"
    if out_json.exists() and not args.regenerate:
        for p in json.loads(out_json.read_text()):
            existing_proposals[p["local_path"]] = p

    proposals: list[dict] = list(existing_proposals.values())
    stats: dict[str, int] = defaultdict(int)
    for i, rec in enumerate(manifest, 1):
        local_path = rec.get("local_path") or ""
        if local_path in existing_proposals:
            stats["already_proposed"] += 1
            continue
        local_abs = EXPLORER_ROOT.parent / local_path if local_path.startswith("discord-chat-explorer/") else EXPLORER_ROOT / local_path[len("media/"):] if local_path.startswith("media/") else EXPLORER_ROOT.parent / local_path
        # The manifest paths look like "media/<channel_id>/<msg_id>-<file>" relative to discord-chat-explorer root.
        local_abs = EXPLORER_ROOT / local_path
        if not local_abs.exists():
            stats["file_missing"] += 1
            continue

        filename = rec.get("filename") or local_abs.name
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        channel = rec.get("stream_name") or rec.get("parent_name") or "unknown"
        msg_id = rec.get("message_id") or ""
        channel_id = rec.get("stream_id") or ""
        author = rec.get("author") or ""
        timestamp = rec.get("timestamp") or ""

        proposal = {
            "local_path": local_path,
            "absolute_path": str(local_abs),
            "filename": filename,
            "ext": ext,
            "size": rec.get("size", 0),
            "channel": channel,
            "channel_id": channel_id,
            "author": author,
            "timestamp": timestamp,
            "message_id": msg_id,
        }

        # ----- rule-based: character sheets (gcs/eqp/pdf in character-sheets channel) -----
        if channel == "character-sheets" and ext in (SHEET_EXTS | {"pdf"}):
            pc, reason = match_pc_from_filename(filename, pcs)
            proposal.update({
                "classifier": "rule",
                "kind": "pc-character-sheet",
                "include": pc is not None,
                "target_page": pc["path"] if pc else None,
                "target_section": "Character Sheets",
                "entity": pc["title"] if pc else None,
                "entity_kind": "pc",
                "reason": reason,
                "vault_attachment_path": (
                    f"vault/attachments/discord/character-sheets/{msg_id}-{filename}"
                    if pc else None
                ),
            })
            stats[f"rule:character-sheet:{'matched' if pc else 'unmatched'}"] += 1
        # ----- skip videos by default; user can opt in later -----
        elif ext in VIDEO_EXTS:
            proposal.update({
                "classifier": "rule",
                "kind": "video",
                "include": False,
                "reason": "video files skipped by default; review manually if relevant",
            })
            stats["rule:video:skipped"] += 1
        # ----- images: vision-based -----
        elif ext in IMAGE_EXTS:
            try:
                context = find_rollup_context(channel_id, msg_id)
                proposal["discord_context"] = context
                verdict = vision_classify(local_abs, context, channel, filename)
            except Exception as e:
                proposal.update({
                    "classifier": "vision",
                    "kind": "error",
                    "include": False,
                    "reason": f"vision error: {e}",
                })
                stats["vision:error"] += 1
                proposals.append(proposal)
                if i % 5 == 0:
                    out_json.write_text(json.dumps(proposals, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"  vision progress: {i}/{len(manifest)} (errors so far: {stats['vision:error']})", file=sys.stderr)
                continue
            include = bool(verdict.get("include"))
            entity = (verdict.get("entity") or "").strip()
            entity_kind = (verdict.get("entity_kind") or "").strip().lower()
            target_page, match_reason = (None, "")
            if include and entity and entity_kind not in ("", "skip"):
                target_page, match_reason = match_vault_page(entity, entity_kind)
            proposal.update({
                "classifier": "vision",
                "kind": verdict.get("kind", "?"),
                "include": include,
                "entity": entity or None,
                "entity_kind": entity_kind or None,
                "caption": verdict.get("caption", ""),
                "vision_reason": verdict.get("reason", ""),
                "target_page": target_page,
                "match_reason": match_reason,
                "target_section": _section_for_kind(verdict.get("kind", "")),
                "vault_attachment_path": (
                    f"vault/attachments/discord/{channel}/{msg_id}-{filename}"
                    if include and target_page else None
                ),
            })
            stats[f"vision:{verdict.get('kind','?')}:{'include' if include else 'skip'}"] += 1
            if include and not target_page:
                stats["vision:include_no_target"] += 1
        # ----- everything else: surface as 'other', no automatic include -----
        else:
            proposal.update({
                "classifier": "rule",
                "kind": "other",
                "include": False,
                "reason": f"ext .{ext} not handled by current rules",
            })
            stats[f"rule:other:{ext or 'no-ext'}"] += 1

        proposals.append(proposal)
        if i % 10 == 0:
            out_json.write_text(json.dumps(proposals, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  progress: {i}/{len(manifest)}", file=sys.stderr)

    _dedup_maps(proposals)
    out_json.write_text(json.dumps(proposals, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_proposal_markdown(proposals)
    print(f"\nproposal stats:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    print(f"wrote {out_json}")
    return 0


def _dedup_maps(proposals: list[dict]) -> None:
    """For map proposals with a resolved target page, keep only the newest per location.

    Map screenshots accumulate over sessions as the party explores further.
    Only the most recent snapshot is worth embedding — it shows the most
    complete state of the dungeon/area. Older ones are marked superseded.
    """
    from collections import defaultdict
    groups: dict[str, list[int]] = defaultdict(list)
    for i, pr in enumerate(proposals):
        if pr.get("kind") == "map" and pr.get("include") and pr.get("target_page"):
            groups[pr["target_page"]].append(i)
    for target_page, indices in groups.items():
        if len(indices) <= 1:
            continue
        indices.sort(key=lambda i: int(proposals[i].get("message_id") or 0), reverse=True)
        newest = proposals[indices[0]]
        for i in indices[1:]:
            proposals[i]["include"] = False
            proposals[i]["superseded_by"] = newest.get("message_id")
            proposals[i]["reason"] = (
                f"older map of same location; superseded by msg {newest.get('message_id')} "
                f"({newest.get('timestamp', '')[:10]})"
            )


def _section_for_kind(kind: str) -> str:
    return {
        "portrait": "Portraits",
        "map": "Maps",
        "character-sheet-screenshot": "Character Sheets",
        "item-photo": "Reference Images",
        "monster-stat-block": "Reference",
        "group-art": "Group Art",
    }.get(kind, "Reference Images")


def _write_proposal_markdown(proposals: list[dict]) -> None:
    p = PROPOSALS_DIR / "media_ingestion_proposals.md"
    inc = [pr for pr in proposals if pr.get("include")]
    skip = [pr for pr in proposals if not pr.get("include")]
    lines = [
        "# Media Ingestion Proposals",
        "",
        f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"Total: {len(proposals)}  (include={len(inc)}, skip={len(skip)})",
        "",
        "## Include — ingest into vault",
        "",
    ]
    by_target: dict[str, list[dict]] = defaultdict(list)
    for pr in inc:
        by_target[pr.get("target_page") or "(unresolved target)"].append(pr)
    for target, items in sorted(by_target.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        lines.append(f"### → `{target}`")
        lines.append("")
        for pr in items:
            lines.append(f"- **{pr['filename']}** ({pr.get('kind','?')}, .{pr['ext']}, {pr['size']} bytes)")
            lines.append(f"  - local: `{pr['local_path']}`")
            lines.append(f"  - source: `#{pr['channel']}` by {pr.get('author','?')} on {pr.get('timestamp','')[:10]}")
            if pr.get("classifier") == "vision":
                lines.append(f"  - vision: kind=`{pr.get('kind','?')}` entity=`{pr.get('entity','')}` ({pr.get('entity_kind','')})")
                lines.append(f"  - caption: {pr.get('caption','')}")
                lines.append(f"  - match: {pr.get('match_reason','')}")
            else:
                lines.append(f"  - rule: {pr.get('reason','')}")
            lines.append(f"  - target section: **{pr.get('target_section','')}**")
            lines.append(f"  - vault path: `{pr.get('vault_attachment_path','')}`")
        lines.append("")
    lines += ["## Skip", ""]
    skip_by_reason: dict[str, int] = defaultdict(int)
    for pr in skip:
        skip_by_reason[f"{pr.get('classifier','?')}: {pr.get('reason','') or pr.get('vision_reason','')}"] += 1
    for r, n in sorted(skip_by_reason.items(), key=lambda kv: -kv[1]):
        lines.append(f"- ({n}) {r[:140]}")
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {p}")


# ---------- apply lane ----------

def apply_media_ingestion(args: argparse.Namespace) -> int:
    out_json = PROPOSALS_DIR / "media_ingestion_proposals.json"
    if not out_json.exists():
        print(f"no proposals at {out_json}", file=sys.stderr)
        return 2
    proposals = json.loads(out_json.read_text())

    applied = []
    for pr in proposals:
        if not pr.get("include"):
            continue
        target = pr.get("target_page")
        vault_path = pr.get("vault_attachment_path")
        if not target or not vault_path:
            continue
        src = Path(pr["absolute_path"])
        dst = ROOT / vault_path
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if args.apply:
            shutil.copy2(src, dst)
        # Inject reference into the target page
        target_path = ROOT / target
        if target_path.exists():
            inject_reference(target_path, vault_path, pr, apply=args.apply)
        applied.append({"file": pr["filename"], "→": target, "section": pr.get("target_section"),
                         "vault_path": vault_path, "target_page": target if target else None,
                         "applied": args.apply})

    if args.apply:
        msg = f"applied {len(applied)} ingestions"
    else:
        msg = f"would apply {len(applied)} ingestions (dry-run; pass --apply)"
    print(msg)
    (PROPOSALS_DIR / "media_ingestion_apply_summary.json").write_text(
        json.dumps(applied, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.apply and applied:
        to_stage = [e["vault_path"] for e in applied if e.get("vault_path")]
        to_stage += [e["target_page"] for e in applied if e.get("target_page")]
        if to_stage:
            r = subprocess.run(["git", "-C", str(ROOT), "add"] + to_stage,
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"git add failed: {r.stderr.strip()}", file=sys.stderr)
            else:
                commit_msg = f"media: batch ingest {len(applied)} attachment(s) into vault"
                r2 = subprocess.run(["git", "-C", str(ROOT), "commit", "-m", commit_msg],
                                    capture_output=True, text=True)
                if r2.returncode != 0 and "nothing to commit" not in r2.stdout:
                    print(f"git commit failed: {r2.stderr.strip()}", file=sys.stderr)
                else:
                    print(r2.stdout.strip() or "git commit ok")

    return 0


def inject_reference(target_path: Path, vault_path: str, pr: dict, apply: bool) -> None:
    """Add an ![[…]] (or [[…]] for binaries) reference under the target section."""
    text = target_path.read_text(encoding="utf-8")
    rel = vault_path[len("vault/"):] if vault_path.startswith("vault/") else vault_path
    ext = pr.get("ext", "").lower()
    if ext in IMAGE_EXTS:
        line = f"- ![[{rel}]] — {pr.get('caption') or pr.get('filename','')}"
    else:
        line = f"- [[{rel}|{pr.get('filename', rel.split('/')[-1])}]]"
    section = pr.get("target_section") or "Reference Images"
    # Find the section header; if not present, append one.
    header_re = re.compile(rf"(?m)^## {re.escape(section)}\s*$")
    if header_re.search(text):
        new = header_re.sub(rf"## {section}\n{line}", text, count=1)
    else:
        if not text.endswith("\n"):
            text += "\n"
        new = text + f"\n## {section}\n\n{line}\n"
    if apply:
        target_path.write_text(new, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_pr = sub.add_parser("propose-media-ingestion")
    p_pr.add_argument("--limit", type=int, default=0)
    p_pr.add_argument("--regenerate", action="store_true", help="Ignore existing proposals and re-classify from scratch")
    p_pr.set_defaults(func=propose_media_ingestion)
    p_ap = sub.add_parser("apply-media-ingestion")
    p_ap.add_argument("--apply", action="store_true")
    p_ap.set_defaults(func=apply_media_ingestion)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
