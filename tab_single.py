import streamlit as st
import random
from utils import DEFAULTS, save_json, get_file_mtime

def render_single_editor(data, file_path):
    is_batch_file = "batch_data" in data or isinstance(data, list)
    
    if is_batch_file:
        st.info("This is a batch file. Switch to the 'Batch Processor' tab.")
        return

    col1, col2 = st.columns([2, 1])
    
    # Unique Key + VERSION TOKEN (This forces the refresh)
    # Every time ui_reset_token increments, all widgets are destroyed and recreated with new values
    fk = f"{file_path.name}_v{st.session_state.ui_reset_token}"

    # --- FORM ---
    with col1:
        with st.expander("🌍 General Prompts (Global Layer)", expanded=False):
            gen_prompt = st.text_area("General Prompt", value=data.get("general_prompt", ""), height=100, key=f"{fk}_gp")
            gen_negative = st.text_area("General Negative", value=data.get("general_negative", DEFAULTS["general_negative"]), height=100, key=f"{fk}_gn")

        st.write("📝 **Specific Prompts**")
        current_prompt_val = data.get("current_prompt", "")
        if 'append_prompt' in st.session_state:
            current_prompt_val = (current_prompt_val.strip() + ", " + st.session_state.append_prompt).strip(', ')
            del st.session_state.append_prompt 
            
        new_prompt = st.text_area("Specific Prompt", value=current_prompt_val, height=150, key=f"{fk}_sp")
        new_negative = st.text_area("Specific Negative", value=data.get("negative", ""), height=100, key=f"{fk}_sn")

        # Seed
        col_seed_val, col_seed_btn = st.columns([4, 1])
        with col_seed_btn:
            st.write("") 
            st.write("") 
            if st.button("🎲 Randomize", key=f"{fk}_rand"):
                st.session_state.rand_seed = random.randint(0, 999999999999)
                st.rerun()
        
        with col_seed_val:
            seed_val = st.session_state.get('rand_seed', int(data.get("seed", 0)))
            new_seed = st.number_input("Seed", value=seed_val, step=1, min_value=0, format="%d", key=f"{fk}_seed")
            data["seed"] = new_seed 

        # LoRAs
        st.subheader("LoRAs")
        l_col1, l_col2 = st.columns(2)
        loras = {}
        keys = ["lora 1 high", "lora 1 low", "lora 2 high", "lora 2 low", "lora 3 high", "lora 3 low"]
        for i, k in enumerate(keys):
            with (l_col1 if i % 2 == 0 else l_col2):
                loras[k] = st.text_input(k.title(), value=data.get(k, ""), key=f"{fk}_{k}")

        # Settings
        st.subheader("Settings")
        spec_fields = {}
        spec_fields["camera"] = st.text_input("Camera", value=str(data.get("camera", DEFAULTS["camera"])), key=f"{fk}_cam")
        spec_fields["flf"] = st.text_input("FLF", value=str(data.get("flf", DEFAULTS["flf"])), key=f"{fk}_flf")
        
        if "vace" in file_path.name:
            spec_fields["frame_to_skip"] = st.number_input("Frame to Skip", value=int(data.get("frame_to_skip", 81)), key=f"{fk}_fts")
            spec_fields["input_a_frames"] = st.number_input("Input A Frames", value=int(data.get("input_a_frames", 0)), key=f"{fk}_ia")
            spec_fields["input_b_frames"] = st.number_input("Input B Frames", value=int(data.get("input_b_frames", 0)), key=f"{fk}_ib")
            spec_fields["reference switch"] = st.number_input("Reference Switch", value=int(data.get("reference switch", 1)), key=f"{fk}_rsw")
            spec_fields["vace schedule"] = st.number_input("VACE Schedule", value=int(data.get("vace schedule", 1)), key=f"{fk}_vsc")
            for f in ["reference path", "video file path", "reference image path"]:
                 spec_fields[f] = st.text_input(f.title(), value=str(data.get(f, "")), key=f"{fk}_{f}")
        elif "i2v" in file_path.name:
            for f in ["reference image path", "flf image path", "video file path"]:
                spec_fields[f] = st.text_input(f.title(), value=str(data.get(f, "")), key=f"{fk}_{f}")

    # --- ACTIONS & HISTORY ---
    with col2:
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
            st.error("⚠️ CONFLICT: Disk changed!")
            if st.button("Force Save"):
                data.update(current_state)
                st.session_state.last_mtime = save_json(file_path, data)
                st.session_state.data_cache = data
                st.toast("Saved!", icon="⚠️")
                st.rerun()
            if st.button("Reload File"):
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
                entry = {"note": archive_note if archive_note else "Snapshot", **current_state}
                if "prompt_history" not in data: data["prompt_history"] = []
                data["prompt_history"].insert(0, entry)
                data.update(entry)
                st.session_state.last_mtime = save_json(file_path, data)
                st.session_state.data_cache = data
                st.toast("Archived!", icon="📦")
                st.rerun()

        # --- FULL HISTORY PANEL ---
        st.markdown("---")
        st.subheader("History")
        history = data.get("prompt_history", [])
        
        if not history:
            st.caption("No history yet.")

        for idx, h in enumerate(history):
            note = h.get('note', 'No Note')
            
            with st.container():
                if st.session_state.edit_history_idx == idx:
                    with st.expander(f"📝 Editing: {note}", expanded=True):
                        edit_note = st.text_input("Note", value=note, key=f"h_en_{idx}")
                        edit_seed = st.number_input("Seed", value=int(h.get('seed', 0)), key=f"h_es_{idx}")
                        edit_gp = st.text_area("General P", value=h.get('general_prompt', ''), height=60, key=f"h_egp_{idx}")
                        edit_gn = st.text_area("General N", value=h.get('general_negative', ''), height=60, key=f"h_egn_{idx}")
                        edit_sp = st.text_area("Specific P", value=h.get('prompt', ''), height=100, key=f"h_esp_{idx}")
                        edit_sn = st.text_area("Specific N", value=h.get('negative', ''), height=60, key=f"h_esn_{idx}")
                        
                        hc1, hc2 = st.columns([1, 4])
                        if hc1.button("💾 Save", key=f"h_save_{idx}"):
                            h.update({
                                'note': edit_note, 'seed': edit_seed,
                                'general_prompt': edit_gp, 'general_negative': edit_gn,
                                'prompt': edit_sp, 'negative': edit_sn
                            })
                            st.session_state.last_mtime = save_json(file_path, data)
                            st.session_state.data_cache = data
                            st.session_state.edit_history_idx = None
                            st.rerun()
                        if hc2.button("Cancel", key=f"h_can_{idx}"):
                            st.session_state.edit_history_idx = None
                            st.rerun()
                            
                else:
                    with st.expander(f"#{idx+1}: {note}"):
                        st.caption(f"Seed: {h.get('seed', 0)}")
                        st.text(f"GEN: {h.get('general_prompt', '')[:40]}...")
                        st.text(f"SPEC: {h.get('prompt', '')[:40]}...")
                        
                        view_data = {k:v for k,v in h.items() if k not in ['prompt', 'negative', 'general_prompt', 'general_negative', 'note']}
                        st.json(view_data, expanded=False)

                        bh1, bh2, bh3 = st.columns([2, 1, 1])
                        
                        if bh1.button("Restore", key=f"h_rest_{idx}", use_container_width=True):
                            data.update(h)
                            if 'prompt' in h: data['current_prompt'] = h['prompt']
                            st.session_state.last_mtime = save_json(file_path, data)
                            st.session_state.data_cache = data
                            
                            # MAGIC FIX: Increment token to force full UI redraw
                            st.session_state.ui_reset_token += 1
                            
                            st.toast("Restored!", icon="⏪")
                            st.rerun()
                        
                        if bh2.button("✏️", key=f"h_edit_{idx}"):
                            st.session_state.edit_history_idx = idx
                            st.rerun()
                            
                        if bh3.button("🗑️", key=f"h_del_{idx}"):
                            history.pop(idx)
                            st.session_state.last_mtime = save_json(file_path, data)
                            st.session_state.data_cache = data
                            st.rerun()
