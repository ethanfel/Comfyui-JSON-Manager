import asyncio
import copy
import json
import logging
import math
import random
import time
from pathlib import Path
from urllib.parse import quote

from nicegui import ui

logger = logging.getLogger(__name__)

from state import AppState
from utils import (
    DEFAULTS, save_json, load_json, sync_to_db,
    KEY_BATCH_DATA, KEY_HISTORY_TREE, KEY_PROMPT_HISTORY, KEY_SEQUENCE_NUMBER,
)
from snapshot_timeline import SnapshotTimeline

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}
_AUTO_SNAP_DEBOUNCE = 30  # seconds between auto-snapshots
_last_auto_snap: dict[str, float] = {}  # file_path -> timestamp
SUB_SEGMENT_MULTIPLIER = 1000
SUB_SEGMENT_NUM_COLORS = 6
FRAME_TO_SKIP_DEFAULT = DEFAULTS['frame_to_skip']

VACE_MODES = [
    'End Extend', 'Pre Extend', 'Middle Extend', 'Edge Extend',
    'Join Extend', 'Bidirectional Extend', 'Frame Interpolation',
    'Replace/Inpaint', 'Video Inpaint', 'Keyframe',
]
VACE_FORMULAS = [
    'base + A', 'base + B', 'base + A + B', 'base + A + B',
    'base + A + B', 'base + A + B', '(B-1) * step',
    'snap(source)', 'snap(source)', 'base + A + B',
]


# --- Sub-segment helpers (same as original) ---

def is_subsegment(seq_num):
    return int(seq_num) >= SUB_SEGMENT_MULTIPLIER

def parent_of(seq_num):
    seq_num = int(seq_num)
    return seq_num // SUB_SEGMENT_MULTIPLIER if is_subsegment(seq_num) else seq_num

def sub_index_of(seq_num):
    seq_num = int(seq_num)
    return seq_num % SUB_SEGMENT_MULTIPLIER if is_subsegment(seq_num) else 0

def format_seq_label(seq_num):
    seq_num = int(seq_num)
    if is_subsegment(seq_num):
        return f'Sub #{parent_of(seq_num)}.{sub_index_of(seq_num)}'
    return f'Sequence #{seq_num}'

def next_sub_segment_number(batch_list, parent_seq_num):
    parent_seq_num = int(parent_seq_num)
    max_sub = 0
    for s in batch_list:
        sn = int(s.get(KEY_SEQUENCE_NUMBER, 0))
        if is_subsegment(sn) and parent_of(sn) == parent_seq_num:
            max_sub = max(max_sub, sub_index_of(sn))
    return parent_seq_num * SUB_SEGMENT_MULTIPLIER + max_sub + 1

def max_main_seq_number(batch_list):
    """Highest non-subsegment sequence number in the batch."""
    return max(
        (int(x.get(KEY_SEQUENCE_NUMBER, 0))
         for x in batch_list if not is_subsegment(x.get(KEY_SEQUENCE_NUMBER, 0))),
        default=0,
    )


def find_insert_position(batch_list, parent_index, parent_seq_num):
    parent_seq_num = int(parent_seq_num)
    pos = parent_index + 1
    while pos < len(batch_list):
        sn = int(batch_list[pos].get(KEY_SEQUENCE_NUMBER, 0))
        if is_subsegment(sn) and parent_of(sn) == parent_seq_num:
            pos += 1
        else:
            break
    return pos


# --- Auto change note ---

def _auto_change_note(timeline, batch_list, state=None, file_path=None):
    """Compare current batch_list against last snapshot and describe changes."""
    # Get previous batch data from the current snapshot
    if not timeline.current_id or timeline.current_id not in timeline.snapshots:
        return f'Initial save ({len(batch_list)} sequences)'

    # Load previous snapshot from inline data or DB
    prev_data = timeline.get_snapshot_data(timeline.current_id)
    if not prev_data and state and state.db_enabled and state.db and state.current_project and file_path:
        df = state.db.get_data_file_by_names(state.current_project, file_path.stem)
        if df:
            prev_data = state.db.get_node_snapshot(df['id'], timeline.current_id)
    prev_batch = (prev_data or {}).get(KEY_BATCH_DATA, [])

    prev_by_seq = {int(s.get(KEY_SEQUENCE_NUMBER, 0)): s for s in prev_batch}
    curr_by_seq = {int(s.get(KEY_SEQUENCE_NUMBER, 0)): s for s in batch_list}

    added = sorted(set(curr_by_seq) - set(prev_by_seq))
    removed = sorted(set(prev_by_seq) - set(curr_by_seq))

    changed_keys = set()
    for seq_num in sorted(set(curr_by_seq) & set(prev_by_seq)):
        old, new = prev_by_seq[seq_num], curr_by_seq[seq_num]
        all_keys = set(old) | set(new)
        for k in all_keys:
            if old.get(k) != new.get(k):
                changed_keys.add(k)

    parts = []
    if added:
        parts.append(f'Added seq {", ".join(str(s) for s in added)}')
    if removed:
        parts.append(f'Removed seq {", ".join(str(s) for s in removed)}')
    if changed_keys:
        # Show up to 4 changed field names
        keys_list = sorted(changed_keys)
        if len(keys_list) > 4:
            keys_str = ', '.join(keys_list[:4]) + f' +{len(keys_list) - 4} more'
        else:
            keys_str = ', '.join(keys_list)
        parts.append(f'Changed: {keys_str}')

    return '; '.join(parts) if parts else 'No changes detected'


