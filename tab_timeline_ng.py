import copy
import time

from nicegui import ui

from state import AppState
from history_tree import HistoryTree
from utils import save_json, KEY_BATCH_DATA, KEY_HISTORY_TREE


def _delete_nodes(htree, data, file_path, node_ids):
    """Delete nodes with backup, branch cleanup, and head fallback."""
    if 'history_tree_backup' not in data:
        data['history_tree_backup'] = []
    data['history_tree_backup'].append(copy.deepcopy(htree.to_dict()))
    for nid in node_ids:
        htree.nodes.pop(nid, None)
    for b, tip in list(htree.branches.items()):
        if tip in node_ids:
            del htree.branches[b]
    if htree.head_id in node_ids:
        if htree.nodes:
            htree.head_id = sorted(htree.nodes.values(),
                                   key=lambda x: x['timestamp'])[-1]['id']
        else:
            htree.head_id = None
    data[KEY_HISTORY_TREE] = htree.to_dict()
    save_json(file_path, data)


def _render_selection_picker(all_nodes, htree, state, refresh_fn):
    """Multi-select picker for batch-deleting timeline nodes."""
    all_ids = [n['id'] for n in all_nodes]

    def fmt_option(nid):
        n = htree.nodes[nid]
        ts = time.strftime('%b %d %H:%M', time.localtime(n['timestamp']))
        note = n.get('note', 'Step')
        head = ' (HEAD)' if nid == htree.head_id else ''
        return f'{note} - {ts} ({nid[:6]}){head}'

    options = {nid: fmt_option(nid) for nid in all_ids}

    def on_selection_change(e):
        state.timeline_selected_nodes = set(e.value) if e.value else set()

    ui.select(
        options,
        value=list(state.timeline_selected_nodes),
        multiple=True,
        label='Select nodes to delete:',
        on_change=on_selection_change,
    ).classes('w-full')

    with ui.row():
        def select_all():
            state.timeline_selected_nodes = set(all_ids)
            refresh_fn()
        def deselect_all():
            state.timeline_selected_nodes = set()
            refresh_fn()
        ui.button('Select All', on_click=select_all).props('flat dense')
        ui.button('Deselect All', on_click=deselect_all).props('flat dense')


def _render_graph_or_log(mode, all_nodes, htree, selected_nodes,
                         selection_mode_on, toggle_select_fn, restore_fn):
    """Render graph visualization or linear log view."""
    if mode in ('Horizontal', 'Vertical'):
        direction = 'LR' if mode == 'Horizontal' else 'TB'
        with ui.card().classes('w-full q-pa-md'):
            try:
                graph_dot = htree.generate_graph(direction=direction)
                _render_graphviz(graph_dot)
            except Exception as e:
                ui.label(f'Graph Error: {e}').classes('text-negative')

    elif mode == 'Linear Log':
        ui.label('Chronological list of all snapshots.').classes('text-caption')
        for n in all_nodes:
            is_head = n['id'] == htree.head_id
            is_selected = n['id'] in selected_nodes

            card_style = ''
            if is_selected:
                card_style = 'background: rgba(239, 68, 68, 0.1) !important; border-left: 3px solid var(--negative);'
            elif is_head:
                card_style = 'background: var(--accent-subtle) !important; border-left: 3px solid var(--accent);'
            with ui.card().classes('w-full q-mb-sm').style(card_style):
                with ui.row().classes('w-full items-center'):
                    if selection_mode_on:
                        ui.checkbox(
                            '',
                            value=is_selected,
                            on_change=lambda e, nid=n['id']: toggle_select_fn(
                                nid, e.value),
                        )

                    icon = 'location_on' if is_head else 'circle'
                    ui.icon(icon).classes(
                        'text-primary' if is_head else 'text-grey')

                    with ui.column().classes('col'):
                        note = n.get('note', 'Step')
                        ts = time.strftime('%b %d %H:%M',
                                           time.localtime(n['timestamp']))
                        label = f'{note} (Current)' if is_head else note
                        ui.label(label).classes('text-bold')
                        ui.label(
                            f'ID: {n["id"][:6]} - {ts}').classes('text-caption')

                    if not is_head and not selection_mode_on:
                        ui.button(
                            'Restore',
                            icon='restore',
                            on_click=lambda node=n: restore_fn(node),
                        ).props('flat dense color=primary')


