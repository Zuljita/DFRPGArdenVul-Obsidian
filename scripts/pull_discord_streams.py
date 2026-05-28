#!/usr/bin/env python3
"""
Pull Discord stream JSONL files from Brain and convert to readable text files
in RawFiles/Discord/, matching the format of existing manual exports.

Downloads all loot threads plus any other specified streams.

Usage:
  python3 scripts/pull_discord_streams.py                     # loot threads only
  python3 scripts/pull_discord_streams.py --pattern "loot-"  # streams matching pattern
  python3 scripts/pull_discord_streams.py --all               # every stream
  python3 scripts/pull_discord_streams.py --dry-run           # list files, don't download

Requirements:
  - SSH access to Brain (set BRAIN_HOST / BRAIN_USER or edit defaults below)
  - SSH_ASKPASS_SCRIPT set to a script that echoes the password, or use key auth
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BRAIN_HOST = os.getenv("BRAIN_HOST", "100.89.15.34")
BRAIN_USER = os.getenv("BRAIN_USER", "kyle")
BRAIN_STREAMS_DIR = "/home/kyle/discord-chat-explorer/guilds/1346534955357835336/streams"

RAWFILES_DIR = Path("RawFiles/Discord")

# Patterns for streams to pull by default (no --all flag)
DEFAULT_PATTERNS = [
    r"^loot-",   # all loot channel threads and the main loot channel
]

SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "ConnectTimeout=15",
    "-o", "BatchMode=no",
]

# If set, used as SSH_ASKPASS for non-interactive password auth
ASKPASS_SCRIPT = os.getenv("SSH_ASKPASS_SCRIPT", "/tmp/ssh_askpass.sh")


def _ssh_env() -> dict[str, str]:
    env = os.environ.copy()
    if Path(ASKPASS_SCRIPT).exists():
        env["SSH_ASKPASS"] = ASKPASS_SCRIPT
        env["SSH_ASKPASS_REQUIRE"] = "force"
        env["DISPLAY"] = env.get("DISPLAY", ":0")
    return env


def ssh_run(cmd: str) -> str:
    """Run a command on Brain, return stdout."""
    proc = subprocess.run(
        ["setsid", "ssh"] + SSH_OPTS + [f"{BRAIN_USER}@{BRAIN_HOST}", cmd],
        capture_output=True, text=True, env=_ssh_env(), timeout=30
    )
    if proc.returncode != 0:
        raise RuntimeError(f"SSH failed: {proc.stderr[:300]}")
    return proc.stdout


def scp_file(remote_path: str, local_path: Path) -> None:
    """Copy a single file from Brain via SCP."""
    proc = subprocess.run(
        ["setsid", "scp"] + SSH_OPTS +
        [f"{BRAIN_USER}@{BRAIN_HOST}:{remote_path}", str(local_path)],
        capture_output=True, text=True, env=_ssh_env(), timeout=60
    )
    if proc.returncode != 0:
        raise RuntimeError(f"SCP failed for {remote_path}: {proc.stderr[:300]}")


def list_remote_streams() -> list[str]:
    """Return list of JSONL filenames in the Brain streams directory."""
    output = ssh_run(f"ls {BRAIN_STREAMS_DIR}/")
    return [f.strip() for f in output.splitlines() if f.strip().endswith(".jsonl")]


def format_timestamp(ts: str) -> str:
    """Convert ISO timestamp to Discord-style 'M/D/YY, H:MM AM/PM'."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%-m/%-d/%y, %-I:%M %p")
    except Exception:
        return ts[:16]


def author_display(author: dict) -> str:
    return (author.get("global_name") or
            author.get("display_name") or
            author.get("username") or "?")


