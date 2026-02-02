import streamlit as st
import random
from pathlib import Path

# --- Import Custom Modules ---
from utils import (
    load_config, save_config, load_snippets, save_snippets,
    load_json, save_json, generate_templates, DEFAULTS, ALLOWED_BASE_DIR
)
from tab_single import render_single_editor
from tab_batch import render_batch_processor
from tab_timeline import render_timeline_tab
from tab_timeline_wip import render_timeline_wip
from tab_comfy import render_comfy_monitor
from tab_raw import render_raw_editor

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(layout="wide", page_title="AI Settings Manager")

# ==========================================
# 2. SESSION STATE INITIALIZATION
# ==========================================
_SESSION_DEFAULTS = {
    "snippets": load_snippets,
    "loaded_file": lambda: None,
    "last_mtime": lambda: 0,
    "edit_history_idx": lambda: None,
    "single_editor_cache": lambda: DEFAULTS.copy(),
    "ui_reset_token": lambda: 0,
    "active_tab_name": lambda: "📝 Single Editor",
}

if 'config' not in st.session_state:
    st.session_state.config = load_config()
    st.session_state.current_dir = Path(st.session_state.config.get("last_dir", Path.cwd()))

for key, factory in _SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = factory()

# ==========================================
# 3. SIDEBAR (NAVIGATOR & TOOLS)
# ==========================================
with st.sidebar:
    st.header("📂 Navigator")
    
    # --- Path Navigator ---
    new_path = st.text_input("Current Path", value=str(st.session_state.current_dir))
    if new_path != str(st.session_state.current_dir):
        p = Path(new_path).resolve()
        if p.exists() and p.is_dir():
            # Restrict navigation to the allowed base directory
            try:
                p.relative_to(ALLOWED_BASE_DIR)
            except ValueError:
                st.error(f"Access denied: path must be under {ALLOWED_BASE_DIR}")
            else:
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
    
    # --- GLOBAL MONITOR TOGGLE (NEW) ---
    st.markdown("---")
    show_monitor = st.checkbox("Show Comfy Monitor", value=True)

# ==========================================
# 4. MAIN APP LOGIC
# ==========================================
if selected_file_name:
    file_path = st.session_state.current_dir / selected_file_name
    
    # --- FILE LOADING & AUTO-SWITCH LOGIC ---
    if st.session_state.loaded_file != str(file_path):
        data, mtime = load_json(file_path)
        st.session_state.data_cache = data
        st.session_state.last_mtime = mtime
        st.session_state.loaded_file = str(file_path)
        
        # Clear transient states
        if 'append_prompt' in st.session_state: del st.session_state.append_prompt
        if 'rand_seed' in st.session_state: del st.session_state.rand_seed
        if 'restored_indicator' in st.session_state: del st.session_state.restored_indicator
        st.session_state.edit_history_idx = None
        
        # --- AUTO-SWITCH TAB LOGIC ---
        is_batch = "batch_data" in data or isinstance(data, list)
        if is_batch:
            st.session_state.active_tab_name = "🚀 Batch Processor"
        else:
            st.session_state.active_tab_name = "📝 Single Editor"
            
    else:
        data = st.session_state.data_cache

    st.title(f"Editing: {selected_file_name}")

    # --- CONTROLLED NAVIGATION ---
    # Removed "🔌 Comfy Monitor" from this list
    tabs_list = [
        "📝 Single Editor", 
        "🚀 Batch Processor", 
        "🕒 Timeline", 
        "🧪 Interactive Timeline",
        "💻 Raw Editor"
    ]
    
    if st.session_state.active_tab_name not in tabs_list:
        st.session_state.active_tab_name = tabs_list[0]

    current_tab = st.radio(
        "Navigation", 
        tabs_list,
        key="active_tab_name", 
        horizontal=True,
        label_visibility="collapsed"
    )
    
    st.markdown("---")

    # --- RENDER EDITOR TABS ---
    if current_tab == "📝 Single Editor":
        render_single_editor(data, file_path)
        
    elif current_tab == "🚀 Batch Processor":
        render_batch_processor(data, file_path, json_files, st.session_state.current_dir, selected_file_name)
        
    elif current_tab == "🕒 Timeline":
        render_timeline_tab(data, file_path)
        
    elif current_tab == "🧪 Interactive Timeline":
        render_timeline_wip(data, file_path)
        
    elif current_tab == "💻 Raw Editor":
        render_raw_editor(data, file_path)

    # --- GLOBAL PERSISTENT MONITOR ---
    if show_monitor:
        st.markdown("---")
        with st.expander("🔌 ComfyUI Monitor", expanded=True):
            render_comfy_monitor()