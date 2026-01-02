import streamlit as st
import random
import graphviz
from utils import DEFAULTS, save_json, get_file_mtime
from history_tree import HistoryTree

def render_single_editor(data, file_path):
    # 1. Safety Check: Ensure this isn't a batch file
    is_batch_file = "batch_data" in data or isinstance(data, list)
    if is_batch_file:
        st.info("This is a batch file. Switch to the 'Batch Processor' tab.")
        return

    # 2. Initialize History Engine
    # We load the tree from the JSON. If it doesn't exist, we look for the old list to migrate.
    tree_data = data.get("history_tree", {})
    if "prompt_history" in data and not tree_data:
        # Migration path for old files
        tree_data = {"prompt_history": data["prompt_history"]}
    
    htree = HistoryTree(tree_data)

    col1, col2 = st.columns([2, 1])
    
    # 3. Generate Unique Key for Widgets
    # We append 'ui_reset_token' so that changing it forces Streamlit to re-render all inputs
    fk = f"{file_path.name}_v{st.session_state.ui_reset_token}"

    # ==============================================================================
    # LEFT COLUMN: THE EDITOR FORM
    # ==============================================================================
    with col1:
        # --- PROMPTS ---
        with st.expander("🌍 General Prompts (Global Layer)", expanded=False):
            gen_prompt = st.text_area("General Prompt", value=data.get("general_prompt", ""), height=100, key=f"{fk}_gp")
            gen_negative = st.text_area("General Negative", value=data.get("general_negative", DEFAULTS["general_negative"]), height=100, key=f"{fk}_gn")

        st.write("📝 **Specific Prompts**")
        current_prompt_val = data.get("current_prompt", "")
        # Logic to append snippets from sidebar
        if 'append_prompt' in st.session_state:
            current_prompt_val = (current_prompt_val.strip() + ", " + st.session_state.append_prompt).strip(', ')
            del st.session_state.append_prompt 
            
        new_prompt = st.text_area("Specific Prompt", value=current_prompt_val, height=150, key=f"{fk}_sp")
        new_negative = st.text_area("Specific Negative", value=data.get("negative", ""), height=100, key=f"{fk}_sn")

        # --- SEED ---
        col_seed_val, col_seed_btn = st.columns([4, 1])
        seed_key = f"{fk}_seed"

        with col_seed_btn:
            st.write("") 
            st.write("") 
            if st.button("🎲", key=f"{fk}_rand", help="Randomize Seed"):
                st.session_state[seed_key] = random.randint(0, 999999999999)
                st.rerun()
        
        with col_seed_val:
            seed_val = st.session_state.get('rand_seed', int(data.get("seed", 0)))
            new_seed = st.number_input("Seed", value=seed_val, step=1, min_value=0, format="%d", key=seed_key)
            data["seed"] = new_seed 

        # --- LORAS ---
        st.subheader("LoRAs")
        l_col1, l_col2 = st.columns(2)
        loras = {}
        lora_keys = ["lora 1 high", "lora 1 low", "lora 2 high", "lora 2 low", "lora 3 high", "lora 3 low"]
        for i, k in enumerate(lora_keys):
            with (l_col1 if i % 2 == 0 else l_col2):
                loras[k] = st.text_input(k.title(), value=data.get(k, ""), key=f"{fk}_{k}")

        # --- STANDARD SETTINGS ---
        st.subheader("Settings")
        spec_fields = {}
        spec_fields["camera"] = st.text_input("Camera", value=str(data.get("camera", DEFAULTS["camera"])), key=f"{fk}_cam")
        spec_fields["flf"] = st.text_input("FLF", value=str(data.get("flf", DEFAULTS["flf"])), key=f"{fk}_flf")
        
        # Define what is "Standard" so Custom Param logic knows what to ignore
        standard_keys = {
            "general_prompt", "general_negative", "current_prompt", "negative", "prompt", "seed",
            "camera", "flf", "batch_data", "prompt_history", "history_tree", "sequence_number", "ui_reset_token"
        }
        standard_keys.update(lora_keys)

        # Conditional Logic for VACE vs I2V
        if "vace" in file_path.name:
            vace_keys = ["frame_to_skip", "input_a_frames", "input_b_frames", "reference switch", "vace schedule", "reference path", "video file path", "reference image path"]
            standard_keys.update(vace_keys)
            
            spec_fields["frame_to_skip"] = st.number_input("Frame to Skip", value=int(data.get("frame_to_skip", 81)), key=f"{fk}_fts")
            spec_fields["input_a_frames"] = st.number_input("Input A Frames", value=int(data.get("input_a_frames", 0)), key=f"{fk}_ia")
            spec_fields["input_b_frames"] = st.number_input("Input B Frames", value=int(data.get("input_b_frames", 0)), key=f"{fk}_ib")
            spec_fields["reference switch"] = st.number_input("Reference Switch", value=int(data.get("reference switch", 1)), key=f"{fk}_rsw")
            spec_fields["vace schedule"] = st.number_input("VACE Schedule", value=int(data.get("vace schedule", 1)), key=f"{fk}_vsc")
            for f in ["reference path", "video file path", "reference image path"]:
                 spec_fields[f] = st.text_input(f.title(), value=str(data.get(f, "")), key=f"{fk}_{f}")
        
        elif "i2v" in file_path.name:
            i2v_keys = ["reference image path", "flf image path", "video file path"]
            standard_keys.update(i2v_keys)
            
            for f in i2v_keys:
                spec_fields[f] = st.text_input(f.title(), value=str(data.get(f, "")), key=f"{fk}_{f}")

        # --- CUSTOM PARAMETERS ---
        st.markdown("---")
        st.subheader("🔧 Custom Parameters")
        
        # Filter: Any key in data that is NOT in standard_keys is a Custom Key
        custom_keys = [k for k in data.keys() if k not in standard_keys]
        keys_to_remove = []

        if custom_keys:
            for k in custom_keys:
                c1, c2, c3 = st.columns([1, 2, 0.5])
                c1.text_input("Key", value=k, disabled=True, key=f"{fk}_ck_lbl_{k}", label_visibility="collapsed")
                val = c2.text_input("Value", value=str(data[k]), key=f"{fk}_cv_{k}", label_visibility="collapsed")
                data[k] = val 
                
                if c3.button("🗑️", key=f"{fk}_cdel_{k}"):
                    keys_to_remove.append(k)
        else:
            st.caption("No custom keys added.")

        # Add New Interface
        with st.expander("➕ Add New Parameter"):
            nk_col, nv_col = st.columns(2)
            new_k = nk_col.text_input("Key Name", key=f"{fk}_new_k")
            new_v = nv_col.text_input("Value", key=f"{fk}_new_v")
            
            if st.button("Add Parameter", key=f"{fk}_add_cust"):
                if new_k and new_k not in data:
                    data[new_k] = new_v
                    st.rerun()
                elif new_k in data:
                    st.error(f"Key '{new_k}' already exists!")

        # Process removals
        if keys_to_remove:
            for k in keys_to_remove:
                del data[k]
            st.rerun()

    # ==============================================================================
    # RIGHT COLUMN: ACTIONS & TIMELINE
    # ==============================================================================
    with col2:
        # 1. Capture State (Form -> Dict)
        current_state = {
            "general_prompt": gen_prompt, "general_negative": gen_negative,
            "current_prompt": new_prompt, "negative": new_negative,
            "seed": new_seed, **loras, **spec_fields
        }
        
        # Merge Custom Keys into current_state so they are saved
        for k in custom_keys:
            if k not in keys_to_remove:
                current_state[k] = data[k]

        st.session_state.single_editor_cache = current_state

        # 2. Disk Operations
        st.subheader("Actions")
        current_disk_mtime = get_file_mtime(file_path)
        is_conflict = current_disk_mtime > st.session_state.last_mtime
        
        if is_conflict:
            st.error("⚠️ CONFLICT: Disk changed!")
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
            if st.button("💾 Quick Save (Update Disk)", use_container_width=True):
                data.update(current_state)
                st.session_state.last_mtime = save_json(file_path, data)
                st.session_state.data_cache = data
                st.toast("Saved!", icon="✅") 

        st.markdown("---")
        
        # 3. HISTORY TREE TIMELINE
        st.subheader("Timeline & Branching")
        
        # Render Graphviz Tree
        try:
            graph_dot = htree.generate_graphviz()
            st.graphviz_chart(graph_dot, use_container_width=True)
        except Exception as e:
            st.error(f"Graph Error: {e}")

        # Snapshot Controls
        st.caption("Create Snapshot (Commits current state to timeline)")
        c_col1, c_col2 = st.columns([3, 1])
        commit_note = c_col1.text_input("Snapshot Note", placeholder="e.g. Added fog", label_visibility="collapsed", key=f"{fk}_snote")
        
        if c_col2.button("📷 Snap", help="Save Snapshot"):
            # Prepare full snapshot data
            full_snapshot = data.copy()
            full_snapshot.update(current_state)
            
            # Clean recursive keys
            if "history_tree" in full_snapshot: del full_snapshot["history_tree"]
            if "prompt_history" in full_snapshot: del full_snapshot["prompt_history"]
            
            # Commit to Tree
            htree.commit(full_snapshot, note=commit_note if commit_note else "Snapshot")
            
            # Save Tree back to main Data object
            data["history_tree"] = htree.to_dict()
            if "prompt_history" in data: del data["prompt_history"] # Clean legacy
            
            save_json(file_path, data)
            st.session_state.ui_reset_token += 1
            st.toast("Snapshot created!", icon="📸")
            st.rerun()

        st.divider()
        
        # Restore Controls
        all_nodes = htree.nodes.values()
        # Sort chronologically reverse
        sorted_nodes = sorted(all_nodes, key=lambda x: x["timestamp"], reverse=True)
        
        node_options = {n["id"]: f"{n.get('note','Step')} ({n['id']})" for n in sorted_nodes}
        
        if not node_options:
            st.caption("No timeline history yet.")
        else:
            selected_node_id = st.selectbox("Jump to Time:", options=list(node_options.keys()), format_func=lambda x: node_options[x], key=f"{fk}_jumpbox")
            
            if st.button("⏪ Jump / Restore", use_container_width=True):
                restored_data = htree.checkout(selected_node_id)
                if restored_data:
                    # 1. Update working data
                    data.update(restored_data)
                    
                    # 2. Save the HEAD move
                    data["history_tree"] = htree.to_dict()
                    save_json(file_path, data)
                    
                    # 3. Force UI Reset
                    st.session_state.ui_reset_token += 1
                    st.toast(f"Jumped to {node_options[selected_node_id]}", icon="⏪")
                    st.rerun()
