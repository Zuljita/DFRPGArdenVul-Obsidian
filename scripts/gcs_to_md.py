#!/usr/bin/env python3
"""Convert the latest GURPS Character Sheet (.gcs) per character into a
markdown summary attached to the canonical PC vault page.

Walks vault/attachments/discord/character-sheets/*.gcs, groups by character
(filename heuristic + GCS `profile.name`), picks the latest by `modified_date`,
parses the JSON, renders a `## Character Sheet Snapshot` section, and either
prints it (dry-run, default) or writes/replaces it on the matched PC page.

Idempotent: if the section already exists for the same modified_date, no write.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import vault_automation as va  # noqa: E402

VAULT = va.VAULT
ROOT = va.ROOT
SHEET_DIR = VAULT / "attachments" / "discord" / "character-sheets"

ATTR_NAMES = {
    "st": "ST", "dx": "DX", "iq": "IQ", "ht": "HT",
    "will": "Will", "per": "Per", "hp": "HP", "fp": "FP",
    "basic_speed": "Basic Speed", "basic_move": "Basic Move",
    "dodge": "Dodge", "lift": "Lift",
}


def normalize_character_key(filename: str, profile_name: str) -> str:
    """Pick a stable key for grouping multiple .gcs files into one character."""
    # Prefer profile name if available; fall back to filename stem.
    if profile_name:
        # Strip variant tags like "Vael Sunshadow - Social" → "Vael Sunshadow"
        name = re.sub(r"\s*[-–]\s*Social\s*$", "", profile_name, flags=re.I)
        return name.strip().lower()
    stem = re.sub(r"^\d+-", "", filename)        # drop discord message-id prefix
    stem = re.sub(r"\.[^.]+$", "", stem)         # drop extension
    stem = re.sub(r"_\-_Social", "", stem)
    stem = re.sub(r"\d{6,}", "", stem)           # drop date-ish blocks
    stem = re.sub(r"[_-]+", " ", stem).strip()
    return stem.lower()


def _follow_redirect(p: Path) -> Path | None:
    try:
        txt = p.read_text(encoding="utf-8")
    except Exception:
        return None
    m = re.search(r"^redirect_to:\s*(.+)$", txt, flags=re.M)
    if not m:
        return p  # not a redirect
    rt = m.group(1).strip().strip('"').strip("'")
    rt_path = ROOT / rt
    return rt_path if rt_path.exists() else None


def find_pc_page(character_name: str, filename_hint: str = "") -> Path | None:
    """Resolve a character display name (and optionally a filename) to a
    canonical vault page. Searches pcs/, pcs/grudge-brigade/, npcs/. Skips
    redirect stubs (or follows them). Considers aliases for the bare name."""
    # Build the set of search candidates.
    candidates: list[Path] = []
    for d in (VAULT / "pcs", VAULT / "pcs" / "grudge-brigade", VAULT / "npcs"):
        if d.is_dir():
            candidates.extend(d.glob("*.md"))

    # Token sources to match by — combine profile name + filename stem.
    sources = [character_name]
    if filename_hint:
        stem = re.sub(r"^\d+-", "", filename_hint)
        stem = re.sub(r"\.[^.]+$", "", stem)
        stem = re.sub(r"\d{6,}", "", stem)
        stem = re.sub(r"[_-]+", " ", stem)
        sources.append(stem)
    name_tokens = set()
    for s in sources:
        name_tokens |= set(t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 2)
    if not name_tokens:
        return None

    # Pass 1: whole-word match — page stem appears as a complete token in the
    # source (or vice-versa). Avoids "Basil" matching "Basilisk_..." files.
    def _token_set(s: str) -> set[str]:
        return set(t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 2)
    for p in candidates:
        if p.stem.lower() in {"index", "readme"}:
            continue
        stem_tokens = _token_set(p.stem)
        if not stem_tokens:
            continue
        for src in sources:
            src_tokens = _token_set(src)
            # Require stem fully contained in source tokens (or vice-versa) AND
            # the longer side share at least 2 tokens (avoid trivial overlap).
            if (stem_tokens <= src_tokens or src_tokens <= stem_tokens) and \
               min(len(stem_tokens), len(src_tokens)) >= 1 and \
               len(stem_tokens & src_tokens) >= max(1, min(len(stem_tokens), len(src_tokens))):
                resolved = _follow_redirect(p)
                if resolved:
                    return resolved
                break

    # Pass 2: alias match — scan frontmatter aliases.
    for p in candidates:
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        m = re.search(r"^aliases:\s*\n((?:\s*-\s*[^\n]+\n)+)", txt, flags=re.M)
        if not m:
            continue
        aliases = [line.strip().lstrip("- ").strip().strip('"').strip("'")
                   for line in m.group(1).strip().split("\n")]
        for a in aliases:
            al = a.lower()
            if not al:
                continue
            for src in sources:
                sl = src.lower()
                if al == sl or al in sl or sl in al:
                    resolved = _follow_redirect(p)
                    if resolved:
                        return resolved

    # Pass 3: token-overlap fallback (≥2 distinctive shared tokens).
    best, best_overlap = None, 0
    for p in candidates:
        toks = set(t for t in re.findall(r"[a-z0-9]+", p.stem.lower()) if len(t) > 2)
        overlap = len(name_tokens & toks)
        if overlap > best_overlap and overlap >= 2:
            resolved = _follow_redirect(p)
            if resolved:
                best, best_overlap = resolved, overlap
    return best


def attr_value(sheet: dict, attr_id: str):
    for a in sheet.get("attributes", []) or []:
        if a.get("attr_id") == attr_id:
            return (a.get("calc") or {}).get("value")
    return None


def flatten_traits(traits: list, kind: str = "all") -> list[dict]:
    """Flatten container-traits into a flat list with their effective points."""
    out = []
    def walk(node, container=""):
        if isinstance(node, list):
            for n in node:
                walk(n, container)
            return
        name = (node.get("name") or "").strip()
        children = node.get("children")
        pts = node.get("calc", {}).get("points") if isinstance(node.get("calc"), dict) else None
        if pts is None:
            pts = node.get("points")
        levels = node.get("levels")
        disabled = node.get("disabled") is True
        is_container = bool(children)
        if name and not is_container and not disabled:
            out.append({"name": name, "points": pts, "levels": levels, "container": container})
        if is_container:
            walk(children, container=name or container)
    walk(traits)
    return out


def flatten_skills(skills: list) -> list[dict]:
    out = []
    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
            return
        name = (node.get("name") or "").strip()
        spec = node.get("specialization")
        tl = node.get("tech_level")
        diff = node.get("difficulty") or ""
        level = (node.get("calc") or {}).get("level") if isinstance(node.get("calc"), dict) else None
        if name and not node.get("children"):
            display = name
            if tl:
                display += f"/TL{tl}"
            if spec:
                display += f" ({spec})"
            out.append({"name": display, "difficulty": diff, "level": level})
        if node.get("children"):
            walk(node["children"])
    walk(skills)
    return out


def flatten_spells(spells: list) -> list[dict]:
    out = []
    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
            return
        name = (node.get("name") or "").strip()
        college = node.get("college") or []
        if isinstance(college, list):
            college = ", ".join(college)
        level = (node.get("calc") or {}).get("level") if isinstance(node.get("calc"), dict) else None
        if name and not node.get("children"):
            out.append({"name": name, "college": college, "level": level})
        if node.get("children"):
            walk(node["children"])
    walk(spells)
    return out


def flatten_equipment(equipment: list) -> list[dict]:
    out = []
    def walk(node, container=""):
        if isinstance(node, list):
            for n in node:
                walk(n, container)
            return
        desc = (node.get("description") or "").strip()
        qty = node.get("quantity")
        weight = node.get("weight")
        value = node.get("value")
        equipped = node.get("equipped") is True
        if desc and not node.get("children"):
            out.append({"description": desc, "quantity": qty, "weight": weight, "value": value,
                        "equipped": equipped, "container": container})
        if node.get("children"):
            walk(node["children"], container=desc or container)
    walk(equipment)
    return out


def render_markdown(sheet: dict, gcs_filename: str) -> str:
    profile = sheet.get("profile", {}) or {}
    modified = (sheet.get("modified_date") or "")[:10] or "?"
    points = sheet.get("total_points", "?")
    name = profile.get("name", "?")

    attrs_rows = []
    for aid, label in ATTR_NAMES.items():
        v = attr_value(sheet, aid)
        if v is not None:
            attrs_rows.append((label, v))
    calc = sheet.get("calc", {}) or {}
    extras = []
    if calc.get("basic_lift"): extras.append(("Basic Lift", calc["basic_lift"]))
    if calc.get("swing"):      extras.append(("Swing", calc["swing"]))
    if calc.get("thrust"):     extras.append(("Thrust", calc["thrust"]))
    if isinstance(calc.get("move"), list) and calc["move"]:
        extras.append(("Move (encumbrance levels)", " / ".join(str(x) for x in calc["move"])))
    if isinstance(calc.get("dodge"), list) and calc["dodge"]:
        extras.append(("Dodge (encumbrance levels)", " / ".join(str(x) for x in calc["dodge"])))

    traits = flatten_traits(sheet.get("traits", []))
    advs = [t for t in traits if (t.get("points") or 0) > 0]
    disadvs = [t for t in traits if (t.get("points") or 0) < 0]
    quirks = [t for t in traits if (t.get("points") == -1 and "quirk" in (t.get("container") or "").lower())]

    skills = flatten_skills(sheet.get("skills", []))
    spells = flatten_spells(sheet.get("spells", []))
    equipment = flatten_equipment(sheet.get("equipment", []))

    lines = [
        f"## Character Sheet Snapshot",
        "",
        f"_Generated from `{gcs_filename}` (sheet `modified_date`: **{modified}**, total points: **{points}**)._",
        "",
        f"- **Name:** {name}",
    ]
    if profile.get("age"):
        lines.append(f"- **Age:** {profile['age']}")
    if profile.get("height"):
        lines.append(f"- **Height:** {profile['height']}")
    if profile.get("weight"):
        lines.append(f"- **Weight:** {profile['weight']}")
    if profile.get("tech_level"):
        lines.append(f"- **Tech Level:** {profile['tech_level']}")
    # Deliberately skip profile.player_name (real-name leak).

    lines += ["", "### Attributes", ""]
    if attrs_rows:
        lines.append("| Attribute | Value |")
        lines.append("| --- | --- |")
        for label, v in attrs_rows:
            lines.append(f"| {label} | {v} |")
        for label, v in extras:
            lines.append(f"| {label} | {v} |")
    else:
        lines.append("(no attributes parsed)")

    def render_list_block(title, items, fmt):
        lines.extend(["", f"### {title}", ""])
        if not items:
            lines.append(f"(none)")
            return
        for it in items:
            lines.append(fmt(it))

    if advs:
        render_list_block(
            f"Advantages / Traits ({len(advs)})", advs,
            lambda t: f"- **{t['name']}** [{t.get('points', '?')} pts]"
        )
    if disadvs:
        render_list_block(
            f"Disadvantages ({len(disadvs)})", disadvs,
            lambda t: f"- **{t['name']}** [{t.get('points', '?')} pts]"
        )
    if skills:
        render_list_block(
            f"Skills ({len(skills)})", skills,
            lambda s: f"- **{s['name']}** ({s['difficulty']}) — level **{s.get('level', '?')}**"
        )
    if spells:
        render_list_block(
            f"Spells ({len(spells)})", spells,
            lambda s: f"- **{s['name']}** — *{s.get('college') or '?'}* — level **{s.get('level', '?')}**"
        )
    if equipment:
        # Show only equipped items by default
        equipped = [e for e in equipment if e.get("equipped")]
        render_list_block(
            f"Equipment ({len(equipped)} equipped of {len(equipment)} total)", equipped,
            lambda e: (
                f"- **{e['description']}**"
                + (f" ×{e['quantity']}" if (e.get('quantity') or 1) != 1 else "")
                + (f" [{e['weight']}]" if e.get("weight") else "")
                + (f" — ${e['value']}" if e.get("value") not in (None, 0) else "")
                + (f" — in {e['container']}" if e.get("container") else "")
            ),
        )

    lines.append("")
    return "\n".join(lines)


def upsert_section(target: Path, new_section: str, apply: bool) -> tuple[bool, str]:
    """Replace existing `## Character Sheet Snapshot` section in `target`, or
    append at end. Returns (changed?, reason)."""
    text = target.read_text(encoding="utf-8")
    pat = re.compile(r"\n*## Character Sheet Snapshot.*?(?=\n## |\Z)", flags=re.S)
    if pat.search(text):
        new_text = pat.sub("\n\n" + new_section, text, count=1).rstrip() + "\n"
        action = "replace"
    else:
        if not text.endswith("\n"):
            text += "\n"
        new_text = text + "\n" + new_section
        action = "append"
    if new_text == text:
        return False, "unchanged"
    if apply:
        target.write_text(new_text, encoding="utf-8")
    return True, action


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="Write to PC pages (default dry-run)")
    p.add_argument("--character", help="Only process matching profile.name substring")
    args = p.parse_args()

    if not SHEET_DIR.is_dir():
        print(f"no sheets directory: {SHEET_DIR}", file=sys.stderr)
        return 2

    # Load every .gcs, group by character key, pick latest by modified_date.
    groups: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for f in sorted(SHEET_DIR.glob("*.gcs")):
        try:
            d = json.load(f.open())
        except Exception as e:
            print(f"  skip (json error): {f.name} — {e}", file=sys.stderr)
            continue
        key = normalize_character_key(f.name, (d.get("profile") or {}).get("name", ""))
        groups[key].append((f, d))

    print(f"distinct characters: {len(groups)}", file=sys.stderr)
    summary = []
    for key, items in groups.items():
        items.sort(key=lambda kv: kv[1].get("modified_date") or "", reverse=True)
        latest_path, latest_sheet = items[0]
        profile_name = (latest_sheet.get("profile") or {}).get("name") or key
        if args.character and args.character.lower() not in profile_name.lower():
            continue
        pc_page = find_pc_page(profile_name, filename_hint=latest_path.name)
        rendered = render_markdown(latest_sheet, latest_path.name)
        if pc_page:
            changed, action = upsert_section(pc_page, rendered, apply=args.apply)
            print(f"  {profile_name!r:<40} ← {latest_path.name}  → {pc_page.relative_to(ROOT)}  [{action}]", file=sys.stderr)
            summary.append({
                "character": profile_name,
                "page": str(pc_page.relative_to(ROOT)),
                "gcs": latest_path.name,
                "modified": latest_sheet.get("modified_date", "")[:10],
                "total_points": latest_sheet.get("total_points"),
                "skill_count": len(flatten_skills(latest_sheet.get("skills", []))),
                "spell_count": len(flatten_spells(latest_sheet.get("spells", []))),
                "action": action,
                "applied": args.apply,
            })
        else:
            print(f"  {profile_name!r:<40} ← {latest_path.name}  → NO PC PAGE MATCH", file=sys.stderr)
            summary.append({
                "character": profile_name,
                "page": None,
                "gcs": latest_path.name,
                "modified": latest_sheet.get("modified_date", "")[:10],
                "total_points": latest_sheet.get("total_points"),
                "unmatched": True,
            })

    proposals_dir = va.AUTOMATION_DIR / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    out = proposals_dir / "gcs_to_md_summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
