import streamlit as st
import json
import os
import time
import random
from pathlib import Path

# --- Configuration ---
CONFIG_FILE = Path(".editor_config.json")
SNIPPETS_FILE = Path(".editor_snippets.json")

st.set_page_config(layout="wide", page_title="AI Settings Manager")

# Defaults
DEFAULTS = {
    "camera": "Camera stand still. Motion starts immediately.",
    "flf": 0,
    "seed": 0,
    "frame_to_skip": 81,
    "input_a_frames": "",
    "input_b_frames": "",
    "reference path": "",
    "reference switch": 1,
    "vace schedule": 1,
    "video file path": "",
    "reference image path": "",
    "flf image path": "",
    
    # --- PROMPTS ---
    "general_prompt": "",      # NEW: The global layer
    "general_negative": "Vivid tones, overexposed, static, blurry details, subtitles, style, artwork, painting, picture, still image, overall gray, worst quality, low quality, JPEG compression artifacts, ugly, deformed, extra fingers, poorly drawn hands, poorly drawn face, distorted, disfigured, malformed limbs, fused fingers, unmoving frame, cluttered background, three legs,",
    "current_prompt": "",      # The specific layer
    "negative": "",            # The specific layer
    
    # --- LORAS ---
    "lora 1 high": "", "lora 1 low": "",
    "lora 2 high": "", "lora 2 low": "",
    "lora 3 high": "", "lora 3 low": "",
    "prompt_history": []
}

