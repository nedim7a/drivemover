import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']

st.set_page_config(page_title="Google Drive File Mover", page_icon="📁", layout="centered")

st.title("📁 Google Drive File Mover (Batch & Search)")
st.write("Manage, search, and transfer files across your Google Drive seamlessly.")

def get_drive_service():
    creds = None
    if "google_token" in st.secrets:
        token_data = dict(st.secrets["google_token"])
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        
    if not creds or not creds.valid:
        st.error("Invalid or missing Google token configuration in Streamlit Secrets!")
        st.stop()
        
    return build('drive', 'v3', credentials=creds)

try:
    service = get_drive_service()
    st.success("Successfully connected to Google Drive!")
    
    # Target Folder Input with Name Verification
    st.markdown("### 🎯 Target Destination")
    target_folder_id = st.text_input("Enter the Target Folder ID:")
    
    if target_folder_id:
        try:
            folder_meta = service.files().get(fileId=target_folder_id, fields='name, mimeType').execute()
            if folder_meta.get('mimeType') == 'application/vnd.google-apps.folder':
                st.info(f"📂 **Verified Target Folder:** `{folder_meta.get('name')}`")
            else:
                st.warning("⚠️ The provided ID belongs to a file, not a folder.")
        except Exception:
            st.error("❌ Could not find a folder with that ID. Please check and re-enter.")

    st.markdown("---")
    mode = st.radio("Choose Action Mode:", ["Move by File ID (or Picker)", "Search & Move by Name"])
    
    if mode == "Move by File ID (or Picker)":
        input_method = st.radio("Select File Input Method:", ["Manual File ID", "Pick from Recent Files"])
        
        file_id = ""
        if input_method == "Manual File ID":
            file_id = st.text_input("Enter the File ID:")
        else:
            # Fetch recent files for dropdown picker
            results = service.files().list(pageSize=15, fields="files(id, name, modifiedTime)").execute()
            files = results.get('files', [])
            if files:
                file_options = {f"{f['name']} (Modified: {f.get('modifiedTime', 'N/A')[:10]})": f['id'] for f in files}
                selected_label = st.selectbox("Select a recent file:", list(file_options.keys()))
                file_id = file_options[selected_label]
            else:
                st.info("No recent files found.")
                
        if st.button("Move File"):
            if file_id and target_folder_id:
                with st.spinner("Moving file..."):
                    file_meta = service.files().get(fileId=file_id, fields='name, parents').execute()
                    file_name = file_meta.get('name')
                    previous_parents = ",".join(file_meta.get('parents', []))
                    
                    service.files().update(
                        fileId=file_id,
                        addParents=target_folder_id,
                        removeParents=previous_parents,
                        fields='id, parents'
                    ).execute()
                st.success(f"✅ Successfully moved **'{file_name}'** to the target folder!")
            else:
                st.warning("Please provide both a valid File ID and a Target Folder ID.")
                
    elif mode == "Search & Move by Name":
        search_query = st.text_input("Enter keywords or name to search for files:")
        if st.button("Search Files"):
            if search_query:
                query = f"name contains '{search_query}' and trashed = false"
                results = service.files().list(q=query, pageSize=25, fields="files(id, name)").execute()
                files = results.get('files', [])
                
                if files:
                    st.session_state['found_files'] = files
                    st.success(f"Found {len(files)} matching file(s).")
                else:
                    st.info("No files found matching that search term.")
            else:
                st.warning("Please enter a search term.")
                
        if 'found_files' in st.session_state and st.session_state['found_files']:
            st.write("### 📋 Matching Files Preview:")
            for f in st.session_state['found_files']:
                st.text(f"• {f['name']} (ID: {f['id']})")
                
            if st.button("Move All Found Files with Progress Tracking"):
                if target_folder_id:
                    files_to_move = st.session_state['found_files']
                    total_files = len(files_to_move)
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    success_count = 0
                    for i, f in enumerate(files_to_move):
                        file_id = f['id']
                        file_name = f['name']
                        status_text.text(f"Moving ({i+1}/{total_files}): {file_name}...")
                        
                        try:
                            file_data = service.files().get(fileId=file_id, fields='parents').execute()
                            previous_parents = ",".join(file_data.get('parents', []))
                            
                            service.files().update(
                                fileId=file_id,
                                addParents=target_folder_id,
                                removeParents=previous_parents,
                                fields='id, parents'
                            ).execute()
                            success_count += 1
                        except Exception as err:
                            st.error(f"Failed to move {file_name}: {err}")
                            
                        progress_bar.progress((i + 1) / total_files)
                        
                    status_text.text("Transfer complete!")
                    st.success(f"🎉 Successfully transferred {success_count} of {total_files} file(s)!")
                    del st.session_state['found_files']
                else:
                    st.error("Please enter a Target Folder ID before executing batch transfers.")

except Exception as e:
    st.error(f"An error occurred: {e}")
