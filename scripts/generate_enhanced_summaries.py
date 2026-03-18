#!/usr/bin/env python3
"""
Enhanced Discord summary generator with entity linking and context building.
"""

import json
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

VAULT_DIR = Path(__file__).parent.parent / "vault"
NOTES_DIR = VAULT_DIR / "notes"
RAW_DIR = Path(__file__).parent.parent / "RawFiles" / "Discord" / "processed"
MESSAGES_FILE = RAW_DIR / "messages.jsonl"
STATUS_FILE = NOTES_DIR / ".weekly_summary_status.json"

# Known entities for linking (expand as we discover more)
KNOWN_ENTITIES = {
    # NPCs
    "Wicktrimmer": "npcs/Wicktrimmer.md",
    "Lyssandra": "npcs/Lyssandra.md", 
    "Pelteon": "npcs/Pelteon.md",
    "Ptarmis": "npcs/Ptarmis.md",
    "Gog": "npcs/Gog.md",
    "Craastonistorex": "npcs/Craastonistorex.md",
    "Azgallatu": "npcs/Azgallatu.md",
    "Lillian": "npcs/Lillian.md",
    "Lord Iskander Burdock": "npcs/Lord Iskander Burdock.md",
    "Lady Alexia": "npcs/Lady Alexia.md",
    "Freydis": "npcs/Freydis.md",
    "Astableon": "npcs/Astableon.md",
    "Plumthorn": "npcs/Plumthorn.md",
    "Stephania": "npcs/Stephania.md",
    "Akla-Chah": "npcs/Akla-Chah.md",
    "Akla Chah": "npcs/Akla-Chah.md",
    
    # Locations
    "Gosterwick": "locations/Gosterwick.md",
    "Arden Vul": "locations/Arden Vul.md",
    "Tower of the Ape": "locations/Tower of the Ape.md",
    "Forum of Set": "locations/Forum of Set.md",
    "Great Cavern": "locations/Great Cavern.md",
    "Pyramid of Thoth": "locations/Pyramid of Thoth.md",
    "Halls of Thoth": "locations/Halls of Thoth.md",
    "Obsidian Gates": "locations/Obsidian Gates.md",
    "Arcane Practitioners Club": "locations/Arcane Practitioners Club.md",
    "Rarities Factor": "locations/Rarities Factor.md",
    "Temple of Demma": "locations/Temple of Demma.md",
    "Great Chasm": "locations/Great Chasm.md",
    "Goblintown": "locations/Goblintown.md",
    "The Canyon": "locations/The Canyon.md",
    
    # Factions
    "Cult of Set": "factions/Cult of Set.md",
    "Settites": "factions/Cult of Set.md",
    "Thoth's Beloved": "factions/Thoth's Beloved.md",
    
    # Lore/Items
    "Book of Priors": "lore/The Book of Priors.md",
    "Arcanum": "lore/Arcanum.md",
    
    # Rudishva (special handling needed)
    "Crallicarus": "npcs/Crellik-Var.md",  # Archontean name -> Rudishva name
    "Crellik-Var": "npcs/Crellik-Var.md",
    "Sakorikus": "npcs/Psalor-Ki.md",
    "Psalor-Ki": "npcs/Psalor-Ki.md",
    "Ravatorus": "npcs/Reiv-Tor.md",
    "Reiv-Tor": "npcs/Reiv-Tor.md",
    "Isocrates": "npcs/Isok-Crix.md",
    "Isok-Crix": "npcs/Isok-Crix.md",
    "Melacorius": "npcs/Melok-Ri.md",
    "Melok-Ri": "npcs/Melok-Ri.md",
    "Nacalorus": "npcs/Naik-Lir.md",
    "Naik-Lir": "npcs/Naik-Lir.md",
}

def extract_entities(text):
    """Extract potential entity mentions from text."""
    entities = []
    for name, path in KNOWN_ENTITIES.items():
        if name in text:
            entities.append((name, path))
    return entities

def classify_content(text, author_alias):
    """Classify the type of content."""
    text_lower = text.lower()
    
    # Check for rumors
    if text.startswith('Rumor') or 'rumor' in text_lower[:30]:
        return 'rumor'
    
    # Check for GM rulings
    if author_alias == 'GM':
        if any(x in text_lower for x in ['rule', 'costs', 'you can', 'you cannot', 'does not', 'counts as']):
            return 'gm_ruling'
        return 'gm_lore'
    
    # Check for in-character statements
    if author_alias in ['Vael, Zuljita', 'Vallium Halcyon', 'Ioannes', 'Uvash', 'Grudge Brigade']:
        return 'ic_statement'
    
    return 'other'

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

