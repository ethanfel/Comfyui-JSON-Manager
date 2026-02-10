import streamlit as st
import copy
import time
from history_tree import HistoryTree
from utils import save_json, KEY_BATCH_DATA, KEY_HISTORY_TREE

try:
    from streamlit_agraph import agraph, Node, Edge, Config
    AGRAPH_AVAILABLE = True
except ImportError:
    AGRAPH_AVAILABLE = False


def render_timeline_tab(data, file_path):
    tree_data = data.get(KEY_HISTORY_TREE, {})
    if not tree_data:
        st.info("No history timeline exists. Make some changes in the Editor first!")
        return

    htree = HistoryTree(tree_data)

    # --- Initialize selection state ---
    if "timeline_selected_nodes" not in st.session_state:
        st.session_state.timeline_selected_nodes = set()

    if 'restored_indicator' in st.session_state and st.session_state.restored_indicator:
        st.info(f"📍 Editing Restored Version: **{st.session_state.restored_indicator}**")

    # --- VIEW SWITCHER + SELECTION MODE ---
    c_title, c_view, c_toggle = st.columns([2, 1, 0.6])
    c_title.subheader("🕰️ Version History")

    view_mode = c_view.radio(
        "View Mode",
        ["🌳 Horizontal", "🌲 Vertical", "📜 Linear Log"],
        horizontal=True,
        label_visibility="collapsed"
    )

    selection_mode = c_toggle.toggle("Select to Delete", key="timeline_selection_mode")
    if not selection_mode:
        st.session_state.timeline_selected_nodes = set()

    # --- Build sorted node list (shared by all views) ---
    all_nodes = list(htree.nodes.values())
    all_nodes.sort(key=lambda x: x["timestamp"], reverse=True)

    # --- RENDER GRAPH VIEWS ---
    if view_mode in ["🌳 Horizontal", "🌲 Vertical"]:
        direction = "LR" if view_mode == "🌳 Horizontal" else "TB"

        if AGRAPH_AVAILABLE:
            # Interactive graph with streamlit-agraph
            selected_set = st.session_state.timeline_selected_nodes if selection_mode else set()
            clicked_node = _render_interactive_graph(htree, direction, selected_set)
            if clicked_node and clicked_node in htree.nodes:
                if selection_mode:
                    # Toggle node in selection set
                    if clicked_node in st.session_state.timeline_selected_nodes:
                        st.session_state.timeline_selected_nodes.discard(clicked_node)
                    else:
                        st.session_state.timeline_selected_nodes.add(clicked_node)
                    st.rerun()
                else:
                    node = htree.nodes[clicked_node]
                    if clicked_node != htree.head_id:
                        _restore_node(data, node, htree, file_path)
        else:
            # Fallback to static graphviz
            try:
                graph_dot = htree.generate_graph(direction=direction)
                if direction == "LR":
                    st.graphviz_chart(graph_dot, use_container_width=True)
                else:
                    _, col_center, _ = st.columns([1, 2, 1])
                    with col_center:
                        st.graphviz_chart(graph_dot, use_container_width=True)
            except Exception as e:
                st.error(f"Graph Error: {e}")
            st.caption("💡 Install `streamlit-agraph` for interactive click-to-restore")

    # --- RENDER LINEAR LOG VIEW ---
    elif view_mode == "📜 Linear Log":
        st.caption("A simple chronological list of all snapshots.")

        for n in all_nodes:
            is_head = (n["id"] == htree.head_id)
            with st.container():
                if selection_mode:
                    c0, c1, c2, c3 = st.columns([0.3, 0.5, 4, 1])
                    with c0:
                        is_selected = n["id"] in st.session_state.timeline_selected_nodes
                        if st.checkbox("", value=is_selected, key=f"log_sel_{n['id']}", label_visibility="collapsed"):
                            st.session_state.timeline_selected_nodes.add(n["id"])
                        else:
                            st.session_state.timeline_selected_nodes.discard(n["id"])
                else:
                    c1, c2, c3 = st.columns([0.5, 4, 1])
                with c1:
                    st.markdown("### 📍" if is_head else "### ⚫")
                with c2:
                    note_txt = n.get('note', 'Step')
                    ts = time.strftime('%b %d %H:%M', time.localtime(n['timestamp']))
                    if is_head:
                        st.markdown(f"**{note_txt}** (Current)")
                    else:
                        st.write(f"**{note_txt}**")
                    st.caption(f"ID: {n['id'][:6]} • {ts}")
                with c3:
                    if not is_head and not selection_mode:
                        if st.button("⏪", key=f"log_rst_{n['id']}", help="Restore this version"):
                            _restore_node(data, n, htree, file_path)
            st.divider()

    # --- BATCH DELETE UI ---
    if selection_mode and st.session_state.timeline_selected_nodes:
        # Prune any selected IDs that no longer exist in the tree
        valid_selected = st.session_state.timeline_selected_nodes & set(htree.nodes.keys())
        st.session_state.timeline_selected_nodes = valid_selected
        count = len(valid_selected)
        if count > 0:
            st.warning(f"**{count}** node{'s' if count != 1 else ''} selected for deletion.")
            if st.button(f"🗑️ Delete {count} Node{'s' if count != 1 else ''}", type="primary"):
                # Backup
                if "history_tree_backup" not in data:
                    data["history_tree_backup"] = []
                data["history_tree_backup"].append(copy.deepcopy(htree.to_dict()))
                # Delete all selected nodes
                for nid in valid_selected:
                    if nid in htree.nodes:
                        del htree.nodes[nid]
                # Clean up branch tips
                for b, tip in list(htree.branches.items()):
                    if tip in valid_selected:
                        del htree.branches[b]
                # Reassign HEAD if deleted
                if htree.head_id in valid_selected:
                    if htree.nodes:
                        fallback = sorted(htree.nodes.values(), key=lambda x: x["timestamp"])[-1]
                        htree.head_id = fallback["id"]
                    else:
                        htree.head_id = None
                # Save and reset
                data[KEY_HISTORY_TREE] = htree.to_dict()
                save_json(file_path, data)
                st.session_state.timeline_selected_nodes = set()
                st.toast(f"Deleted {count} node{'s' if count != 1 else ''}!", icon="🗑️")
                st.rerun()

    st.markdown("---")

    # --- NODE SELECTOR ---
    col_sel, col_act = st.columns([3, 1])

    def fmt_node(n):
        ts = time.strftime('%b %d %H:%M', time.localtime(n['timestamp']))
        return f"{n.get('note', 'Step')} • {ts} ({n['id'][:6]})"

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

    if not selected_node:
        return

    node_data = selected_node["data"]

    # --- RESTORE ---
    with col_act:
        st.write(""); st.write("")
        if st.button("⏪ Restore Version", type="primary", use_container_width=True):
            _restore_node(data, selected_node, htree, file_path)

    # --- RENAME ---
    rn_col1, rn_col2 = st.columns([3, 1])
    new_label = rn_col1.text_input("Rename Label", value=selected_node.get("note", ""))
    if rn_col2.button("Update Label"):
        selected_node["note"] = new_label
        data[KEY_HISTORY_TREE] = htree.to_dict()
        save_json(file_path, data)
        st.rerun()

    # --- DANGER ZONE ---
    st.markdown("---")
    with st.expander("⚠️ Danger Zone (Delete)"):
        st.warning("Deleting a node cannot be undone.")
        if st.button("🗑️ Delete This Node", type="primary"):
            if selected_node['id'] in htree.nodes:
                if "history_tree_backup" not in data:
                    data["history_tree_backup"] = []
                data["history_tree_backup"].append(copy.deepcopy(htree.to_dict()))
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
                data[KEY_HISTORY_TREE] = htree.to_dict()
                save_json(file_path, data)
                st.toast("Node Deleted", icon="🗑️")
                st.rerun()

    # --- DATA PREVIEW ---
    st.markdown("---")
    with st.expander("🔍 Data Preview", expanded=False):
        batch_list = node_data.get(KEY_BATCH_DATA, [])

        if batch_list and isinstance(batch_list, list) and len(batch_list) > 0:
            st.info(f"📚 This snapshot contains {len(batch_list)} sequences.")
            for i, seq_data in enumerate(batch_list):
                seq_num = seq_data.get("sequence_number", i + 1)
                with st.expander(f"🎬 Sequence #{seq_num}", expanded=(i == 0)):
                    prefix = f"p_{selected_node['id']}_s{i}"
                    _render_preview_fields(seq_data, prefix)
        else:
            prefix = f"p_{selected_node['id']}_single"
            _render_preview_fields(node_data, prefix)


