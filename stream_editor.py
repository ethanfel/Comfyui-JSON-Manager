import streamlit as st
import json
import os
import time
from pathlib import Path

# --- Configuration ---
CONFIG_FILE = Path(".editor_config.json")
SNIPPETS_FILE = Path(".editor_snippets.json")

st.set_page_config(layout="wide", page_title="AI Settings Manager")

# Defaults
DEFAULTS = {
    "camera": "Camera stand still. Motion starts immediately.",
    "flf": 0,
    "frame_to_skip": 81,
    "input_a_frames": "",
    "input_b_frames": "",
    "reference path": "",
    "reference switch": 1,
    "vace schedule": 1,
    "video file path": "",
    "reference image path": "",
    "flf image path": "",  # <--- NEW KEY
    "current_prompt": "",
    "negative": "",
    "lora 1 high": "", "lora 1 low": "",
    "lora 2 high": "", "lora 2 low": "",
    "lora 3 high": "", "lora 3 low": "",
    "prompt_history": []
}

GLOBAL_NEGATIVE = "Vivid tones, overexposed, static, blurry details, subtitles, style, artwork, painting, picture, still image, overall gray, worst quality, low quality, JPEG compression artifacts, ugly, deformed, extra fingers, poorly drawn hands, poorly drawn face, distorted, disfigured, malformed limbs, fused fingers, unmoving frame, cluttered background, three legs,"

GENERIC_TEMPLATES = ["prompt_global.json", "prompt_i2v.json", "prompt_global_extend.json", "prompt_vace_extend.json"]

# --- Helper Functions ---
def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return {"last_dir": str(Path.cwd()), "favorites": []}

def save_config(current_dir, favorites):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"last_dir": str(current_dir), "favorites": favorites}, f, indent=4)

