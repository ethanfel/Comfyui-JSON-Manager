import asyncio
import copy
import json
import logging
import time

from nicegui import ui

from state import AppState
from snapshot_timeline import SnapshotTimeline, diff_snapshots
from utils import save_json, load_json, sync_to_db, KEY_BATCH_DATA, KEY_HISTORY_TREE

logger = logging.getLogger(__name__)


# ======================================================================
# Main entry point
# ======================================================================

def render_timeline_tab(state: AppState):
    t0 = time.perf_counter()
    logger.info("render_timeline_tab START")
    data = state.data_cache
    file_path = state.file_path

    tree_data = data.get(KEY_HISTORY_TREE, {})
    if not tree_data:
        ui.label('No version history exists. Make some changes in the Editor first!').classes(
            'text-subtitle1 q-pa-md')
        return

    timeline = SnapshotTimeline(tree_data)
    if not timeline.snapshots:
        ui.label('No snapshots found in history.').classes('text-subtitle1 q-pa-md')
        return

    # Local UI state
    ui_state = {
        'selected_id': state.timeline_selected_id or timeline.current_id,
        'search': '',
        'filter': 'All',  # All | Pinned | Auto
    }

    if state.restored_indicator:
        ui.label(f'Editing Restored Version: {state.restored_indicator}').classes(
            'text-info q-pa-sm')

    ui.label('Version History').classes('text-h6 q-mb-sm')

    # Mutable container so left/right panels can cross-reference each other's refreshables
    panels: dict = {}

    # ======================================================================
    # Splitter layout: 35% left (list) / 65% right (detail)
    # ======================================================================
    with ui.splitter(value=35).classes('w-full').style('height: calc(100vh - 200px); min-height: 600px') as splitter:

        # ==============================================================
        # LEFT PANEL — Snapshot list
        # ==============================================================
        with splitter.before:
            with ui.column().classes('w-full q-pa-sm').style('height: 100%'):
                # Search + filter
                search_input = ui.input(
                    placeholder='Search notes...',
                ).classes('w-full').props('dense outlined clearable')

                with ui.row().classes('w-full q-gutter-xs'):
                    filter_toggle = ui.toggle(
                        ['All', 'Pinned', 'Auto'], value='All',
                    ).props('dense no-caps')

                @ui.refreshable
                def render_snapshot_list():
                    _render_snapshot_list(
                        timeline, ui_state, data, file_path, state,
                        render_snapshot_list, panels)

                panels['list'] = render_snapshot_list

                def _on_search(e):
                    ui_state['search'] = search_input.value or ''
                    render_snapshot_list.refresh()

                def _on_filter(e):
                    ui_state['filter'] = e.value
                    render_snapshot_list.refresh()

                search_input.on('update:model-value', _on_search)
                filter_toggle.on_value_change(_on_filter)

                render_snapshot_list()

        # ==============================================================
        # RIGHT PANEL — Detail tabs
        # ==============================================================
        with splitter.after:
            @ui.refreshable
            def render_detail_panel():
                _render_detail_panel(timeline, ui_state, data, file_path, state,
                                     panels)

            panels['detail'] = render_detail_panel
            render_detail_panel()

    logger.info("render_timeline_tab END (%.3fs)", time.perf_counter() - t0)


# ======================================================================
# Left panel: snapshot list
# ======================================================================