def _render_interactive_graph(htree, direction, selected_nodes=None):
    """Render an interactive graph using streamlit-agraph. Returns clicked node id."""
    if selected_nodes is None:
        selected_nodes = set()

    # Build reverse lookup: branch tip -> branch name(s)
    tip_to_branches = {}
    for b_name, tip_id in htree.branches.items():
        if tip_id:
            tip_to_branches.setdefault(tip_id, []).append(b_name)

    sorted_nodes_list = sorted(htree.nodes.values(), key=lambda x: x["timestamp"])

    nodes = []
    edges = []

    for n in sorted_nodes_list:
        nid = n["id"]
        full_note = n.get('note', 'Step')
        display_note = (full_note[:20] + '..') if len(full_note) > 20 else full_note
        ts = time.strftime('%b %d %H:%M', time.localtime(n['timestamp']))

        # Branch label
        branch_label = ""
        if nid in tip_to_branches:
            branch_label = f"\n[{', '.join(tip_to_branches[nid])}]"

        label = f"{display_note}\n{ts}{branch_label}"

        # Colors - selected nodes override to red
        if nid in selected_nodes:
            color = "#ff5555"  # Selected for deletion - red
        elif nid == htree.head_id:
            color = "#ffdd44"  # Current head - bright yellow
        elif nid in htree.branches.values():
            color = "#66dd66"  # Branch tip - bright green
        else:
            color = "#aaccff"  # Normal - light blue

        nodes.append(Node(
            id=nid,
            label=label,
            size=20,
            color=color,
            font={"size": 10, "color": "#ffffff"}
        ))

        if n["parent"] and n["parent"] in htree.nodes:
            edges.append(Edge(source=n["parent"], target=nid, color="#888888"))

    # Config based on direction
    is_horizontal = direction == "LR"
    config = Config(
        width="100%",
        height=400 if is_horizontal else 600,
        directed=True,
        hierarchical=True,
        physics=False,
        nodeHighlightBehavior=True,
        highlightColor="#ffcc00",
        collapsible=False,
        layout={
            "hierarchical": {
                "enabled": True,
                "direction": "LR" if is_horizontal else "UD",
                "sortMethod": "directed",
                "levelSeparation": 150 if is_horizontal else 80,
                "nodeSpacing": 100 if is_horizontal else 60,
            }
        }
    )

    return agraph(nodes=nodes, edges=edges, config=config)


