import streamlit as st
import random
from pathlib import Path
import time

# --- Import Custom Modules ---
from db_manager import DatabaseManager
# We retain your UI modules, but they should now just receive data/dicts
from tab_single import render_single_editor
from tab_batch import render_batch_processor
from tab_timeline import render_timeline_tab
from tab_timeline_wip import render_timeline_wip
from tab_comfy import render_comfy_monitor

# Defined locally to avoid missing utils import, or keep your utils for DEFAULTS only
DEFAULTS = {
    "positive_prompt": "",
    "negative_prompt": "",
    "seed": -1,
    "steps": 20,
    "cfg": 7.0,
}

# ==========================================
# 1. PAGE CONFIGURATION & DB INIT
# ==========================================
st.set_page_config(layout="wide", page_title="AI Settings Manager (DB)")

# Initialize Database Manager
if 'db' not in st.session_state:
    st.session_state.db = DatabaseManager()

# ==========================================
# 2. SESSION STATE INITIALIZATION
# ==========================================
# Load App Config from DB
if 'config' not in st.session_state:
    st.session_state.config = st.session_state.db.load_app_config()
    
    # --- MIGRATION CHECK ---
    # If DB is empty, try to migrate from the folder in 'last_dir' or current cwd
    if st.session_state.db.is_empty():
        migration_target = st.session_state.config.get("last_dir", Path.cwd())
        st.session_state.db.migrate_from_json(migration_target)
        # Reload config after potential migration
        st.session_state.config = st.session_state.db.load_app_config()

    st.session_state.current_dir = Path(st.session_state.config.get("last_dir", Path.cwd()))

if 'snippets' not in st.session_state: 
    st.session_state.snippets = st.session_state.db.load_snippets()

if 'loaded_file' not in st.session_state: 
    st.session_state.loaded_file = None

# Track the active tab state
if 'active_tab_name' not in st.session_state:
    st.session_state.active_tab_name = "📝 Single Editor"

# ==========================================
# 3. SIDEBAR (NAVIGATOR & TOOLS)
# ==========================================
with st.sidebar:
    st.header("📂 Navigator")
    
    # --- Path Navigator ---
    # Note: User still navigates folders to FIND projects, but projects live in DB.
    new_path = st.text_input("Current Path", value=str(st.session_state.current_dir))
    if new_path != str(st.session_state.current_dir):
        p = Path(new_path)
        if p.exists() and p.is_dir():
            st.session_state.current_dir = p
            st.session_state.config['last_dir'] = str(p)
            st.session_state.db.save_app_config(st.session_state.config)
            st.rerun()

    # --- Favorites System ---
    if st.button("📌 Pin Current Folder"):
        if str(st.session_state.current_dir) not in st.session_state.config['favorites']:
            st.session_state.config['favorites'].append(str(st.session_state.current_dir))
            st.session_state.db.save_app_config(st.session_state.config)
            st.rerun()

    fav_selection = st.radio(
        "Jump to:", 
        ["Select..."] + st.session_state.config['favorites'], 
        index=0, 
        label_visibility="collapsed"
    )
    if fav_selection != "Select..." and fav_selection != str(st.session_state.current_dir):
        st.session_state.current_dir = Path(fav_selection)
        st.rerun()

    st.markdown("---")
    
    # --- Snippet Library (DB Backed) ---
    st.subheader("🧩 Snippet Library")
    with st.expander("Add New Snippet"):
        snip_name = st.text_input("Name", placeholder="e.g. Cinematic")
        snip_content = st.text_area("Content", placeholder="4k, high quality...")
        if st.button("Save Snippet"):
            if snip_name and snip_content:
                st.session_state.db.save_snippet(snip_name, snip_content)
                st.session_state.snippets = st.session_state.db.load_snippets() # Reload
                st.success(f"Saved '{snip_name}'")
                st.rerun()

    if st.session_state.snippets:
        st.caption("Click to Append to Prompt:")
        for name, content in st.session_state.snippets.items():
            col_s1, col_s2 = st.columns([4, 1])
            if col_s1.button(f"➕ {name}", use_container_width=True):
                st.session_state.append_prompt = content
                st.rerun()
            if col_s2.button("🗑️", key=f"del_snip_{name}"):
                st.session_state.db.delete_snippet(name)
                st.session_state.snippets = st.session_state.db.load_snippets()
                st.rerun()

    st.markdown("---")
    
    # --- File List (From DB) ---
    # We query the DB for projects that belong to the current directory
    db_files = st.session_state.db.get_projects_in_dir(st.session_state.current_dir)
    
    with st.expander("Create New Project"):
        new_filename = st.text_input("Project Name", placeholder="my_prompt_vace")
        is_batch = st.checkbox("Is Batch File?")
        if st.button("Create"):
            if not new_filename.endswith(".json"): new_filename += ".json" # Keep extension for legacy feel/compatibility
            
            # Init Data
            if is_batch:
                data = {"batch_data": []}
            else:
                data = DEFAULTS.copy()
                if "vace" in new_filename: data.update({"frame_to_skip": 81, "vace schedule": 1, "video file path": ""})
                
            # Save to DB
            full_path = st.session_state.current_dir / new_filename
            st.session_state.db.save_project(full_path, data, is_batch)
            st.rerun()

    # --- File Selector ---
    if 'file_selector' not in st.session_state:
        st.session_state.file_selector = db_files[0] if db_files else None
    
    # If list is empty or current selection not in list, reset
    if db_files and (st.session_state.file_selector not in db_files):
        st.session_state.file_selector = db_files[0]
    
    selected_file_name = None
    if db_files:
        selected_file_name = st.radio("Select Project", db_files, key="file_selector")
    else:
        st.info("No projects found in this folder.")