def _render_snapshot_list(timeline, ui_state, data, file_path, state,
                          refresh_list, panels):
    snapshots = sorted(timeline.snapshots.values(),
                       key=lambda s: s['timestamp'], reverse=True)

    # Apply filters
    search_term = ui_state.get('search', '').lower()
    filter_mode = ui_state.get('filter', 'All')

    if search_term:
        snapshots = [s for s in snapshots
                     if search_term in s.get('note', '').lower()]
    if filter_mode == 'Pinned':
        snapshots = [s for s in snapshots if s.get('pinned')]
    elif filter_mode == 'Auto':
        snapshots = [s for s in snapshots if s.get('auto')]

    if not snapshots:
        ui.label('No snapshots match your filter.').classes('text-caption q-pa-md')
        return

    with ui.scroll_area().classes('w-full').style('flex: 1; min-height: 0'):
        for snap in snapshots:
            sid = snap['id']
            is_current = sid == timeline.current_id
            is_selected = sid == ui_state.get('selected_id')
            is_pinned = snap.get('pinned', False)
            is_auto = snap.get('auto', False)

            # Card styling
            border = ''
            if is_current:
                border = 'border-left: 4px solid #eebb00;'
            if is_selected:
                border = 'border-left: 4px solid #4caf50;'
            bg = 'background: rgba(76,175,80,0.08) !important;' if is_selected else ''

            def select_snap(snap_id=sid):
                ui_state['selected_id'] = snap_id
                state.timeline_selected_id = snap_id
                refresh_list.refresh()
                detail = panels.get('detail')
                if detail is not None:
                    detail.refresh()

            with ui.card().classes('w-full q-mb-xs q-pa-xs cursor-pointer').style(
                    f'{border} {bg}').on('click', select_snap):
                with ui.row().classes('w-full items-center no-wrap'):
                    # Icon
                    if is_pinned:
                        icon_name = 'push_pin'
                        icon_cls = 'text-amber'
                    elif is_auto:
                        icon_name = 'bolt'
                        icon_cls = 'text-grey'
                    else:
                        icon_name = 'save'
                        icon_cls = 'text-primary'
                    ui.icon(icon_name, size='sm').classes(icon_cls)

                    # Text
                    with ui.column().classes('col q-ml-xs').style('min-width: 0'):
                        note = snap.get('note', 'Snapshot')
                        lbl = ui.label(note).classes('text-body2 ellipsis')
                        if is_current:
                            lbl.classes('text-bold')
                        ts = time.strftime('%b %d %H:%M',
                                           time.localtime(snap['timestamp']))
                        seq_count = snap.get('seq_count', '?')
                        ui.label(f'{ts} \u00b7 {seq_count} seqs').classes(
                            'text-caption text-grey')

                    # Badges
                    if is_current:
                        ui.badge('current', color='amber').props('dense')

                    # Pin toggle
                    async def toggle_pin(snap_id=sid):
                        timeline.toggle_pin(snap_id)
                        data[KEY_HISTORY_TREE] = timeline.to_dict()
                        snapshot = json.loads(json.dumps(data))
                        await asyncio.to_thread(save_json, file_path, snapshot)
                        refresh_list.refresh()

                    pin_icon = 'push_pin' if is_pinned else 'o_push_pin'
                    ui.button(icon=pin_icon, on_click=toggle_pin).props(
                        'flat dense round size=xs').on('click.stop', lambda: None)


# ======================================================================
# Right panel: detail tabs (Preview / Compare / Cherry-pick)
# ======================================================================

