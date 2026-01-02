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

    # --- 1. PREPARE NODES & EDGES ---
    nodes = []
    edges = []
    
    # Sort nodes to ensure consistent rendering order
    sorted_nodes = sorted(htree.nodes.values(), key=lambda x: x["timestamp"])
    
    for n in sorted_nodes:
        nid = n["id"]
        note = n.get('note', 'Step')
        # Shorten text for the bubble
        short_note = (note[:15] + '..') if len(note) > 15 else note
        
        # Color Logic
        color = "#ffffff"     # Default White
        border = "#666666"    # Grey border
        
        if nid == htree.head_id:
            color = "#fff6cd" # Yellow (Current)
            border = "#eebb00"
        
        if nid in htree.branches.values():
            if color == "#ffffff": 
                color = "#e6ffe6" # Green (Tips)
                border = "#44aa44"

        nodes.append(Node(
            id=nid,
            label=f"{short_note}\n({nid[:4]})",
            size=25,
            shape="box",
            color=color,
            borderWidth=1,
            borderColor=border,
            # Force text to black so it's readable
            font={'color': 'black', 'face': 'Arial', 'size': 14}
        ))
        
        if n["parent"] and n["parent"] in htree.nodes:
            edges.append(Edge(
                source=n["parent"],
                target=nid,
                color="#aaaaaa",
                type="STRAIGHT" # Keeps lines clean
            ))

    # --- 2. ROBUST CONFIGURATION ---
    # This specific config block is key to fixing the blank screen
    config = Config(
        width="100%",
        height="500px",  # MUST be string with px
        directed=True, 
        physics=False,   # False = Rigid Tree (Better for timelines)
        hierarchical=True, 
        layout={
            "hierarchical": {
                "enabled": True,
                "levelSeparation": 150,
                "nodeSpacing": 100,
                "treeSpacing": 100,
                "direction": "LR", # Left-to-Right
                "sortMethod": "directed"
            }
        }
    )

    st.subheader("🧪 Interactive Playground")
    st.caption("Click any node to load it into the inspector below.")
    
    # Render Graph
    # This returns the ID of the node you click
    clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

    st.markdown("---")

    # --- 3. INTERACTIVE INSPECTOR ---
    # Determine which node to show
    target_node_id = clicked_node_id if clicked_node_id else htree.head_id

    if target_node_id and target_node_id in htree.nodes:
        selected_node = htree.nodes[target_node_id]
        node_data = selected_node["data"]

        c_h1, c_h2 = st.columns([3, 1])
        c_h1.markdown(f"### 🔎 Inspecting: {selected_node.get('note', 'Step')}")
        c_h1.caption(f"ID: {target_node_id}")

        # Diff View
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

        # Actions
        with c_h2:
            st.write(""); st.write("")
            if st.button("⏪ Restore This Version", type="primary", use_container_width=True):
                data.update(node_data)
                htree.head_id = target_node_id
                
                data["history_tree"] = htree.to_dict()
                save_json(file_path, data)
                
                st.session_state.ui_reset_token += 1
                
                label = f"{selected_node.get('note')} ({target_node_id[:4]})"
                st.session_state.restored_indicator = label
                
                st.toast(f"Restored {target_node_id}!", icon="🔄")
                st.rerun()
