import os
from pathlib import Path
import re

VAULT_DIR = Path('/home/knorton/.openclaw/workspace/DFRPGArdenVul-Obsidian/vault')
NOTES_DIR = VAULT_DIR / 'notes'

ENTITY_FOLDERS = ['npcs', 'locations', 'factions', 'items']

# 1. Remove auto-generated notes
deleted_count = 0
for p in NOTES_DIR.glob('*.md'):
    try:
        content = p.read_text(encoding='utf-8')
        if 'tags:\n  - auto-generated' in content:
            p.unlink()
            deleted_count += 1
    except Exception as e:
        pass

print(f"Deleted {deleted_count} auto-generated notes.")

# 2. Remove ## Discord Insights block from existing files
cleaned_count = 0
for folder in ENTITY_FOLDERS:
    for p in (VAULT_DIR / folder).glob('*.md'):
        try:
            content = p.read_text(encoding='utf-8')
            if '## Discord Insights' in content:
                # Remove the block. It starts at ## Discord Insights and ends before ## Sessions, ## Appears In, or end of file
                # Use regex to strip it
                new_content = re.sub(r'## Discord Insights\n(?:- .*\n)*', '', content)
                # also clean up double newlines that might have been left
                new_content = re.sub(r'\n{3,}', '\n\n', new_content)
                p.write_text(new_content, encoding='utf-8')
                cleaned_count += 1
        except Exception as e:
            pass

print(f"Cleaned {cleaned_count} existing notes.")
