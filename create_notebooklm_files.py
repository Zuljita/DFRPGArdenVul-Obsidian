#!/usr/bin/env python3
import os
import shutil
import re
import sys

def create_notebooklm_files(output_dir):
    """
    This script consolidates all markdown files in the vault into large notebook files
    for use with NotebookLM.
    """
    vault_path = 'vault'
    
    # Create the output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    # Clear the output directory
    for filename in os.listdir(output_dir):
        file_path = os.path.join(output_dir, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

    # Iterate through the subdirectories of the vault
    for subdir in os.listdir(vault_path):
        subdir_path = os.path.join(vault_path, subdir)
        if os.path.isdir(subdir_path):
            # Skip the .obsidian directory
            if subdir == '.obsidian' or subdir == 'templates':
                continue
                
            # Concatenate the content of all markdown files in the subdirectory
            concatenated_content = ''
            for filename in os.listdir(subdir_path):
                if filename.endswith('.md'):
                    file_path = os.path.join(subdir_path, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                        # Remove Obsidian link markers, handling display text
                        # Pattern to match [[Page Name|Display Text]] or [[Page Name]]
                        # Replace [[Page Name|Display Text]] with Display Text
                        file_content = re.sub(r'\[\[[^|]+\|([^\]]+)\]\]', r'\1', file_content)
                        # Replace [[Page Name]] with Page Name
                        file_content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', file_content)
                        concatenated_content += file_content + '\n\n'
                        
            # Save the concatenated content to a new file
            if concatenated_content:
                output_filename = f'{subdir}.txt'
                output_path = os.path.join(output_dir, output_filename)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(concatenated_content)
                    
    print("NotebookLM files created successfully.")

    # Merge the two smallest files
    files = [f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
    if len(files) > 10:
        files.sort(key=lambda f: os.path.getsize(os.path.join(output_dir, f)))
        
        smallest_file_1 = files[0]
        smallest_file_2 = files[1]
        
        file_1_path = os.path.join(output_dir, smallest_file_1)
        file_2_path = os.path.join(output_dir, smallest_file_2)
        
        with open(file_1_path, 'r', encoding='utf-8') as f1:
            content1 = f1.read()
            
        with open(file_2_path, 'r', encoding='utf-8') as f2:
            content2 = f2.read()
            
        merged_content = content1 + '\n\n' + content2
        
        merged_filename = f'{os.path.splitext(smallest_file_1)[0]}-and-{os.path.splitext(smallest_file_2)[0]}.txt'
        merged_filepath = os.path.join(output_dir, merged_filename)
        
        with open(merged_filepath, 'w', encoding='utf-8') as f:
            f.write(merged_content)
            
        os.remove(file_1_path)
        os.remove(file_2_path)
        
        print(f"Merged {smallest_file_1} and {smallest_file_2} into {merged_filename}")

if __name__ == '__main__':
    output_directory = 'notebookLMFiles'
    if len(sys.argv) > 1:
        output_directory = sys.argv[1]
    create_notebooklm_files(output_directory)
