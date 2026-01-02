import streamlit as st
import random
from pathlib import Path

# --- Import Custom Modules ---
from utils import (
    load_config, save_config, load_snippets, save_snippets, 
    load_json, save_json, generate_templates, fetch_comfy_metadata, DEFAULTS
)
from tab_single import render_single_editor
from tab_batch import render_batch_processor
from tab_timeline import render_timeline_tab
from tab_timeline_wip import render_timeline_wip
from tab_comfy import render_comfy_monitor

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(layout="wide", page_title="AI Settings Manager")

# ==========================================
# 2. SESSION STATE INITIALIZATION
# ==========================================
if 'config' not in st.session_state:
    st.session_state.config = load_config()
    st.session_state.current_dir = Path(st.session_state.config.get("last_dir", Path.cwd()))

if 'snippets' not in st.session_state: 
    st.session_state.snippets = load_snippets()

if 'loaded_file' not in st.session_state: 
    st.session_state.loaded_file = None

if 'last_mtime' not in st.session_state: 
    st.session_state.last_mtime = 0

if 'edit_history_idx' not in st.session_state: 
    st.session_state.edit_history_idx = None

if 'single_editor_cache' not in st.session_state: 
    st.session_state.single_editor_cache = DEFAULTS.copy()

if 'ui_reset_token' not in st.session_state: 
    st.session_state.ui_reset_token = 0

# --- NEW: FETCH METADATA ON STARTUP ---
if 'comfy_meta' not in st.session_state:
    # Try to get URL from first instance, or default
    instances = st.session_state.config.get("comfy_instances", [])
    target_url = instances[0]["url"] if instances else "http://127.0.0.1:8188"
    
    st.session_state.comfy_meta = fetch_comfy_metadata(target_url)
# --------------------------------------

# ==========================================
# 3. SIDEBAR (NAVIGATOR & TOOLS)
# ==========================================
with st.sidebar:
    st.header("📂 Navigator")
    
    # --- Path Navigator ---
    new_path = st.text_input("Current Path", value=str(st.session_state.current_dir))
    if new_path != str(st.session_state.current_dir):
        p = Path(new_path)
        if p.exists() and p.is_dir():
            st.session_state.current_dir = p
            st.session_state.config['last_dir'] = str(p)
            save_config(st.session_state.current_dir, st.session_state.config['favorites'])
            st.rerun()

    # --- Favorites System ---
    if st.button("📌 Pin Current Folder"):
        if str(st.session_state.current_dir) not in st.session_state.config['favorites']:
            st.session_state.config['favorites'].append(str(st.session_state.current_dir))
            save_config(st.session_state.current_dir, st.session_state.config['favorites'])
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
    
    # --- Snippet Library ---
    st.subheader("🧩 Snippet Library")
    with st.expander("Add New Snippet"):
        snip_name = st.text_input("Name", placeholder="e.g. Cinematic")
        snip_content = st.text_area("Content", placeholder="4k, high quality...")
        if st.button("Save Snippet"):
            if snip_name and snip_content:
                st.session_state.snippets[snip_name] = snip_content
                save_snippets(st.session_state.snippets)
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
                del st.session_state.snippets[name]
                save_snippets(st.session_state.snippets)
                st.rerun()

    st.markdown("---")
    
    # --- File List & Creation ---
    json_files = sorted(list(st.session_state.current_dir.glob("*.json")))
    json_files = [f for f in json_files if f.name != ".editor_config.json" and f.name != ".editor_snippets.json"]

    if not json_files:
        if st.button("Generate Templates"):
            generate_templates(st.session_state.current_dir)
            st.rerun()
    
    with st.expander("Create New JSON"):
        new_filename = st.text_input("Filename", placeholder="my_prompt_vace")
        is_batch = st.checkbox("Is Batch File?")
        if st.button("Create"):
            if not new_filename.endswith(".json"): new_filename += ".json"
            path = st.session_state.current_dir / new_filename
            if is_batch:
                data = {"batch_data": []}
            else:
                data = DEFAULTS.copy()
                if "vace" in new_filename: data.update({"frame_to_skip": 81, "vace schedule": 1, "video file path": ""})
                elif "i2v" in new_filename: data.update({"reference image path": "", "flf image path": ""})
            save_json(path, data)
            st.rerun()

    # --- File Selector ---
    if 'file_selector' not in st.session_state:
        st.session_state.file_selector = json_files[0].name if json_files else None
    if st.session_state.file_selector not in [f.name for f in json_files] and json_files:
        st.session_state.file_selector = json_files[0].name
    
    selected_file_name = st.radio("Select File", [f.name for f in json_files], key="file_selector")

# ==========================================
# 4. MAIN APP LOGIC
# ==========================================
if selected_file_name:
    file_path = st.session_state.current_dir / selected_file_name
    
    if st.session_state.loaded_file != str(file_path):
        data, mtime = load_json(file_path)
        st.session_state.data_cache = data
        st.session_state.last_mtime = mtime
        st.session_state.loaded_file = str(file_path)
        if 'append_prompt' in st.session_state: del st.session_state.append_prompt
        if 'rand_seed' in st.session_state: del st.session_state.rand_seed
        if 'restored_indicator' in st.session_state: del st.session_state.restored_indicator
        st.session_state.edit_history_idx = None
    else:
        data = st.session_state.data_cache

    st.title(f"Editing: {selected_file_name}")

    # --- TABS ---
    tab_single, tab_batch, tab_timeline, tab_wip, tab_comfy = st.tabs([
        "📝 Single Editor", 
        "🚀 Batch Processor", 
        "🕒 Timeline", 
        "🧪 WIP Timeline",
        "🔌 Comfy Monitor"
    ])
    
    with tab_single:
        render_single_editor(data, file_path)
        
    with tab_batch:
        render_batch_processor(data, file_path, json_files, st.session_state.current_dir, selected_file_name)
        
    with tab_timeline:
        render_timeline_tab(data, file_path)
        
    with tab_wip:
        render_timeline_wip(data, file_path)

    with tab_comfy:
        render_comfy_monitor()