def _render_batch_delete(htree, data, file_path, state, refresh_fn):
    """Render batch delete controls for selected timeline nodes."""
    valid = state.timeline_selected_nodes & set(htree.nodes.keys())
    state.timeline_selected_nodes = valid
    count = len(valid)
    if count == 0:
        return

    ui.label(
        f'{count} node{"s" if count != 1 else ""} selected for deletion.'
    ).classes('text-warning q-mt-md')

    def do_batch_delete():
        current_valid = state.timeline_selected_nodes & set(htree.nodes.keys())
        _delete_nodes(htree, data, file_path, current_valid)
        state.timeline_selected_nodes = set()
        ui.notify(
            f'Deleted {len(current_valid)} node{"s" if len(current_valid) != 1 else ""}!',
            type='positive')
        refresh_fn()

    ui.button(
        f'Delete {count} Node{"s" if count != 1 else ""}',
        icon='delete',
        on_click=do_batch_delete,
    ).props('color=negative')


def _render_node_manager(all_nodes, htree, data, file_path, restore_fn, refresh_fn):
    """Render node selector with restore, rename, delete, and preview."""
    ui.label('Manage Version').classes('section-header')

    def fmt_node(n):
        ts = time.strftime('%b %d %H:%M', time.localtime(n['timestamp']))
        return f'{n.get("note", "Step")} - {ts} ({n["id"][:6]})'

    node_options = {n['id']: fmt_node(n) for n in all_nodes}
    current_id = htree.head_id if htree.head_id in node_options else (
        all_nodes[0]['id'] if all_nodes else None)

    selected_node_id = ui.select(
        node_options,
        value=current_id,
        label='Select Version to Manage:',
    ).classes('w-full')

    with ui.row().classes('w-full items-end q-gutter-md'):
        def restore_selected():
            nid = selected_node_id.value
            if nid and nid in htree.nodes:
                restore_fn(htree.nodes[nid])

        ui.button('Restore Version', icon='restore',
                  on_click=restore_selected).props('color=primary')

    # Rename
    with ui.row().classes('w-full items-end q-gutter-md'):
        rename_input = ui.input('Rename Label').classes('col')

        def rename_node():
            nid = selected_node_id.value
            if nid and nid in htree.nodes and rename_input.value:
                htree.nodes[nid]['note'] = rename_input.value
                data[KEY_HISTORY_TREE] = htree.to_dict()
                save_json(file_path, data)
                ui.notify('Label updated', type='positive')
                refresh_fn()

        ui.button('Update Label', on_click=rename_node).props('flat')

    # Danger zone
    with ui.expansion('Danger Zone (Delete)', icon='warning').classes('w-full q-mt-md').style('border-left: 3px solid var(--negative)'):
        ui.label('Deleting a node cannot be undone.').classes('text-warning')

        def delete_selected():
            nid = selected_node_id.value
            if nid and nid in htree.nodes:
                _delete_nodes(htree, data, file_path, {nid})
                ui.notify('Node Deleted', type='positive')
                refresh_fn()

        ui.button('Delete This Node', icon='delete',
                  on_click=delete_selected).props('color=negative')

    # Data preview
    ui.separator()
    with ui.expansion('Data Preview', icon='preview').classes('w-full'):
        @ui.refreshable
        def render_preview():
            _render_data_preview(selected_node_id, htree)
        selected_node_id.on_value_change(lambda _: render_preview.refresh())
        render_preview()


def render_timeline_tab(state: AppState):
    data = state.data_cache
    file_path = state.file_path

    tree_data = data.get(KEY_HISTORY_TREE, {})
    if not tree_data:
        ui.label('No history timeline exists. Make some changes in the Editor first!').classes(
            'text-subtitle1 q-pa-md')
        return

    htree = HistoryTree(tree_data)

    if state.restored_indicator:
        ui.label(f'Editing Restored Version: {state.restored_indicator}').classes(
            'text-info q-pa-sm')

    # --- View mode + Selection toggle ---
    with ui.row().classes('w-full items-center q-gutter-md q-mb-md'):
        ui.label('Version History').classes('text-h6 col')
        view_mode = ui.toggle(
            ['Horizontal', 'Vertical', 'Linear Log'],
            value='Horizontal',
        )
        selection_mode = ui.switch('Select to Delete')

    @ui.refreshable
    def render_timeline():
        all_nodes = sorted(htree.nodes.values(), key=lambda x: x['timestamp'], reverse=True)
        selected_nodes = state.timeline_selected_nodes if selection_mode.value else set()

        if selection_mode.value:
            _render_selection_picker(all_nodes, htree, state, render_timeline.refresh)

        _render_graph_or_log(
            view_mode.value, all_nodes, htree, selected_nodes,
            selection_mode.value, _toggle_select, _restore_and_refresh)

        if selection_mode.value and state.timeline_selected_nodes:
            _render_batch_delete(htree, data, file_path, state, render_timeline.refresh)

        with ui.card().classes('w-full q-pa-md q-mt-md'):
            _render_node_manager(
                all_nodes, htree, data, file_path,
                _restore_and_refresh, render_timeline.refresh)

    def _toggle_select(nid, checked):
        if checked:
            state.timeline_selected_nodes.add(nid)
        else:
            state.timeline_selected_nodes.discard(nid)
        render_timeline.refresh()

    def _restore_and_refresh(node):
        _restore_node(data, node, htree, file_path, state)
        # Refresh all tabs (batch, raw, timeline) so they pick up the restored data
        state._render_main.refresh()

    view_mode.on_value_change(lambda _: render_timeline.refresh())
    selection_mode.on_value_change(lambda _: render_timeline.refresh())
    render_timeline()


