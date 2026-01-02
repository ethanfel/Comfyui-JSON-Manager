import streamlit as st
import json
import graphviz
from history_tree import HistoryTree
from utils import save_json

def render_timeline_tab(data, file_path):
    # 1. Initialize Tree
    tree_data = data.get("history_tree", {})
    if not tree_data:
        st.info("No history timeline exists for this file yet. Make some changes in the Editor first!")
        return

    htree = HistoryTree(tree_data)

    # 2. Horizontal Visualizer (Fusion 360 Style)
    st.subheader("🕰️ Version History")
    try:
        graph_dot = htree.generate_horizontal_graph()
        st.graphviz_chart(graph_dot, use_container_width=True)
    except Exception as e:
        st.error(f"Graph Error (Ensure 'graphviz' is installed in Docker): {e}")

    st.markdown("---")

    # 3. The "Scrubber" / Inspector
    col_sel, col_act = st.columns([3, 1])
    
    all_nodes = list(htree.nodes.values())
    all_nodes.sort(key=lambda x: x["timestamp"], reverse=True) # Newest first
    
    def fmt_node(n):
        return f"{n.get('note', 'Step')} ({n['id']})"

    with col_sel:
        current_idx = 0
        for i, n in enumerate(all_nodes):
            if n["id"] == htree.head_id:
                current_idx = i
                break
                
        selected_node = st.selectbox(
            "Inspect Node (Select to View/Edit):", 
            all_nodes, 
            format_func=fmt_node,
            index=current_idx
        )

    # 4. The Editor (Inspector Panel)
    if selected_node:
        node_data = selected_node["data"]
        
        st.info(f"Viewing State: **{selected_node.get('note')}** (ID: {selected_node['id']})")
        
        with st.expander("📝 View / Edit Data for this Point", expanded=True):
            edited_json_str = st.text_area(
                "Raw Data (JSON)", 
                value=json.dumps(node_data, indent=4), 
                height=300
            )
        
        # 5. Restore / Branch Button
        with col_act:
            st.write("") 
            st.write("")
            if st.button("⏪ Restore & Branch", type="primary", use_container_width=True):
                try:
                    new_data_content = json.loads(edited_json_str)
                    
                    # 1. Update the Main Data
                    data.update(new_data_content)
                    
                    # 2. Move Head
                    htree.head_id = selected_node['id']
                    
                    # 3. Save to Disk
                    data["history_tree"] = htree.to_dict()
                    save_json(file_path, data)
                    
                    # 4. Reset UI
                    st.session_state.ui_reset_token += 1
                    
                    # FIXED: Changed icon to standard 'Refresh' emoji
                    st.toast(f"Restored to {selected_node['id']}!", icon="🔄")
                    st.rerun()
                    
                except json.JSONDecodeError:
                    st.error("Invalid JSON format in editor.")

    # 6. Delete Option
    with st.expander("Danger Zone"):
        if st.button("🗑️ Delete this History Node"):
            if selected_node['id'] in htree.nodes:
                del htree.nodes[selected_node['id']]
                # Fix branches pointing to this
                for b, tip in list(htree.branches.items()):
                    if tip == selected_node['id']:
                        del htree.branches[b] 
                
                data["history_tree"] = htree.to_dict()
                save_json(file_path, data)
                st.rerun()
