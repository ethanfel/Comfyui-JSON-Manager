import streamlit as st
import json
import graphviz
from history_tree import HistoryTree
from utils import save_json

def render_timeline_tab(data, file_path):
    tree_data = data.get("history_tree", {})
    if not tree_data:
        st.info("No history timeline exists. Make some changes in the Editor first!")
        return

    htree = HistoryTree(tree_data)

    # 1. INDICATOR
    if 'restored_indicator' in st.session_state and st.session_state.restored_indicator:
        st.info(f"📍 Editing Restored Version: **{st.session_state.restored_indicator}**")

    # 2. GRAPH (Compact & Clean)
    st.subheader("🕰️ Version History")
    try:
        graph_dot = htree.generate_horizontal_graph()
        st.graphviz_chart(graph_dot, use_container_width=True)
    except Exception as e:
        st.error(f"Graph Error: {e}")

    st.markdown("---")

    # 3. SELECTOR (Navigation)
    col_sel, col_act = st.columns([3, 1])
    
    all_nodes = list(htree.nodes.values())
    all_nodes.sort(key=lambda x: x["timestamp"], reverse=True) 
    
    def fmt_node(n):
        return f"{n.get('note', 'Step')} ({n['id']})"

    with col_sel:
        # Default to Head
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

    # 4. INSPECTOR
    if selected_node:
        node_data = selected_node["data"]
        
        # --- DIFF VIEWER ---
        with st.expander(f"🔎 Compare '{selected_node.get('note')}' with Current State", expanded=True):
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

        # --- ACTIONS ---
        with col_act:
            st.write(""); st.write("")
            if st.button("⏪ Restore", type="primary", use_container_width=True):
                data.update(node_data)
                htree.head_id = selected_node['id']
                
                data["history_tree"] = htree.to_dict()
                save_json(file_path, data)
                
                st.session_state.ui_reset_token += 1
                
                label = f"{selected_node.get('note')} ({selected_node['id'][:4]})"
                st.session_state.restored_indicator = label
                
                st.toast(f"Restored!", icon="🔄")
                st.rerun()

        # --- RENAME ---
        rn_col1, rn_col2 = st.columns([3, 1])
        new_label = rn_col1.text_input("Rename Label", value=selected_node.get("note", ""))
        if rn_col2.button("Update Label"):
            selected_node["note"] = new_label
            data["history_tree"] = htree.to_dict()
            save_json(file_path, data)
            st.rerun()