def _render_detail_panel(timeline, ui_state, data, file_path, state,
                         panels):
    sel_id = ui_state.get('selected_id')
    if not sel_id or sel_id not in timeline.snapshots:
        ui.label('Select a snapshot from the list.').classes('text-caption q-pa-lg')
        return

    def _refresh_both():
        """Refresh both list and detail panels."""
        lp = panels.get('list')
        dp = panels.get('detail')
        if lp:
            lp.refresh()
        if dp:
            dp.refresh()

    snap = timeline.snapshots[sel_id]
    note = snap.get('note', 'Snapshot')
    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(snap['timestamp']))
    ui.label(f'{note}').classes('text-subtitle1 text-bold')
    ui.label(f'{ts} \u2022 ID: {sel_id}').classes('text-caption text-grey q-mb-sm')

    # Action buttons
    with ui.row().classes('q-gutter-sm q-mb-sm'):
        is_current = sel_id == timeline.current_id

        if not is_current:
            async def restore_full():
                await _restore_snapshot(data, sel_id, timeline, file_path, state)
                state._render_main.refresh()

            ui.button('Restore Full', icon='restore',
                      on_click=restore_full).props('color=primary dense')

        # Rename
        rename_input = ui.input(placeholder='New note...').props('dense outlined').classes('w-48')

        async def rename():
            if rename_input.value and sel_id in timeline.snapshots:
                timeline.snapshots[sel_id]['note'] = rename_input.value
                data[KEY_HISTORY_TREE] = timeline.to_dict()
                snapshot = json.loads(json.dumps(data))
                await asyncio.to_thread(save_json, file_path, snapshot)
                if state.db_enabled and state.current_project and state.db:
                    await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, snapshot)
                ui.notify('Note updated', type='positive')
                _refresh_both()

        ui.button('Rename', on_click=rename).props('flat dense')

        # Delete
        async def delete_snap():
            timeline.delete(sel_id)
            # Clean up DB snapshots
            if state.db_enabled and state.db and state.current_project:
                df = state.db.get_data_file_by_names(state.current_project, file_path.stem)
                if df:
                    state.db.delete_node_snapshots(df['id'], {sel_id})
            data[KEY_HISTORY_TREE] = timeline.to_dict()
            snapshot = json.loads(json.dumps(data))
            await asyncio.to_thread(save_json, file_path, snapshot)
            if state.db_enabled and state.current_project and state.db:
                await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, snapshot)
            ui_state['selected_id'] = timeline.current_id
            state.timeline_selected_id = timeline.current_id
            ui.notify('Snapshot deleted', type='positive')
            _refresh_both()

        ui.button(icon='delete', on_click=delete_snap).props('flat dense color=negative')

    # Sub-tabs
    with ui.tabs().classes('w-full') as tabs:
        preview_tab = ui.tab('Preview', icon='visibility')
        compare_tab = ui.tab('Compare', icon='compare')
        cherry_tab = ui.tab('Cherry-pick', icon='content_paste')

    with ui.tab_panels(tabs, value=preview_tab).classes('w-full'):
        with ui.tab_panel(preview_tab):
            _render_preview_tab(sel_id, timeline, state, file_path)

        with ui.tab_panel(compare_tab):
            _render_compare_tab(sel_id, timeline, data, state, file_path)

        with ui.tab_panel(cherry_tab):
            _render_cherry_pick_tab(sel_id, timeline, data, file_path, state,
                                    panels)


# ======================================================================
# Tab 1: Preview
# ======================================================================

def _render_preview_tab(sel_id, timeline, state, file_path):
    snap_data = _load_snapshot_data(sel_id, timeline, state, file_path)
    if not snap_data:
        ui.label('Snapshot data not available.').classes('text-caption text-warning')
        return

    batch_list = snap_data.get(KEY_BATCH_DATA, [])
    if batch_list and isinstance(batch_list, list):
        ui.label(f'{len(batch_list)} sequences in this snapshot.').classes('text-caption')
        for i, seq_data in enumerate(batch_list):
            seq_num = seq_data.get('sequence_number', i + 1)
            with ui.expansion(f'Sequence #{seq_num}', value=(i == 0)):
                _render_preview_fields(seq_data)
    else:
        _render_preview_fields(snap_data)


# ======================================================================
# Tab 2: Compare
# ======================================================================

def _render_compare_tab(sel_id, timeline, data, state, file_path):
    snap_data = _load_snapshot_data(sel_id, timeline, state, file_path)
    if not snap_data:
        ui.label('Snapshot data not available.').classes('text-caption text-warning')
        return

    old_batch = snap_data.get(KEY_BATCH_DATA, [])
    new_batch = data.get(KEY_BATCH_DATA, [])

    if not old_batch and not new_batch:
        ui.label('No batch data to compare.').classes('text-caption')
        return

    diffs = diff_snapshots(old_batch, new_batch)

    show_all = ui.switch('Show unchanged', value=False)

    @ui.refreshable
    def render_diff():
        any_diff = False
        for d in diffs:
            if d['status'] == 'unchanged' and not show_all.value:
                continue
            any_diff = True
            seq_num = d['seq_num']
            status = d['status']

            # Header styling
            if status == 'added':
                icon = 'add_circle'
                color = 'text-positive'
                label = f'Sequence #{seq_num} \u2014 ADDED (not in snapshot)'
            elif status == 'removed':
                icon = 'remove_circle'
                color = 'text-negative'
                label = f'Sequence #{seq_num} \u2014 REMOVED (not in current)'
            elif status == 'changed':
                icon = 'change_circle'
                color = 'text-warning'
                label = f'Sequence #{seq_num} \u2014 {len(d["changes"])} field{"s" if len(d["changes"]) != 1 else ""} changed'
            else:
                icon = 'check_circle'
                color = 'text-grey'
                label = f'Sequence #{seq_num} \u2014 No changes'

            with ui.expansion(label, icon=icon).classes(f'w-full {color}'):
                if status == 'changed' and d['changes']:
                    # Table of field changes
                    columns = [
                        {'name': 'field', 'label': 'Field', 'field': 'field', 'align': 'left'},
                        {'name': 'old', 'label': 'Snapshot', 'field': 'old', 'align': 'left'},
                        {'name': 'new', 'label': 'Current', 'field': 'new', 'align': 'left'},
                    ]
                    rows = []
                    for c in d['changes']:
                        rows.append({
                            'field': c['field'],
                            'old': _truncate(c['old']),
                            'new': _truncate(c['new']),
                        })
                    ui.table(columns=columns, rows=rows, row_key='field').classes(
                        'w-full').props('dense flat bordered')
                elif status in ('added', 'removed'):
                    ui.label('Entire sequence differs.').classes('text-caption')

        if not any_diff:
            ui.label('All sequences are identical.').classes('text-caption q-pa-md')

    show_all.on_value_change(lambda _: render_diff.refresh())
    render_diff()


