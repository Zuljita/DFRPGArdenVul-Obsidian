#!/usr/bin/env python3
import os
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def sync_to_drive(service_account_file, folder_id, local_dir):
    """
    This script syncs the files from a local directory to a Google Drive folder.
    """
    # Authenticate with Google Drive
    creds = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=['https://www.googleapis.com/auth/drive'])
    service = build('drive', 'v3', credentials=creds)

    # Get the list of files in the Google Drive folder
    drive_files = {}
    page_token = None
    while True:
        response = service.files().list(q=f"'{folder_id}' in parents",
                                      spaces='drive',
                                      fields='nextPageToken, files(id, name)',
                                      pageToken=page_token).execute()
        for file in response.get('files', []):
            drive_files[file.get('name')] = file.get('id')
        page_token = response.get('nextPageToken', None)
        if page_token is None:
            break

    # Get the list of local files
    local_files = [f for f in os.listdir(local_dir) if os.path.isfile(os.path.join(local_dir, f))]

    # Sync local files to Google Drive
    for filename in local_files:
        file_path = os.path.join(local_dir, filename)
        media = MediaFileUpload(file_path, mimetype='text/plain')
        
        if filename in drive_files:
            # Update existing file
            file_id = drive_files[filename]
            service.files().update(fileId=file_id, media_body=media).execute()
            print(f'Updated {filename} in Google Drive.')
            del drive_files[filename]
        else:
            # Create new file
            file_metadata = {'name': filename, 'parents': [folder_id]}
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f'Created {filename} in Google Drive.')

    # Delete files from Google Drive that are no longer present locally
    for filename, file_id in drive_files.items():
        service.files().delete(fileId=file_id).execute()
        print(f'Deleted {filename} from Google Drive.')

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print('Usage: python3 sync_to_drive.py <service_account_file> <folder_id> <local_dir>')
        sys.exit(1)
        
    sa_file = sys.argv[1]
    g_folder_id = sys.argv[2]
    l_dir = sys.argv[3]
    
    sync_to_drive(sa_file, g_folder_id, l_dir)