# Only these two types exist now
GENERIC_TEMPLATES = ["prompt_i2v.json", "prompt_vace_extend.json"]

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
        elif "i2v" in filename: 
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
        if st.button("Generate Templates (I2V / VACE)"):
            generate_templates(st.session_state.current_dir)
            st.rerun()
    
    with st.expander("Create New JSON"):
        new_filename = st.text_input("Filename", placeholder="my_prompt_vace")
        if st.button("Create"):
            if not new_filename.endswith(".json"): new_filename += ".json"
            path = st.session_state.current_dir / new_filename
            data = DEFAULTS.copy()
            if "vace" in new_filename: data.update({"frame_to_skip": 81, "vace schedule": 1, "video file path": ""})
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
        if 'rand_seed' in st.session_state: del st.session_state.rand_seed
        st.session_state.edit_history_idx = None
    else:
        data = st.session_state.data_cache

    st.title(f"Editing: {selected_file_name}")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # --- GENERAL SECTION (Collapsible) ---
        with st.expander("🌍 General Prompts (Global Layer)", expanded=False):
            gen_prompt = st.text_area("General Prompt", value=data.get("general_prompt", ""), height=100)
            gen_negative = st.text_area("General Negative", value=data.get("general_negative", DEFAULTS["general_negative"]), height=100)

        # --- SPECIFIC SECTION ---
        st.write("📝 **Specific Prompts**")
        current_prompt_val = data.get("current_prompt", "")
        if 'append_prompt' in st.session_state:
            current_prompt_val = (current_prompt_val.strip() + ", " + st.session_state.append_prompt).strip(', ')
            del st.session_state.append_prompt 
            
        new_prompt = st.text_area("Specific Prompt", value=current_prompt_val, height=150)
        new_negative = st.text_area("Specific Negative", value=data.get("negative", ""), height=100)

        # --- SEED ---
        col_seed_val, col_seed_btn = st.columns([4, 1])
        with col_seed_btn:
            st.write("") 
            st.write("") 
            if st.button("🎲 Randomize"):
                st.session_state.rand_seed = random.randint(0, 999999999999)
                st.rerun()
        
        with col_seed_val:
            seed_val = st.session_state.get('rand_seed', int(data.get("seed", 0)))
            new_seed = st.number_input("Seed", value=seed_val, step=1, min_value=0, format="%d")
            data["seed"] = new_seed 
        
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
        elif "i2v" in fname:
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
                data.update({
                    "current_prompt": new_prompt, "negative": new_negative,
                    "general_prompt": gen_prompt, "general_negative": gen_negative,
                    "seed": new_seed
                })
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
                data.update({
                    "current_prompt": new_prompt, "negative": new_negative,
                    "general_prompt": gen_prompt, "general_negative": gen_negative,
                    "seed": new_seed
                })
                data.update(loras)
                data.update(spec_fields)
                st.session_state.last_mtime = save_json(file_path, data)
                st.session_state.data_cache = data
                st.toast("File updated successfully!", icon="✅") 

            st.markdown("---")

            archive_note = st.text_input("Archive Note (Optional)", placeholder="e.g. V1 with high motion")
            if st.button("📦 Snapshot to History", use_container_width=True):
                entry = {
                    "general_prompt": gen_prompt, "general_negative": gen_negative,
                    "prompt": new_prompt, "negative": new_negative, 
                    "seed": new_seed,
                    "note": archive_note if archive_note else f"Snapshot {len(data.get('prompt_history', [])) + 1}",
                    "loras": loras, 
                    **spec_fields
                }
                if "prompt_history" not in data: data["prompt_history"] = []
                data["prompt_history"].insert(0, entry)
                # Update main state too
                data.update(entry)
                data["current_prompt"] = new_prompt
                
                st.session_state.last_mtime = save_json(file_path, data)
                st.session_state.data_cache = data
                st.toast("Archived & Saved!", icon="📦")
                st.rerun()

        st.markdown("---")

        st.subheader("Media Preview")
        preview_path = None
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
    search_term = h_head_2.text_input("🔍 Search History", placeholder="Filter...").lower()

    if history:
        for idx, h in enumerate(history):
            note_text = str(h.get('note', '')).lower()
            if search_term and search_term not in note_text: continue

            note_title = h.get('note', 'No Note') or "No Note"
            expander_label = f"#{idx+1}: {note_title}"
            
            with st.container():
                if st.session_state.edit_history_idx == idx:
                    with st.expander(f"📝 EDITING: {note_title}", expanded=True):
                        st.info("Editing History Entry")
                        edit_note = st.text_input("Note", value=h.get('note', ''), key=f"edit_note_{idx}")
                        
                        ec_seed1, ec_seed2 = st.columns([1, 3])
                        edit_seed = ec_seed1.number_input("Seed", value=int(h.get('seed', 0)), step=1, key=f"edit_seed_{idx}")
                        
                        # EDIT ALL PROMPTS
                        st.caption("General Layer")
                        edit_gen_p = st.text_area("Gen Prompt", value=h.get('general_prompt', ''), height=60, key=f"egp_{idx}")
                        edit_gen_n = st.text_area("Gen Negative", value=h.get('general_negative', ''), height=60, key=f"egn_{idx}")
                        
                        st.caption("Specific Layer")
                        edit_prompt = st.text_area("Prompt", value=h.get('prompt', ''), height=100, key=f"edit_prompt_{idx}")
                        edit_negative = st.text_area("Negative", value=h.get('negative', ''), height=60, key=f"edit_neg_{idx}")
                        
                        ec1, ec2 = st.columns([1, 4])
                        if ec1.button("💾 Save", key=f"save_edit_{idx}", type="primary"):
                            h.update({
                                'note': edit_note, 'seed': edit_seed,
                                'general_prompt': edit_gen_p, 'general_negative': edit_gen_n,
                                'prompt': edit_prompt, 'negative': edit_negative
                            })
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
                            st.caption(f"📝 Prompts (Seed: {h.get('seed', 0)})")
                            # Show combined snippet
                            st.text(f"GEN: {h.get('general_prompt', '')[:50]}...\nSPEC: {h.get('prompt', '')[:50]}...")
                            
                            st.caption("🧩 LoRAs & Files")
                            info_dict = {k:v for k,v in h.items() if k not in ['prompt', 'negative', 'general_prompt', 'general_negative', 'note', 'seed'] and v}
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
                                    data["general_prompt"] = h.get("general_prompt", "")
                                    data["general_negative"] = h.get("general_negative", "")
                                    data["seed"] = int(h.get("seed", 0))
                                    
                                    if "loras" in h and isinstance(h["loras"], dict):
                                        data.update(h["loras"])
                                    for k, v in h.items():
                                        if k not in ["note", "prompt", "loras", "negative", "seed", "general_prompt", "general_negative"]:
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
