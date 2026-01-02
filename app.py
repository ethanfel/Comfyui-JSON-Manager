import streamlit as st
import random
from pathlib import Path

# Import Modules
from utils import (
    load_config, save_config, load_snippets, save_snippets, 
    load_json, save_json, generate_templates, DEFAULTS
)
from tab_single import render_single_editor
from tab_batch import render_batch_processor
from tab_timeline import render_timeline_tab  # <--- IMPORT NEW TAB

# ... (Keep all setup code: set_page_config, session state init, sidebar) ...
# ... [Use the app.py code from previous response, just change the Main App Logic section below] ...

# --- Main App Logic ---
if selected_file_name:
    file_path = st.session_state.current_dir / selected_file_name
    
    # Load or Reload if file changed
    if st.session_state.loaded_file != str(file_path):
        data, mtime = load_json(file_path)
        st.session_state.data_cache = data
        st.session_state.last_mtime = mtime
        st.session_state.loaded_file = str(file_path)
        if 'append_prompt' in st.session_state: del st.session_state.append_prompt
        if 'rand_seed' in st.session_state: del st.session_state.rand_seed
        st.session_state.edit_history_idx = None
    else:
        data = st.session_state.data_cache

    st.title(f"Editing: {selected_file_name}")

    # --- TABS CONFIGURATION ---
    # We add the 3rd Tab here
    tab_single, tab_batch, tab_timeline = st.tabs(["📝 Single Editor", "🚀 Batch Processor", "🕒 Timeline"])
    
    with tab_single:
        render_single_editor(data, file_path)
        
    with tab_batch:
        render_batch_processor(data, file_path, json_files, st.session_state.current_dir, selected_file_name)
        
    with tab_timeline:
        # Check if batch file, as requested "only for batch"
        # But honestly, it's useful for single too. I'll enable it for both, 
        # but if you STRICTLY want batch only, uncomment the if statement inside render_timeline_tab
        render_timeline_tab(data, file_path)