# ======================================================================
# Tab 3: Cherry-pick Restore
# ======================================================================

def _render_cherry_pick_tab(sel_id, timeline, data, file_path, state,
                            panels):
    snap_data = _load_snapshot_data(sel_id, timeline, state, file_path)
    if not snap_data:
        ui.label('Snapshot data not available.').classes('text-caption text-warning')
        return

    old_batch = snap_data.get(KEY_BATCH_DATA, [])
    if not old_batch:
        ui.label('No sequences in this snapshot.').classes('text-caption')
        return

    ui.label('Select sequences and fields to restore from this snapshot.').classes(
        'text-caption q-mb-sm')

    mode = ui.toggle(['Whole sequences', 'Selected fields'], value='Whole sequences').props(
        'dense no-caps')

    # Build checkboxes per sequence
    seq_checks: dict[int, ui.checkbox] = {}
    field_checks: dict[int, dict[str, ui.checkbox]] = {}

    for seq_item in old_batch:
        seq_num = int(seq_item.get('sequence_number', 0))
        seq_cb = ui.checkbox(f'Sequence #{seq_num}')
        seq_checks[seq_num] = seq_cb

        with ui.expansion(f'Fields for #{seq_num}').classes('w-full q-ml-lg'):
            field_checks[seq_num] = {}
            for k in sorted(seq_item.keys()):
                if k == 'sequence_number':
                    continue
                val_str = _truncate(seq_item.get(k))
                fcb = ui.checkbox(f'{k}: {val_str}')
                field_checks[seq_num][k] = fcb

    async def apply_cherry_pick():
        current_batch = data.get(KEY_BATCH_DATA, [])
        curr_by_seq = {int(s.get('sequence_number', 0)): s for s in current_batch}
        old_by_seq = {int(s.get('sequence_number', 0)): s for s in old_batch}

        applied = 0
        for seq_num, cb in seq_checks.items():
            if not cb.value:
                continue
            if seq_num not in old_by_seq:
                continue

            if mode.value == 'Whole sequences':
                # Replace or add entire sequence
                restored = copy.deepcopy(old_by_seq[seq_num])
                if seq_num in curr_by_seq:
                    # Find and replace in-place
                    for i, s in enumerate(current_batch):
                        if int(s.get('sequence_number', 0)) == seq_num:
                            current_batch[i] = restored
                            break
                else:
                    current_batch.append(restored)
                applied += 1
            else:
                # Selected fields only
                if seq_num not in curr_by_seq:
                    continue
                target = curr_by_seq[seq_num]
                fields = field_checks.get(seq_num, {})
                for field_name, fcb in fields.items():
                    if fcb.value and field_name in old_by_seq[seq_num]:
                        target[field_name] = copy.deepcopy(old_by_seq[seq_num][field_name])
                        applied += 1

        if applied == 0:
            ui.notify('Nothing selected to restore.', type='warning')
            return

        data[KEY_BATCH_DATA] = current_batch

        # Auto-snapshot noting the cherry-pick
        snap_note = timeline.snapshots.get(sel_id, {}).get('note', 'unknown')
        snap_json = json.dumps({k: v for k, v in data.items()
                                if k != KEY_HISTORY_TREE})
        snap_payload = json.loads(snap_json)
        timeline.record(snap_payload, note=f'Cherry-pick from "{snap_note}"')
        if state.db_enabled and state.current_project and state.db:
            data[KEY_HISTORY_TREE] = timeline.to_dict()
            db_snap = json.loads(json.dumps(data))
            await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, db_snap)
            timeline.strip_snapshots()
        data[KEY_HISTORY_TREE] = timeline.to_dict()
        save_snap = json.loads(json.dumps(data))
        await asyncio.to_thread(save_json, file_path, save_snap)
        ui.notify(f'Applied {applied} item{"s" if applied != 1 else ""}!', type='positive')
        for p in ('list', 'detail'):
            ref = panels.get(p)
            if ref:
                ref.refresh()

    ui.button('Apply Selected', icon='check', on_click=apply_cherry_pick).props(
        'color=primary q-mt-md')


