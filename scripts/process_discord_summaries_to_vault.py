#!/usr/bin/env python3
import os
import re
from pathlib import Path
from collections import Counter

VAULT_DIR = Path('/home/knorton/.openclaw/workspace/DFRPGArdenVul-Obsidian/vault')
NOTES_DIR = VAULT_DIR / 'notes'

# Folders to check for existing articles
ENTITY_FOLDERS = ['npcs', 'locations', 'factions', 'items']

def load_existing_entities():
    entities = {}
    for folder in ENTITY_FOLDERS:
        for p in (VAULT_DIR / folder).glob('*.md'):
            name = p.stem
            entities[name] = p
    return entities

def extract_nouns_from_line(line):
    # Find Title Case phrases of 2 or more words
    # e.g., "Sword of Light", "Great Cavern"
    # Or single words if they are very clearly weird (we'll stick to 2+ words to be safe)
    words_groups = re.findall(r'\b(?:[A-Z][a-z]+(?:\s+of\s+|\s+the\s+|\s+)?)+\b', line)
    
    stop_words = {'The', 'A', 'An', 'In', 'On', 'At', 'To', 'Yes', 'No', 'If', 'And', 'Or', 'But', 'When', 'Where', 'Why', 'How', 'Is', 'Are', 'Was', 'Were', 'Do', 'Did', 'Does', 'Can', 'Could', 'Should', 'Would', 'Will', 'It', 'Its', 'They', 'Their', 'Them', 'He', 'His', 'She', 'Her', 'We', 'Our', 'Us', 'You', 'Your', 'I', 'My', 'Me', 'As', 'For', 'With', 'By', 'About', 'Against', 'Between', 'Into', 'Through', 'During', 'Before', 'After', 'Above', 'Below', 'From', 'Up', 'Down', 'Out', 'Off', 'Over', 'Under', 'Again', 'Further', 'Then', 'Once', 'Here', 'There', 'All', 'Any', 'Both', 'Each', 'Few', 'More', 'Most', 'Other', 'Some', 'Such', 'No', 'Nor', 'Not', 'Only', 'Own', 'Same', 'So', 'Than', 'Too', 'Very', 'Just', 'Don', 'Now', 'That', 'This', 'These', 'Those', 'Which', 'Who', 'Whom', 'Whose'}

    valid_candidates = []
    for group in words_groups:
        group = group.strip()
        parts = group.split()
        if len(parts) < 2:
            continue
        if parts[0] in stop_words:
            group = " ".join(parts[1:])
            parts = group.split()
            if len(parts) < 2:
                continue
        if len(group) > 3:
            valid_candidates.append(group)
    return valid_candidates

def enhance_article(path, fact, source):
    content = path.read_text(encoding='utf-8')
    if '## Discord Insights' not in content:
        if '## Sessions' in content:
            parts = content.split('## Sessions')
            new_content = parts[0] + f"## Discord Insights\n- {fact} ({source})\n\n## Sessions" + parts[1]
        elif '## Appears In' in content:
            parts = content.split('## Appears In')
            new_content = parts[0] + f"## Discord Insights\n- {fact} ({source})\n\n## Appears In" + parts[1]
        else:
            new_content = content + f"\n\n## Discord Insights\n- {fact} ({source})\n"
    else:
        # Check if fact already there
        if fact not in content:
            parts = content.split('## Discord Insights\n')
            new_content = parts[0] + f"## Discord Insights\n- {fact} ({source})\n" + parts[1]
        else:
            new_content = content
    path.write_text(new_content, encoding='utf-8')

def create_article(name, fact, source):
    safe_name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    if not safe_name: return
    path = NOTES_DIR / f"{safe_name}.md"
    if not path.exists():
        content = f"---\ntags:\n  - auto-generated\n---\n# {safe_name}\n\n## Discord Insights\n- {fact} ({source})\n"
        path.write_text(content, encoding='utf-8')
    else:
        enhance_article(path, fact, source)

def process_summaries():
    existing_entities = load_existing_entities()
    summary_files = sorted(NOTES_DIR.glob('Discord Summary *.md'))
    
    enhanced_count = 0
    created_count = 0
    
    for sf in summary_files:
        source_name = sf.stem
        lines = sf.read_text(encoding='utf-8').splitlines()
        for line in lines:
            if not line.startswith('- **') and not line.startswith('- ('):
                continue
            
            # Extract fact
            match = re.match(r'- \*\*.*?\*\* \([^)]+\):\s*(.*)', line)
            if not match:
                match = re.match(r'- \([^)]+\):\s*(.*)', line) # GM rulings format
            if not match:
                continue
            
            fact = match.group(1).strip()
            
            found_existing = False
            for entity_name, entity_path in list(existing_entities.items()):
                if entity_name in fact:
                    enhance_article(entity_path, fact, f"[[notes/{source_name}.md|{source_name}]]")
                    enhanced_count += 1
                    found_existing = True
            
            if not found_existing:
                nouns = extract_nouns_from_line(fact)
                for noun in nouns:
                    if noun not in existing_entities:
                        create_article(noun, fact, f"[[notes/{source_name}.md|{source_name}]]")
                        created_count += 1
                        existing_entities[noun] = NOTES_DIR / f"{noun}.md"

    print(f"Done. Enhanced {enhanced_count} times, created {created_count} new entity notes.")

if __name__ == '__main__':
    process_summaries()