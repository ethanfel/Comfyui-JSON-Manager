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
    
    sorted_nodes = sorted(htree.nodes.values(), key=lambda x: x["timestamp"])
    
    for n in sorted_nodes:
        nid = n["id"]
        note = n.get('note', 'Step')
        short_note = (note[:15] + '..') if len(note) > 15 else note
        
        # Styles
        color = "#ffffff"     
        border = "#666666"    
        
        # Highlight Head
        if nid == htree.head_id:
            color = "#fff6cd" 
            border = "#eebb00"
        
        # Highlight Tips
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

    # --- 2. CONFIGURATION ---
    config = Config(
        width="100%",
        height="500px", 
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
    st.caption("Click any node to inspect changes.")
    
    # RENDER GRAPH
    # key="interactive_graph" ensures the selection persists
    clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

    st.markdown("---")

    # --- 3. IMPROVED INSPECTOR ---
    target_node_id = clicked_node_id if clicked_node_id else htree.head_id

    if target_node_id and target_node_id in htree.nodes:
        selected_node = htree.nodes[target_node_id]
        node_data = selected_node["data"]

        c_h1, c_h2 = st.columns([3, 1])
        c_h1.markdown(f"### 🔎 Inspecting: {selected_node.get('note', 'Step')}")
        c_h1.caption(f"ID: {target_node_id}")

        # --- BETTER DIFF LOGIC ---
        with st.expander(f"Compare with Current State", expanded=True):
            diffs = []
            
            # 1. Gather all unique keys from both sides
            all_keys = set(data.keys()) | set(node_data.keys())
            
            # 2. Define keys to strictly ignore (System / Metadata)
            ignore_keys = {
                "history_tree", "prompt_history", "batch_data", 
                "ui_reset_token", "sequence_number", 
                "input_a_frames", "input_b_frames" # Add any other noisy keys here
            }
            
            for k in all_keys:
                if k in ignore_keys: continue
                
                # 3. Get values, treating Missing as Empty String for comparison
                val_now = data.get(k, "")
                val_then = node_data.get(k, "")
                
                # 4. Normalize types (float 1.0 == int 1 == str "1")
                # We convert everything to string and strip whitespace
                str_now = str(val_now).strip()
                str_then = str(val_then).strip()
                
                # Handle Float/Int mismatch (e.g., "20" vs "20.0")
                if str_now != str_then:
                    try:
                        # Try converting both to float and compare with tolerance
                        f_now = float(str_now)
                        f_then = float(str_then)
                        if abs(f_now - f_then) < 0.001:
                            continue # They are effectively the same number
                    except ValueError:
                        pass # Not numbers, so the string difference is real
                    
                    # If we get here, they are different
                    diffs.append((k, str_now, str_then))

            if not diffs:
                st.caption("✅ Identical to current state (or only ignored keys differ)")
            else:
                for k, v_now, v_then in diffs:
                    dc1, dc2, dc3 = st.columns([1, 2, 2])
                    dc1.markdown(f"**{k}**")
                    # Highlight 'Missing' or empty values clearly
                    disp_now = v_now if v_now else "*(empty)*"
                    disp_then = v_then if v_then else "*(empty)*"
                    
                    dc2.markdown(f"🔴 Current: `{disp_now[:30]}`")
                    dc3.markdown(f"🟢 Selected: `{disp_then[:30]}`")

        # Actions
        with c_h2:
            st.write(""); st.write("")
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
