import os
import shutil

def create_notebooklm_files():
    """
    This script consolidates all markdown files in the vault into large notebook files
    for use with NotebookLM.
    """
    vault_path = 'vault'
    output_dir = 'notebookLMFiles'
    
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
            if subdir == '.obsidian':
                continue
                
            # Concatenate the content of all markdown files in the subdirectory
            concatenated_content = ''
            for filename in os.listdir(subdir_path):
                if filename.endswith('.md'):
                    file_path = os.path.join(subdir_path, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        concatenated_content += f.read() + '\n\n'
                        
            # Save the concatenated content to a new file
            if concatenated_content:
                output_filename = f'{subdir}.md'
                output_path = os.path.join(output_dir, output_filename)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(concatenated_content)
                    
    print("NotebookLM files created successfully.")

if __name__ == '__main__':
    create_notebooklm_files()