# --- Helper for repetitive dict-bound inputs ---

def dict_input(element_fn, label, seq, key, **kwargs):
    """Create an input element bound to seq[key] via blur and model-value update."""
    val = seq.get(key, '')
    if isinstance(val, (int, float)):
        val = str(val) if element_fn != ui.number else val
    el = element_fn(label, value=val, **kwargs)

    def _sync(k=key):
        seq[k] = el.value

    el.on('blur', lambda _: _sync())
    el.on('update:model-value', lambda _: _sync())
    return el


def dict_number(label, seq, key, default=0, **kwargs):
    """Number input bound to seq[key] via blur and model-value update."""
    val = seq.get(key, default)
    try:
        # Try float first to handle "1.5" strings, then check if it's a clean int
        fval = float(val)
        if not math.isfinite(fval):
            fval = float(default)
        val = int(fval) if fval == int(fval) else fval
    except (ValueError, TypeError, OverflowError):
        val = default
    el = ui.number(label, value=val, **kwargs)

    def _sync(k=key, d=default):
        v = el.value
        if v is None:
            v = d
        elif isinstance(v, float):
            if not math.isfinite(v):
                v = d
            else:
                try:
                    v = int(v) if v == int(v) else v
                except (OverflowError, ValueError):
                    v = d
        seq[k] = v

    el.on('blur', lambda _: _sync())
    el.on('update:model-value', lambda _: _sync())
    return el


def dict_textarea(label, seq, key, **kwargs):
    """Textarea bound to seq[key] via blur and model-value update."""
    el = ui.textarea(label, value=seq.get(key, ''), **kwargs)

    def _sync(k=key):
        seq[k] = el.value

    el.on('blur', lambda _: _sync())
    el.on('update:model-value', lambda _: _sync())
    return el


# ======================================================================
# Main render function
# ======================================================================