# ==========================================
# 4. MAIN APP LOGIC
# ==========================================
if selected_file_name:
    file_path = st.session_state.current_dir / selected_file_name
    
    # --- LOAD FROM DB ---
    # We reload if the file changed OR if we just performed a save (to get updates)
    if st.session_state.loaded_file != str(file_path):
        data = st.session_state.db.load_project(file_path)
        st.session_state.data_cache = data
        st.session_state.loaded_file = str(file_path)
        
        # Clear transient states
        if 'append_prompt' in st.session_state: del st.session_state.append_prompt
        
        # --- AUTO-SWITCH TAB LOGIC ---
        is_batch = "batch_data" in data or isinstance(data, list)
        if is_batch:
            st.session_state.active_tab_name = "🚀 Batch Processor"
        else:
            st.session_state.active_tab_name = "📝 Single Editor"
            
    else:
        data = st.session_state.data_cache

    st.title(f"Editing: {selected_file_name}")

    # --- NAVIGATION ---
    tabs_list = [
        "📝 Single Editor", 
        "🚀 Batch Processor", 
        "🕒 Timeline", 
        "🧪 Interactive Timeline",
        "🔌 Comfy Monitor"
    ]
    
    # Sync radio with session state
    current_tab = st.radio(
        "Navigation", 
        tabs_list,
        index=tabs_list.index(st.session_state.active_tab_name) if st.session_state.active_tab_name in tabs_list else 0,
        horizontal=True,
        label_visibility="collapsed"
    )
    st.session_state.active_tab_name = current_tab
    
    st.markdown("---")

    # --- RENDER TABS ---
    # Note: Inside your render functions (tab_single.py etc), you likely have a "Save" button.
    # You must update those files to call st.session_state.db.save_project() instead of save_json().
    # OR, we can handle the save here if we pass a callback or check for state changes.
    
    # For now, assuming render functions modify 'data' dictionary in place:
    
    if current_tab == "📝 Single Editor":
        # Pass data. Return value could be ignored if render modifies dict in place
        render_single_editor(data, file_path) 
        
        # SAVE BUTTON for Single Editor (Global override)
        if st.button("💾 Save Changes to DB", key="save_main"):
            st.session_state.db.save_project(file_path, data)
            st.success("Saved to Database!")
        
    elif current_tab == "🚀 Batch Processor":
        # We pass the list of 'db_files' instead of 'json_files'
        render_batch_processor(data, file_path, db_files, st.session_state.current_dir, selected_file_name)
        if st.button("💾 Save Batch to DB", key="save_batch"):
            st.session_state.db.save_project(file_path, data, is_batch=True)
            st.success("Batch Saved!")
        
    elif current_tab == "🕒 Timeline":
        render_timeline_tab(data, file_path)
        
    elif current_tab == "🧪 Interactive Timeline":
        render_timeline_wip(data, file_path)

    elif current_tab == "🔌 Comfy Monitor":
        render_comfy_monitor()
