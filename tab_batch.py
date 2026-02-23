import streamlit as st
import random
import copy
from utils import DEFAULTS, save_json, load_json, KEY_BATCH_DATA, KEY_HISTORY_TREE, KEY_PROMPT_HISTORY, KEY_SEQUENCE_NUMBER
from history_tree import HistoryTree

SUB_SEGMENT_MULTIPLIER = 1000

def is_subsegment(seq_num):
    """Return True if seq_num is a sub-segment (>= 1000)."""
    return int(seq_num) >= SUB_SEGMENT_MULTIPLIER

def parent_of(seq_num):
    """Return the parent segment number (or self if already a parent)."""
    seq_num = int(seq_num)
    return seq_num // SUB_SEGMENT_MULTIPLIER if is_subsegment(seq_num) else seq_num

def sub_index_of(seq_num):
    """Return the sub-index (0 if parent)."""
    seq_num = int(seq_num)
    return seq_num % SUB_SEGMENT_MULTIPLIER if is_subsegment(seq_num) else 0

def format_seq_label(seq_num):
    """Return display label: 'Sequence #3' or 'Sub #2.1'."""
    seq_num = int(seq_num)
    if is_subsegment(seq_num):
        return f"Sub #{parent_of(seq_num)}.{sub_index_of(seq_num)}"
    return f"Sequence #{seq_num}"

def next_sub_segment_number(batch_list, parent_seq_num):
    """Find the next available sub-segment number under a parent."""
    parent_seq_num = int(parent_seq_num)
    max_sub = 0
    for s in batch_list:
        sn = int(s.get(KEY_SEQUENCE_NUMBER, 0))
        if is_subsegment(sn) and parent_of(sn) == parent_seq_num:
            max_sub = max(max_sub, sub_index_of(sn))
    return parent_seq_num * SUB_SEGMENT_MULTIPLIER + max_sub + 1

def find_insert_position(batch_list, parent_index, parent_seq_num):
    """Find the insert position after the parent's last existing sub-segment."""
    parent_seq_num = int(parent_seq_num)
    pos = parent_index + 1
    while pos < len(batch_list):
        sn = int(batch_list[pos].get(KEY_SEQUENCE_NUMBER, 0))
        if is_subsegment(sn) and parent_of(sn) == parent_seq_num:
            pos += 1
        else:
            break
    return pos

def _render_mass_update(batch_list, data, file_path, key_prefix):
    """Render the mass update UI section."""
    with st.expander("🔄 Mass Update", expanded=False):
        if len(batch_list) < 2:
            st.info("Need at least 2 sequences for mass update.")
            return

        # Source sequence selector
        source_idx = st.selectbox(
            "Copy from sequence:",
            range(len(batch_list)),
            format_func=lambda i: format_seq_label(batch_list[i].get('sequence_number', i+1)),
            key=f"{key_prefix}_mass_src"
        )
        source_seq = batch_list[source_idx]

        # Field multi-select (exclude sequence_number)
        available_keys = [k for k in source_seq.keys() if k != "sequence_number"]
        selected_keys = st.multiselect("Fields to copy:", available_keys, key=f"{key_prefix}_mass_fields")

        if not selected_keys:
            return

        # Target sequence checkboxes
        st.write("Apply to:")
        select_all = st.checkbox("Select All", key=f"{key_prefix}_mass_all")

        target_indices = []
        target_cols = st.columns(min(4, len(batch_list) - 1)) if len(batch_list) > 1 else [st]
        col_idx = 0
        for i, seq in enumerate(batch_list):
            if i == source_idx:
                continue
            seq_num = seq.get("sequence_number", i + 1)
            with target_cols[col_idx % len(target_cols)]:
                checked = select_all or st.checkbox(format_seq_label(seq_num), key=f"{key_prefix}_mass_t{i}")
            if checked:
                target_indices.append(i)
            col_idx += 1

        # Preview
        if target_indices and selected_keys:
            with st.expander("Preview changes", expanded=True):
                for key in selected_keys:
                    val = source_seq.get(key, "")
                    display_val = str(val)[:100] + "..." if len(str(val)) > 100 else str(val)
                    st.caption(f"**{key}**: {display_val}")

            # Apply button
            if st.button("Apply Changes", type="primary", key=f"{key_prefix}_mass_apply"):
                for i in target_indices:
                    for key in selected_keys:
                        batch_list[i][key] = copy.deepcopy(source_seq.get(key))

                # Save with history snapshot
                data[KEY_BATCH_DATA] = batch_list
                htree = HistoryTree(data.get(KEY_HISTORY_TREE, {}))
                snapshot_payload = copy.deepcopy(data)
                if KEY_HISTORY_TREE in snapshot_payload:
                    del snapshot_payload[KEY_HISTORY_TREE]
                htree.commit(snapshot_payload, f"Mass update: {', '.join(selected_keys)}")
                data[KEY_HISTORY_TREE] = htree.to_dict()
                save_json(file_path, data)
                st.session_state.data_cache = data
                st.session_state.ui_reset_token += 1
                st.toast(f"Updated {len(target_indices)} sequences", icon="✅")
                st.rerun()


