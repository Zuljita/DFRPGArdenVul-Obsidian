#!/usr/bin/env python3
"""
LEGACY — do not run.

This emits `- **Author** (date): text` lines that bake real handles + verbatim chat
into vault/notes/Discord Summary YYYY-WNN.md, which Quartz then publishes. The
active pipeline is `vault_automation.py::import_discord_digests`, which copies the
curated narrative digest in from discord-chat-explorer's `weekly-digests/`. Kept
here only for archaeological reference.
"""

import json
import os
import sys
import re
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

if os.environ.get("ARDEN_ALLOW_RAW_DISCORD_SUMMARIES") != "1":
    sys.stderr.write(
        "refusing to run: this script writes raw per-message chat into the published vault.\n"
        "use scripts/vault_automation.py import-discord-digests instead.\n"
        "if you really mean it, set ARDEN_ALLOW_RAW_DISCORD_SUMMARIES=1.\n"
    )
    sys.exit(2)

VAULT_DIR = Path(__file__).parent.parent / "vault"
NOTES_DIR = VAULT_DIR / "notes"
RAW_DIR = Path(__file__).parent.parent / "RawFiles" / "Discord" / "processed"
MESSAGES_FILE = RAW_DIR / "messages.jsonl"
STATUS_FILE = NOTES_DIR / ".weekly_summary_status.json"

def load_messages():
    """Load all classified messages."""
    messages = []
    if not MESSAGES_FILE.exists():
        print(f"Error: {MESSAGES_FILE} not found")
        return messages
    
    with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                msg = json.loads(line.strip())
                # Filter for in-world content
                if msg.get('classification') in ['ic_or_lore', 'gm_lore_or_ruling']:
                    messages.append(msg)
            except json.JSONDecodeError:
                continue
    return messages

def group_by_week(messages):
    """Group messages by ISO week."""
    weeks = defaultdict(list)
    for msg in messages:
        ts = msg.get('timestamp_iso', '')
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00').replace('+00:00', ''))
            week_key = dt.strftime('%Y-W%W')
            weeks[week_key].append(msg)
        except:
            continue
    return weeks

def generate_weekly_summary(week_key, messages):
    """Generate a markdown summary for a week."""
    # Sort by timestamp
    messages.sort(key=lambda x: x.get('timestamp_iso', ''))
    
    # Parse week dates
    year, week = week_key.split('-W')
    year = int(year)
    week = int(week)
    
    # Calculate week start (Monday)
    jan1 = datetime(year, 1, 1)
    week_start = jan1 + timedelta(days=(week * 7) - jan1.weekday())
    week_end = week_start + timedelta(days=6)
    
    # Build summary
    lines = [
        f"# Discord Summary: {week_key}",
        f"",
        f"**Date Range:** {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}",
        f"**Messages:** {len(messages)}",
        f"",
        f"## In-World Highlights",
        f"",
    ]
    
    # Group by channel for organization
    by_channel = defaultdict(list)
    for msg in messages:
        ch = msg.get('channel', 'unknown')
        by_channel[ch].append(msg)
    
    for channel, msgs in sorted(by_channel.items()):
        lines.append(f"### #{channel}")
        lines.append("")
        for msg in msgs:
            author = msg.get('author_alias') or msg.get('author_name', 'Unknown')
            ts = msg.get('timestamp_iso', '')[:10]  # Just the date
            text = msg.get('text', '').replace('\n', ' ')
            # Strip emojis
            text = re.sub(r'[^\x00-\x7F]+', '', text)
            # Truncate very long messages
            if len(text) > 300:
                text = text[:297] + "..."
            lines.append(f"- **{author}** ({ts}): {text}")
        lines.append("")
    
    lines.append("---")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    
    return '\n'.join(lines)

def load_status():
    """Load processing status."""
    if STATUS_FILE.exists():
        with open(STATUS_FILE, 'r') as f:
            return json.load(f)
    return {"completed_weeks": [], "last_run": None}

def save_status(status):
    """Save processing status."""
    with open(STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=2)

def process_next_chunk(batch_size=3):
    """Process the next batch of unprocessed weeks."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    
    messages = load_messages()
    if not messages:
        print("No messages to process")
        return False
    
    weeks = group_by_week(messages)
    status = load_status()
    completed = set(status.get('completed_weeks', []))
    
    # Get unprocessed weeks in chronological order
    pending = [w for w in sorted(weeks.keys()) if w not in completed]
    
    if not pending:
        print("✅ All weeks processed!")
        return True
    
    print(f"📊 Total weeks: {len(weeks)}")
    print(f"✅ Completed: {len(completed)}")
    print(f"⏳ Pending: {len(pending)}")
    print(f"📝 Processing next {min(batch_size, len(pending))} weeks...")
    print()
    
    processed_this_run = []
    for week_key in pending[:batch_size]:
        summary = generate_weekly_summary(week_key, weeks[week_key])
        output_file = NOTES_DIR / f"Discord Summary {week_key}.md"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        processed_this_run.append(week_key)
        completed.add(week_key)
        print(f"  ✓ {week_key} → {output_file.name}")
    
    # Update status
    status['completed_weeks'] = sorted(completed)
    status['last_run'] = datetime.now().isoformat()
    status['last_processed'] = processed_this_run
    save_status(status)
    
    print()
    print(f"✅ Completed {len(processed_this_run)} weeks this run")
    print(f"⏳ {len(pending) - len(processed_this_run)} weeks remaining")
    
    return len(pending) <= len(processed_this_run)

if __name__ == '__main__':
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    all_done = process_next_chunk(batch_size=batch)
    sys.exit(0 if all_done else 1)