def load_snippets():
    if SNIPPETS_FILE.exists():
        try:
            with open(SNIPPETS_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return {}

def save_snippets(snippets):
    with open(SNIPPETS_FILE, 'w') as f:
        json.dump(snippets, f, indent=4)

def get_file_mtime(path):
    if path.exists(): return os.path.getmtime(path)
    return 0

def load_json(path):
    with open(path, 'r') as f:
        data = json.load(f)
    return data, get_file_mtime(path)

def save_json(path, data):
    clean_data = {k: v for k, v in data.items() if k in DEFAULTS or k == "prompt_history"}
    if path.exists():
        try:
            with open(path, 'r') as f:
                existing = json.load(f)
            existing.update(clean_data)
            clean_data = existing
        except: pass
    with open(path, 'w') as f:
        json.dump(clean_data, f, indent=4)
    return get_file_mtime(path)

def generate_templates(directory):
    for filename in GENERIC_TEMPLATES:
        path = directory / filename
        data = DEFAULTS.copy()
        if "vace" in filename: 
            data.update({"frame_to_skip": 81, "vace schedule": 1, "video file path": ""})
        elif "global" in filename: 
            data.update({"video file path": "", "negative": GLOBAL_NEGATIVE})
        elif "i2v" in filename: 
            # Updated I2V Template
            data.update({"reference image path": "", "flf image path": ""})
        save_json(path, data)

# --- Initialization ---
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

# --- Sidebar ---
with st.sidebar:
    st.header("📂 Navigator")
    
    new_path = st.text_input("Current Path", value=str(st.session_state.current_dir))
    if new_path != str(st.session_state.current_dir):
        p = Path(new_path)
        if p.exists() and p.is_dir():
            st.session_state.current_dir = p
            st.session_state.config['last_dir'] = str(p)
            save_config(st.session_state.current_dir, st.session_state.config['favorites'])
            st.rerun()

    if st.button("📌 Pin Current Folder"):
        if str(st.session_state.current_dir) not in st.session_state.config['favorites']:
            st.session_state.config['favorites'].append(str(st.session_state.current_dir))
            save_config(st.session_state.current_dir, st.session_state.config['favorites'])
            st.rerun()

    fav_selection = st.radio("Jump to:", ["Select..."] + st.session_state.config['favorites'], index=0, label_visibility="collapsed")
    if fav_selection != "Select..." and fav_selection != str(st.session_state.current_dir):
        st.session_state.current_dir = Path(fav_selection)
        st.rerun()

    st.markdown("---")
    
    st.subheader("🧩 Snippet Library")
    with st.expander("Add New Snippet"):
        snip_name = st.text_input("Name", placeholder="e.g. Cinematic")
        snip_content = st.text_area("Content", placeholder="4k, high quality, dramatic lighting...")
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
    
    json_files = sorted(list(st.session_state.current_dir.glob("*.json")))
    json_files = [f for f in json_files if f.name != ".editor_config.json" and f.name != ".editor_snippets.json"]

    if not json_files:
        if st.button("Generate Generic Templates"):
            generate_templates(st.session_state.current_dir)
            st.rerun()
    
    with st.expander("Create New JSON"):
        new_filename = st.text_input("Filename", placeholder="my_prompt_vace")
        if st.button("Create"):
            if not new_filename.endswith(".json"): new_filename += ".json"
            path = st.session_state.current_dir / new_filename
            data = DEFAULTS.copy()
            if "vace" in new_filename: data.update({"frame_to_skip": 81, "vace schedule": 1, "video file path": ""})
            elif "global" in new_filename: data.update({"video file path": "", "negative": GLOBAL_NEGATIVE})
            elif "i2v" in new_filename: data.update({"reference image path": "", "flf image path": ""})
            save_json(path, data)
            st.rerun()

    selected_file_name = st.radio("Select File", [f.name for f in json_files])

# --- Main Editor Area ---
if selected_file_name:
    file_path = st.session_state.current_dir / selected_file_name
    
    if st.session_state.loaded_file != str(file_path):
        data, mtime = load_json(file_path)
        st.session_state.data_cache = data
        st.session_state.last_mtime = mtime
        st.session_state.loaded_file = str(file_path)
        if 'append_prompt' in st.session_state: del st.session_state.append_prompt
        st.session_state.edit_history_idx = None
    else:
        data = st.session_state.data_cache

    st.title(f"Editing: {selected_file_name}")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        current_prompt_val = data.get("current_prompt", "")
        if 'append_prompt' in st.session_state:
            current_prompt_val = (current_prompt_val.strip() + ", " + st.session_state.append_prompt).strip(', ')
            del st.session_state.append_prompt 
            
        new_prompt = st.text_area("Current Prompt", value=current_prompt_val, height=150)
        new_negative = st.text_area("Negative Prompt", value=data.get("negative", ""), height=100)
        
        st.subheader("LoRAs")
        st.code("<lora::1.0>", language="text")
        
        l_col1, l_col2 = st.columns(2)
        loras = {}
        keys = ["lora 1 high", "lora 1 low", "lora 2 high", "lora 2 low", "lora 3 high", "lora 3 low"]
        for i, k in enumerate(keys):
            with (l_col1 if i % 2 == 0 else l_col2):
                loras[k] = st.text_input(k, value=data.get(k, ""))

        st.subheader("Settings")
        spec_fields = {}
        fields = ["camera", "flf"]
        fname = selected_file_name
        
        if "vace" in fname:
            fields += ["frame_to_skip", "input_a_frames", "input_b_frames", "reference path", "reference switch", "vace schedule", "video file path"]
        elif "global" in fname:
            fields += ["video file path"]
        elif "i2v" in fname:
            # I2V Specific Fields Update
            fields += ["reference image path", "flf image path"]
            
        for f in fields:
            val = data.get(f, DEFAULTS.get(f, ""))
            spec_fields[f] = st.text_input(f, value=str(val))

    with col2:
        st.subheader("Actions")
        
        current_disk_mtime = get_file_mtime(file_path)
        is_conflict = current_disk_mtime > st.session_state.last_mtime
        
        if is_conflict:
            st.error("⚠️ CONFLICT: File changed on disk!")
            c_col1, c_col2 = st.columns(2)
            if c_col1.button("Force Overwrite", type="primary"):
                data["current_prompt"] = new_prompt
                data["negative"] = new_negative
                data.update(loras)
                data.update(spec_fields)
                st.session_state.last_mtime = save_json(file_path, data)
                st.session_state.data_cache = data
                st.toast("Forced overwrite success!", icon="⚠️")
                st.rerun()

            if c_col2.button("Reload File"):
                st.session_state.loaded_file = None
                st.rerun()
        
        else:
            if st.button("💾 Update File", use_container_width=True):
                data["current_prompt"] = new_prompt
                data["negative"] = new_negative
                data.update(loras)
                data.update(spec_fields)
                st.session_state.last_mtime = save_json(file_path, data)
                st.session_state.data_cache = data
                st.toast("File updated successfully!", icon="✅") 

            st.markdown("---")

            archive_note = st.text_input("Archive Note (Optional)", placeholder="e.g. V1 with high motion")
            if st.button("📦 Snapshot to History", use_container_width=True):
                entry = {
                    "prompt": new_prompt, 
                    "negative": new_negative, 
                    "note": archive_note if archive_note else f"Snapshot {len(data.get('prompt_history', [])) + 1}",
                    "loras": loras, 
                    **spec_fields
                }
                if "prompt_history" not in data: data["prompt_history"] = []
                data["prompt_history"].insert(0, entry)
                data.update(entry)
                data["current_prompt"] = new_prompt 
                st.session_state.last_mtime = save_json(file_path, data)
                st.session_state.data_cache = data
                st.toast("Archived & Saved!", icon="📦")
                st.rerun()

        st.markdown("---")

        st.subheader("Media Preview")
        preview_path = None
        # Add flf image path to preview logic
        for k in ["reference path", "video file path", "reference image path", "flf image path"]:
            if spec_fields.get(k):
                preview_path = spec_fields[k]
                break
        
        if preview_path:
            full_prev_path = Path(preview_path) if os.path.isabs(preview_path) else st.session_state.current_dir / preview_path
            if full_prev_path.exists():
                ext = full_prev_path.suffix.lower()
                if ext in ['.mp4', '.avi', '.mov']:
                    st.video(str(full_prev_path))
                else:
                    st.image(str(full_prev_path))
            else:
                st.warning(f"File not found: {preview_path}")
        else:
            st.info("No media path set.")

    # ---------------- HISTORY SECTION ----------------
    st.markdown("---")
    history = data.get("prompt_history", [])
    
    h_head_1, h_head_2 = st.columns([1, 2])
    h_head_1.subheader(f"History ({len(history)})")
    search_term = h_head_2.text_input("🔍 Search History", placeholder="Filter by prompt keyword or note...").lower()

    if history:
        for idx, h in enumerate(history):
            note_text = str(h.get('note', '')).lower()
            prompt_text = str(h.get('prompt', '')).lower()
            if search_term and (search_term not in note_text and search_term not in prompt_text):
                continue

            note_title = h.get('note', 'No Note') or "No Note"
            expander_label = f"#{idx+1}: {note_title}"
            
            with st.container():
                if st.session_state.edit_history_idx == idx:
                    with st.expander(f"📝 EDITING: {note_title}", expanded=True):
                        st.info("Editing History Entry (In-Place)")
                        edit_note = st.text_input("Note", value=h.get('note', ''), key=f"edit_note_{idx}")
                        edit_prompt = st.text_area("Prompt", value=h.get('prompt', ''), height=150, key=f"edit_prompt_{idx}")
                        edit_negative = st.text_area("Negative", value=h.get('negative', ''), height=80, key=f"edit_neg_{idx}")
                        
                        ec1, ec2 = st.columns([1, 4])
                        if ec1.button("💾 Save", key=f"save_edit_{idx}", type="primary"):
                            h['note'] = edit_note
                            h['prompt'] = edit_prompt
                            h['negative'] = edit_negative
                            st.session_state.last_mtime = save_json(file_path, data)
                            st.session_state.data_cache = data
                            st.session_state.edit_history_idx = None
                            st.toast("History entry updated!", icon="✏️")
                            st.rerun()
                            
                        if ec2.button("Cancel", key=f"cancel_edit_{idx}"):
                            st.session_state.edit_history_idx = None
                            st.rerun()
                else:
                    with st.expander(expander_label):
                        col_h1, col_h2 = st.columns([3, 1])
                        
                        with col_h1:
                            st.caption("📝 Prompt")
                            st.text(h.get('prompt', ''))
                            
                            st.caption("🧩 LoRAs & Files")
                            info_dict = {k:v for k,v in h.items() if k not in ['prompt', 'negative', 'note'] and v}
                            if 'loras' in h and isinstance(h['loras'], dict):
                                info_dict.update({k:v for k,v in h['loras'].items() if v})
                                if 'loras' in info_dict: del info_dict['loras']
                            st.json(info_dict, expanded=False)

                        with col_h2:
                            if st.button("Restore", key=f"rest_{idx}", use_container_width=True):
                                if is_conflict:
                                    st.error("Resolve conflict first.")
                                else:
                                    data["current_prompt"] = h.get("prompt", "")
                                    data["negative"] = h.get("negative", "")
                                    if "loras" in h and isinstance(h["loras"], dict):
                                        data.update(h["loras"])
                                    for k, v in h.items():
                                        if k not in ["note", "prompt", "loras", "negative"]:
                                            data[k] = v
                                    
                                    st.session_state.last_mtime = save_json(file_path, data)
                                    st.session_state.data_cache = data
                                    st.toast("Restored settings from history!", icon="⏪")
                                    st.rerun()
                            
                            if st.button("✏️ Edit", key=f"open_edit_{idx}", use_container_width=True):
                                st.session_state.edit_history_idx = idx
                                st.rerun()

                            if st.button("Delete", key=f"del_{idx}", use_container_width=True):
                                if is_conflict:
                                    st.error("Resolve conflict first.")
                                else:
                                    data["prompt_history"].pop(idx)
                                    st.session_state.last_mtime = save_json(file_path, data)
                                    st.session_state.data_cache = data
                                    st.rerun()
