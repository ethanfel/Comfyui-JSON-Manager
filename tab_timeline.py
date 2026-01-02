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
        st.info(f"📍 You are currently viewing restored version: **{st.session_state.restored_indicator}**")

    # 2. Horizontal Visualizer (Compact)
    st.caption("Timeline")
    try:
        graph_dot = htree.generate_horizontal_graph()
        st.graphviz_chart(graph_dot, use_container_width=True)
    except Exception as e:
        st.error(f"Graph Error: {e}")

    st.markdown("---")

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
            "Inspect Node:", 
            all_nodes, 
            format_func=fmt_node,
            index=current_idx
        )

    if selected_node:
        node_data = selected_node["data"]
        
        with st.expander(f"📝 Data Inspector: {selected_node.get('note')}", expanded=False):
            edited_json_str = st.text_area(
                "Raw Data", 
                value=json.dumps(node_data, indent=4), 
                height=300
            )
        
        with col_act:
            st.write(""); st.write("")
            if st.button("⏪ Restore", type="primary", use_container_width=True):
                try:
                    new_data_content = json.loads(edited_json_str)
                    data.update(new_data_content)
                    htree.head_id = selected_node['id']
                    
                    data["history_tree"] = htree.to_dict()
                    save_json(file_path, data)
                    
                    st.session_state.ui_reset_token += 1
                    
                    # SET INDICATOR
                    node_label = f"{selected_node.get('note', 'Step')} ({selected_node['id'][:4]})"
                    st.session_state.restored_indicator = node_label
                    
                    st.toast(f"Restored to {selected_node['id']}!", icon="🔄")
                    st.rerun()
                    
                except json.JSONDecodeError:
                    st.error("Invalid JSON format.")

    with st.expander("Danger Zone"):
        if st.button("🗑️ Delete Node"):
            if selected_node['id'] in htree.nodes:
                del htree.nodes[selected_node['id']]
                for b, tip in list(htree.branches.items()):
                    if tip == selected_node['id']:
                        del htree.branches[b] 
                
                data["history_tree"] = htree.to_dict()
                save_json(file_path, data)
                st.rerun()