def render_batch_processor(state: AppState):
    t0 = time.perf_counter()
    logger.info("render_batch_processor START")
    data = state.data_cache
    file_path = state.file_path
    if isinstance(data, list):
        data = {KEY_BATCH_DATA: data}
        state.data_cache = data
    is_batch_file = KEY_BATCH_DATA in data

    if not is_batch_file:
        ui.label('This is a Single file. To use Batch mode, create a copy.').classes(
            'text-warning')

        async def create_batch():
            new_name = f'batch_{file_path.name}'
            new_path = file_path.parent / new_name
            if new_path.exists():
                ui.notify(f'File {new_name} already exists!', type='warning')
                return
            first_item = copy.deepcopy(data)
            first_item.pop(KEY_PROMPT_HISTORY, None)
            first_item.pop(KEY_HISTORY_TREE, None)
            first_item[KEY_SEQUENCE_NUMBER] = 1
            new_data = {KEY_BATCH_DATA: [first_item], KEY_HISTORY_TREE: {},
                        KEY_PROMPT_HISTORY: []}
            await asyncio.to_thread(save_json, new_path, new_data)
            if state.db_enabled and state.current_project and state.db:
                await asyncio.to_thread(sync_to_db, state.db, state.current_project, new_path, new_data)
            ui.notify(f'Created {new_name}', type='positive')

        ui.button('Create Batch Copy', icon='content_copy', on_click=create_batch)
        return

    if state.restored_indicator:
        ui.label(f'Editing Restored Version: {state.restored_indicator}').classes(
            'text-info q-pa-sm')

    batch_list = data.get(KEY_BATCH_DATA, [])

    # Source file data for importing
    with ui.card().classes('w-full q-pa-md q-mb-lg'):
        with ui.expansion('Add New Sequence from Source File', icon='playlist_add').classes('w-full'):
            json_files = sorted(state.current_dir.glob('*.json'))
            json_files = [f for f in json_files if f.name not in (
                '.editor_config.json', '.editor_snippets.json')]
            file_options = {f.name: f.name for f in json_files}

            src_file_select = ui.select(
                file_options,
                value=file_path.name,
                label='Source File:',
            ).classes('w-64')

            src_seq_select = ui.select([], label='Source Sequence:').classes('w-64')

            # Track loaded source data (on state so it's cleared on file switch)
            _src_cache = state._src_cache

            def _update_src():
                name = src_file_select.value
                if name and name != _src_cache['name']:
                    # Reuse current data if source is the same file
                    if name == file_path.name:
                        src_data = data
                    else:
                        src_data, _ = load_json(state.current_dir / name)
                    _src_cache['data'] = src_data
                    _src_cache['batch'] = src_data.get(KEY_BATCH_DATA, [])
                    _src_cache['name'] = name
                    if _src_cache['batch']:
                        opts = {i: format_seq_label(s.get(KEY_SEQUENCE_NUMBER, i+1))
                                for i, s in enumerate(_src_cache['batch'])}
                        src_seq_select.set_options(opts, value=0)
                    else:
                        src_seq_select.set_options({})

            src_file_select.on_value_change(lambda _: _update_src())
            _update_src()

            async def _add_sequence(new_item):
                new_item[KEY_SEQUENCE_NUMBER] = max_main_seq_number(batch_list) + 1
                for k in [KEY_PROMPT_HISTORY, KEY_HISTORY_TREE, 'note', 'loras']:
                    new_item.pop(k, None)
                batch_list.append(new_item)
                data[KEY_BATCH_DATA] = batch_list
                snapshot = json.loads(json.dumps(data))
                await asyncio.to_thread(save_json, file_path, snapshot)
                if state.db_enabled and state.current_project and state.db:
                    await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, snapshot)
                render_sequence_list.refresh()

            with ui.row().classes('q-mt-sm'):
                async def add_empty():
                    await _add_sequence(copy.deepcopy(DEFAULTS))

                async def add_from_source():
                    item = copy.deepcopy(DEFAULTS)
                    src_batch = _src_cache['batch']
                    sel_idx = src_seq_select.value
                    if src_batch and sel_idx is not None and int(sel_idx) < len(src_batch):
                        item.update(copy.deepcopy(src_batch[int(sel_idx)]))
                    elif _src_cache['data']:
                        item.update(copy.deepcopy(_src_cache['data']))
                    await _add_sequence(item)

                ui.button('Add Empty', icon='add', on_click=add_empty)
                ui.button('From Source', icon='file_download', on_click=add_from_source)

    # --- Standard / LoRA / VACE key sets ---
    lora_keys = ['lora 1 high', 'lora 1 high strength', 'lora 1 low', 'lora 1 low strength',
                 'lora 2 high', 'lora 2 high strength', 'lora 2 low', 'lora 2 low strength',
                 'lora 3 high', 'lora 3 high strength', 'lora 3 low', 'lora 3 low strength']
    standard_keys = {
        'name', 'mode', 'general_prompt', 'general_negative', 'current_prompt', 'negative', 'prompt',
        'seed', 'camera', KEY_SEQUENCE_NUMBER,
        'frame_to_skip', 'logic index', 'transition', 'vace_length',
        'input_a_frames', 'input_b_frames', 'reference switch', 'vace schedule',
        'start frame path', 'start frame high strength', 'start frame low strength',
        'middle frame path', 'middle frame high strength', 'middle frame low strength',
        'end frame path', 'end frame high strength', 'end frame low strength',
        'video file path',
    }
    standard_keys.update(lora_keys)

    async def sort_by_number():
        batch_list.sort(key=lambda s: int(s.get(KEY_SEQUENCE_NUMBER, 0)))
        data[KEY_BATCH_DATA] = batch_list
        snapshot = json.loads(json.dumps(data))
        await asyncio.to_thread(save_json, file_path, snapshot)
        if state.db_enabled and state.current_project and state.db:
            await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, snapshot)
        ui.notify('Sorted by sequence number!', type='positive')
        render_sequence_list.refresh()

    # --- Sequence list + mass update (inside refreshable so they stay in sync) ---
    @ui.refreshable
    def render_sequence_list():
        t1 = time.perf_counter()
        logger.info("render_sequence_list START (%d sequences)", len(batch_list))
        # Mass update (rebuilt on refresh so checkboxes match current sequences)
        _render_mass_update(batch_list, data, file_path, state, render_sequence_list)

        with ui.row().classes('w-full items-center'):
            ui.label(f'Batch contains {len(batch_list)} sequences.')
            ui.button('Sort by Number', icon='sort', on_click=sort_by_number).props('flat')

        for i, seq in enumerate(batch_list):
            with ui.card().classes('w-full q-mb-sm'):
                _render_sequence_card(
                    i, seq, batch_list, data, file_path, state,
                    _src_cache, src_seq_select,
                    standard_keys, render_sequence_list,
                )
        logger.info("render_sequence_list END (%.3fs)", time.perf_counter() - t1)

    render_sequence_list()
    logger.info("render_batch_processor END (%.3fs)", time.perf_counter() - t0)

    # --- Save & Snap ---
    with ui.card().classes('w-full q-pa-md q-mt-lg'):
        with ui.row().classes('w-full items-end q-gutter-md'):
            commit_input = ui.input('Change Note (Optional)',
                                    placeholder='e.g. Added sequence 3').classes('col')

            async def save_and_snap():
                t_ss = time.perf_counter()
                logger.info("save_and_snap START")
                data[KEY_BATCH_DATA] = batch_list
                tree_data = data.get(KEY_HISTORY_TREE, {})
                timeline = SnapshotTimeline(tree_data)
                note = commit_input.value if commit_input.value else _auto_change_note(timeline, batch_list, state=state, file_path=file_path)
                # Single serialization: json roundtrip gives us an isolated snapshot
                t1 = time.perf_counter()
                snapshot_json = json.dumps({k: v for k, v in data.items()
                                            if k != KEY_HISTORY_TREE})
                snapshot_payload = json.loads(snapshot_json)
                logger.info("save_and_snap snapshot %.3fs", time.perf_counter() - t1)
                try:
                    timeline.record(snapshot_payload, note=note)
                except ValueError as e:
                    ui.notify(f'Save failed: {e}', type='negative')
                    return
                if state.db_enabled and state.current_project and state.db:
                    full_tree = timeline.to_dict()
                    data[KEY_HISTORY_TREE] = full_tree
                    t1 = time.perf_counter()
                    db_snapshot = json.loads(json.dumps(data))
                    await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, db_snapshot)
                    logger.info("save_and_snap sync_to_db %.3fs", time.perf_counter() - t1)
                    timeline.strip_snapshots()
                    data[KEY_HISTORY_TREE] = timeline.to_dict()
                    t1 = time.perf_counter()
                    slim_snapshot = json.loads(json.dumps(data))
                    await asyncio.to_thread(save_json, file_path, slim_snapshot)
                    logger.info("save_and_snap save_json %.3fs", time.perf_counter() - t1)
                else:
                    data[KEY_HISTORY_TREE] = timeline.to_dict()
                    t1 = time.perf_counter()
                    save_snapshot = json.loads(json.dumps(data))
                    await asyncio.to_thread(save_json, file_path, save_snapshot)
                    logger.info("save_and_snap save_json %.3fs", time.perf_counter() - t1)
                state.restored_indicator = None
                commit_input.set_value('')
                logger.info("save_and_snap END (%.3fs)", time.perf_counter() - t_ss)
                ui.notify('Batch Saved & Snapshot Created!', type='positive')

            ui.button('Save & Snap', icon='save', on_click=save_and_snap).props('color=primary')


