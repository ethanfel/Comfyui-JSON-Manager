import streamlit as st
import json
import graphviz
from history_tree import HistoryTree
from utils import save_json

def render_timeline_tab(data, file_path):
    tree_data = data.get("history_tree", {})
    if not tree_data:
        st.info("No history timeline exists for this file yet. Make some changes in the Editor first!")
        return

    htree = HistoryTree(tree_data)

    # 1. STATUS INDICATOR
    if 'restored_indicator' in st.session_state and st.session_state.restored_indicator:
        st.info(f"📍 Editing Restored Version: **{st.session_state.restored_indicator}**")

    # 2. COMPACT VISUALIZER
    st.subheader("🕰️ Version History")
    try:
        graph_dot = htree.generate_horizontal_graph()
        st.graphviz_chart(graph_dot, use_container_width=True)
    except Exception as e:
        st.error(f"Graph Error: {e}")

    st.markdown("---")

    # 3. INSPECTOR AREA
    col_sel, col_act = st.columns([3, 1])
    
    all_nodes = list(htree.nodes.values())
    all_nodes.sort(key=lambda x: x["timestamp"], reverse=True) 
    
    def fmt_node(n):
        return f"{n.get('note', 'Step')} ({n['id']})"

    with col_sel:
        # Auto-select HEAD if possible
        current_idx = 0
        for i, n in enumerate(all_nodes):
            if n["id"] == htree.head_id:
                current_idx = i
                break
                
        selected_node = st.selectbox(
            "Inspect Node:", 
            all_nodes, 
            format_func=fmt_node,
            index=current_idx
        )

    # 4. SMART INSPECTOR
    if selected_node:
        node_data = selected_node["data"]
        
        # --- A. DIFF VIEWER (NEW) ---
        # Calculate differences between CURRENT Data and SELECTED Node
        diffs = []
        
        # Compare keys
        all_keys = set(data.keys()) | set(node_data.keys())
        ignore_keys = {"history_tree", "prompt_history", "batch_data", "ui_reset_token"}
        
        for k in all_keys:
            if k in ignore_keys: continue
            
            val_now = data.get(k, "N/A")
            val_then = node_data.get(k, "N/A")
            
            if str(val_now) != str(val_then):
                diffs.append((k, val_now, val_then))

        with st.expander(f"🔍 Delta Inspector (Differences from Current)", expanded=True):
            if not diffs:
                st.caption("✅ This node is identical to your current state.")
            else:
                for k, v_now, v_then in diffs:
                    c1, c2, c3 = st.columns([1, 2, 2])
                    c1.markdown(f"**{k}**")
                    c2.markdown(f"🔴 Current: `{str(v_now)[:50]}`")
                    c3.markdown(f"🟢 Selected: `{str(v_then)[:50]}`")

        # --- B. RENAME TOOL (NEW) ---
        c_ren1, c_ren2 = st.columns([3, 1])
        new_note = c_ren1.text_input("Rename Node Label", value=selected_node.get("note", ""))
        if c_ren2.button("Update Label"):
            selected_node["note"] = new_note
            data["history_tree"] = htree.to_dict()
            save_json(file_path, data)
            st.rerun()

        # --- C. RESTORE BUTTON ---
        with col_act:
            st.write(""); st.write("")
            if st.button("⏪ Restore", type="primary", use_container_width=True):
                # Restore Logic
                data.update(node_data)
                htree.head_id = selected_node['id']
                
                data["history_tree"] = htree.to_dict()
                save_json(file_path, data)
                
                st.session_state.ui_reset_token += 1
                
                # Set Indicator
                node_label = f"{selected_node.get('note', 'Step')} ({selected_node['id'][:4]})"
                st.session_state.restored_indicator = node_label
                
                st.toast(f"Restored to {selected_node['id']}!", icon="🔄")
                st.rerun()

    # 5. RAW DATA & DELETE
    with st.expander("Advanced Options (Raw JSON & Delete)"):
        st.json(node_data, expanded=False)
        if st.button("🗑️ Delete Node"):
            if selected_node['id'] in htree.nodes:
                del htree.nodes[selected_node['id']]
                for b, tip in list(htree.branches.items()):
                    if tip == selected_node['id']:
                        del htree.branches[b] 
                
                data["history_tree"] = htree.to_dict()
                save_json(file_path, data)
                st.rerun()
