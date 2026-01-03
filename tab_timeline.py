import streamlit as st
import json
import graphviz
import time
from history_tree import HistoryTree
from utils import save_json

def render_timeline_tab(data, file_path):
    tree_data = data.get("history_tree", {})
    if not tree_data:
        st.info("No history timeline exists. Make some changes in the Editor first!")
        return

    htree = HistoryTree(tree_data)

    if 'restored_indicator' in st.session_state and st.session_state.restored_indicator:
        st.info(f"📍 Editing Restored Version: **{st.session_state.restored_indicator}**")

    # --- VIEW SWITCHER ---
    c_title, c_view = st.columns([2, 1])
    c_title.subheader("🕰️ Version History")
    
    view_mode = c_view.radio(
        "View Mode", 
        ["🌳 Horizontal", "🌲 Vertical", "📜 Linear Log"], 
        horizontal=True,
        label_visibility="collapsed"
    )

    # --- RENDER GRAPH VIEWS ---
    if view_mode in ["🌳 Horizontal", "🌲 Vertical"]:
        direction = "LR" if view_mode == "🌳 Horizontal" else "TB"
        try:
            graph_dot = htree.generate_graph(direction=direction)
            st.graphviz_chart(graph_dot, use_container_width=True)
        except Exception as e:
            st.error(f"Graph Error: {e}")
            
    # --- RENDER LINEAR LOG VIEW ---
    elif view_mode == "📜 Linear Log":
        st.caption("A simple chronological list of all snapshots.")
        all_nodes = list(htree.nodes.values())
        all_nodes.sort(key=lambda x: x["timestamp"], reverse=True)
        
        for n in all_nodes:
            is_head = (n["id"] == htree.head_id)
            with st.container():
                c1, c2, c3 = st.columns([0.5, 4, 1])
                with c1:
                    st.markdown("### 📍" if is_head else "### ⚫")
                with c2:
                    note_txt = n.get('note', 'Step')
                    ts = time.strftime('%H:%M:%S', time.localtime(n['timestamp']))
                    if is_head:
                        st.markdown(f"**{note_txt}** (Current)")
                    else:
                        st.write(f"**{note_txt}**")
                    st.caption(f"ID: {n['id'][:6]} • Time: {ts}")
                with c3:
                    if not is_head:
                        if st.button("⏪", key=f"log_rst_{n['id']}", help="Restore this version"):
                            data.update(n["data"])
                            htree.head_id = n['id']
                            data["history_tree"] = htree.to_dict()
                            save_json(file_path, data)
                            st.session_state.ui_reset_token += 1
                            label = f"{n.get('note')} ({n['id'][:4]})"
                            st.session_state.restored_indicator = label
                            st.toast(f"Restored!", icon="🔄")
                            st.rerun()
            st.divider()

    st.markdown("---")

    # --- ACTIONS & SELECTION ---
    col_sel, col_act = st.columns([3, 1])
    
    all_nodes = list(htree.nodes.values())
    all_nodes.sort(key=lambda x: x["timestamp"], reverse=True) 
    
    def fmt_node(n):
        return f"{n.get('note', 'Step')} ({n['id']})"

    with col_sel:
        current_idx = 0
        for i, n in enumerate(all_nodes):
            if n["id"] == htree.head_id:
                current_idx = i
                break
                
        selected_node = st.selectbox(
            "Select Version to Manage:", 
            all_nodes, 
            format_func=fmt_node,
            index=current_idx
        )

    if selected_node:
        node_data = selected_node["data"]
        
        # --- ACTIONS ---
        with col_act:
            st.write(""); st.write("")
            if st.button("⏪ Restore Version", type="primary", use_container_width=True):
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

        # --- DANGER ZONE ---
        st.markdown("---")
        with st.expander("⚠️ Danger Zone (Delete)"):
            st.warning("Deleting a node cannot be undone.")
            if st.button("🗑️ Delete This Node", type="primary"):
                if selected_node['id'] in htree.nodes:
                    del htree.nodes[selected_node['id']]
                    for b, tip in list(htree.branches.items()):
                        if tip == selected_node['id']:
                            del htree.branches[b] 
                    if htree.head_id == selected_node['id']:
                        if htree.nodes:
                            fallback = sorted(htree.nodes.values(), key=lambda x: x["timestamp"])[-1]
                            htree.head_id = fallback["id"]
                        else:
                            htree.head_id = None
                    data["history_tree"] = htree.to_dict()
                    save_json(file_path, data)
                    st.toast("Node Deleted", icon="🗑️")
                    st.rerun()
