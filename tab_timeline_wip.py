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
        height="400px", 
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
    
    # Render Graph
    selected_id = agraph(nodes=nodes, edges=edges, config=config)

    st.markdown("---")

    # --- 2. DETERMINE TARGET ---
    # Default to HEAD if nothing clicked
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
                data.update(node_data)
                htree.head_id = target_node_id
                
                data["history_tree"] = htree.to_dict()
                save_json(file_path, data)
                
                st.session_state.ui_reset_token += 1
                label = f"{selected_node.get('note')} ({target_node_id[:4]})"
                st.session_state.restored_indicator = label
                
                st.toast(f"Restored {target_node_id}!", icon="🔄")
                st.rerun()

        # --- 3. PREVIEW PANELS (DYNAMIC KEYS FIX) ---
        # We append target_node_id to every key to force a hard refresh
        
        # A. Prompts
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            val_gp = node_data.get("general_prompt", "")
            st.text_area("General Positive", value=val_gp, height=80, disabled=True, key=f"p_gp_{target_node_id}")
            
            val_sp = node_data.get("current_prompt", "") or node_data.get("prompt", "")
            st.text_area("Specific Positive", value=val_sp, height=80, disabled=True, key=f"p_sp_{target_node_id}")
            
        with p_col2:
            val_gn = node_data.get("general_negative", "")
            st.text_area("General Negative", value=val_gn, height=80, disabled=True, key=f"p_gn_{target_node_id}")
            
            val_sn = node_data.get("negative", "")
            st.text_area("Specific Negative", value=val_sn, height=80, disabled=True, key=f"p_sn_{target_node_id}")

        # B. Key Settings
        st.caption("⚙️ Core Settings")
        s_col1, s_col2, s_col3 = st.columns(3)
        s_col1.text_input("Camera", value=str(node_data.get("camera", "static")), disabled=True, key=f"p_cam_{target_node_id}")
        s_col2.text_input("FLF", value=str(node_data.get("flf", "0.0")), disabled=True, key=f"p_flf_{target_node_id}")
        s_col3.text_input("Seed", value=str(node_data.get("seed", "-1")), disabled=True, key=f"p_seed_{target_node_id}")

        # C. LoRAs
        with st.expander("💊 LoRA Configuration", expanded=False):
            l1, l2, l3 = st.columns(3)
            with l1:
                st.text_input("LoRA 1 Name", value=node_data.get("lora 1 high", ""), disabled=True, key=f"p_l1h_{target_node_id}")
                st.text_input("LoRA 1 Str", value=str(node_data.get("lora 1 low", "")), disabled=True, key=f"p_l1l_{target_node_id}")
            with l2:
                st.text_input("LoRA 2 Name", value=node_data.get("lora 2 high", ""), disabled=True, key=f"p_l2h_{target_node_id}")
                st.text_input("LoRA 2 Str", value=str(node_data.get("lora 2 low", "")), disabled=True, key=f"p_l2l_{target_node_id}")
            with l3:
                st.text_input("LoRA 3 Name", value=node_data.get("lora 3 high", ""), disabled=True, key=f"p_l3h_{target_node_id}")
                st.text_input("LoRA 3 Str", value=str(node_data.get("lora 3 low", "")), disabled=True, key=f"p_l3l_{target_node_id}")

        # D. VACE / I2V Specifics
        vace_keys = ["frame_to_skip", "vace schedule", "video file path"]
        has_vace = any(k in node_data for k in vace_keys)
        
        if has_vace:
            with st.expander("🎞️ VACE / I2V Settings", expanded=True):
                v1, v2, v3 = st.columns(3)
                v1.text_input("Skip Frames", value=str(node_data.get("frame_to_skip", "")), disabled=True, key=f"p_fts_{target_node_id}")
                v2.text_input("Schedule", value=str(node_data.get("vace schedule", "")), disabled=True, key=f"p_vsc_{target_node_id}")
                v3.text_input("Video Path", value=str(node_data.get("video file path", "")), disabled=True, key=f"p_vid_{target_node_id}")