def _restore_node(data, node, htree, file_path):
    """Restore a history node as the current version."""
    node_data = node["data"]
    if KEY_BATCH_DATA not in node_data and KEY_BATCH_DATA in data:
        del data[KEY_BATCH_DATA]
    data.update(node_data)
    htree.head_id = node['id']
    data[KEY_HISTORY_TREE] = htree.to_dict()
    save_json(file_path, data)
    st.session_state.ui_reset_token += 1
    label = f"{node.get('note')} ({node['id'][:4]})"
    st.session_state.restored_indicator = label
    st.toast("Restored!", icon="🔄")
    st.rerun()


def _render_preview_fields(item_data, prefix):
    """Render a read-only preview of prompts, settings, and LoRAs."""
    # Prompts
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        st.text_area("General Positive", value=item_data.get("general_prompt", ""), height=80, disabled=True, key=f"{prefix}_gp")
        val_sp = item_data.get("current_prompt", "") or item_data.get("prompt", "")
        st.text_area("Specific Positive", value=val_sp, height=80, disabled=True, key=f"{prefix}_sp")
    with p_col2:
        st.text_area("General Negative", value=item_data.get("general_negative", ""), height=80, disabled=True, key=f"{prefix}_gn")
        st.text_area("Specific Negative", value=item_data.get("negative", ""), height=80, disabled=True, key=f"{prefix}_sn")

    # Settings
    s_col1, s_col2, s_col3 = st.columns(3)
    s_col1.text_input("Camera", value=str(item_data.get("camera", "static")), disabled=True, key=f"{prefix}_cam")
    s_col2.text_input("FLF", value=str(item_data.get("flf", "0.0")), disabled=True, key=f"{prefix}_flf")
    s_col3.text_input("Seed", value=str(item_data.get("seed", "-1")), disabled=True, key=f"{prefix}_seed")

    # LoRAs
    with st.expander("💊 LoRA Configuration", expanded=False):
        l1, l2, l3 = st.columns(3)
        with l1:
            st.text_input("L1 Name", value=item_data.get("lora 1 high", ""), disabled=True, key=f"{prefix}_l1h")
            st.text_input("L1 Str", value=str(item_data.get("lora 1 low", "")), disabled=True, key=f"{prefix}_l1l")
        with l2:
            st.text_input("L2 Name", value=item_data.get("lora 2 high", ""), disabled=True, key=f"{prefix}_l2h")
            st.text_input("L2 Str", value=str(item_data.get("lora 2 low", "")), disabled=True, key=f"{prefix}_l2l")
        with l3:
            st.text_input("L3 Name", value=item_data.get("lora 3 high", ""), disabled=True, key=f"{prefix}_l3h")
            st.text_input("L3 Str", value=str(item_data.get("lora 3 low", "")), disabled=True, key=f"{prefix}_l3l")

    # VACE
    vace_keys = ["frame_to_skip", "vace schedule", "video file path"]
    if any(k in item_data for k in vace_keys):
        with st.expander("🎞️ VACE / I2V Settings", expanded=False):
            v1, v2, v3 = st.columns(3)
            v1.text_input("Skip Frames", value=str(item_data.get("frame_to_skip", "")), disabled=True, key=f"{prefix}_fts")
            v2.text_input("Schedule", value=str(item_data.get("vace schedule", "")), disabled=True, key=f"{prefix}_vsc")
            v3.text_input("Video Path", value=str(item_data.get("video file path", "")), disabled=True, key=f"{prefix}_vid")
