import streamlit as st
import json
from history_tree import HistoryTree
from utils import save_json
# NEW IMPORTS
from streamlit_agraph import agraph, Node, Edge, Config

def render_timeline_tab(data, file_path):
    tree_data = data.get("history_tree", {})
    if not tree_data:
        st.info("No history timeline exists. Make some changes in the Editor first!")
        return

    htree = HistoryTree(tree_data)

    # 1. STATUS INDICATOR
    if 'restored_indicator' in st.session_state and st.session_state.restored_indicator:
        st.info(f"📍 Editing Restored Version: **{st.session_state.restored_indicator}**")

    # 2. CONVERT TREE TO AGRAPH FORMAT
    nodes = []
    edges = []
    
    # Sort for consistent processing
    sorted_nodes = sorted(htree.nodes.values(), key=lambda x: x["timestamp"])
    
    for n in sorted_nodes:
        nid = n["id"]
        note = n.get('note', 'Step')
        short_note = (note[:15] + '..') if len(note) > 15 else note
        
        # Colors
        color = "#ffffff"     # Default White
        border = "#cccccc"
        shape = "box"
        
        # Highlight HEAD (Current)
        if nid == htree.head_id:
            color = "#fff6cd" # Yellow
            border = "#eebb00"
        
        # Highlight Branch Tips
        if nid in htree.branches.values():
            if color == "#ffffff": 
                color = "#e6ffe6" # Green
                border = "#99cc99"

        # Create Node
        nodes.append(Node(
            id=nid,
            label=f"{short_note}\n{nid[:4]}",
            size=25,
            shape=shape,
            color=color,
            borderWidth=1,
            borderColor=border,
            font={'color': 'black', 'face': 'Arial', 'size': 12}
        ))
        
        # Create Edge
        if n["parent"] and n["parent"] in htree.nodes:
            edges.append(Edge(
                source=n["parent"],
                target=nid,
                color="#aaaaaa",
                type="STRAIGHT" # Keeps timeline looking clean
            ))

    # 3. CONFIGURE GRAPH VISUALS
    config = Config(
        width="100%",
        height=300,  # Fixed height! Solves "Way too big" issue.
        directed=True, 
        physics=False, # Disable physics for a rigid timeline structure
        hierarchical=True, # Force Tree Layout
        direction="LR", # Left to Right
        sortMethod="directed",
        levelSeparation=150, # Space between time steps
        nodeSpacing=100
    )

    st.subheader("🕰️ Interactive Timeline")
    st.caption("Scroll to Zoom • Drag to Pan • Click to Inspect")
    
    # 4. RENDER & CAPTURE CLICK
    # agraph returns the 'id' of the clicked node, or None
    clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

    st.markdown("---")

    # 5. DETERMINE INSPECTION TARGET
    # Priority: Clicked Node > Dropdown > Head
    
    # Helper list for dropdown
    all_nodes_list = list(htree.nodes.values())
    all_nodes_list.sort(key=lambda x: x["timestamp"], reverse=True)
    
    target_node_id = None
    
    # If user clicked graph, use that
    if clicked_node_id:
        target_node_id = clicked_node_id
    else:
        # Fallback to current HEAD
        target_node_id = htree.head_id

    # 6. INSPECTOR UI
    if target_node_id and target_node_id in htree.nodes:
        selected_node = htree.nodes[target_node_id]
        node_data = selected_node["data"]

        # Header
        c_h1, c_h2 = st.columns([3, 1])
        c_h1.markdown(f"### 🔎 Inspecting: {selected_node.get('note', 'Step')}")
        c_h1.caption(f"ID: {target_node_id}")

        # --- A. DIFF VIEWER ---
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

        # --- B. ACTIONS ---
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

        # --- C. RENAME ---
        rn_col1, rn_col2 = st.columns([3, 1])
        new_label = rn_col1.text_input("Rename Label", value=selected_node.get("note", ""))
        if rn_col2.button("Update"):
            selected_node["note"] = new_label
            data["history_tree"] = htree.to_dict()
            save_json(file_path, data)
            st.rerun()
