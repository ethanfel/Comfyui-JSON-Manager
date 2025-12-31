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
    "input_a_frames": 0,
    "input_b_frames": 0,
    "reference path": "",
    "reference switch": 1,
    "vace schedule": 1,
    "video file path": "",
    "reference image path": "",
    "flf image path": "",
    
    # --- PROMPTS ---
    "general_prompt": "",
    "general_negative": "Vivid tones, overexposed, static, blurry details, subtitles, style, artwork, painting, picture, still image, overall gray, worst quality, low quality, JPEG compression artifacts, ugly, deformed, extra fingers, poorly drawn hands, poorly drawn face, distorted, disfigured, malformed limbs, fused fingers, unmoving frame, cluttered background, three legs,",
    "current_prompt": "",
    "negative": "",
    
    # --- LORAS ---
    "lora 1 high": "", "lora 1 low": "",
    "lora 2 high": "", "lora 2 low": "",
    "lora 3 high": "", "lora 3 low": "",
    "prompt_history": []
}

GENERIC_TEMPLATES = ["prompt_i2v.json", "prompt_vace_extend.json", "batch_i2v.json", "batch_vace.json"]

# --- Helper Functions ---
def load_config():
    if CONFIG_FILE.exists():
        try: 
            with open(CONFIG_FILE, 'r') as f: 
                return json.load(f)
        except: 
            pass
    return {"last_dir": str(Path.cwd()), "favorites": []}

def save_config(current_dir, favorites):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"last_dir": str(current_dir), "favorites": favorites}, f, indent=4)

def load_snippets():
    if SNIPPETS_FILE.exists():
        try: 
            with open(SNIPPETS_FILE, 'r') as f: 
                return json.load(f)
        except: 
            pass
    return {}

def save_snippets(snippets):
    with open(SNIPPETS_FILE, 'w') as f:
        json.dump(snippets, f, indent=4)

def get_file_mtime(path):
    if path.exists(): return os.path.getmtime(path)
    return 0

def load_json(path):
    if not path.exists(): return DEFAULTS.copy(), 0
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return data, get_file_mtime(path)
    except:
        return DEFAULTS.copy(), 0

def save_json(path, data):
    if path.exists():
        try:
            with open(path, 'r') as f:
                existing = json.load(f)
            if isinstance(existing, dict) and isinstance(data, dict):
                existing.update(data)
                data = existing
        except: 
            pass
        
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)
    return get_file_mtime(path)

def generate_templates(directory):
    for filename in GENERIC_TEMPLATES:
        path = directory / filename
        if "batch" in filename:
            data = {"batch_data": []} 
        else:
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
if 'snippets' not in st.session_state: st.session_state.snippets = load_snippets()
if 'loaded_file' not in st.session_state: st.session_state.loaded_file = None
if 'last_mtime' not in st.session_state: st.session_state.last_mtime = 0
if 'edit_history_idx' not in st.session_state: st.session_state.edit_history_idx = None
if 'single_editor_cache' not in st.session_state: st.session_state.single_editor_cache = DEFAULTS.copy()

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

    # File Selector
    if 'file_selector' not in st.session_state:
        st.session_state.file_selector = json_files[0].name if json_files else None

    if st.session_state.file_selector not in [f.name for f in json_files] and json_files:
        st.session_state.file_selector = json_files[0].name

    selected_file_name = st.radio("Select File", [f.name for f in json_files], key="file_selector")