def generate_enhanced_summary(week_key, messages):
    """Generate an enhanced markdown summary for a week with entity linking."""
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
    
    # Categorize messages
    rumors = []
    gm_rulings = []
    gm_lore = []
    ic_statements = []
    other = []
    
    for msg in messages:
        text = msg.get('text', '')
        # Strip emojis
        text = re.sub(r'[^\x00-\x7F]+', '', text)
        msg['text'] = text
        author = msg.get('author_alias') or msg.get('author_name', 'Unknown')
        category = classify_content(text, author)
        
        if category == 'rumor':
            rumors.append(msg)
        elif category == 'gm_ruling':
            gm_rulings.append(msg)
        elif category == 'gm_lore':
            gm_lore.append(msg)
        elif category == 'ic_statement':
            ic_statements.append(msg)
        else:
            other.append(msg)
    
    # Build summary
    lines = [
        f"# Discord Summary: {week_key}",
        f"",
        f"**Date Range:** {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}",
        f"**Messages:** {len(messages)}",
        f"",
        f"## Contents",
        f"- [Rumors](#rumors) ({len(rumors)})",
        f"- [GM Rulings](#gm-rulings) ({len(gm_rulings)})",
        f"- [GM Lore Drops](#gm-lore-drops) ({len(gm_lore)})",
        f"- [In-World Activity](#in-world-activity) ({len(ic_statements)})",
        f"",
    ]
    
    # Rumors section
    if rumors:
        lines.append("## Rumors")
        lines.append("")
        for msg in rumors:
            author = msg.get('author_alias') or msg.get('author_name', 'Unknown')
            ts = msg.get('timestamp_iso', '')[:10]
            text = msg.get('text', '').replace('\n', ' ')
            entities = extract_entities(text)
            # Add entity links
            for name, path in entities:
                text = text.replace(name, f"[[{path}|{name}]]")
            lines.append(f"- **{author}** ({ts}): {text}")
        lines.append("")
    
    # GM Rulings section
    if gm_rulings:
        lines.append("## GM Rulings")
        lines.append("")
        for msg in gm_rulings:
            ts = msg.get('timestamp_iso', '')[:10]
            text = msg.get('text', '').replace('\n', ' ')
            entities = extract_entities(text)
            for name, path in entities:
                text = text.replace(name, f"[[{path}|{name}]]")
            lines.append(f"- ({ts}): {text}")
        lines.append("")
    
    # GM Lore section
    if gm_lore:
        lines.append("## GM Lore Drops")
        lines.append("")
        for msg in gm_lore:
            ts = msg.get('timestamp_iso', '')[:10]
            text = msg.get('text', '').replace('\n', ' ')
            if len(text) > 400:
                text = text[:397] + "..."
            entities = extract_entities(text)
            for name, path in entities:
                text = text.replace(name, f"[[{path}|{name}]]")
            lines.append(f"- ({ts}): {text}")
        lines.append("")
    
    # In-World Activity section
    if ic_statements:
        lines.append("## In-World Activity")
        lines.append("")
        # Group by channel
        by_channel = defaultdict(list)
        for msg in ic_statements:
            ch = msg.get('channel', 'unknown')
            by_channel[ch].append(msg)
        
        for channel, msgs in sorted(by_channel.items()):
            lines.append(f"### #{channel}")
            lines.append("")
            for msg in msgs:
                author = msg.get('author_alias') or msg.get('author_name', 'Unknown')
                ts = msg.get('timestamp_iso', '')[:10]
                text = msg.get('text', '').replace('\n', ' ')
                if len(text) > 300:
                    text = text[:297] + "..."
                entities = extract_entities(text)
                for name, path in entities:
                    text = text.replace(name, f"[[{path}|{name}]]")
                lines.append(f"- **{author}** ({ts}): {text}")
            lines.append("")
    
    # Other content
    if other:
        lines.append("## Other Notes")
        lines.append("")
        for msg in other:
            author = msg.get('author_alias') or msg.get('author_name', 'Unknown')
            ts = msg.get('timestamp_iso', '')[:10]
            text = msg.get('text', '').replace('\n', ' ')
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
    """Process the next batch of unprocessed weeks with enhanced summaries."""
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
    print(f"📝 Processing next {min(batch_size, len(pending))} weeks with enhanced linking...")
    print()
    
    processed_this_run = []
    for week_key in pending[:batch_size]:
        summary = generate_enhanced_summary(week_key, weeks[week_key])
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
    import sys
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    all_done = process_next_chunk(batch_size=batch)
    sys.exit(0 if all_done else 1)