def create_batch_callback(original_filename, current_data, current_dir):
    new_name = f"batch_{original_filename}"
    new_path = current_dir / new_name
    
    if new_path.exists():
        st.toast(f"File {new_name} already exists!", icon="⚠️")
        return

    first_item = current_data.copy()
    if KEY_PROMPT_HISTORY in first_item: del first_item[KEY_PROMPT_HISTORY]
    if KEY_HISTORY_TREE in first_item: del first_item[KEY_HISTORY_TREE]

    first_item[KEY_SEQUENCE_NUMBER] = 1

    new_data = {
        KEY_BATCH_DATA: [first_item],
        KEY_HISTORY_TREE: {},
        KEY_PROMPT_HISTORY: []
    }
    
    save_json(new_path, new_data)
    st.toast(f"Created {new_name}", icon="✨")
    st.session_state.file_selector = new_name


def render_batch_processor(data, file_path, json_files, current_dir, selected_file_name):
    is_batch_file = KEY_BATCH_DATA in data or isinstance(data, list)
    
    if not is_batch_file:
        st.warning("This is a Single file. To use Batch mode, create a copy.")
        st.button("✨ Create Batch Copy", on_click=create_batch_callback, args=(selected_file_name, data, current_dir))
        return

    if 'restored_indicator' in st.session_state and st.session_state.restored_indicator:
        st.info(f"📍 Editing Restored Version: **{st.session_state.restored_indicator}**")

    batch_list = data.get(KEY_BATCH_DATA, [])
    
    # --- ADD NEW SEQUENCE AREA ---
    st.subheader("Add New Sequence")
    ac1, ac2 = st.columns(2)

    with ac1:
        file_options = [f.name for f in json_files]
        d_idx = file_options.index(selected_file_name) if selected_file_name in file_options else 0
        src_name = st.selectbox("Source File:", file_options, index=d_idx, key="batch_src_file")
        src_data, _ = load_json(current_dir / src_name)

    with ac2:
        src_batch = src_data.get(KEY_BATCH_DATA, [])
        if src_batch:
            seq_opts = list(range(len(src_batch)))
            sel_seq_idx = st.selectbox(
                "Source Sequence:",
                seq_opts,
                format_func=lambda i: format_seq_label(src_batch[i].get(KEY_SEQUENCE_NUMBER, i + 1)),
                key="batch_src_seq"
            )
        else:
            st.caption("Single file (no sequences)")
            sel_seq_idx = None

    bc1, bc2 = st.columns(2)

    def add_sequence(new_item):
        max_seq = 0
        for s in batch_list:
            sn = int(s.get(KEY_SEQUENCE_NUMBER, 0))
            if not is_subsegment(sn):
                max_seq = max(max_seq, sn)
        new_item[KEY_SEQUENCE_NUMBER] = max_seq + 1

        for k in [KEY_PROMPT_HISTORY, KEY_HISTORY_TREE, "note", "loras"]:
            if k in new_item: del new_item[k]

        batch_list.append(new_item)
        data[KEY_BATCH_DATA] = batch_list
        save_json(file_path, data)
        st.session_state.ui_reset_token += 1
        st.rerun()

    if bc1.button("➕ Add Empty", use_container_width=True):
        add_sequence(DEFAULTS.copy())

    if bc2.button("➕ From Source", use_container_width=True, help=f"Import from {src_name}"):
        item = DEFAULTS.copy()
        if src_batch and sel_seq_idx is not None:
            item.update(src_batch[sel_seq_idx])
        else:
            item.update(src_data)
        add_sequence(item)

    # --- RENDER LIST ---
    st.markdown("---")
    info_col, reorder_col = st.columns([3, 1])
    info_col.info(f"Batch contains {len(batch_list)} sequences.")
    if reorder_col.button("🔢 Sort by Number", use_container_width=True, help="Reorder sequences by sequence number"):
        batch_list.sort(key=lambda s: int(s.get(KEY_SEQUENCE_NUMBER, 0)))
        data[KEY_BATCH_DATA] = batch_list
        save_json(file_path, data)
        st.session_state.ui_reset_token += 1
        st.toast("Sorted by sequence number!", icon="🔢")
        st.rerun()

    # --- MASS UPDATE SECTION ---
    ui_reset_token = st.session_state.get("ui_reset_token", 0)
    _render_mass_update(batch_list, data, file_path, f"{selected_file_name}_v{ui_reset_token}")

    # Updated LoRA keys to match new logic
    lora_keys = ["lora 1 high", "lora 1 low", "lora 2 high", "lora 2 low", "lora 3 high", "lora 3 low"]
    standard_keys = {
        "general_prompt", "general_negative", "current_prompt", "negative", "prompt", "seed",
        "camera", "flf", KEY_SEQUENCE_NUMBER
    }
    standard_keys.update(lora_keys)
    standard_keys.update([
        "frame_to_skip", "end_frame", "transition",
        "input_a_frames", "input_b_frames", "reference switch", "vace schedule",
        "reference path", "video file path", "reference image path", "flf image path"
    ])

    for i, seq in enumerate(batch_list):
        seq_num = seq.get(KEY_SEQUENCE_NUMBER, i+1)
        prefix = f"{selected_file_name}_seq{i}_v{st.session_state.ui_reset_token}" 

        if is_subsegment(seq_num):
            expander_label = f"🔗  ↳ Sub #{parent_of(seq_num)}.{sub_index_of(seq_num)}  ({int(seq_num)})"
        else:
            expander_label = f"🎬 Sequence #{seq_num}"

        with st.expander(expander_label, expanded=False):
            # --- ACTION ROW ---
            act_c1, act_c2, act_c3, act_c4 = st.columns([1.2, 1.8, 1.2, 0.5])
            
            # 1. Copy Source
            with act_c1:
                if st.button(f"📥 Copy {src_name}", key=f"{prefix}_copy", use_container_width=True):
                    item = DEFAULTS.copy()
                    if src_batch and sel_seq_idx is not None:
                        item.update(src_batch[sel_seq_idx])
                    else:
                        item.update(src_data)
                    item[KEY_SEQUENCE_NUMBER] = seq_num
                    for k in [KEY_PROMPT_HISTORY, KEY_HISTORY_TREE]:
                        if k in item: del item[k]
                    batch_list[i] = item
                    data[KEY_BATCH_DATA] = batch_list
                    save_json(file_path, data)
                    st.session_state.ui_reset_token += 1 
                    st.toast("Copied!", icon="📥")
                    st.rerun()

            # 2. Cloning Tools
            with act_c2:
                cl_1, cl_2, cl_3 = st.columns(3)
                if cl_1.button("👯 Next", key=f"{prefix}_c_next", help="Clone and insert below", use_container_width=True):
                    new_seq = copy.deepcopy(seq)
                    max_sn = 0
                    for s in batch_list:
                        sn = int(s.get(KEY_SEQUENCE_NUMBER, 0))
                        if not is_subsegment(sn):
                            max_sn = max(max_sn, sn)
                    new_seq[KEY_SEQUENCE_NUMBER] = max_sn + 1
                    if not is_subsegment(seq_num):
                        insert_pos = find_insert_position(batch_list, i, int(seq_num))
                    else:
                        insert_pos = i + 1
                    batch_list.insert(insert_pos, new_seq)
                    data[KEY_BATCH_DATA] = batch_list
                    save_json(file_path, data)
                    st.session_state.ui_reset_token += 1
                    st.toast("Cloned to Next!", icon="👯")
                    st.rerun()

                if cl_2.button("⏬ End", key=f"{prefix}_c_end", help="Clone and add to bottom", use_container_width=True):
                    new_seq = copy.deepcopy(seq)
                    max_sn = 0
                    for s in batch_list:
                        sn = int(s.get(KEY_SEQUENCE_NUMBER, 0))
                        if not is_subsegment(sn):
                            max_sn = max(max_sn, sn)
                    new_seq[KEY_SEQUENCE_NUMBER] = max_sn + 1
                    batch_list.append(new_seq)
                    data[KEY_BATCH_DATA] = batch_list
                    save_json(file_path, data)
                    st.session_state.ui_reset_token += 1
                    st.toast("Cloned to End!", icon="⏬")
                    st.rerun()

                if cl_3.button("🔗 Sub", key=f"{prefix}_c_sub", help="Clone as sub-segment", use_container_width=True):
                    new_seq = copy.deepcopy(seq)
                    p_seq_num = parent_of(seq_num)
                    # Find the parent's index in batch_list
                    p_idx = i
                    if is_subsegment(seq_num):
                        for pi, ps in enumerate(batch_list):
                            if int(ps.get(KEY_SEQUENCE_NUMBER, 0)) == p_seq_num:
                                p_idx = pi
                                break
                    new_seq[KEY_SEQUENCE_NUMBER] = next_sub_segment_number(batch_list, p_seq_num)
                    insert_pos = find_insert_position(batch_list, p_idx, p_seq_num)
                    batch_list.insert(insert_pos, new_seq)
                    data[KEY_BATCH_DATA] = batch_list
                    save_json(file_path, data)
                    st.session_state.ui_reset_token += 1
                    st.toast(f"Created {format_seq_label(new_seq[KEY_SEQUENCE_NUMBER])}!", icon="🔗")
                    st.rerun()

            # 3. Promote
            with act_c3:
                if st.button("↖️ Promote", key=f"{prefix}_prom", help="Save as Single File", use_container_width=True):
                    single_data = seq.copy()
                    single_data[KEY_PROMPT_HISTORY] = data.get(KEY_PROMPT_HISTORY, [])
                    single_data[KEY_HISTORY_TREE] = data.get(KEY_HISTORY_TREE, {})
                    if KEY_SEQUENCE_NUMBER in single_data: del single_data[KEY_SEQUENCE_NUMBER]
                    save_json(file_path, single_data)
                    st.session_state.data_cache = single_data
                    st.session_state.ui_reset_token += 1
                    st.toast("Converted to Single!", icon="✅")
                    st.rerun()

            # 4. Remove
            with act_c4:
                if st.button("🗑️", key=f"{prefix}_del", use_container_width=True):
                    batch_list.pop(i)
                    data[KEY_BATCH_DATA] = batch_list
                    save_json(file_path, data)
                    st.session_state.ui_reset_token += 1
                    st.rerun()

            st.markdown("---")
            c1, c2 = st.columns([2, 1])
            with c1:
                seq["general_prompt"] = st.text_area("General Prompt", value=seq.get("general_prompt", ""), height=60, key=f"{prefix}_gp")
                seq["general_negative"] = st.text_area("General Negative", value=seq.get("general_negative", ""), height=60, key=f"{prefix}_gn")
                seq["current_prompt"] = st.text_area("Specific Prompt", value=seq.get("current_prompt", ""), height=300, key=f"{prefix}_sp")
                seq["negative"] = st.text_area("Specific Negative", value=seq.get("negative", ""), height=60, key=f"{prefix}_sn")
            
            with c2:
                sn_label = f"Sequence Number (↳ Sub #{parent_of(seq_num)}.{sub_index_of(seq_num)})" if is_subsegment(seq_num) else "Sequence Number"
                seq[KEY_SEQUENCE_NUMBER] = st.number_input(sn_label, value=int(seq_num), key=f"{prefix}_sn_val")
                
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
                
                seq["video file path"] = st.text_input("Video File Path", value=seq.get("video file path", ""), key=f"{prefix}_vid")
                seq["reference image path"] = st.text_input("Reference Image Path", value=seq.get("reference image path", ""), key=f"{prefix}_rip")
                seq["reference path"] = st.text_input("Reference Path", value=seq.get("reference path", ""), key=f"{prefix}_rp")
                seq["flf image path"] = st.text_input("FLF Image Path", value=seq.get("flf image path", ""), key=f"{prefix}_flfi")
                with st.expander("VACE Settings"):
                    fts_col, fts_btn = st.columns([3, 1])
                    saved_fts_key = f"{prefix}_fts_saved"
                    if saved_fts_key not in st.session_state:
                        st.session_state[saved_fts_key] = int(seq.get("frame_to_skip", 81))
                    old_fts = st.session_state[saved_fts_key]
                    seq["frame_to_skip"] = fts_col.number_input("Frame to Skip", value=old_fts, key=f"{prefix}_fts")
                    delta = int(seq["frame_to_skip"]) - old_fts
                    delta_label = f"Shift ↓ ({delta:+d})" if delta != 0 else "Shift ↓ (0)"
                    fts_btn.write("")
                    fts_btn.write("")
                    if fts_btn.button(delta_label, key=f"{prefix}_fts_shift", help="Apply delta to all following sequences", disabled=(delta == 0)):
                        if delta != 0:
                            shifted = 0
                            for j in range(i + 1, len(batch_list)):
                                batch_list[j]["frame_to_skip"] = int(batch_list[j].get("frame_to_skip", 81)) + delta
                                shifted += 1
                            data[KEY_BATCH_DATA] = batch_list
                            save_json(file_path, data)
                            st.session_state.ui_reset_token += 1
                            st.toast(f"Shifted {shifted} sequences by {delta:+d}", icon="⏬")
                            st.rerun()
                        else:
                            st.toast("No change to shift", icon="ℹ️")
                    seq["end_frame"] = st.number_input("End Frame", value=int(seq.get("end_frame", 0)), key=f"{prefix}_ef")
                    seq["transition"] = st.text_input("Transition", value=str(seq.get("transition", "1-2")), key=f"{prefix}_trans")
                    seq["input_a_frames"] = st.number_input("Input A Frames", value=int(seq.get("input_a_frames", 0)), key=f"{prefix}_ia")
                    seq["input_b_frames"] = st.number_input("Input B Frames", value=int(seq.get("input_b_frames", 0)), key=f"{prefix}_ib")
                    seq["reference switch"] = st.number_input("Reference Switch", value=int(seq.get("reference switch", 1)), key=f"{prefix}_rsw")
                    seq["vace schedule"] = st.number_input("VACE Schedule", value=int(seq.get("vace schedule", 1)), key=f"{prefix}_vsc")

            # --- UPDATED: LoRA Settings with Tag Wrapping ---
            with st.expander("💊 LoRA Settings"):
                lc1, lc2, lc3 = st.columns(3)
                
                # Helper to render the tag wrapper UI
                def render_lora_col(col_obj, lora_idx):
                    with col_obj:
                        st.caption(f"**LoRA {lora_idx}**")
                        
                        # --- HIGH ---
                        k_high = f"lora {lora_idx} high"
                        raw_h = str(seq.get(k_high, ""))
                        # Strip tags for display
                        disp_h = raw_h.replace("<lora:", "").replace(">", "")
                        
                        st.write("High:")
                        rh1, rh2, rh3 = st.columns([0.25, 1, 0.1])
                        rh1.markdown("<div style='text-align: right; padding-top: 8px;'><code>&lt;lora:</code></div>", unsafe_allow_html=True)
                        val_h = rh2.text_input(f"L{lora_idx}H", value=disp_h, key=f"{prefix}_l{lora_idx}h", label_visibility="collapsed")
                        rh3.markdown("<div style='padding-top: 8px;'><code>&gt;</code></div>", unsafe_allow_html=True)
                        
                        if val_h:
                            seq[k_high] = f"<lora:{val_h}>"
                        else:
                            seq[k_high] = ""

                        # --- LOW ---
                        k_low = f"lora {lora_idx} low"
                        raw_l = str(seq.get(k_low, ""))
                        # Strip tags for display
                        disp_l = raw_l.replace("<lora:", "").replace(">", "")
                        
                        st.write("Low:")
                        rl1, rl2, rl3 = st.columns([0.25, 1, 0.1])
                        rl1.markdown("<div style='text-align: right; padding-top: 8px;'><code>&lt;lora:</code></div>", unsafe_allow_html=True)
                        val_l = rl2.text_input(f"L{lora_idx}L", value=disp_l, key=f"{prefix}_l{lora_idx}l", label_visibility="collapsed")
                        rl3.markdown("<div style='padding-top: 8px;'><code>&gt;</code></div>", unsafe_allow_html=True)
                        
                        if val_l:
                            seq[k_low] = f"<lora:{val_l}>"
                        else:
                            seq[k_low] = ""

                render_lora_col(lc1, 1)
                render_lora_col(lc2, 2)
                render_lora_col(lc3, 3)

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
            data[KEY_BATCH_DATA] = batch_list
            
            tree_data = data.get(KEY_HISTORY_TREE, {})
            htree = HistoryTree(tree_data)
            
            snapshot_payload = copy.deepcopy(data)
            if KEY_HISTORY_TREE in snapshot_payload: del snapshot_payload[KEY_HISTORY_TREE]
            
            htree.commit(snapshot_payload, note=commit_msg if commit_msg else "Batch Update")
            
            data[KEY_HISTORY_TREE] = htree.to_dict()
            save_json(file_path, data)
            
            if 'restored_indicator' in st.session_state:
                del st.session_state.restored_indicator
            
            st.toast("Batch Saved & Snapshot Created!", icon="🚀")
            st.rerun()