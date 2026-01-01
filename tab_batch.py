import streamlit as st
import random
from utils import DEFAULTS, save_json, load_json

def create_batch_callback(original_filename, current_data, current_dir):
    new_name = f"batch_{original_filename}"
    new_path = current_dir / new_name
    
    if new_path.exists():
        st.toast(f"File {new_name} already exists!", icon="⚠️")
        return

    first_item = current_data.copy()
    if "prompt_history" in first_item: del first_item["prompt_history"]
    first_item["sequence_number"] = 1
    
    new_data = {
        "batch_data": [first_item], 
        "prompt_history": current_data.get("prompt_history", [])
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

    batch_list = data.get("batch_data", [])
    
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
        sel_hist = st.selectbox("History Entry:", h_opts, key="batch_src_hist")

    bc1, bc2, bc3 = st.columns(3)
    
    def add_sequence(new_item):
        max_seq = 0
        for s in batch_list:
            if "sequence_number" in s: max_seq = max(max_seq, int(s["sequence_number"]))
        new_item["sequence_number"] = max_seq + 1
        for k in ["prompt_history", "note", "loras"]: 
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

    st.markdown("---")
    st.info(f"Batch contains {len(batch_list)} sequences.")

    for i, seq in enumerate(batch_list):
        seq_num = seq.get("sequence_number", i+1)
        prefix = f"{selected_file_name}_seq{i}_v{st.session_state.ui_reset_token}" 

        with st.expander(f"🎬 Sequence #{seq_num}", expanded=False):
            b1, b2, b3 = st.columns([1, 1, 2])
            
            if b1.button(f"📥 Copy {src_name}", key=f"{prefix}_copy"):
                item = DEFAULTS.copy()
                flat = src_data["batch_data"][0] if "batch_data" in src_data and src_data["batch_data"] else src_data
                item.update(flat)
                item["sequence_number"] = seq_num
                if "prompt_history" in item: del item["prompt_history"]
                batch_list[i] = item
                data["batch_data"] = batch_list
                save_json(file_path, data)
                st.session_state.ui_reset_token += 1 
                st.toast("Copied!", icon="📥")
                st.rerun()

            if b2.button("↖️ Promote to Single", key=f"{prefix}_prom"):
                single_data = seq.copy()
                single_data["prompt_history"] = data.get("prompt_history", [])
                if "sequence_number" in single_data: del single_data["sequence_number"]
                save_json(file_path, single_data)
                st.toast("Converted to Single!", icon="✅")
                st.rerun()

            if b3.button("🗑️ Remove", key=f"{prefix}_del"):
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
                seq["sequence_number"] = st.number_input("Seq Num", value=int(seq_num), key=f"{prefix}_sn_val")
                
                # --- FIXED SEED ROW ---
                s_row1, s_row2 = st.columns([3, 1])
                seed_key = f"{prefix}_seed"
                with s_row2:
                    st.write("")
                    st.write("")
                    if st.button("🎲", key=f"{prefix}_rand"):
                        st.session_state[seed_key] = random.randint(0, 999999999999)
                        st.rerun()
                with s_row1:
                    seq["seed"] = st.number_input("Seed", value=int(seq.get("seed", 0)), key=seed_key)
                # -----------------------

                seq["camera"] = st.text_input("Camera", value=seq.get("camera", ""), key=f"{prefix}_cam")
                seq["flf"] = st.text_input("FLF", value=str(seq.get("flf", DEFAULTS["flf"])), key=f"{prefix}_flf")
                
                if "video file path" in seq or "vace" in selected_file_name:
                    seq["video file path"] = st.text_input("Video Path", value=seq.get("video file path", ""), key=f"{prefix}_vid")
                    with st.expander("VACE Settings"):
                        seq["frame_to_skip"] = st.number_input("Skip", value=int(seq.get("frame_to_skip", 81)), key=f"{prefix}_fts")
                        seq["input_a_frames"] = st.number_input("In A", value=int(seq.get("input_a_frames", 0)), key=f"{prefix}_ia")
                        seq["input_b_frames"] = st.number_input("In B", value=int(seq.get("input_b_frames", 0)), key=f"{prefix}_ib")
                        seq["reference switch"] = st.number_input("Switch", value=int(seq.get("reference switch", 1)), key=f"{prefix}_rsw")
                        seq["vace schedule"] = st.number_input("Sched", value=int(seq.get("vace schedule", 1)), key=f"{prefix}_vsc")
                        seq["reference path"] = st.text_input("Ref Path", value=seq.get("reference path", ""), key=f"{prefix}_rp")
                        seq["reference image path"] = st.text_input("Ref Img", value=seq.get("reference image path", ""), key=f"{prefix}_rip")
                
                if "i2v" in selected_file_name and "vace" not in selected_file_name:
                    seq["reference image path"] = st.text_input("Ref Img", value=seq.get("reference image path", ""), key=f"{prefix}_ri2")
                    seq["flf image path"] = st.text_input("FLF Img", value=seq.get("flf image path", ""), key=f"{prefix}_flfi")

            with st.expander("LoRA Settings"):
                lc1, lc2 = st.columns(2)
                lkeys = ["lora 1 high", "lora 1 low", "lora 2 high", "lora 2 low", "lora 3 high", "lora 3 low"]
                for li, lk in enumerate(lkeys):
                    with (lc1 if li % 2 == 0 else lc2):
                        seq[lk] = st.text_input(lk.title(), value=seq.get(lk, ""), key=f"{prefix}_{lk}")

    st.markdown("---")
    if st.button("💾 Save Batch Changes"):
        data["batch_data"] = batch_list
        save_json(file_path, data)
        st.toast("Batch saved!", icon="🚀")
