import streamlit as st
import random
import copy
from utils import DEFAULTS, save_json, load_json
from history_tree import HistoryTree 

def create_batch_callback(original_filename, current_data, current_dir):
    new_name = f"batch_{original_filename}"
    new_path = current_dir / new_name
    
    if new_path.exists():
        st.toast(f"File {new_name} already exists!", icon="⚠️")
        return

    first_item = current_data.copy()
    if "prompt_history" in first_item: del first_item["prompt_history"]
    if "history_tree" in first_item: del first_item["history_tree"] 
    
    first_item["sequence_number"] = 1
    
    new_data = {
        "batch_data": [first_item], 
        "history_tree": {},
        "prompt_history": [] 
    }
    
    save_json(new_path, new_data)
    st.toast(f"Created {new_name}", icon="✨")
    st.session_state.file_selector = new_name


def render_batch_processor(data, file_path, json_files, current_dir, selected_file_name):
    is_batch_file = "batch_data" in data or isinstance(data, list)
    
    if not is_batch_file:
        st.warning("This is a Single file. To use Batch mode, create a copy.")
        st.button("✨ Create Batch Copy", on_click=create_batch_callback, args=(selected_file_name, data, current_dir))
        return

    if 'restored_indicator' in st.session_state and st.session_state.restored_indicator:
        st.info(f"📍 Editing Restored Version: **{st.session_state.restored_indicator}**")

    batch_list = data.get("batch_data", [])
    
    # --- ADD NEW SEQUENCE AREA ---
    st.subheader("Add New Sequence")
    ac1, ac2 = st.columns(2)
    
    with ac1:
        file_options = [f.name for f in json_files]
        d_idx = file_options.index(selected_file_name) if selected_file_name in file_options else 0
        src_name = st.selectbox("Source File:", file_options, index=d_idx, key="batch_src_file")
        src_data, _ = load_json(current_dir / src_name)

    with ac2:
        src_hist = src_data.get("prompt_history", [])
        h_opts = [f"#{i+1}: {h.get('note', 'No Note')} ({h.get('prompt', '')[:15]}...)" for i, h in enumerate(src_hist)] if src_hist else []
        sel_hist = st.selectbox("History Entry (Legacy):", h_opts, key="batch_src_hist")

    bc1, bc2, bc3 = st.columns(3)
    
    def add_sequence(new_item):
        max_seq = 0
        for s in batch_list:
            if "sequence_number" in s: max_seq = max(max_seq, int(s["sequence_number"]))
        new_item["sequence_number"] = max_seq + 1
        
        for k in ["prompt_history", "history_tree", "note", "loras"]: 
            if k in new_item: del new_item[k]
        
        batch_list.append(new_item)
        data["batch_data"] = batch_list
        save_json(file_path, data)
        st.session_state.ui_reset_token += 1
        st.rerun()

    if bc1.button("➕ Add Empty", use_container_width=True):
        add_sequence(DEFAULTS.copy())

    if bc2.button("➕ From File", use_container_width=True, help=f"Copy {src_name}"):
        item = DEFAULTS.copy()
        flat = src_data["batch_data"][0] if "batch_data" in src_data and src_data["batch_data"] else src_data
        item.update(flat)
        add_sequence(item)

    if bc3.button("➕ From History", use_container_width=True, disabled=not src_hist):
        if sel_hist:
            idx = int(sel_hist.split(":")[0].replace("#", "")) - 1
            item = DEFAULTS.copy()
            h_item = src_hist[idx]
            item.update(h_item)
            if "loras" in h_item and isinstance(h_item["loras"], dict):
                item.update(h_item["loras"])
            add_sequence(item)

    # --- RENDER LIST ---
    st.markdown("---")
    st.info(f"Batch contains {len(batch_list)} sequences.")

    lora_keys = ["lora 1 high", "lora 1 low", "lora 2 high", "lora 2 low", "lora 3 high", "lora 3 low"]
    standard_keys = {
        "general_prompt", "general_negative", "current_prompt", "negative", "prompt", "seed",
        "camera", "flf", "sequence_number"
    }
    standard_keys.update(lora_keys)
    standard_keys.update([
        "frame_to_skip", "input_a_frames", "input_b_frames", "reference switch", "vace schedule", 
        "reference path", "video file path", "reference image path", "flf image path"
    ])

    for i, seq in enumerate(batch_list):
        seq_num = seq.get("sequence_number", i+1)
        prefix = f"{selected_file_name}_seq{i}_v{st.session_state.ui_reset_token}" 

        with st.expander(f"🎬 Sequence #{seq_num}", expanded=False):
            # --- NEW: ACTION ROW WITH CLONING ---
            act_c1, act_c2, act_c3, act_c4 = st.columns([1.2, 1.8, 1.2, 0.5])
            
            # 1. Copy Source
            with act_c1:
                if st.button(f"📥 Copy {src_name}", key=f"{prefix}_copy", use_container_width=True):
                    item = DEFAULTS.copy()
                    flat = src_data["batch_data"][0] if "batch_data" in src_data and src_data["batch_data"] else src_data
                    item.update(flat)
                    item["sequence_number"] = seq_num
                    for k in ["prompt_history", "history_tree"]: 
                        if k in item: del item[k]
                    batch_list[i] = item
                    data["batch_data"] = batch_list
                    save_json(file_path, data)
                    st.session_state.ui_reset_token += 1 
                    st.toast("Copied!", icon="📥")
                    st.rerun()

            # 2. Cloning Tools (Next / End)
            with act_c2:
                cl_1, cl_2 = st.columns(2)
                
                # Clone Next
                if cl_1.button("👯 Next", key=f"{prefix}_c_next", help="Clone and insert below", use_container_width=True):
                    new_seq = seq.copy()
                    # Calculate new max sequence number
                    max_sn = 0
                    for s in batch_list: max_sn = max(max_sn, int(s.get("sequence_number", 0)))
                    new_seq["sequence_number"] = max_sn + 1
                    
                    batch_list.insert(i + 1, new_seq)
                    data["batch_data"] = batch_list
                    save_json(file_path, data)
                    st.session_state.ui_reset_token += 1
                    st.toast("Cloned to Next!", icon="👯")
                    st.rerun()

                # Clone End
                if cl_2.button("⏬ End", key=f"{prefix}_c_end", help="Clone and add to bottom", use_container_width=True):
                    new_seq = seq.copy()
                    max_sn = 0
                    for s in batch_list: max_sn = max(max_sn, int(s.get("sequence_number", 0)))
                    new_seq["sequence_number"] = max_sn + 1
                    
                    batch_list.append(new_seq)
                    data["batch_data"] = batch_list
                    save_json(file_path, data)
                    st.session_state.ui_reset_token += 1
                    st.toast("Cloned to End!", icon="⏬")
                    st.rerun()

            # 3. Promote
            with act_c3:
                if st.button("↖️ Promote", key=f"{prefix}_prom", help="Save as Single File", use_container_width=True):
                    single_data = seq.copy()
                    single_data["prompt_history"] = data.get("prompt_history", [])
                    single_data["history_tree"] = data.get("history_tree", {})
                    if "sequence_number" in single_data: del single_data["sequence_number"]
                    save_json(file_path, single_data)
                    st.toast("Converted to Single!", icon="✅")
                    st.rerun()

            # 4. Remove
            with act_c4:
                if st.button("🗑️", key=f"{prefix}_del", use_container_width=True):
                    batch_list.pop(i)
                    data["batch_data"] = batch_list
                    save_json(file_path, data)
                    st.rerun()

            st.markdown("---")
            c1, c2 = st.columns([2, 1])
            with c1:
                seq["general_prompt"] = st.text_area("General Prompt", value=seq.get("general_prompt", ""), height=60, key=f"{prefix}_gp")
                seq["general_negative"] = st.text_area("General Negative", value=seq.get("general_negative", ""), height=60, key=f"{prefix}_gn")
                seq["current_prompt"] = st.text_area("Specific Prompt", value=seq.get("current_prompt", ""), height=100, key=f"{prefix}_sp")
                seq["negative"] = st.text_area("Specific Negative", value=seq.get("negative", ""), height=60, key=f"{prefix}_sn")
            
            with c2:
                seq["sequence_number"] = st.number_input("Sequence Number", value=int(seq_num), key=f"{prefix}_sn_val")
                
                s_row1, s_row2 = st.columns([3, 1])
                seed_key = f"{prefix}_seed"
                with s_row2:
                    st.write("")
                    st.write("")
                    if st.button("🎲", key=f"{prefix}_rand"):
                        st.session_state[seed_key] = random.randint(0, 999999999999)
                        st.rerun()
                with s_row1:
                    current_seed = st.session_state.get(seed_key, int(seq.get("seed", 0)))
                    val = st.number_input("Seed", value=current_seed, key=seed_key)
                    seq["seed"] = val

                seq["camera"] = st.text_input("Camera", value=seq.get("camera", ""), key=f"{prefix}_cam")
                seq["flf"] = st.text_input("FLF", value=str(seq.get("flf", DEFAULTS["flf"])), key=f"{prefix}_flf")
                
                if "video file path" in seq or "vace" in selected_file_name:
                    seq["video file path"] = st.text_input("Video File Path", value=seq.get("video file path", ""), key=f"{prefix}_vid")
                    with st.expander("VACE Settings"):
                        # --- UPDATED: Full labels for VACE settings ---
                        seq["frame_to_skip"] = st.number_input("Frame to Skip", value=int(seq.get("frame_to_skip", 81)), key=f"{prefix}_fts")
                        seq["input_a_frames"] = st.number_input("Input A Frames", value=int(seq.get("input_a_frames", 0)), key=f"{prefix}_ia")
                        seq["input_b_frames"] = st.number_input("Input B Frames", value=int(seq.get("input_b_frames", 0)), key=f"{prefix}_ib")
                        seq["reference switch"] = st.number_input("Reference Switch", value=int(seq.get("reference switch", 1)), key=f"{prefix}_rsw")
                        seq["vace schedule"] = st.number_input("VACE Schedule", value=int(seq.get("vace schedule", 1)), key=f"{prefix}_vsc")
                        seq["reference path"] = st.text_input("Reference Path", value=seq.get("reference path", ""), key=f"{prefix}_rp")
                        seq["reference image path"] = st.text_input("Reference Image Path", value=seq.get("reference image path", ""), key=f"{prefix}_rip")
                
                if "i2v" in selected_file_name and "vace" not in selected_file_name:
                    # --- UPDATED: Full labels for I2V settings ---
                    seq["reference image path"] = st.text_input("Reference Image Path", value=seq.get("reference image path", ""), key=f"{prefix}_ri2")
                    seq["flf image path"] = st.text_input("FLF Image Path", value=seq.get("flf image path", ""), key=f"{prefix}_flfi")

            # --- LoRA Settings ---
            with st.expander("💊 LoRA Settings"):
                lc1, lc2, lc3 = st.columns(3)
                with lc1:
                    seq["lora 1 high"] = st.text_input("LoRA 1 Name", value=seq.get("lora 1 high", ""), key=f"{prefix}_l1h")
                    seq["lora 1 low"] = st.text_input("LoRA 1 Strength", value=str(seq.get("lora 1 low", "")), key=f"{prefix}_l1l")
                with lc2:
                    seq["lora 2 high"] = st.text_input("LoRA 2 Name", value=seq.get("lora 2 high", ""), key=f"{prefix}_l2h")
                    seq["lora 2 low"] = st.text_input("LoRA 2 Strength", value=str(seq.get("lora 2 low", "")), key=f"{prefix}_l2l")
                with lc3:
                    seq["lora 3 high"] = st.text_input("LoRA 3 Name", value=seq.get("lora 3 high", ""), key=f"{prefix}_l3h")
                    seq["lora 3 low"] = st.text_input("LoRA 3 Strength", value=str(seq.get("lora 3 low", "")), key=f"{prefix}_l3l")

            # --- CUSTOM PARAMETERS ---
            st.markdown("---")
            st.caption("🔧 Custom Parameters")
            
            custom_keys = [k for k in seq.keys() if k not in standard_keys]
            keys_to_remove = []

            if custom_keys:
                for k in custom_keys:
                    ck1, ck2, ck3 = st.columns([1, 2, 0.5])
                    ck1.text_input("Key", value=k, disabled=True, key=f"{prefix}_ck_lbl_{k}", label_visibility="collapsed")
                    val = ck2.text_input("Value", value=str(seq[k]), key=f"{prefix}_cv_{k}", label_visibility="collapsed")
                    seq[k] = val 
                    
                    if ck3.button("🗑️", key=f"{prefix}_cdel_{k}"):
                        keys_to_remove.append(k)
            
            with st.expander("➕ Add Parameter"):
                nk_col, nv_col = st.columns(2)
                new_k = nk_col.text_input("Key", key=f"{prefix}_new_k")
                new_v = nv_col.text_input("Value", key=f"{prefix}_new_v")
                
                if st.button("Add", key=f"{prefix}_add_cust"):
                    if new_k and new_k not in seq:
                        seq[new_k] = new_v
                        save_json(file_path, data)
                        st.session_state.ui_reset_token += 1
                        st.rerun()

            if keys_to_remove:
                for k in keys_to_remove:
                    del seq[k]
                save_json(file_path, data)
                st.session_state.ui_reset_token += 1
                st.rerun()

    st.markdown("---")
    
    # --- SAVE ACTIONS WITH HISTORY COMMIT ---
    col_save, col_note = st.columns([1, 2])
    
    with col_note:
        commit_msg = st.text_input("Change Note (Optional)", placeholder="e.g. Added sequence 3")
        
    with col_save:
        if st.button("💾 Save & Snap", use_container_width=True):
            data["batch_data"] = batch_list
            
            tree_data = data.get("history_tree", {})
            htree = HistoryTree(tree_data)
            
            snapshot_payload = copy.deepcopy(data)
            if "history_tree" in snapshot_payload: del snapshot_payload["history_tree"]
            
            htree.commit(snapshot_payload, note=commit_msg if commit_msg else "Batch Update")
            
            data["history_tree"] = htree.to_dict()
            save_json(file_path, data)
            
            if 'restored_indicator' in st.session_state:
                del st.session_state.restored_indicator
            
            st.toast("Batch Saved & Snapshot Created!", icon="🚀")
            st.rerun()