def jsonl_to_text(jsonl_path: Path) -> str:
    """Convert a JSONL stream file to the RawFiles text format."""
    lines = [l for l in jsonl_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return ""

    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # Sort by message snowflake ID (chronological)
    records.sort(key=lambda r: int(r.get("message", {}).get("id", "0") or "0"))

    if not records:
        return ""

    stream_name = records[0].get("stream_name", "")
    parts = [stream_name, ""]

    for r in records:
        msg = r.get("message", {})
        content = msg.get("content", "").strip()
        if not content:
            # Skip system messages and empty content
            continue
        author = author_display(msg.get("author", {}))
        ts = format_timestamp(msg.get("timestamp", ""))
        parts.append(f"{author} — {ts}")
        parts.append(content)
        parts.append("")

    return "\n".join(parts)


def output_filename(jsonl_name: str) -> str:
    """Turn a JSONL filename into a local text filename."""
    # loot-destruction-2025-12-29-<id>.jsonl → DiscordLoot_destruction-2025-12-29.txt
    # loot-loot-2025-05-16-<id>.jsonl       → DiscordLoot_2025-05-16.txt
    # general-1346...jsonl                   → DiscordGeneral.txt
    stem = jsonl_name.replace(".jsonl", "")
    # Strip trailing Discord channel ID (last segment is a long number)
    stem = re.sub(r"-\d{15,}$", "", stem)

    if stem.startswith("loot-loot-"):
        date = stem[len("loot-loot-"):]
        return f"DiscordLootThread_{date}.txt"
    if stem.startswith("loot-"):
        label = stem[len("loot-"):]
        return f"DiscordLoot_{label}.txt"
    if stem.startswith("general-"):
        label = stem[len("general-"):]
        return f"DiscordGeneral_{label}.txt" if label else "DiscordGeneral.txt"
    # Fallback: use full stem (kebab-case → Title_Snake) for a unique name
    parts_raw = stem.split("-")
    label = "_".join(p.capitalize() for p in parts_raw)
    # Trim to avoid absurdly long filenames while keeping them unique
    if len(label) > 80:
        label = label[:80].rsplit("_", 1)[0]
    return f"Discord_{label}.txt"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Pull Discord stream JSONL files from Brain and convert to text."
    )
    ap.add_argument("--all", action="store_true",
                    help="Pull every stream (default: loot threads only)")
    ap.add_argument("--pattern", action="append", metavar="REGEX",
                    help="Pull streams whose filename matches REGEX (can repeat)")
    ap.add_argument("--dry-run", action="store_true",
                    help="List matching streams without downloading")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing local text files")
    ap.add_argument("--out-dir", default=str(RAWFILES_DIR),
                    help=f"Output directory (default: {RAWFILES_DIR})")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    patterns = args.pattern or DEFAULT_PATTERNS
    compiled = [re.compile(p) for p in patterns]

    print("Listing streams on Brain …", file=sys.stderr)
    try:
        all_files = list_remote_streams()
    except Exception as e:
        print(f"ERROR listing streams: {e}", file=sys.stderr)
        sys.exit(1)

    if args.all:
        targets = all_files
    else:
        targets = [f for f in all_files if any(p.search(f) for p in compiled)]

    print(f"  {len(all_files)} total streams, {len(targets)} match filter", file=sys.stderr)

    if args.dry_run:
        for f in sorted(targets):
            local = output_filename(f)
            exists = (out_dir / local).exists()
            marker = " [exists]" if exists else ""
            print(f"  {f} → {local}{marker}")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    skipped = 0
    errors = 0

    with tempfile.TemporaryDirectory() as tmp:
        for remote_file in sorted(targets):
            local_name = output_filename(remote_file)
            local_path = out_dir / local_name

            if local_path.exists() and not args.force:
                skipped += 1
                continue

            remote_path = f"{BRAIN_STREAMS_DIR}/{remote_file}"
            tmp_jsonl = Path(tmp) / remote_file

            print(f"  ↓ {remote_file} → {local_name}", file=sys.stderr)
            try:
                scp_file(remote_path, tmp_jsonl)
                text = jsonl_to_text(tmp_jsonl)
                if text.strip():
                    local_path.write_text(text, encoding="utf-8")
                    downloaded += 1
                else:
                    print(f"    (empty, skipping)", file=sys.stderr)
            except Exception as e:
                print(f"    ERROR: {e}", file=sys.stderr)
                errors += 1

    print(f"\nDone: {downloaded} downloaded, {skipped} skipped (use --force to overwrite), {errors} errors",
          file=sys.stderr)


if __name__ == "__main__":
    main()
