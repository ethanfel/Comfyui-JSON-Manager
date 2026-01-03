import streamlit as st
import json
from history_tree import HistoryTree
from utils import save_json, DEFAULTS
from streamlit_agraph import agraph, Node, Edge, Config

def render_timeline_wip(data, file_path):
    tree_data = data.get("history_tree", {})
    if not tree_data:
        st.info("No history timeline exists.")
        return

    htree = HistoryTree(tree_data)

    # ==========================================
    # 1. BUILD GRAPH DATA (NODES & EDGES)
    # ==========================================
    nodes = []
    edges = []
    
    sorted_nodes = sorted(htree.nodes.values(), key=lambda x: x["timestamp"])
    
    for n in sorted_nodes:
        nid = n["id"]
        note = n.get('note', 'Step')
        short_note = (note[:15] + '..') if len(note) > 15 else note
        
        # Default Styles
        color = "#ffffff"     
        border = "#666666"    
        
        # Highlight Head (Current Pointer)
        if nid == htree.head_id:
            color = "#fff6cd" 
            border = "#eebb00"
        
        # Highlight Tips (Ends of branches)
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

    # ==========================================
    # 2. RENDER INTERACTIVE GRAPH
    # ==========================================
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
    st.caption("Click any node to preview its settings and compare changes.")
    
    clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

    st.markdown("---")

    # ==========================================
    # 3. INSPECTION PANEL
    # ==========================================
    target_node_id = clicked_node_id if clicked_node_id else htree.head_id

    if target_node_id and target_node_id in htree.nodes:
        selected_node = htree.nodes[target_node_id]
        node_data = selected_node["data"]

        c_h1, c_h2 = st.columns([3, 1])
        c_h1.markdown(f"### 🔎 Inspecting: {selected_node.get('note', 'Step')}")
        c_h1.caption(f"ID: {target_node_id}")

        # --- A. COMPARE CHANGES (DIFF) ---
        with st.expander(f"📊 Compare Changes", expanded=False):
            diffs = []
            all_keys = set(data.keys()) | set(node_data.keys())
            
            # Keys to ignore in diff view to reduce noise
            ignore_keys = {
                "history_tree", "prompt_history", "batch_data", 
                "ui_reset_token", "sequence_number", 
                "input_a_frames", "input_b_frames"
            }
            
            for k in all_keys:
                if k in ignore_keys: continue
                val_now = data.get(k, "")
                val_then = node_data.get(k, "")
                
                # Convert to string and strip whitespace for clean comparison
                str_now = str(val_now).strip()
                str_then = str(val_then).strip()
                
                if str_now != str_then:
                    # Fuzzy match for numbers (ignore 1 vs 1.0)
                    try:
                        f_now = float(str_now)
                        f_then = float(str_then)
                        if abs(f_now - f_then) < 0.001: continue 
                    except ValueError:
                        pass
                    
                    diffs.append((k, str_now, str_then))

            if not diffs:
                st.caption("✅ Identical to current state")
            else:
                for k, v_now, v_then in diffs:
                    dc1, dc2, dc3 = st.columns([1, 2, 2])
                    dc1.markdown(f"**{k}**")
                    dc2.markdown(f"🔴 `{str(v_now)[:30]}`")
                    dc3.markdown(f"🟢 `{str(v_then)[:30]}`")
        
        # --- B. RESTORE ACTION ---
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

        # --- C. SNAPSHOT PREVIEW (READ ONLY FORM) ---
        st.markdown("#### 📄 Snapshot Preview")
        
        # 1. Prompts (Handles both old 'positive_prompt' and new 'general_prompt' keys)
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            val_p = node_data.get("positive_prompt", "") or node_data.get("general_prompt", "")
            st.text_area("Positive Prompt", value=val_p, height=100, disabled=True, key="prev_pp")
        with p_col2:
            val_n = node_data.get("negative_prompt", "") or node_data.get("general_negative", "")
            st.text_area("Negative Prompt", value=val_n, height=100, disabled=True, key="prev_np")

        # 2. Key Settings
        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
        s_col1.text_input("Seed", value=str(node_data.get("seed", "")), disabled=True, key="prev_seed")
        s_col2.text_input("Steps", value=str(node_data.get("steps", "")), disabled=True, key="prev_steps")
        s_col3.text_input("CFG", value=str(node_data.get("cfg", "")), disabled=True, key="prev_cfg")
        s_col4.text_input("Denoise", value=str(node_data.get("denoise", "")), disabled=True, key="prev_den")

        # 3. Models
        m_col1, m_col2 = st.columns(2)
        m_col1.text_input("Checkpoint", value=node_data.get("model_name", ""), disabled=True, key="prev_ckpt")
        m_col2.text_input("VAE", value=node_data.get("vae_name", ""), disabled=True, key="prev_vae")

        # 4. LoRAs
        with st.expander("💊 LoRA Configuration"):
            l1, l2, l3 = st.columns(3)
            with l1:
                st.text_input("L1 Name", value=node_data.get("lora 1 high", ""), disabled=True, key="prev_l1h")
                st.text_input("L1 Str", value=str(node_data.get("lora 1 low", "")), disabled=True, key="prev_l1l")
            with l2:
                st.text_input("L2 Name", value=node_data.get("lora 2 high", ""), disabled=True, key="prev_l2h")
                st.text_input("L2 Str", value=str(node_data.get("lora 2 low", "")), disabled=True, key="prev_l2l")
            with l3:
                st.text_input("L3 Name", value=node_data.get("lora 3 high", ""), disabled=True, key="prev_l3h")
                st.text_input("L3 Str", value=str(node_data.get("lora 3 low", "")), disabled=True, key="prev_l3l")
