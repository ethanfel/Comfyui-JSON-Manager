import streamlit as st
import json
from history_tree import HistoryTree
from utils import save_json
from streamlit_agraph import agraph, Node, Edge, Config

def render_timeline_tab(data, file_path):
    tree_data = data.get("history_tree", {})
    if not tree_data:
        st.info("No history timeline exists. Make some changes in the Editor first!")
        return

    htree = HistoryTree(tree_data)

    if 'restored_indicator' in st.session_state and st.session_state.restored_indicator:
        st.info(f"📍 Editing Restored Version: **{st.session_state.restored_indicator}**")

    # --- 1. BUILD NODES & EDGES ---
    nodes = []
    edges = []
    
    sorted_nodes = sorted(htree.nodes.values(), key=lambda x: x["timestamp"])
    
    for n in sorted_nodes:
        nid = n["id"]
        note = n.get('note', 'Step')
        # Shorten note for the visual bubble
        short_note = (note[:15] + '..') if len(note) > 15 else note
        
        # Styles
        color = "#ffffff"     # White background
        border = "#666666"    # Grey border
        
        # Current Head
        if nid == htree.head_id:
            color = "#fff6cd" # Yellow
            border = "#eebb00"
        
        # Branch Tips
        if nid in htree.branches.values():
            if color == "#ffffff": 
                color = "#e6ffe6" # Green
                border = "#44aa44"

        nodes.append(Node(
            id=nid,
            label=f"{short_note}\n({nid[:4]})",
            size=25,
            shape="box",
            color=color,
            borderWidth=1,
            borderColor=border,
            # Force black text so it's visible on light nodes
            font={'color': 'black', 'face': 'Arial', 'size': 14}
        ))
        
        if n["parent"] and n["parent"] in htree.nodes:
            edges.append(Edge(
                source=n["parent"],
                target=nid,
                color="#aaaaaa",
            ))

    # --- 2. CONFIGURATION (THE FIX) ---
    config = Config(
        width="100%",
        height="500px", # FIXED: Must be a string with 'px'
        directed=True, 
        physics=False,  # Keep False for rigid timeline
        hierarchical=True, 
        # Detailed Hierarchy Settings to prevent layout collapse
        layout={
            "hierarchical": {
                "enabled": True,
                "levelSeparation": 150,
                "nodeSpacing": 100,
                "treeSpacing": 100,
                "direction": "LR", # Left to Right
                "sortMethod": "directed"
            }
        }
    )

    st.subheader("🕰️ Interactive Timeline")
    st.caption("Scroll to Zoom • Drag to Pan • Click to Inspect")
    
    # 3. RENDER
    # If this still shows black, try changing physics=True briefly
    clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

    st.markdown("---")

    # 4. INSPECTION LOGIC
    # Helper list for dropdown
    all_nodes_list = list(htree.nodes.values())
    all_nodes_list.sort(key=lambda x: x["timestamp"], reverse=True)
    
    target_node_id = None
    
    if clicked_node_id:
        target_node_id = clicked_node_id
    else:
        target_node_id = htree.head_id

    if target_node_id and target_node_id in htree.nodes:
        selected_node = htree.nodes[target_node_id]
        node_data = selected_node["data"]

        c_h1, c_h2 = st.columns([3, 1])
        c_h1.markdown(f"### 🔎 Inspecting: {selected_node.get('note', 'Step')}")
        c_h1.caption(f"ID: {target_node_id}")

        with st.expander(f"Compare with Current State", expanded=True):
            diffs = []
            all_keys = set(data.keys()) | set(node_data.keys())
            ignore_keys = {"history_tree", "prompt_history", "batch_data", "ui_reset_token"}
            
            for k in all_keys:
                if k in ignore_keys: continue
                val_now = data.get(k, "N/A")
                val_then = node_data.get(k, "N/A")
                if str(val_now) != str(val_then):
                    diffs.append((k, val_now, val_then))

            if not diffs:
                st.caption("✅ Identical to current state")
            else:
                for k, v_now, v_then in diffs:
                    dc1, dc2, dc3 = st.columns([1, 2, 2])
                    dc1.markdown(f"**{k}**")
                    dc2.markdown(f"🔴 `{str(v_now)[:30]}`")
                    dc3.markdown(f"🟢 `{str(v_then)[:30]}`")

        with c_h2:
            st.write("")
            if st.button("⏪ Restore Version", type="primary", use_container_width=True):
                data.update(node_data)
                htree.head_id = target_node_id
                
                data["history_tree"] = htree.to_dict()
                save_json(file_path, data)
                
                st.session_state.ui_reset_token += 1
                
                label = f"{selected_node.get('note')} ({target_node_id[:4]})"
                st.session_state.restored_indicator = label
                
                st.toast(f"Restored {target_node_id}!", icon="🔄")
                st.rerun()

        rn_col1, rn_col2 = st.columns([3, 1])
        new_label = rn_col1.text_input("Rename Label", value=selected_node.get("note", ""))
        if rn_col2.button("Update"):
            selected_node["note"] = new_label
            data["history_tree"] = htree.to_dict()
            save_json(file_path, data)
            st.rerun()
