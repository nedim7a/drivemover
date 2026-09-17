import os
import json
import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']

st.title("📁 Google Drive File Mover (Batch & Search)")
st.write("Search for files by name or move them using a target folder ID.")

def get_drive_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Check if we are running on Streamlit Cloud with secrets
            if "google_credentials" in st.secrets:
                # Load credentials dictionary directly from Streamlit Secrets
                client_config = dict(st.secrets["google_credentials"])
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            else:
                # Local fallback for your PC
                if not os.path.exists('credentials.json'):
                    st.error("Missing 'credentials.json' or Streamlit secrets configuration!")
                    st.stop()
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            
            creds = flow.run_local_server(port=0)
            
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

try:
    service = get_drive_service()
    st.success("Successfully connected to Google Drive!")
    
    mode = st.radio("Choose Action Mode:", ["Move by File ID", "Search & Move by Name"])
    target_folder_id = st.text_input("Enter the Target Folder ID:")
    
    if mode == "Move by File ID":
        file_id = st.text_input("Enter the File ID:")
        if st.button("Move File"):
            if file_id and target_folder_id:
                with st.spinner("Moving file..."):
                    file = service.files().get(fileId=file_id, fields='parents').execute()
                    previous_parents = ",".join(file.get('parents', []))
                    
                    service.files().update(
                        fileId=file_id,
                        addParents=target_folder_id,
                        removeParents=previous_parents,
                        fields='id, parents'
                    ).execute()
                st.success("File moved successfully!")
            else:
                st.warning("Please enter both a File ID and a Target Folder ID.")
                
    elif mode == "Search & Move by Name":
        search_query = st.text_input("Enter keywords or name to search for files:")
        if st.button("Search Files"):
            if search_query:
                query = f"name contains '{search_query}' and trashed = false"
                results = service.files().list(q=query, pageSize=20, fields="files(id, name)").execute()
                files = results.get('files', [])
                
                if files:
                    st.session_state['found_files'] = files
                    st.success(f"Found {len(files)} file(s).")
                else:
                    st.info("No files found matching that search term.")
            else:
                st.warning("Please enter a search term.")
                
        if 'found_files' in st.session_state and st.session_state['found_files']:
            st.write("### Matching Files:")
            for f in st.session_state['found_files']:
                st.text(f"- {f['name']} (ID: {f['id']})")
                
            if st.button("Move All Found Files to Target Folder"):
                if target_folder_id:
                    with st.spinner("Moving files..."):
                        for f in st.session_state['found_files']:
                            file_id = f['id']
                            file_data = service.files().get(fileId=file_id, fields='parents').execute()
                            previous_parents = ",".join(file_data.get('parents', []))
                            
                            service.files().update(
                                fileId=file_id,
                                addParents=target_folder_id,
                                removeParents=previous_parents,
                                fields='id, parents'
                            ).execute()
                    st.success("All matching files moved successfully!")
                    del st.session_state['found_files']
                else:
                    st.error("Please enter a Target Folder ID before moving.")

except Exception as e:
    st.error(f"An error occurred: {e}")