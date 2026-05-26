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


def find_rollup_context(channel_id: str, message_id: str, window_msgs: int = 2) -> str:
    """Return surrounding Discord rollup text for context: up to N messages before
    and N messages after the given message. Walks all weekly rollups."""
    context_lines: list[str] = []
    # message IDs are snowflakes; we can compare numerically.
    target = int(message_id) if message_id.isdigit() else 0
    found = []
    for rollup_md in sorted(ROLLUPS_ROOT.glob("*/channels/*.md")):
        text = rollup_md.read_text(encoding="utf-8", errors="ignore")
        # Each block: "## <date> ... - <author> - <msg_id>\n\n<body>"
        for m in re.finditer(
            r"^## (?P<dt>\d{4}-\d{2}-\d{2}[^\n-]*) - (?P<author>[^\n-]+) - (?P<mid>\d+)\s*\n+(?P<body>.+?)(?=^## \d{4}-\d{2}-\d{2}|\Z)",
            text, flags=re.M | re.S,
        ):
            mid = int(m.group("mid"))
            found.append((mid, m.group("dt").strip(), m.group("author").strip(),
                          m.group("body").strip(), rollup_md.parent.parent.name))
    if not found:
        return ""
    found.sort(key=lambda x: x[0])
    # find target index
    idx = next((i for i, f in enumerate(found) if f[0] == target), None)
    if idx is None:
        return ""
    lo = max(0, idx - window_msgs)
    hi = min(len(found), idx + window_msgs + 1)
    for i in range(lo, hi):
        mid, dt, author, body, week = found[i]
        marker = " ◀ THIS MESSAGE" if i == idx else ""
        context_lines.append(f"[{dt}] {author}: {body[:500]}{marker}")
    return "\n".join(context_lines)


# ---------- vision classifier ----------

VISION_SYSTEM = """You are classifying images posted to a private Discord server for an Arden Vul DFRPG campaign. For each image, decide:
  1. What kind of image it is (portrait, map, character-sheet-screenshot, item-photo, monster-stat-block, group-art, meme, chat-screenshot, off-topic).
  2. Whether it belongs in the campaign vault knowledge-base (skip memes, chat screenshots, off-topic).
  3. If yes, which vault entity it is about (NPC name, PC name, location name, item name, monster name, or just "general lore").

Output JSON exactly:
{"kind":"...","include":true|false,"entity":"<title or empty>","entity_kind":"npc|pc|location|item|monster|lore|skip","caption":"<one short sentence>","reason":"<why include/skip>"}
"""


def vision_classify(image_path: Path, context: str, channel: str, filename: str) -> dict:
    sources = va.load_local_sources()
    base_url = sources.get("llm_base_url") or "http://100.76.165.94:1234/v1"
    model = sources.get("llm_model") or "google/gemma-4-26b-a4b"
    if image_path.suffix.lower() in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif image_path.suffix.lower() == ".webp":
        mime = "image/webp"
    elif image_path.suffix.lower() == ".gif":
        mime = "image/gif"
    else:
        mime = "image/png"
    data_url = f"data:{mime};base64,{base64.b64encode(image_path.read_bytes()).decode()}"
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

    out_json.write_text(json.dumps(proposals, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_proposal_markdown(proposals)
    print(f"\nproposal stats:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    print(f"wrote {out_json}")
    return 0


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
        applied.append({"file": pr["filename"], "→": target, "section": pr.get("target_section"), "applied": args.apply})

    if args.apply:
        msg = f"applied {len(applied)} ingestions"
    else:
        msg = f"would apply {len(applied)} ingestions (dry-run; pass --apply)"
    print(msg)
    (PROPOSALS_DIR / "media_ingestion_apply_summary.json").write_text(
        json.dumps(applied, indent=2, ensure_ascii=False), encoding="utf-8")
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