# ======================================================================
# Single sequence card
# ======================================================================


def _render_sequence_card(i, seq, batch_list, data, file_path, state,
                          src_cache, src_seq_select, standard_keys,
                          refresh_list):
    async def commit(message=None):
        data[KEY_BATCH_DATA] = batch_list
        # Auto-snapshot with debounce
        fp_key = str(file_path)
        now = time.time()
        did_snap = False
        if now - _last_auto_snap.get(fp_key, 0) >= _AUTO_SNAP_DEBOUNCE:
            timeline = SnapshotTimeline(data.get(KEY_HISTORY_TREE, {}))
            snap_json = json.dumps({k: v for k, v in data.items()
                                    if k != KEY_HISTORY_TREE})
            snap_payload = json.loads(snap_json)
            try:
                timeline.record(snap_payload, note=message or "Auto-save", auto=True)
                if state.db_enabled and state.current_project and state.db:
                    data[KEY_HISTORY_TREE] = timeline.to_dict()
                    db_snap = json.loads(json.dumps(data))
                    await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, db_snap)
                    timeline.strip_snapshots()
                    did_snap = True
                data[KEY_HISTORY_TREE] = timeline.to_dict()
                _last_auto_snap[fp_key] = now
            except ValueError:
                pass  # Non-critical: skip auto-snapshot on ID collision
        snapshot = json.loads(json.dumps(data))
        await asyncio.to_thread(save_json, file_path, snapshot)
        if state.db_enabled and state.current_project and state.db and not did_snap:
            await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, snapshot)
        if message:
            ui.notify(message, type='positive')
        refresh_list.refresh()

    seq_num = seq.get(KEY_SEQUENCE_NUMBER, i + 1)
    seq_name = seq.get('name', '')

    if is_subsegment(seq_num):
        label = f'Sub #{parent_of(seq_num)}.{sub_index_of(seq_num)}  ({int(seq_num)})'
    else:
        label = f'Sequence #{seq_num}'
    if seq_name:
        label += f' — {seq_name}'

    if is_subsegment(seq_num):
        color_idx = (sub_index_of(seq_num) - 1) % SUB_SEGMENT_NUM_COLORS
        exp_classes = f'w-full subsegment-color-{color_idx}'
    else:
        exp_classes = 'w-full'
    with ui.expansion(label, icon='movie').classes(exp_classes) as expansion:
        # --- Action row ---
        with ui.row().classes('w-full q-gutter-sm action-row'):
            # Rename
            async def rename(s=seq):
                result = await ui.run_javascript(
                    f'prompt("Rename sequence:", {json.dumps(s.get("name", ""))})',
                    timeout=30.0,
                )
                if result is not None:
                    s['name'] = result
                    await commit('Renamed!')

            ui.button('Rename', icon='edit', on_click=rename).props('outline')
            # Copy from source
            async def copy_source(idx=i, sn=seq_num):
                item = copy.deepcopy(DEFAULTS)
                src_batch = src_cache['batch']
                sel_idx = src_seq_select.value
                if src_batch and sel_idx is not None and int(sel_idx) < len(src_batch):
                    item.update(copy.deepcopy(src_batch[int(sel_idx)]))
                elif src_cache['data']:
                    item.update(copy.deepcopy(src_cache['data']))
                item[KEY_SEQUENCE_NUMBER] = sn
                item.pop(KEY_PROMPT_HISTORY, None)
                item.pop(KEY_HISTORY_TREE, None)
                batch_list[idx] = item
                await commit('Copied!')

            ui.button('Copy Src', icon='file_download', on_click=copy_source).props('outline')

            # Clone Next
            async def clone_next(idx=i, sn=seq_num, s=seq):
                new_seq = copy.deepcopy(s)
                new_seq[KEY_SEQUENCE_NUMBER] = max_main_seq_number(batch_list) + 1
                if not is_subsegment(sn):
                    pos = find_insert_position(batch_list, idx, int(sn))
                else:
                    pos = idx + 1
                batch_list.insert(pos, new_seq)
                await commit('Cloned to Next!')

            ui.button('Clone Next', icon='content_copy', on_click=clone_next).props('outline')

            # Clone End
            async def clone_end(s=seq):
                new_seq = copy.deepcopy(s)
                new_seq[KEY_SEQUENCE_NUMBER] = max_main_seq_number(batch_list) + 1
                batch_list.append(new_seq)
                await commit('Cloned to End!')

            ui.button('Clone End', icon='vertical_align_bottom', on_click=clone_end).props('outline')

            # Clone Sub
            async def clone_sub(idx=i, sn=seq_num, s=seq):
                new_seq = copy.deepcopy(s)
                p_seq = parent_of(sn)
                p_idx = idx
                if is_subsegment(sn):
                    for pi, ps in enumerate(batch_list):
                        if int(ps.get(KEY_SEQUENCE_NUMBER, 0)) == p_seq:
                            p_idx = pi
                            break
                new_seq[KEY_SEQUENCE_NUMBER] = next_sub_segment_number(batch_list, p_seq)
                pos = find_insert_position(batch_list, p_idx, p_seq)
                batch_list.insert(pos, new_seq)
                await commit(f'Created {format_seq_label(new_seq[KEY_SEQUENCE_NUMBER])}!')

            ui.button('Clone Sub', icon='link', on_click=clone_sub).props('outline')

            ui.element('div').classes('col')

            # Delete
            async def delete(idx=i):
                if idx < len(batch_list):
                    batch_list.pop(idx)
                    await commit()

            ui.button(icon='delete', on_click=delete).props('color=negative')

        ui.separator()

        # --- Prompts + Settings (2-column) ---
        frame_switches = []  # populated below, used for bidirectional sync with logic index
        with ui.splitter(value=66).classes('w-full') as splitter:
            with splitter.before:
                dict_textarea('General Prompt', seq, 'general_prompt').classes(
                    'w-full q-mt-sm').props('outlined rows=2')
                dict_textarea('General Negative', seq, 'general_negative').classes(
                    'w-full q-mt-sm').props('outlined rows=2')
                dict_textarea('Specific Prompt', seq, 'current_prompt').classes(
                    'w-full q-mt-sm').props('outlined rows=10')
                dict_textarea('Specific Negative', seq, 'negative').classes(
                    'w-full q-mt-sm').props('outlined rows=2')

                # --- Frame paths (start / middle / end) ---
                logic_val = int(seq.get('logic index', 0))
                for bit, img_label, img_key, hi_key, lo_key in [
                    (0, 'Start Frame', 'start frame path', 'start frame high strength', 'start frame low strength'),
                    (1, 'Middle Frame', 'middle frame path', 'middle frame high strength', 'middle frame low strength'),
                    (2, 'End Frame', 'end frame path', 'end frame high strength', 'end frame low strength'),
                ]:
                    ui.label(img_label).classes('text-caption text-weight-bold q-mt-sm')
                    is_on = bool((logic_val >> bit) & 1)
                    with ui.row().classes('w-full items-center no-wrap q-mt-xs'):
                        inp = dict_input(ui.input, 'Path', seq, img_key).classes(
                            'col').props('outlined dense input-style="text-align: right"')
                        thumb = None
                        img_path = Path(seq.get(img_key, '')) if seq.get(img_key) else None
                        if (img_path and img_path.exists() and
                                img_path.suffix.lower() in IMAGE_EXTENSIONS):
                            img_url = f'/api/image-preview?path={quote(str(img_path))}'
                            with ui.dialog() as img_dlg, ui.card().style('max-width:90vw; padding:0'):
                                ui.html(f'<img src="{img_url}" '
                                        f'style="max-width:80vw;max-height:80vh;display:block">')
                            thumb = ui.html(
                                f'<img src="{img_url}" '
                                f'style="width:36px;height:36px;object-fit:cover;'
                                f'border-radius:4px;cursor:pointer;flex-shrink:0;'
                                f'opacity:{"1.0" if is_on else "0.25"}">'
                            ).on('click', img_dlg.open)
                        sw = ui.switch(value=is_on)
                        frame_switches.append(sw)
                        if thumb is not None:
                            sw.on('update:model-value',
                                  lambda e, t=thumb: t.style(f'opacity: {"1.0" if e.args else "0.25"}'))
                    with ui.row().classes('w-full no-wrap q-mt-xs q-gutter-xs'):
                        dict_number('High', seq, hi_key, default=1.0,
                                    step=0.05, format='%.2f').classes('col').props('outlined dense')
                        dict_number('Low', seq, lo_key, default=1.0,
                                    step=0.05, format='%.2f').classes('col').props('outlined dense')

            with splitter.after:
                # Mode
                dict_number('Mode', seq, 'mode').props('outlined').classes('w-full')

                # Sequence number
                sn_label = (
                    f'Seq Number (Sub #{parent_of(seq_num)}.{sub_index_of(seq_num)})'
                    if is_subsegment(seq_num) else 'Sequence Number'
                )
                sn_input = dict_number(sn_label, seq, KEY_SEQUENCE_NUMBER)
                sn_input.props('outlined').classes('w-full')

                # Seed + randomize
                with ui.row().classes('w-full items-end'):
                    seed_input = dict_number('Seed', seq, 'seed').classes('col').props('outlined')

                    def randomize_seed(si=seed_input, s=seq):
                        new_seed = random.randint(0, 999999999999)
                        si.set_value(new_seed)
                        s['seed'] = new_seed

                    ui.button(icon='casino', on_click=randomize_seed).props('flat')

                dict_input(ui.input, 'Camera', seq, 'camera').props('outlined').classes('w-full')
                seq.setdefault('logic index', 0)
                li_input = dict_number('Logic Index', seq, 'logic index').props('outlined readonly').classes('w-full')
                with li_input:
                    ui.tooltip(
                        'Binary flags — bit 0: start frame | bit 1: middle frame | bit 2: end frame\n'
                        '0: none  1: start  2: middle  3: start+middle\n'
                        '4: end   5: start+end   6: middle+end   7: all'
                    )
                dict_input(ui.input, 'Video File Path', seq, 'video file path').props(
                    'outlined input-style="text-align: right"').classes('w-full')

        # Switches → logic index (sole writer)
        def _sync_switches_to_logic(li=li_input, switches=frame_switches, s=seq):
            v = sum(int(sw.value) << b for b, sw in enumerate(switches))
            s['logic index'] = v
            li.set_value(v)

        for frame_sw in frame_switches:
            frame_sw.on('update:model-value', lambda _, s=_sync_switches_to_logic: s())

        # --- Resolutions (8 fixed slots) ---
        resolutions = seq.setdefault('resolutions', [])
        while len(resolutions) < 8:
            resolutions.append([512, 512, 0])
        for r_i in range(len(resolutions)):
            if len(resolutions[r_i]) < 3:
                resolutions[r_i] = list(resolutions[r_i]) + [0]
        with ui.expansion('Resolutions', icon='aspect_ratio').classes('w-full'):
            for idx in range(8):
                entry = resolutions[idx]
                with ui.row().classes('items-center w-full q-mt-xs no-wrap'):
                    ui.label(str(idx)).classes('text-caption').style('min-width:16px')
                    w_inp = ui.number(value=int(entry[0]), min=1, step=1, label='W').style(
                        'width:70px').props('outlined dense hide-bottom-space')
                    h_inp = ui.number(value=int(entry[1]), min=1, step=1, label='H').style(
                        'width:70px').props('outlined dense hide-bottom-space')
                    seed_inp = ui.number(value=int(entry[2]), min=0, step=1, label='Seed').style(
                        'flex:1; min-width:60px').props('outlined dense hide-bottom-space')

                    async def _sync_entry(r=idx, wi=w_inp, hi=h_inp, si=seed_inp):
                        seq['resolutions'][r] = [
                            int(wi.value) if wi.value else 512,
                            int(hi.value) if hi.value else 512,
                            int(si.value) if si.value else 0,
                        ]
                        await commit()

                    async def _randomize(si=seed_inp, r=idx):
                        si.value = random.randint(0, 2**32 - 1)
                        seq['resolutions'][r][2] = int(si.value)
                        await commit()

                    ui.button(icon='casino', on_click=_randomize).props(
                        'flat dense round').classes('q-ml-xs')

                    w_inp.on('blur', lambda _, s=_sync_entry: s())
                    w_inp.on('update:model-value', lambda _, s=_sync_entry: s())
                    h_inp.on('blur', lambda _, s=_sync_entry: s())
                    h_inp.on('update:model-value', lambda _, s=_sync_entry: s())
                    seed_inp.on('blur', lambda _, s=_sync_entry: s())
                    seed_inp.on('update:model-value', lambda _, s=_sync_entry: s())

        # --- VACE Settings (full width) ---
        with ui.expansion('VACE Settings', icon='settings').classes('w-full'):
            _render_vace_settings(i, seq, batch_list, data, file_path, state, refresh_list)

        # --- LoRA Settings ---
        with ui.expansion('LoRA Settings', icon='style').classes('w-full'):
            for lora_idx in range(1, 4):
                for tier, tier_label in [('high', 'High'), ('low', 'Low')]:
                    lora_key = f'lora {lora_idx} {tier}'

                    lora_name = str(seq.get(lora_key, ''))
                    strength_key = f'lora {lora_idx} {tier} strength'
                    lora_strength = seq.get(strength_key, 1.0)
                    try:
                        lora_strength = float(lora_strength)
                    except (ValueError, TypeError):
                        lora_strength = 1.0

                    with ui.row().classes('w-full items-center q-gutter-sm'):
                        ui.label(f'L{lora_idx} {tier_label}').classes(
                            'text-caption').style('min-width: 55px')
                        name_input = ui.input(
                            'Name',
                            value=lora_name,
                        ).classes('col').props('outlined dense')
                        strength_input = ui.number(
                            'Str',
                            value=lora_strength,
                            min=0, max=10, step=0.1,
                            format='%.1f',
                        ).props('outlined dense').style('max-width: 80px')

                        def _lora_sync(k=lora_key, sk=strength_key, n_inp=name_input, s_inp=strength_input):
                            seq[k] = n_inp.value or ''
                            seq[sk] = float(s_inp.value) if s_inp.value is not None else 1.0

                        name_input.on('blur', lambda _, s=_lora_sync: s())
                        name_input.on('update:model-value', lambda _, s=_lora_sync: s())
                        strength_input.on('blur', lambda _, s=_lora_sync: s())
                        strength_input.on('update:model-value', lambda _, s=_lora_sync: s())

        # --- Custom Parameters ---
        ui.label('Custom Parameters').classes('section-header q-mt-md')

        custom_keys = [k for k in seq.keys() if k not in standard_keys and k != 'resolutions']
        if custom_keys:
            for k in custom_keys:
                with ui.row().classes('w-full items-center'):
                    ui.input('Key', value=k).props('readonly outlined dense').classes('w-32')
                    dict_input(ui.input, 'Value', seq, k).props('outlined dense').classes('col')

                    async def del_custom(key=k):
                        del seq[key]
                        await commit()

                    ui.button(icon='delete', on_click=del_custom).props('flat dense color=negative')

        with ui.expansion('Add Parameter', icon='add').classes('w-full'):
            new_k_input = ui.input('Key').props('outlined dense')
            new_v_input = ui.input('Value').props('outlined dense')

            async def add_param():
                k = new_k_input.value
                v = new_v_input.value
                if k and k not in seq:
                    seq[k] = v
                    new_k_input.set_value('')
                    new_v_input.set_value('')
                    await commit()

            ui.button('Add', on_click=add_param).props('flat')


