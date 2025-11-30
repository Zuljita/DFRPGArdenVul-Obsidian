import os
import re

def add_tag_to_file(file_path, tag):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if re.search(r'^---', content, re.MULTILINE):
        if re.search(r'^tags:', content, re.MULTILINE):
            # tags key exists, append new tag
            new_content = re.sub(r'^(tags:.*)$', r'\1\n  - ' + tag, content, 1, re.MULTILINE)
        else:
            # frontmatter exists, but no tags key
            new_content = re.sub(r'^(---)$', r'\1\ntags:\n  - ' + tag, content, 1, re.MULTILINE)
    else:
        # no frontmatter
        new_content = f"---\ntags:\n  - {tag}\n---\n\n{content}"

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

def main():
    vault_path = 'vault'
    for root, dirs, files in os.walk(vault_path):
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file)
                folder = os.path.basename(root)
                
                if folder == 'npcs':
                    add_tag_to_file(file_path, 'npc')
                elif folder == 'locations':
                    add_tag_to_file(file_path, 'location')
                elif folder == 'items':
                    add_tag_to_file(file_path, 'item')
                elif folder == 'factions':
                    add_tag_to_file(file_path, 'faction')
                elif folder == 'spells':
                    add_tag_to_file(file_path, 'spell')
                elif folder == 'concepts':
                    add_tag_to_file(file_path, 'concept')
                elif folder == 'lore':
                    add_tag_to_file(file_path, 'lore')
                elif folder == 'monsters':
                    add_tag_to_file(file_path, 'monster')
                elif folder == 'pcs':
                    add_tag_to_file(file_path, 'pc')
                elif folder == 'sessions':
                    add_tag_to_file(file_path, 'session')

if __name__ == '__main__':
    main()
