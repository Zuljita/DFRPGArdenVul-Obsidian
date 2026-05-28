#!/usr/bin/env python3
"""Import revised Discord weekly digests into the Obsidian vault."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path("/tmp/arden-vul-revised-digests")
TARGET_DIR = REPO / "vault" / "notes" / "weekly-digests"


def week_date_from_path(path: Path) -> str:
    match = re.search(r"week-ending-(\d{4}-\d{2}-\d{2})-2300-central", str(path))
    if not match:
        raise ValueError(f"cannot parse week date from {path}")
    return match.group(1)


def frontmatter(date: str) -> str:
    return "\n".join([
        "---",
        "tags:",
        "  - note",
        "  - discord-weekly-digest",
        f"week-ending: {date}",
        "source: discord-chat-explorer",
        "---",
        "",
    ])


def import_digest(source_file: Path) -> Path:
    date = week_date_from_path(source_file)
    target = TARGET_DIR / f"Week Ending {date}.md"
    body = source_file.read_text(encoding="utf-8").strip() + "\n"
    target.write_text(frontmatter(date) + body, encoding="utf-8")
    return target


def write_index(imported: list[Path]) -> None:
    lines = [
        "---",
        "tags:",
        "  - note",
        "  - index",
        "  - discord-weekly-digest",
        "---",
        "",
        "# Weekly Discord Digests",
        "",
        "QA-revised weekly campaign digests generated from Discord transcripts. Weeks end Friday at 11 PM Central.",
        "",
    ]
    for path in sorted(imported):
        label = path.stem
        lines.append(f"- [[{label}]]")
    (TARGET_DIR / "Index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    source_root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    source_files = sorted(source_root.glob("week-ending-*/revised-digest.md"))
    if not source_files:
        print(f"no revised digest files found under {source_root}", file=sys.stderr)
        return 1
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    imported = [import_digest(path) for path in source_files]
    write_index(imported)
    print(f"imported {len(imported)} revised weekly digests into {TARGET_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