# ======================================================================
# Shared helpers
# ======================================================================

def _load_snapshot_data(snap_id, timeline, state, file_path):
    """Load snapshot data from inline, DB, or disk fallback."""
    snap_data = timeline.get_snapshot_data(snap_id)
    if snap_data:
        return snap_data

    # Try DB
    if state and state.db_enabled and state.db and state.current_project and file_path:
        df = state.db.get_data_file_by_names(state.current_project, file_path.stem)
        if df:
            snap_data = state.db.get_node_snapshot(df['id'], snap_id)
            if snap_data:
                return snap_data

    # Disk fallback
    if file_path:
        try:
            raw_data, _ = load_json(file_path)
            tree_on_disk = raw_data.get(KEY_HISTORY_TREE, {})
            # New format
            entry = tree_on_disk.get('snapshots', {}).get(snap_id)
            if entry and 'data' in entry:
                return entry['data']
            # Old format
            entry = tree_on_disk.get('nodes', {}).get(snap_id)
            if entry and 'data' in entry:
                return entry['data']
        except Exception as e:
            logger.warning("Failed to load snapshot %s from disk: %s", snap_id, e)
    return None


async def _restore_snapshot(data, snap_id, timeline, file_path, state):
    """Restore a snapshot as the current version (full replace)."""
    snap_data = _load_snapshot_data(snap_id, timeline, state, file_path)
    if not snap_data:
        ui.notify('Snapshot data not available', type='negative')
        return

    node_data = json.loads(json.dumps(snap_data))

    # Preserve history tree
    preserved_tree = data.get(KEY_HISTORY_TREE)
    preserved_backup = data.get('history_tree_backup')
    data.clear()
    data.update(node_data)
    if preserved_tree is not None:
        data[KEY_HISTORY_TREE] = preserved_tree
    if preserved_backup is not None:
        data['history_tree_backup'] = preserved_backup

    timeline.current_id = snap_id
    data[KEY_HISTORY_TREE] = timeline.to_dict()

    snapshot = json.loads(json.dumps(data))
    await asyncio.to_thread(save_json, file_path, snapshot)
    if state.db_enabled and state.current_project and state.db:
        await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, snapshot)

    note = timeline.snapshots.get(snap_id, {}).get('note', 'Snapshot')
    label = f"{note} ({snap_id[:4]})"
    state.restored_indicator = label
    ui.notify('Restored!', type='positive')


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
                for tier, tier_label in [('high', 'High'), ('low', 'Low')]:
                    lora_name = item_data.get(f'lora {lora_idx} {tier}', '')
                    lora_str = item_data.get(f'lora {lora_idx} {tier} strength', 1.0)
                    ui.input(f'L{lora_idx} {tier_label}',
                             value=str(lora_name)).props('readonly outlined dense')
                    ui.number(f'L{lora_idx} {tier_label} Str',
                              value=float(lora_str)).props('readonly outlined dense').style('max-width: 80px')

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


def _truncate(val, max_len=60):
    """Truncate a value for display."""
    s = str(val) if val is not None else ''
    return (s[:max_len] + '...') if len(s) > max_len else s