def _render_graphviz(dot_source: str):
    """Render graphviz DOT source as SVG using ui.html."""
    try:
        import graphviz
        src = graphviz.Source(dot_source)
        svg = src.pipe(format='svg').decode('utf-8')
        ui.html(f'<div style="overflow-x: auto;">{svg}</div>')
    except ImportError:
        ui.label('Install graphviz Python package for graph rendering.').classes('text-warning')
        ui.code(dot_source).classes('w-full')
    except Exception as e:
        ui.label(f'Graph rendering error: {e}').classes('text-negative')


def _restore_node(data, node, htree, file_path, state: AppState):
    """Restore a history node as the current version."""
    node_data = copy.deepcopy(node['data'])
    if KEY_BATCH_DATA not in node_data and KEY_BATCH_DATA in data:
        del data[KEY_BATCH_DATA]
    data.update(node_data)
    htree.head_id = node['id']
    data[KEY_HISTORY_TREE] = htree.to_dict()
    save_json(file_path, data)
    label = f"{node.get('note', 'Step')} ({node['id'][:4]})"
    state.restored_indicator = label
    ui.notify('Restored!', type='positive')


def _render_data_preview(selected_node_id, htree):
    """Render a read-only preview of the selected node's data."""
    nid = selected_node_id.value
    if not nid or nid not in htree.nodes:
        ui.label('No node selected.').classes('text-caption')
        return

    node_data = htree.nodes[nid]['data']
    batch_list = node_data.get(KEY_BATCH_DATA, [])

    if batch_list and isinstance(batch_list, list) and len(batch_list) > 0:
        ui.label(f'This snapshot contains {len(batch_list)} sequences.').classes('text-caption')
        for i, seq_data in enumerate(batch_list):
            seq_num = seq_data.get('sequence_number', i + 1)
            with ui.expansion(f'Sequence #{seq_num}', value=(i == 0)):
                _render_preview_fields(seq_data)
    else:
        _render_preview_fields(node_data)


def _render_preview_fields(item_data: dict):
    """Render read-only preview of prompts, settings, LoRAs."""
    with ui.grid(columns=2).classes('w-full'):
        ui.textarea('General Positive',
                    value=item_data.get('general_prompt', '')).props('readonly outlined rows=3')
        ui.textarea('General Negative',
                    value=item_data.get('general_negative', '')).props('readonly outlined rows=3')
        val_sp = item_data.get('current_prompt', '') or item_data.get('prompt', '')
        ui.textarea('Specific Positive',
                    value=val_sp).props('readonly outlined rows=3')
        ui.textarea('Specific Negative',
                    value=item_data.get('negative', '')).props('readonly outlined rows=3')

    with ui.row().classes('w-full q-gutter-md'):
        ui.input('Camera', value=str(item_data.get('camera', 'static'))).props('readonly outlined')
        ui.input('FLF', value=str(item_data.get('flf', '0.0'))).props('readonly outlined')
        ui.input('Seed', value=str(item_data.get('seed', '-1'))).props('readonly outlined')

    with ui.expansion('LoRA Configuration'):
        with ui.row().classes('w-full q-gutter-md'):
            for lora_idx in range(1, 4):
                with ui.column():
                    ui.input(f'L{lora_idx} Name',
                             value=item_data.get(f'lora {lora_idx} high', '')).props(
                        'readonly outlined dense')
                    ui.input(f'L{lora_idx} Str',
                             value=str(item_data.get(f'lora {lora_idx} low', ''))).props(
                        'readonly outlined dense')

    vace_keys = ['frame_to_skip', 'vace schedule', 'video file path']
    if any(k in item_data for k in vace_keys):
        with ui.expansion('VACE / I2V Settings'):
            with ui.row().classes('w-full q-gutter-md'):
                ui.input('Skip Frames',
                         value=str(item_data.get('frame_to_skip', ''))).props('readonly outlined')
                ui.input('Schedule',
                         value=str(item_data.get('vace schedule', ''))).props('readonly outlined')
                ui.input('Video Path',
                         value=str(item_data.get('video file path', ''))).props('readonly outlined')
