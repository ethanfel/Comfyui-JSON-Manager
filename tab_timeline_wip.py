import streamlit as st
import json
from history_tree import HistoryTree
from utils import save_json
from streamlit_agraph import agraph, Node, Edge, Config

def render_timeline_wip(data, file_path):
    tree_data = data.get("history_tree", {})
    if not tree_data:
        st.info("No history timeline exists.")
        return

    htree = HistoryTree(tree_data)

    # --- 1. BUILD GRAPH ---
    nodes = []
    edges = []
    
    sorted_nodes = sorted(htree.nodes.values(), key=lambda x: x["timestamp"])
    
    for n in sorted_nodes:
        nid = n["id"]
        note = n.get('note', 'Step')
        short_note = (note[:15] + '..') if len(note) > 15 else note
        
        color = "#ffffff"     
        border = "#666666"    
        
        if nid == htree.head_id:
            color = "#fff6cd" 
            border = "#eebb00"
        
        if nid in htree.branches.values():
            if color == "#ffffff": 
                color = "#e6ffe6"
                border = "#44aa44"

        nodes.append(Node(
            id=nid,
            label=f"{short_note}\n({nid[:4]})",
            size=25,
            shape="box",
            color=color,
            borderWidth=1,
            borderColor=border,
            font={'color': 'black', 'face': 'Arial', 'size': 14}
        ))
        
        if n["parent"] and n["parent"] in htree.nodes:
            edges.append(Edge(
                source=n["parent"],
                target=nid,
                color="#aaaaaa",
                type="STRAIGHT"
            ))

    config = Config(
        width="100%",
        height="800px", 
        directed=True, 
        physics=False, 
        hierarchical=True, 
        layout={
            "hierarchical": {
                "enabled": True,
                "levelSeparation": 150,
                "nodeSpacing": 100,
                "treeSpacing": 100,
                "direction": "LR", 
                "sortMethod": "directed"
            }
        }
    )

    st.subheader("✨ Interactive Timeline")
    st.caption("Click a node to view its settings below.")
    
    # --- FIX: REMOVED 'key' ARGUMENT ---
    selected_id = agraph(nodes=nodes, edges=edges, config=config)

    st.markdown("---")

    # --- 2. DETERMINE TARGET ---
    target_node_id = selected_id if selected_id else htree.head_id

    if target_node_id and target_node_id in htree.nodes:
        selected_node = htree.nodes[target_node_id]
        node_data = selected_node["data"]

        # Header
        c_h1, c_h2 = st.columns([3, 1])
        c_h1.markdown(f"### 📄 Previewing: {selected_node.get('note', 'Step')}")
        c_h1.caption(f"ID: {target_node_id}")

        # Restore Button
        with c_h2:
            st.write(""); st.write("")
            if st.button("⏪ Restore This Version", type="primary", use_container_width=True, key=f"rst_{target_node_id}"):
                # --- FIX: Cleanup 'batch_data' if restoring a Single File ---
                if "batch_data" not in node_data and "batch_data" in data:
                    del data["batch_data"]
                # -------------------------------------------------------------

                data.update(node_data)
                htree.head_id = target_node_id
                
                data["history_tree"] = htree.to_dict()
                save_json(file_path, data)
                
                st.session_state.ui_reset_token += 1
                label = f"{selected_node.get('note')} ({target_node_id[:4]})"
                st.session_state.restored_indicator = label
                
                st.toast(f"Restored {target_node_id}!", icon="🔄")
                st.rerun()

        # --- 3. PREVIEW LOGIC (BATCH VS SINGLE) ---
        
        # Helper to render one set of inputs
        def render_preview_fields(item_data, prefix):
            # A. Prompts
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                val_gp = item_data.get("general_prompt", "")
                st.text_area("General Positive", value=val_gp, height=80, disabled=True, key=f"{prefix}_gp")
                
                val_sp = item_data.get("current_prompt", "") or item_data.get("prompt", "")
                st.text_area("Specific Positive", value=val_sp, height=80, disabled=True, key=f"{prefix}_sp")
            with p_col2:
                val_gn = item_data.get("general_negative", "")
                st.text_area("General Negative", value=val_gn, height=80, disabled=True, key=f"{prefix}_gn")
                
                val_sn = item_data.get("negative", "")
                st.text_area("Specific Negative", value=val_sn, height=80, disabled=True, key=f"{prefix}_sn")

            # B. Settings
            s_col1, s_col2, s_col3 = st.columns(3)
            s_col1.text_input("Camera", value=str(item_data.get("camera", "static")), disabled=True, key=f"{prefix}_cam")
            s_col2.text_input("FLF", value=str(item_data.get("flf", "0.0")), disabled=True, key=f"{prefix}_flf")
            s_col3.text_input("Seed", value=str(item_data.get("seed", "-1")), disabled=True, key=f"{prefix}_seed")

            # C. LoRAs
            with st.expander("💊 LoRA Configuration", expanded=False):
                l1, l2, l3 = st.columns(3)
                with l1:
                    st.text_input("L1 Name", value=item_data.get("lora 1 high", ""), disabled=True, key=f"{prefix}_l1h")
                    st.text_input("L1 Str", value=str(item_data.get("lora 1 low", "")), disabled=True, key=f"{prefix}_l1l")
                with l2:
                    st.text_input("L2 Name", value=item_data.get("lora 2 high", ""), disabled=True, key=f"{prefix}_l2h")
                    st.text_input("L2 Str", value=str(item_data.get("lora 2 low", "")), disabled=True, key=f"{prefix}_l2l")
                with l3:
                    st.text_input("L3 Name", value=item_data.get("lora 3 high", ""), disabled=True, key=f"{prefix}_l3h")
                    st.text_input("L3 Str", value=str(item_data.get("lora 3 low", "")), disabled=True, key=f"{prefix}_l3l")
            
            # D. VACE
            vace_keys = ["frame_to_skip", "vace schedule", "video file path"]
            has_vace = any(k in item_data for k in vace_keys)
            if has_vace:
                with st.expander("🎞️ VACE / I2V Settings", expanded=False):
                    v1, v2, v3 = st.columns(3)
                    v1.text_input("Skip Frames", value=str(item_data.get("frame_to_skip", "")), disabled=True, key=f"{prefix}_fts")
                    v2.text_input("Schedule", value=str(item_data.get("vace schedule", "")), disabled=True, key=f"{prefix}_vsc")
                    v3.text_input("Video Path", value=str(item_data.get("video file path", "")), disabled=True, key=f"{prefix}_vid")

        # --- DETECT BATCH VS SINGLE ---
        batch_list = node_data.get("batch_data", [])
        
        if batch_list and isinstance(batch_list, list) and len(batch_list) > 0:
            st.info(f"📚 This snapshot contains {len(batch_list)} sequences.")
            
            for i, seq_data in enumerate(batch_list):
                seq_num = seq_data.get("sequence_number", i+1)
                with st.expander(f"🎬 Sequence #{seq_num}", expanded=(i==0)):
                    # Unique prefix for every sequence in every node
                    prefix = f"p_{target_node_id}_s{i}"
                    render_preview_fields(seq_data, prefix)
        else:
            # Single File Preview
            prefix = f"p_{target_node_id}_single"
            render_preview_fields(node_data, prefix)
