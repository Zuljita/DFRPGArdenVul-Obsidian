#!/usr/bin/env python3
"""Enrich vault pages with cross-cutting taxonomy tags (conservative).

Walks every vault md, applies tags based on deterministic signals:
  - Title / filename stem keywords
  - Existing tag implications
  - Wikilink presence (a page that links to [[npcs/Thoth.md]] is Thothian)
  - First-paragraph keyword frequency

Never adds a tag based on an LLM judgement or fuzzy semantics. False negatives
are preferred over false positives. Outputs a dry-run report by default; pass
`--apply` to write tags.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import vault_automation as va  # noqa: E402

VAULT = va.VAULT


@dataclass
class TagRule:
    tag: str
    # If any of these regex patterns hit the title/filename, apply the tag.
    title_patterns: tuple[str, ...] = ()
    # If page has any of these wikilink targets, apply the tag.
    wikilink_targets: tuple[str, ...] = ()
    # If any of these regex patterns hit the first 1000 chars of body, apply.
    body_patterns: tuple[str, ...] = ()
    # If the page already has any of these tags, apply.
    implied_by_tags: tuple[str, ...] = ()
    # Folders to restrict the rule to (empty = all folders).
    folders: tuple[str, ...] = ()
    # Require AT LEAST this many distinct signals to fire (default 1).
    min_signals: int = 1


# Taxonomy — conservative. Add more later as patterns become clear.
RULES: list[TagRule] = [
    # ----- creature type -----
    TagRule(
        tag="type/ghost",
        title_patterns=(r"\bghost\b", r"\bspectre\b", r"\bhaunted\b", r"\bwraith\b"),
        body_patterns=(r"\bis a ghost\b", r"\bis a spirit\b", r"\bis a wraith\b",
                       r"\b(?:undead|spectral|incorporeal) (?:ghost|spirit)\b"),
        # Removed implied_by_tags=classification/undead — caught zombies / wights as ghosts.
        folders=("npcs", "monsters"),
    ),
    TagRule(
        tag="type/dragon",
        title_patterns=(r"\bdragon\b", r"\bwyrm\b", r"\bdrake\b"),
        body_patterns=(r"\bis a (?:green|red|blue|black|white|gold|silver|copper|bronze|brass)? ?dragon\b",
                       r"\bis a wyrm\b"),
        folders=("npcs", "monsters"),
    ),
    TagRule(
        tag="type/wyvern",
        title_patterns=(r"\bwyvern\b",),
        body_patterns=(r"\bis a wyvern\b",),
        folders=("npcs", "monsters"),
    ),
    TagRule(
        tag="type/undead",
        implied_by_tags=("classification/undead",),
        folders=("npcs", "monsters"),
    ),
    TagRule(
        tag="type/baboon",
        title_patterns=(r"\bbaboon\b",),
        body_patterns=(r"\bgiant (?:four-armed )?baboon\b", r"\bbaboon (?:leader|tribe|clan)\b"),
        folders=("npcs", "monsters"),
    ),
    TagRule(
        tag="type/goblin",
        title_patterns=(r"\bgoblin\b",),
        body_patterns=(r"\bis a goblin\b", r"\bgoblin (?:boss|chief|king|warrior|merchant)\b"),
        folders=("npcs",),
    ),
    TagRule(
        tag="type/halfling",
        title_patterns=(r"\bhalfling\b",),
        body_patterns=(r"\bis a halfling\b", r"\bhalfling (?:thug|merchant|farmer)\b"),
        folders=("npcs",),
    ),
    TagRule(
        tag="type/troll",
        title_patterns=(r"\btroll\b", r"\bvarumani\b"),
        body_patterns=(r"\bvarumani\b", r"\bis a troll\b"),
        folders=("npcs", "monsters", "factions"),
    ),
    TagRule(
        tag="type/heqeti",
        title_patterns=(r"\bheqeti\b", r"\bhopper\b"),
        body_patterns=(r"\bheqeti\b", r"\bamphibian.{0,50}heqeti\b"),
        folders=("npcs", "monsters", "factions"),
    ),
    TagRule(
        tag="type/golem",
        title_patterns=(r"\bgolem\b", r"\bconstruct\b"),
        body_patterns=(r"\bis a golem\b", r"\bstone golem\b", r"\biron golem\b"),
        folders=("npcs", "monsters", "items"),
    ),
    # ----- religious / cultural tradition -----
    TagRule(
        tag="tradition/thothian",
        title_patterns=(r"\bthothian\b", r"\bthoth\b", r"\bprior\b"),
        wikilink_targets=("npcs/Thoth.md", "lore/Thothian.md", "lore/The Book of Priors.md",
                          "Thoth", "Thothian", "Book of Priors"),
        body_patterns=(r"\bThothian\b", r"\b(?:prior|priesthood) of Thoth\b", r"\bcult of Thoth\b"),
    ),
    TagRule(
        tag="tradition/settite",
        title_patterns=(r"\bsettite\b", r"\bcult of set\b"),
        wikilink_targets=("npcs/Set.md", "factions/Cult of Set.md", "Cult of Set", "Settite"),
        body_patterns=(r"\bSettite\b", r"\bCult of Set\b", r"\bpriest(?:hood)? of Set\b"),
        min_signals=2,  # 'Set' is ambiguous; require two signals
    ),
    TagRule(
        tag="tradition/demma",
        title_patterns=(r"\bdemma\b",),
        wikilink_targets=("npcs/Demma.md", "lore/Priesthood of Demma.md", "Demma", "Priesthood of Demma"),
        body_patterns=(r"\bgoddess Demma\b", r"\bpriest(?:hood)? of Demma\b", r"\bcleric of Demma\b"),
    ),
    TagRule(
        tag="tradition/mitran",
        title_patterns=(r"\bmitran\b",),
        wikilink_targets=("npcs/Mitra.md", "Mitra"),
        body_patterns=(r"\bMitran\b", r"\btemple of Mitra\b", r"\bcleric of Mitra\b"),
    ),
    TagRule(
        tag="tradition/rudishva",
        title_patterns=(r"\brudishva\b",),
        wikilink_targets=("concepts/Rudishva.md", "factions/Rudishva.md", "Rudishva"),
        body_patterns=(r"\bRudishva\b",),
        min_signals=2,
    ),
    # ----- culture (racial / political) -----
    TagRule(
        tag="culture/thorcin",
        title_patterns=(r"\bthorcin\b",),
        wikilink_targets=("lore/Thorcin.md", "Thorcin"),
        body_patterns=(r"\bThorcin\b",),
    ),
    TagRule(
        tag="culture/archontean",
        title_patterns=(r"\barchontean\b", r"\barchon\b"),
        wikilink_targets=("factions/Archontean Empire.md", "Archontean Empire"),
        body_patterns=(r"\bArchontean\b", r"\barchon (?:of|named)\b"),
        min_signals=2,
    ),
    TagRule(
        tag="culture/wiskin",
        title_patterns=(r"\bwiskin\b",),
        body_patterns=(r"\bWiskin\b",),
    ),
    # ----- era -----
    TagRule(
        tag="era/historical",
        body_patterns=(r"\b\d{3,4} AEP\b", r"\b\d{3,4} SP\b",
                       r"\b(?:approximately|about|over) \d{2,4} years ago\b",
                       r"\bhistorical (?:figure|account)\b"),
        min_signals=1,
    ),
    # ----- status -----
    TagRule(
        tag="status/deceased",
        body_patterns=(r"\b(?:he|she|they) (?:died|was killed|was slain)\b",
                       r"\bdied (?:approximately )?\d+ years ago\b",
                       r"\bnow deceased\b", r"\bkilled by\b"),
        min_signals=1,
        folders=("npcs",),
    ),
]


def parse_frontmatter_tags(text: str) -> tuple[list[str], str, str]:
    """Return (tags_list, frontmatter_text, body)."""
    m = re.match(r"^(---\n)(.*?)(\n---\n)", text, flags=re.S)
    if not m:
        return [], "", text
    fm = m.group(2)
    body = text[len(m.group(0)):]
    tags: list[str] = []
    tm = re.search(r"^tags:\s*\n((?:\s*-\s*[^\n]+\n)+)", fm, flags=re.M)
    if tm:
        for line in tm.group(1).strip().split("\n"):
            t = line.strip().lstrip("- ").strip().strip('"').strip("'")
            if t:
                tags.append(t)
    else:
        # inline form: tags: [a, b]
        tm2 = re.search(r"^tags:\s*\[([^\]]*)\]\s*$", fm, flags=re.M)
        if tm2:
            for t in tm2.group(1).split(","):
                t = t.strip().strip('"').strip("'")
                if t:
                    tags.append(t)
    return tags, m.group(0), body


def extract_wikilink_targets(text: str) -> set[str]:
    return {m.group(1).split("#", 1)[0].strip() for m in re.finditer(r"\[\[([^|\]]+)(?:\|[^\]]+)?\]\]", text)}


def evaluate_rule(rule: TagRule, *, title: str, stem: str, existing_tags: list[str],
                  wikilink_targets: set[str], body_first1000: str, folder: str) -> tuple[bool, list[str]]:
    if rule.folders and folder not in rule.folders:
        return False, []
    if rule.tag in existing_tags:
        return False, ["already tagged"]
    signals: list[str] = []
    name_search = f"{title} {stem}".lower()
    for pat in rule.title_patterns:
        if re.search(pat, name_search, flags=re.I):
            signals.append(f"title /{pat}/")
            break
    for tgt in rule.wikilink_targets:
        if tgt in wikilink_targets:
            signals.append(f"wikilink [[{tgt}]]")
            break
    for pat in rule.body_patterns:
        if re.search(pat, body_first1000, flags=re.I):
            signals.append(f"body /{pat}/")
            break
    for tag in rule.implied_by_tags:
        if tag in existing_tags:
            signals.append(f"implied-by tag '{tag}'")
            break
    if len(signals) >= rule.min_signals:
        return True, signals
    return False, signals


def add_tag(text: str, tag: str) -> str:
    """Add a tag to frontmatter, preserving structure."""
    m = re.match(r"^(---\n)(.*?)(\n---\n)", text, flags=re.S)
    if not m:
        # No frontmatter — prepend one
        return f"---\ntags:\n  - {tag}\n---\n{text}"
    fm = m.group(2)
    tail = text[len(m.group(0)):]
    if re.search(r"^tags:\s*\n", fm, flags=re.M):
        # Multi-line tags list — append a new "  - <tag>" line
        fm_new = re.sub(r"(^tags:\s*\n(?:\s*-\s*[^\n]+\n)*)", r"\1  - " + tag + "\n", fm, count=1, flags=re.M)
    elif re.search(r"^tags:\s*\[", fm, flags=re.M):
        fm_new = re.sub(r"^(tags:\s*\[)([^\]]*)(\])", lambda mm: mm.group(1) + (mm.group(2) + ", " if mm.group(2).strip() else "") + tag + mm.group(3), fm, flags=re.M)
    else:
        fm_new = fm + f"\ntags:\n  - {tag}"
    return f"---\n{fm_new}\n---\n{tail}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Write tags (default: dry-run report)")
    ap.add_argument("--folders", nargs="*", default=None, help="Limit to vault subfolders (default: all)")
    args = ap.parse_args()

    stats: dict[str, int] = defaultdict(int)
    per_rule: dict[str, list[str]] = defaultdict(list)
    files_changed = 0

    for md in sorted(VAULT.rglob("*.md")):
        rel = str(md.relative_to(VAULT)).replace("\\", "/")
        folder = rel.split("/")[0] if "/" in rel else ""
        if args.folders and folder not in args.folders:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        existing_tags, _, body = parse_frontmatter_tags(text)
        # Skip redirects
        if "redirect" in existing_tags or "status: redirect" in text:
            continue
        title_match = re.search(r"^# (.+)$", body, flags=re.M)
        title = (title_match.group(1).strip() if title_match else md.stem).strip()
        wikilinks = extract_wikilink_targets(text)
        body_first = body[:1500]
        new_tags = list(existing_tags)
        added_here = []
        for rule in RULES:
            fired, signals = evaluate_rule(rule,
                title=title, stem=md.stem,
                existing_tags=new_tags,
                wikilink_targets=wikilinks,
                body_first1000=body_first,
                folder=folder)
            if fired:
                new_tags.append(rule.tag)
                added_here.append((rule.tag, signals))
                stats[rule.tag] += 1
                per_rule[rule.tag].append(f"{rel}  [{', '.join(signals)}]")
        if added_here:
            files_changed += 1
            if args.apply:
                new_text = text
                for tag, _ in added_here:
                    new_text = add_tag(new_text, tag)
                md.write_text(new_text, encoding="utf-8")

    print(f"=== Tag enrichment {'APPLIED' if args.apply else 'DRY-RUN'} ===")
    print(f"files {'changed' if args.apply else 'would-change'}: {files_changed}")
    print(f"tags added by category:")
    for tag, n in sorted(stats.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {tag}")
    out = va.AUTOMATION_DIR / "proposals" / "tag_enrichment_report.md"
    lines = [f"# Tag Enrichment Report ({'applied' if args.apply else 'dry-run'})", "",
             f"Files affected: {files_changed}", "",
             "## By Tag", ""]
    for tag, n in sorted(stats.items(), key=lambda kv: -kv[1]):
        lines.append(f"### `{tag}` ({n})")
        for ex in per_rule[tag]:
            lines.append(f"- {ex}")
        lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