# ======================================================================
# VACE Settings sub-section
# ======================================================================

def _render_vace_settings(i, seq, batch_list, data, file_path, state, refresh_list):
    # VACE Schedule (needed early for both columns)
    def _safe_int(val, default=0):
        try:
            return int(float(val))
        except (ValueError, TypeError, OverflowError):
            return default

    sched_val = max(0, min(_safe_int(seq.get('vace schedule', 1), 1), len(VACE_MODES) - 1))

    # Mode reference dialog
    with ui.dialog() as ref_dlg, ui.card():
        table_md = (
            '| # | Mode | Formula |\n|:--|:-----|:--------|\n'
            + '\n'.join(
                f'| **{j}** | {VACE_MODES[j]} | `{VACE_FORMULAS[j]}` |'
                for j in range(len(VACE_MODES)))
            + '\n\n*All totals snapped to 4n+1 (1,5,9,...,49,...,81,...)*'
        )
        ui.markdown(table_md)

    with ui.row().classes('w-full q-gutter-md'):
        # --- Left column ---
        with ui.column().classes('col'):
            # Frame to Skip + shift
            with ui.row().classes('w-full items-end'):
                fts_input = dict_number('Frame to Skip', seq, 'frame_to_skip').classes(
                    'col').props('outlined')

                _original_fts = _safe_int(seq.get('frame_to_skip', FRAME_TO_SKIP_DEFAULT), FRAME_TO_SKIP_DEFAULT)

                async def shift_fts(idx=i, orig=_original_fts):
                    new_fts = _safe_int(fts_input.value, orig)
                    delta = new_fts - orig
                    if delta == 0:
                        ui.notify('No change to shift', type='info')
                        return
                    shifted = 0
                    for j in range(idx + 1, len(batch_list)):
                        batch_list[j]['frame_to_skip'] = _safe_int(
                            batch_list[j].get('frame_to_skip', FRAME_TO_SKIP_DEFAULT), FRAME_TO_SKIP_DEFAULT) + delta
                        shifted += 1
                    data[KEY_BATCH_DATA] = batch_list
                    snapshot = json.loads(json.dumps(data))
                    await asyncio.to_thread(save_json, file_path, snapshot)
                    if state.db_enabled and state.current_project and state.db:
                        await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, snapshot)
                    ui.notify(f'Shifted {shifted} sequences by {delta:+d}', type='positive')
                    refresh_list.refresh()

                ui.button('Shift', icon='arrow_downward', on_click=shift_fts).props(
                    'outline').style('height: 40px')

            dict_input(ui.input, 'Transition', seq, 'transition').props('outlined').classes(
                'w-full q-mt-sm')

            # VACE Schedule
            with ui.row().classes('w-full items-center q-mt-sm'):
                vs_input = dict_number('VACE Schedule', seq, 'vace schedule', default=1,
                                       min=0, max=len(VACE_MODES) - 1).classes('col').props(
                    'outlined')
                mode_label = ui.label(VACE_MODES[sched_val]).classes('text-caption')
                ui.button(icon='help', on_click=ref_dlg.open).props('flat dense round')

                def update_mode_label(e):
                    idx = _safe_int(e.sender.value, 0)
                    idx = max(0, min(idx, len(VACE_MODES) - 1))
                    mode_label.set_text(VACE_MODES[idx])

                vs_input.on('update:model-value', update_mode_label)

        # --- Right column ---
        with ui.column().classes('col'):
            ia_input = dict_number('Input A Frames', seq, 'input_a_frames').props(
                'outlined').classes('w-full')
            ib_input = dict_number('Input B Frames', seq, 'input_b_frames').props(
                'outlined').classes('w-full q-mt-sm')

            # VACE Length + output calculation
            input_a = _safe_int(seq.get('input_a_frames', 16), 16)
            input_b = _safe_int(seq.get('input_b_frames', 16), 16)
            stored_total = _safe_int(seq.get('vace_length', 49), 49)
            mode_idx = _safe_int(seq.get('vace schedule', 1), 1)

            if mode_idx == 0:
                base_length = max(stored_total - input_a, 1)
            elif mode_idx == 1:
                base_length = max(stored_total - input_b, 1)
            else:
                base_length = max(stored_total - input_a - input_b, 1)

            with ui.row().classes('w-full items-center q-mt-sm'):
                vl_input = ui.number('VACE Length', value=base_length, min=1).classes(
                    'col').props('outlined')
                output_label = ui.label(f'Output: {stored_total}').classes('text-bold')

            dict_number('Reference Switch', seq, 'reference switch').props(
                'outlined').classes('w-full q-mt-sm')

    # Recalculate VACE output when any input changes
    def recalc_vace(*_args):
        mi = _safe_int(vs_input.value, 0)
        ia = _safe_int(ia_input.value, 16)
        ib = _safe_int(ib_input.value, 16)
        nb = _safe_int(vl_input.value, 1)

        if mi == 0:
            raw = nb + ia
        elif mi == 1:
            raw = nb + ib
        else:
            raw = nb + ia + ib

        snapped = ((raw + 2) // 4) * 4 + 1
        seq['vace_length'] = snapped
        output_label.set_text(f'Output: {snapped}')

    for inp in (vs_input, ia_input, ib_input, vl_input):
        inp.on('update:model-value', recalc_vace)


# ======================================================================
# Mass Update
# ======================================================================

def _render_mass_update(batch_list, data, file_path, state: AppState, refresh_list=None):
    with ui.expansion('Mass Update', icon='sync').classes('w-full'):
        if len(batch_list) < 2:
            ui.label('Need at least 2 sequences for mass update.').classes('text-caption')
            return

        source_options = {i: format_seq_label(s.get(KEY_SEQUENCE_NUMBER, i+1))
                         for i, s in enumerate(batch_list)}
        source_select = ui.select(source_options, value=0,
                                  label='Copy from sequence:').classes('w-full')

        field_select = ui.select([], multiple=True,
                                 label='Fields to copy:').classes('w-full')

        def update_fields(_=None):
            idx = source_select.value
            if idx is not None and 0 <= idx < len(batch_list):
                src = batch_list[idx]
                keys = [k for k in src.keys() if k != 'sequence_number']
                field_select.set_options(keys)

        source_select.on_value_change(update_fields)
        update_fields()

        ui.label('Apply to:').classes('subsection-header q-mt-md')
        select_all_cb = ui.checkbox('Select All')
        target_checks = {}
        with ui.scroll_area().style('max-height: 250px'):
            for idx, s in enumerate(batch_list):
                sn = s.get(KEY_SEQUENCE_NUMBER, idx + 1)
                cb = ui.checkbox(format_seq_label(sn))
                target_checks[idx] = cb

        def on_select_all(e):
            for cb in target_checks.values():
                cb.set_value(e.value)

        select_all_cb.on_value_change(on_select_all)

        async def apply_mass_update():
            src_idx = source_select.value
            if src_idx is None or src_idx >= len(batch_list):
                ui.notify('Source sequence no longer exists', type='warning')
                return
            selected_keys = field_select.value or []
            if not selected_keys:
                ui.notify('No fields selected', type='warning')
                return

            source_seq = batch_list[src_idx]
            targets = [idx for idx, cb in target_checks.items()
                       if cb.value and idx != src_idx and idx < len(batch_list)]
            if not targets:
                ui.notify('No target sequences selected', type='warning')
                return

            for idx in targets:
                for key in selected_keys:
                    batch_list[idx][key] = copy.deepcopy(source_seq.get(key))

            data[KEY_BATCH_DATA] = batch_list
            timeline = SnapshotTimeline(data.get(KEY_HISTORY_TREE, {}))
            snapshot_json = json.dumps({k: v for k, v in data.items()
                                        if k != KEY_HISTORY_TREE})
            snapshot = json.loads(snapshot_json)
            try:
                timeline.record(snapshot, f"Mass update: {', '.join(selected_keys)}")
            except ValueError as e:
                ui.notify(f'Mass update failed: {e}', type='negative')
                return
            if state.db_enabled and state.current_project and state.db:
                full_tree = timeline.to_dict()
                data[KEY_HISTORY_TREE] = full_tree
                db_snapshot = json.loads(json.dumps(data))
                await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, db_snapshot)
                timeline.strip_snapshots()
                data[KEY_HISTORY_TREE] = timeline.to_dict()
                slim_snapshot = json.loads(json.dumps(data))
                await asyncio.to_thread(save_json, file_path, slim_snapshot)
            else:
                data[KEY_HISTORY_TREE] = timeline.to_dict()
                save_snapshot = json.loads(json.dumps(data))
                await asyncio.to_thread(save_json, file_path, save_snapshot)
            ui.notify(f'Updated {len(targets)} sequences', type='positive')
            if refresh_list:
                refresh_list.refresh()

        ui.button('Apply Changes', icon='check', on_click=apply_mass_update).props(
            'color=primary')
