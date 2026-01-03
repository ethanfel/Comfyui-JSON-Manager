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

    # --- 1. GRAPH NODES ---
    nodes = []
    edges = []
    
    sorted_nodes = sorted(htree.nodes.values(), key=lambda x: x["timestamp"])
    
    for n in sorted_nodes:
        nid = n["id"]
        note = n.get('note', 'Step')
        short_note = (note[:15] + '..') if len(note) > 15 else note
        
        # Colors
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
        width="100%", height="500px", directed=True, physics=False, hierarchical=True, 
        layout={"hierarchical": {"enabled": True, "levelSeparation": 150, "nodeSpacing": 100, "treeSpacing": 100, "direction": "LR", "sortMethod": "directed"}}
    )

    st.subheader("✨ Interactive Timeline")
    st.caption("Click any node to preview its prompts and settings.")
    
    clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

    st.markdown("---")

    # --- 2. INSPECTOR ---
    target_node_id = clicked_node_id if clicked_node_id else htree.head_id

    if target_node_id and target_node_id in htree.nodes:
        selected_node = htree.nodes[target_node_id]
        node_data = selected_node["data"]

        c_h1, c_h2 = st.columns([3, 1])
        c_h1.markdown(f"### 🔎 Inspecting: {selected_node.get('note', 'Step')}")
        c_h1.caption(f"ID: {target_node_id}")

        # --- COMPARE (Only here) ---
        with st.expander(f"📊 Compare Changes", expanded=False):
            diffs = []
            all_keys = set(data.keys()) | set(node_data.keys())
            ignore_keys = {"history_tree", "prompt_history", "batch_data", "ui_reset_token", "sequence_number"}
            
            for k in all_keys:
                if k in ignore_keys: continue
                val_now = str(data.get(k, "")).strip()
                val_then = str(node_data.get(k, "")).strip()
                
                if val_now != val_then:
                    # Ignore tiny float differences
                    try:
                        if abs(float(val_now) - float(val_then)) < 0.001: continue
                    except: pass
                    diffs.append((k, val_now, val_then))

            if not diffs:
                st.caption("✅ Identical to current state")
            else:
                for k, v_now, v_then in diffs:
                    dc1, dc2, dc3 = st.columns([1, 2, 2])
                    dc1.markdown(f"**{k}**")
                    dc2.markdown(f"🔴 `{v_now[:30]}`")
                    dc3.markdown(f"🟢 `{v_then[:30]}`")
        
        # --- RESTORE ACTION ---
        with c_h2:
            st.write(""); st.write("")
            if st.button("⏪ Restore This Version", type="primary", use_container_width=True):
                data.update(node_data)
                htree.head_id = target_node_id
                data["history_tree"] = htree.to_dict()
                save_json(file_path, data)
                st.session_state.ui_reset_token += 1
                st.session_state.restored_indicator = f"{selected_node.get('note')} ({target_node_id[:4]})"
                st.toast(f"Restored {target_node_id}!", icon="🔄")
                st.rerun()

        # --- PREVIEW (CORRECTED SCHEMA) ---
        st.markdown("#### 📄 Snapshot Preview")
        
        # 1. Prompts
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            val = node_data.get("general_prompt", "")
            st.text_area("General Prompt", value=val, height=80, disabled=True, key="prev_gp")
            
            val_sp = node_data.get("current_prompt", "") or node_data.get("prompt", "")
            st.text_area("Specific Prompt", value=val_sp, height=80, disabled=True, key="prev_sp")
            
        with p_col2:
            val = node_data.get("general_negative", "")
            st.text_area("General Negative", value=val, height=80, disabled=True, key="prev_gn")
            
            val_sn = node_data.get("negative", "")
            st.text_area("Specific Negative", value=val_sn, height=80, disabled=True, key="prev_sn")

        # 2. Key Settings (Camera / FLF / Seed)
        st.caption("Settings")
        s_col1, s_col2, s_col3 = st.columns(3)
        s_col1.text_input("Camera", value=str(node_data.get("camera", "")), disabled=True, key="prev_cam")
        s_col2.text_input("FLF", value=str(node_data.get("flf", "")), disabled=True, key="prev_flf")
        s_col3.text_input("Seed", value=str(node_data.get("seed", "")), disabled=True, key="prev_seed")

        # 3. VACE / I2V Specifics (Conditional)
        vace_keys = ["frame_to_skip", "vace schedule", "video file path"]
        has_vace = any(k in node_data for k in vace_keys)
        
        if has_vace:
            with st.expander("VACE / I2V Settings", expanded=True):
                v1, v2, v3 = st.columns(3)
                v1.text_input("Skip Frames", value=str(node_data.get("frame_to_skip", "")), disabled=True, key="prev_fts")
                v2.text_input("Schedule", value=str(node_data.get("vace schedule", "")), disabled=True, key="prev_vsc")
                v3.text_input("Video Path", value=str(node_data.get("video file path", "")), disabled=True, key="prev_vid")

        # 4. LoRAs
        with st.expander("💊 LoRA Configuration"):
            l1, l2, l3 = st.columns(3)
            l1.text_input("L1", value=f"{node_data.get('lora 1 high','')} : {node_data.get('lora 1 low','')}", disabled=True, key="prev_l1")
            l2.text_input("L2", value=f"{node_data.get('lora 2 high','')} : {node_data.get('lora 2 low','')}", disabled=True, key="prev_l2")
            l3.text_input("L3", value=f"{node_data.get('lora 3 high','')} : {node_data.get('lora 3 low','')}", disabled=True, key="prev_l3")
