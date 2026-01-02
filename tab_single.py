import streamlit as st
import random
import json
from utils import DEFAULTS, save_json, get_file_mtime, render_smart_input
from history_tree import HistoryTree 

def render_single_editor(data, file_path):
    is_batch_file = "batch_data" in data or isinstance(data, list)
    if is_batch_file:
        st.warning("⚠️ This file looks like a Batch file. Please switch to the 'Batch Processor' tab.")
        return

    # Check external modification
    current_mtime = get_file_mtime(file_path)
    if st.session_state.last_mtime != 0 and current_mtime > st.session_state.last_mtime:
        st.error("⚠️ File has been modified externally! Save will overwrite.")

    # --- TOP ROW: MODELS (SMART INPUTS) ---
    st.subheader("🤖 Models")
    c1, c2 = st.columns(2)
    
    # Access metadata from session state
    meta = st.session_state.get("comfy_meta", {})
    ckpts = meta.get("checkpoints", [])
    vaes = meta.get("vaes", [])
    
    with c1:
        data["model_name"] = render_smart_input(
            "Checkpoint", "s_model", data.get("model_name", ""), ckpts
        )
    with c2:
        data["vae_name"] = render_smart_input(
            "VAE", "s_vae", data.get("vae_name", ""), vaes
        )

    # --- PROMPTS ---
    st.markdown("---")
    st.subheader("📝 Prompts")

    if 'append_prompt' in st.session_state:
        current_p = data.get("positive_prompt", "")
        if current_p: current_p += "\n"
        data["positive_prompt"] = current_p + st.session_state.append_prompt
        del st.session_state.append_prompt

    data["positive_prompt"] = st.text_area("Positive Prompt", value=data.get("positive_prompt", ""), height=150)
    data["negative_prompt"] = st.text_area("Negative Prompt", value=data.get("negative_prompt", ""), height=100)

    # --- MAIN SETTINGS ---
    st.markdown("---")
    st.subheader("⚙️ Settings")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        data["steps"] = st.number_input("Steps", value=int(data.get("steps", 20)))
        data["cfg"] = st.number_input("CFG", value=float(data.get("cfg", 7.0)))
    with col2:
        data["denoise"] = st.number_input("Denoise", value=float(data.get("denoise", 1.0)))
        data["sampler_name"] = st.text_input("Sampler", value=data.get("sampler_name", "euler"))
    with col3:
        data["scheduler"] = st.text_input("Scheduler", value=data.get("scheduler", "normal"))
        
        # Seed Logic
        s_row1, s_row2 = st.columns([3, 1])
        with s_row2:
            st.write("")
            st.write("")
            if st.button("🎲"):
                st.session_state.rand_seed = random.randint(0, 999999999999)
                st.rerun()
        with s_row1:
            current_seed = st.session_state.get('rand_seed', int(data.get("seed", -1)))
            val = st.number_input("Seed", value=current_seed)
            data["seed"] = val

    # --- ADVANCED SECTIONS ---
    with st.expander("🎥 Camera & FLF Settings"):
        data["camera"] = st.text_input("Camera Motion", value=data.get("camera", "static"))
        data["flf"] = st.number_input("FLF", value=float(data.get("flf", 0.0)))
        data["frame_to_skip"] = st.number_input("Frames to Skip (VACE)", value=int(data.get("frame_to_skip", 81)))
        data["vace schedule"] = st.number_input("VACE Schedule", value=int(data.get("vace schedule", 1)))

    with st.expander("📂 File Paths"):
        data["video file path"] = st.text_input("Video Input Path", value=data.get("video file path", ""))
        data["reference image path"] = st.text_input("Reference Image Path", value=data.get("reference image path", ""))

    # --- LORAS (SMART INPUTS) ---
    st.subheader("💊 LoRAs")
    lora_list = meta.get("loras", [])
    
    l1, l2 = st.columns(2)
    
    def lora_row(col, num):
        with col:
            st.caption(f"LoRA {num}")
            k_high = f"lora {num} high"
            k_low = f"lora {num} low"
            
            # SMART INPUT for Name
            data[k_high] = render_smart_input(
                "Model", f"s_l{num}_h", data.get(k_high, ""), lora_list
            )
            # Slider for Strength
            try:
                val = float(data.get(k_low, 1.0))
            except:
                val = 1.0
            data[k_low] = st.slider("Strength", 0.0, 2.0, val, 0.05, key=f"s_l{num}_l")

    lora_row(l1, 1)
    lora_row(l2, 2)
    lora_row(l1, 3)

    # --- CUSTOM PARAMETERS ---
    st.markdown("---")
    st.caption("🔧 Custom Parameters")
    
    standard_keys = list(DEFAULTS.keys()) + ["history_tree", "prompt_history"]
    custom_keys = [k for k in data.keys() if k not in standard_keys]
    
    if custom_keys:
        keys_to_remove = []
        for k in custom_keys:
            ck1, ck2, ck3 = st.columns([1, 2, 0.5])
            ck1.text_input("Key", value=k, disabled=True, key=f"ck_lbl_{k}", label_visibility="collapsed")
            data[k] = ck2.text_input("Value", value=str(data[k]), key=f"cv_{k}", label_visibility="collapsed")
            if ck3.button("🗑️", key=f"cdel_{k}"):
                keys_to_remove.append(k)
        
        if keys_to_remove:
            for k in keys_to_remove: del data[k]
            save_json(file_path, data)
            st.rerun()

    with st.expander("➕ Add Parameter"):
        nk, nv = st.columns(2)
        new_k = nk.text_input("New Key")
        new_v = nv.text_input("New Value")
        if st.button("Add Parameter"):
            if new_k and new_k not in data:
                data[new_k] = new_v
                save_json(file_path, data)
                st.rerun()

    # --- SAVE ACTIONS ---
    st.markdown("---")
    c_save, c_snap = st.columns([1, 2])
    
    with c_save:
        if st.button("💾 Save Changes", use_container_width=True):
            save_json(file_path, data)
            st.toast("Saved!", icon="✅")
    
    with c_snap:
        with st.popover("📸 Save Snapshot (History)", use_container_width=True):
            note = st.text_input("Snapshot Note", placeholder="e.g. Changed lighting")
            if st.button("Confirm Snapshot"):
                # Commit to History Tree
                tree_data = data.get("history_tree", {})
                htree = HistoryTree(tree_data)
                
                snapshot = data.copy()
                if "history_tree" in snapshot: del snapshot["history_tree"]
                
                htree.commit(snapshot, note=note if note else "Manual Snapshot")
                data["history_tree"] = htree.to_dict()
                
                save_json(file_path, data)
                st.toast("Snapshot Saved!", icon="📸")
