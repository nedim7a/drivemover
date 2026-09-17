import streamlit as st
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os

# Allow OAuth over HTTPS
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '0'

SCOPES = ['https://www.googleapis.com/auth/drive']

st.set_page_config(page_title="Google Drive File Mover", page_icon="📁", layout="centered")

st.title("📁 Google Drive File Mover (Multi-User)")
st.write("Log in with your Google account to manage and transfer files in your own Google Drive.")

def get_oauth_flow():
    client_config = {
        "web": {
            "client_id": st.secrets["google_credentials"]["client_id"],
            "client_secret": st.secrets["google_credentials"]["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["https://7adrivemover.streamlit.app"]
        }
    }
    return Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri="https://7adrivemover.streamlit.app")

# --- Authentication State Handling ---
if "credentials" not in st.session_state:
    st.session_state["credentials"] = None

# Handle redirect from Google OAuth
query_params = st.query_params
if "code" in query_params and not st.session_state["credentials"]:
    try:
        flow = get_oauth_flow()
        flow.fetch_token(code=query_params["code"])
        st.session_state["credentials"] = flow.credentials
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Authentication failed: {e}")

# If not logged in, show the Google Sign-in button
if not st.session_state["credentials"]:
    flow = get_oauth_flow()
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    
    st.markdown("### 🔐 Authentication Required")
    st.write("Click below to sign in with your Google account and access your personal Drive.")
    st.markdown(
        f'<a href="{auth_url}" target="_self">'
        f'<button style="background-color:#4285F4; color:white; padding:10px 24px; border:none; border-radius:6px; font-size:16px; font-weight:600; cursor:pointer;">'
        f'Sign in with Google</button></a>',
        unsafe_allow_html=True
    )
    
    st.info("💡 *Note: Because this is an internal application, Google may display a standard 'Unverified app' notice. Click **Advanced** ➔ **Go to Drive Mover (unsafe)** to proceed.*")
    st.stop()

# --- Main Application (Runs for the logged-in user) ---
try:
    creds = Credentials(
        token=st.session_state["credentials"].token,
        refresh_token=st.session_state["credentials"].refresh_token,
        token_uri=st.session_state["credentials"].token_uri,
        client_id=st.session_state["credentials"].client_id,
        client_secret=st.session_state["credentials"].client_secret,
        scopes=st.session_state["credentials"].scopes
    )
    service = build('drive', 'v3', credentials=creds)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.success("Successfully connected to your Google Drive!")
    with col2:
        if st.button("Log Out"):
            st.session_state["credentials"] = None
            st.rerun()

    # Target Folder Input
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
            st.error("❌ Could not find a folder with that ID in your Drive. Please check and re-enter.")

    st.markdown("---")
    mode = st.radio("Choose Action Mode:", ["Move by File ID (or Picker)", "Search & Move by Name"])
    
    if mode == "Move by File ID (or Picker)":
        input_method = st.radio("Select File Input Method:", ["Manual File ID", "Pick from Recent Files"])
        
        file_id = ""
        if input_method == "Manual File ID":
            file_id = st.text_input("Enter the File ID:")
        else:
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
                    
                    if total_files > 0:
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
    st.error(f"An error occurred or session expired: {e}")
    if st.button("Re-authenticate"):
        st.session_state["credentials"] = None
        st.rerun()