# --- Load Logic ---
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

    is_batch_file = "batch_data" in data or isinstance(data, list)
    
    # --- TABS ---
    tab_single, tab_batch = st.tabs(["📝 Single Editor", "🚀 Batch Processor"])

    # ==============================================================================
    # TAB 1: SINGLE EDITOR
    # ==============================================================================
    with tab_single:
        if is_batch_file:
            st.info("This is a batch file. Switch to the 'Batch Processor' tab.")
        else:
            col1, col2 = st.columns([2, 1])
            with col1:
                with st.expander("🌍 General Prompts (Global Layer)", expanded=False):
                    gen_prompt = st.text_area("General Prompt", value=data.get("general_prompt", ""), height=100)
                    gen_negative = st.text_area("General Negative", value=data.get("general_negative", DEFAULTS["general_negative"]), height=100)

                st.write("📝 **Specific Prompts**")
                current_prompt_val = data.get("current_prompt", "")
                if 'append_prompt' in st.session_state:
                    current_prompt_val = (current_prompt_val.strip() + ", " + st.session_state.append_prompt).strip(', ')
                    del st.session_state.append_prompt 
                    
                new_prompt = st.text_area("Specific Prompt", value=current_prompt_val, height=150)
                new_negative = st.text_area("Specific Negative", value=data.get("negative", ""), height=100)

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
                spec_fields["camera"] = st.text_input("camera", value=str(data.get("camera", DEFAULTS["camera"])))
                spec_fields["flf"] = st.text_input("flf", value=str(data.get("flf", DEFAULTS["flf"])))
                
                if "vace" in selected_file_name:
                    spec_fields["frame_to_skip"] = st.number_input("frame_to_skip", value=int(data.get("frame_to_skip", 81)))
                    spec_fields["input_a_frames"] = st.number_input("input_a_frames", value=int(data.get("input_a_frames", 0)))
                    spec_fields["input_b_frames"] = st.number_input("input_b_frames", value=int(data.get("input_b_frames", 0)))
                    spec_fields["reference switch"] = st.number_input("reference switch", value=int(data.get("reference switch", 1)))
                    spec_fields["vace schedule"] = st.number_input("vace schedule", value=int(data.get("vace schedule", 1)))
                    for f in ["reference path", "video file path", "reference image path"]:
                         spec_fields[f] = st.text_input(f, value=str(data.get(f, "")))
                elif "i2v" in selected_file_name:
                    for f in ["reference image path", "flf image path", "video file path"]:
                        spec_fields[f] = st.text_input(f, value=str(data.get(f, "")))

            with col2:
                # Capture State
                current_state = {
                    "general_prompt": gen_prompt, "general_negative": gen_negative,
                    "current_prompt": new_prompt, "negative": new_negative,
                    "seed": new_seed, **loras, **spec_fields
                }
                st.session_state.single_editor_cache = current_state

                st.subheader("Actions")
                current_disk_mtime = get_file_mtime(file_path)
                is_conflict = current_disk_mtime > st.session_state.last_mtime
                
                if is_conflict:
                    st.error("⚠️ CONFLICT: Disk change detected!")
                    c1, c2 = st.columns(2)
                    if c1.button("Force Save"):
                        data.update(current_state)
                        st.session_state.last_mtime = save_json(file_path, data)
                        st.session_state.data_cache = data
                        st.toast("Saved!", icon="⚠️")
                        st.rerun()
                    if c2.button("Reload"):
                        st.session_state.loaded_file = None
                        st.rerun()
                else:
                    if st.button("💾 Update File", use_container_width=True):
                        data.update(current_state)
                        st.session_state.last_mtime = save_json(file_path, data)
                        st.session_state.data_cache = data
                        st.toast("Updated!", icon="✅") 

                    st.markdown("---")
                    
                    archive_note = st.text_input("Archive Note")
                    if st.button("📦 Snapshot to History", use_container_width=True):
                        entry = {
                            "note": archive_note if archive_note else f"Snapshot",
                            **current_state
                        }
                        if "prompt_history" not in data: data["prompt_history"] = []
                        data["prompt_history"].insert(0, entry)
                        data.update(entry)
                        st.session_state.last_mtime = save_json(file_path, data)
                        st.session_state.data_cache = data
                        st.toast("Archived!", icon="📦")
                        st.rerun()

                st.markdown("---")
                st.subheader("History")
                history = data.get("prompt_history", [])
                for idx, h in enumerate(history):
                    with st.expander(f"#{idx+1}: {h.get('note', 'No Note')}"):
                        if st.button(f"Restore #{idx+1}", key=f"rest_{idx}"):
                            data.update(h)
                            st.session_state.last_mtime = save_json(file_path, data)
                            st.rerun()

    # ==============================================================================
    # TAB 2: BATCH PROCESSOR
    # ==============================================================================
    with tab_batch:
        if not is_batch_file:
            st.warning("This is a Single file. To use Batch mode, create a copy.")
            
            if st.button("✨ Create Batch Copy (Preserves Original)"):
                new_name = f"batch_{selected_file_name}"
                new_path = st.session_state.current_dir / new_name
                
                if new_path.exists():
                    st.error(f"File {new_name} already exists!")
                else:
                    first_item = data.copy()
                    if "prompt_history" in first_item: del first_item["prompt_history"]
                    first_item["sequence_number"] = 1
                    new_data = {"batch_data": [first_item], "prompt_history": data.get("prompt_history", [])}
                    save_json(new_path, new_data)
                    st.toast(f"Created {new_name}", icon="✨")
                    st.session_state.file_selector = new_name
                    st.rerun()
        else:
            batch_list = data.get("batch_data", [])
            
            st.subheader("Add New Sequence")
            
            add_c1, add_c2 = st.columns(2)
            with add_c1:
                file_options = [f.name for f in json_files]
                default_idx = 0
                if selected_file_name in file_options: 
                    default_idx = file_options.index(selected_file_name)
                import_source_name = st.selectbox("Source File:", file_options, index=default_idx)
                source_data_imported, _ = load_json(st.session_state.current_dir / import_source_name)

            with add_c2:
                source_history = source_data_imported.get("prompt_history", [])
                hist_options = []
                if source_history:
                    hist_options = [f"#{i+1}: {h.get('note', 'No Note')} ({h.get('prompt', '')[:15]}...)" for i, h in enumerate(source_history)]
                    selected_hist_str = st.selectbox("History Entry:", hist_options)
                else:
                    st.caption(f"No history in {import_source_name}.")
                    selected_hist_str = None

            btn_c1, btn_c2, btn_c3 = st.columns(3)
            
            if btn_c1.button("➕ Add Empty", use_container_width=True):
                new_seq = DEFAULTS.copy()
                if "prompt_history" in new_seq: del new_seq["prompt_history"]
                max_seq = 0
                for s in batch_list:
                    if "sequence_number" in s: max_seq = max(max_seq, int(s["sequence_number"]))
                new_seq["sequence_number"] = max_seq + 1
                batch_list.append(new_seq)
                data["batch_data"] = batch_list
                save_json(file_path, data)
                st.rerun()

            if btn_c2.button("➕ From File", use_container_width=True, help=f"Copy current state from {import_source_name}"):
                new_seq = DEFAULTS.copy()
                src_flat = source_data_imported
                if "batch_data" in source_data_imported and source_data_imported["batch_data"]:
                    src_flat = source_data_imported["batch_data"][0]
                new_seq.update(src_flat)
                if "prompt_history" in new_seq: del new_seq["prompt_history"]
                max_seq = 0
                for s in batch_list:
                    if "sequence_number" in s: max_seq = max(max_seq, int(s["sequence_number"]))
                new_seq["sequence_number"] = max_seq + 1
                batch_list.append(new_seq)
                data["batch_data"] = batch_list
                save_json(file_path, data)
                st.rerun()

            if btn_c3.button("➕ From History", use_container_width=True, disabled=not source_history):
                if selected_hist_str:
                    hist_idx = int(selected_hist_str.split(":")[0].replace("#", "")) - 1
                    h_item = source_history[hist_idx]
                    new_seq = DEFAULTS.copy()
                    new_seq.update(h_item)
                    if "loras" in h_item and isinstance(h_item["loras"], dict):
                        new_seq.update(h_item["loras"])
                    for k in ["prompt_history", "note", "loras"]:
                        if k in new_seq: del new_seq[k]
                    max_seq = 0
                    for s in batch_list:
                        if "sequence_number" in s: max_seq = max(max_seq, int(s["sequence_number"]))
                    new_seq["sequence_number"] = max_seq + 1
                    batch_list.append(new_seq)
                    data["batch_data"] = batch_list
                    save_json(file_path, data)
                    st.rerun()

            st.markdown("---")
            st.info(f"Batch contains {len(batch_list)} sequences.")
            
            for i, seq in enumerate(batch_list):
                seq_num = seq.get("sequence_number", i+1)
                
                with st.expander(f"🎬 Sequence #{seq_num} : {seq.get('current_prompt', '')[:40]}...", expanded=False):
                    
                    b_col1, b_col2, b_col3 = st.columns([1, 1, 2])
                    
                    if b_col1.button(f"📥 Copy from {import_source_name}", key=f"copy_src_{i}"):
                        updated_seq = DEFAULTS.copy()
                        src_flat = source_data_imported
                        if "batch_data" in source_data_imported and source_data_imported["batch_data"]:
                            src_flat = source_data_imported["batch_data"][0]
                        updated_seq.update(src_flat)
                        updated_seq["sequence_number"] = seq_num
                        if "prompt_history" in updated_seq: del updated_seq["prompt_history"]
                        batch_list[i] = updated_seq
                        data["batch_data"] = batch_list
                        save_json(file_path, data)
                        st.toast(f"Updated from {import_source_name}!", icon="📥")
                        st.rerun()

                    if b_col2.button("↖️ Promote to Single", key=f"prom_seq_{i}"):
                        new_single_data = seq.copy()
                        new_single_data["prompt_history"] = data.get("prompt_history", [])
                        if "sequence_number" in new_single_data: del new_single_data["sequence_number"]
                        st.session_state.last_mtime = save_json(file_path, new_single_data)
                        st.session_state.data_cache = new_single_data
                        st.toast("Converted to Single!", icon="✅")
                        st.rerun()

                    if b_col3.button("🗑️ Remove", key=f"del_seq_{i}"):
                        batch_list.pop(i)
                        data["batch_data"] = batch_list
                        save_json(file_path, data)
                        st.rerun()

                    st.markdown("---")
                    
                    # --- BATCH EDIT LAYOUT ---
                    
                    # 1. PROMPTS
                    sb_col1, sb_col2 = st.columns([2, 1])
                    with sb_col1:
                        seq["general_prompt"] = st.text_area("General P", value=seq.get("general_prompt", ""), height=60, key=f"b_gp_{i}")
                        seq["general_negative"] = st.text_area("General N", value=seq.get("general_negative", ""), height=60, key=f"b_gn_{i}")
                        seq["current_prompt"] = st.text_area("Specific P", value=seq.get("current_prompt", ""), height=100, key=f"b_sp_{i}")
                        seq["negative"] = st.text_area("Specific N", value=seq.get("negative", ""), height=60, key=f"b_sn_{i}")
                    
                    with sb_col2:
                        seq["sequence_number"] = st.number_input("Seq Num", value=int(seq_num), key=f"b_seqn_{i}")
                        seq["seed"] = st.number_input("Seed", value=int(seq.get("seed", 0)), key=f"b_seed_{i}")
                        seq["camera"] = st.text_input("Camera", value=seq.get("camera", ""), key=f"b_cam_{i}")
                        seq["flf"] = st.text_input("FLF", value=str(seq.get("flf", DEFAULTS["flf"])), key=f"b_flf_{i}")
                        
                        # Dynamic Paths & Params
                        if "video file path" in seq or "vace" in selected_file_name:
                            seq["video file path"] = st.text_input("Video Path", value=seq.get("video file path", ""), key=f"b_vid_{i}")
                            # VACE Params
                            with st.expander("VACE Settings"):
                                seq["frame_to_skip"] = st.number_input("Skip", value=int(seq.get("frame_to_skip", 81)), key=f"b_fts_{i}")
                                seq["input_a_frames"] = st.number_input("In A", value=int(seq.get("input_a_frames", 0)), key=f"b_ia_{i}")
                                seq["input_b_frames"] = st.number_input("In B", value=int(seq.get("input_b_frames", 0)), key=f"b_ib_{i}")
                                seq["reference switch"] = st.number_input("Switch", value=int(seq.get("reference switch", 1)), key=f"b_rsw_{i}")
                                seq["vace schedule"] = st.number_input("Sched", value=int(seq.get("vace schedule", 1)), key=f"b_vsc_{i}")
                                seq["reference path"] = st.text_input("Ref Path", value=seq.get("reference path", ""), key=f"b_rp_{i}")
                                seq["reference image path"] = st.text_input("Ref Img", value=seq.get("reference image path", ""), key=f"b_rip_{i}")

                        if "i2v" in selected_file_name and "vace" not in selected_file_name:
                            seq["reference image path"] = st.text_input("Ref Img", value=seq.get("reference image path", ""), key=f"b_ref_{i}")
                            seq["flf image path"] = st.text_input("FLF Img", value=seq.get("flf image path", ""), key=f"b_flfi_{i}")

                    # 2. LORAS EXPANDER
                    with st.expander("LoRA Settings"):
                        bl_c1, bl_c2 = st.columns(2)
                        lkeys = ["lora 1 high", "lora 1 low", "lora 2 high", "lora 2 low", "lora 3 high", "lora 3 low"]
                        for li, lk in enumerate(lkeys):
                            with (bl_c1 if li % 2 == 0 else bl_c2):
                                seq[lk] = st.text_input(lk, value=seq.get(lk, ""), key=f"b_{lk}_{i}")

            st.markdown("---")
            if st.button("💾 Save Batch Changes"):
                data["batch_data"] = batch_list
                st.session_state.last_mtime = save_json(file_path, data)
                st.session_state.data_cache = data
                st.toast("Batch saved!", icon="🚀")
