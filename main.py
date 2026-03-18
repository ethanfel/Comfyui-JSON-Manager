import asyncio
import copy
import json
import logging
from pathlib import Path

from nicegui import ui

from state import AppState
from utils import (
    load_config, save_config, load_snippets, save_snippets,
    load_json, save_json, generate_templates, DEFAULTS,
    KEY_BATCH_DATA, KEY_SEQUENCE_NUMBER,
    resolve_path_case_insensitive,
)
from tab_batch_ng import render_batch_processor
from tab_timeline_ng import render_timeline_tab
from tab_raw_ng import render_raw_editor
from tab_comfy_ng import render_comfy_monitor
from tab_projects_ng import render_projects_tab
from db import ProjectDB
from api_routes import register_api_routes

logger = logging.getLogger(__name__)

# Single shared DB instance for both the UI and API routes
_shared_db: ProjectDB | None = None
try:
    _shared_db = ProjectDB()
except Exception as e:
    logger.warning(f"Failed to initialize ProjectDB: {e}")


@ui.page('/')
def index():
    ui.dark_mode(True)
    ui.colors(primary='#F59E0B')
    ui.add_head_html(
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">'
    )
    ui.add_css('''
        /* === Dark Theme with Depth Palette === */
        :root {
            --bg-page:      #0B0E14;
            --bg-surface-1: #13161E;
            --bg-surface-2: #1A1E2A;
            --bg-surface-3: #242836;
            --border:        rgba(255,255,255,0.08);
            --text-primary:  #EAECF0;
            --text-secondary: rgba(234,236,240,0.55);
            --accent:        #F59E0B;
            --accent-subtle: rgba(245,158,11,0.12);
            --negative:      #EF4444;
        }

        /* Backgrounds */
        body.body--dark,
        .q-page.body--dark,
        .body--dark .q-page { background: var(--bg-page) !important; }
        .body--dark .q-drawer { background: var(--bg-surface-1) !important; }
        .body--dark .q-card {
            background: var(--bg-surface-2) !important;
            border: 1px solid var(--border);
            border-radius: 0.75rem;
        }
        .body--dark .q-tab-panels { background: transparent !important; }
        .body--dark .q-tab-panel { background: transparent !important; }
        .body--dark .q-expansion-item { background: transparent !important; }

        /* Text */
        .body--dark { color: var(--text-primary) !important; }
        .body--dark .q-field__label { color: var(--text-secondary) !important; }
        .body--dark .text-caption { color: var(--text-secondary) !important; }
        .body--dark .text-subtitle1,
        .body--dark .text-subtitle2 { color: var(--text-primary) !important; }

        /* Inputs & textareas */
        .body--dark .q-field--outlined .q-field__control {
            background: var(--bg-surface-3) !important;
            border-radius: 0.5rem !important;
        }
        .body--dark .q-field--outlined .q-field__control:before {
            border-color: var(--border) !important;
            border-radius: 0.5rem !important;
        }
        .body--dark .q-field--outlined.q-field--focused .q-field__control:after {
            border-color: var(--accent) !important;
        }
        .body--dark .q-field__native,
        .body--dark .q-field__input { color: var(--text-primary) !important; }

        /* Sidebar inputs get page bg */
        .body--dark .q-drawer .q-field--outlined .q-field__control {
            background: var(--bg-page) !important;
        }

        /* Buttons */
        .body--dark .q-btn--standard { border-radius: 0.5rem !important; }
        .body--dark .q-btn--outline {
            transition: background 0.15s ease;
        }
        .body--dark .q-btn--outline:hover {
            background: var(--accent-subtle) !important;
        }

        /* Tabs */
        .body--dark .q-tab--active { color: var(--accent) !important; }
        .body--dark .q-tab__indicator { background: var(--accent) !important; }

        /* Separators */
        .body--dark .q-separator { background: var(--border) !important; }

        /* Expansion items */
        .body--dark .q-expansion-item__content { padding: 12px 16px; }
        .body--dark .q-item { border-radius: 0.5rem; }

        /* Splitter */
        .body--dark .q-splitter__separator { background: var(--border) !important; }
        .body--dark .q-splitter__before,
        .body--dark .q-splitter__after { padding: 0 8px; }

        /* Action row wrap */
        .action-row { flex-wrap: wrap !important; gap: 8px !important; }

        /* Notifications */
        .body--dark .q-notification { border-radius: 0.5rem; }

        /* Font */
        body { font-family: "Inter", "Source Sans Pro", "Source Sans 3", sans-serif !important; }

        /* Surface utility classes (need .body--dark to beat .body--dark .q-card specificity) */
        .body--dark .surface-1 { background: var(--bg-surface-1) !important; }
        .body--dark .surface-2 { background: var(--bg-surface-2) !important; }
        .body--dark .surface-3 { background: var(--bg-surface-3) !important; }

        /* Typography utility classes */
        .section-header {
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary) !important;
        }
        .subsection-header {
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-primary) !important;
        }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.12);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255,255,255,0.2);
        }

        /* Sub-sequence accent colors (per sub-index, cycling) */
        .body--dark .subsegment-color-0 > .q-expansion-item__container > .q-item { border-left: 6px solid #06B6D4; padding-left: 10px; }
        .body--dark .subsegment-color-0 .q-expansion-item__toggle-icon { color: #06B6D4 !important; }
        .body--dark .subsegment-color-1 > .q-expansion-item__container > .q-item { border-left: 6px solid #A78BFA; padding-left: 10px; }
        .body--dark .subsegment-color-1 .q-expansion-item__toggle-icon { color: #A78BFA !important; }
        .body--dark .subsegment-color-2 > .q-expansion-item__container > .q-item { border-left: 6px solid #34D399; padding-left: 10px; }
        .body--dark .subsegment-color-2 .q-expansion-item__toggle-icon { color: #34D399 !important; }
        .body--dark .subsegment-color-3 > .q-expansion-item__container > .q-item { border-left: 6px solid #F472B6; padding-left: 10px; }
        .body--dark .subsegment-color-3 .q-expansion-item__toggle-icon { color: #F472B6 !important; }
        .body--dark .subsegment-color-4 > .q-expansion-item__container > .q-item { border-left: 6px solid #FBBF24; padding-left: 10px; }
        .body--dark .subsegment-color-4 .q-expansion-item__toggle-icon { color: #FBBF24 !important; }
        .body--dark .subsegment-color-5 > .q-expansion-item__container > .q-item { border-left: 6px solid #FB923C; padding-left: 10px; }
        .body--dark .subsegment-color-5 .q-expansion-item__toggle-icon { color: #FB923C !important; }

        /* Secondary pane teal accent */
        .pane-secondary .q-field--outlined.q-field--focused .q-field__control:after {
            border-color: #06B6D4 !important;
        }
        .pane-secondary .q-btn.bg-primary { background-color: #06B6D4 !important; }
        .pane-secondary .section-header { color: rgba(6,182,212,0.7) !important; }
    ''')

    config = load_config()
    state = AppState(
        config=config,
        current_dir=Path(config.get('last_dir', str(Path.cwd()))),
        snippets=load_snippets(),
        db_enabled=config.get('db_enabled', False),
        current_project=config.get('current_project', ''),
    )

    # Use the shared DB instance
    state.db = _shared_db

    dual_pane = {'active': False, 'state': None}

    # ------------------------------------------------------------------
    # Define helpers FIRST (before sidebar, which needs them)
    # ------------------------------------------------------------------

    @ui.refreshable
    def render_main_content():
        import time as _time
        _t0 = _time.perf_counter()
        logger.info("render_main_content START")
        max_w = '2400px' if dual_pane['active'] else '1200px'
        with ui.column().classes('w-full q-pa-md').style(f'max-width: {max_w}; margin: 0 auto'):
            if not state.file_path or not state.file_path.exists():
                ui.label('Select a file from the sidebar to begin.').classes(
                    'text-subtitle1 q-pa-lg')
                return

            ui.label(f'Editing: {state.file_path.name}').classes('text-h5 q-mb-lg').style('font-weight: 600')

            with ui.tabs().classes('w-full').style('border-bottom: 1px solid var(--border)') as tabs:
                ui.tab('batch', label='Batch Processor')
                ui.tab('timeline', label='Timeline')
                ui.tab('raw', label='Raw Editor')
                ui.tab('projects', label='Projects')

            with ui.tab_panels(tabs, value='batch').classes('w-full'):
                with ui.tab_panel('batch'):
                    _render_batch_tab_content()
                with ui.tab_panel('timeline'):
                    render_timeline_tab(state)
                with ui.tab_panel('raw'):
                    render_raw_editor(state)
                with ui.tab_panel('projects'):
                    render_projects_tab(state)

            if state.show_comfy_monitor:
                ui.separator()
                with ui.expansion('ComfyUI Monitor', icon='dns').classes('w-full'):
                    render_comfy_monitor(state)

        logger.info("render_main_content END (%.3fs)", _time.perf_counter() - _t0)

    @ui.refreshable
    def _render_batch_tab_content():
        def on_toggle(e):
            dual_pane['active'] = e.value
            if e.value and dual_pane['state'] is None:
                s2 = state.create_secondary()
                s2._render_main = _render_batch_tab_content
                dual_pane['state'] = s2
            render_main_content.refresh()

        ui.switch('Dual Pane', value=dual_pane['active'], on_change=on_toggle)

        if not dual_pane['active']:
            render_batch_processor(state)
        else:
            s2 = dual_pane['state']
            with ui.row().classes('w-full gap-4'):
                with ui.column().classes('col'):
                    ui.label('Pane A').classes('section-header q-mb-sm')
                    _render_pane_file_selector(state)
                    render_batch_processor(state)
                with ui.column().classes('col pane-secondary'):
                    ui.label('Pane B').classes('section-header q-mb-sm')
                    _render_pane_file_selector(s2)
                    if s2.file_path and s2.file_path.exists():
                        render_batch_processor(s2)
                    else:
                        ui.label('Select a file above to begin.').classes(
                            'text-caption q-pa-md')

    def _render_pane_file_selector(pane_state: AppState):
        if not pane_state.current_dir.exists():
            ui.label('Directory not found.').classes('text-warning')
            return
        json_files = sorted(pane_state.current_dir.glob('*.json'))
        json_files = [f for f in json_files if f.name not in (
            '.editor_config.json', '.editor_snippets.json')]
        file_names = [f.name for f in json_files]

        current_val = pane_state.file_path.name if pane_state.file_path else None

        async def on_select(e):
            if not e.value:
                return
            import time as _time
            _t0 = _time.perf_counter()
            logger.info("on_select START: %s", e.value)
            fp = pane_state.current_dir / e.value
            data, mtime = await asyncio.to_thread(load_json, fp)
            pane_state.data_cache = data
            pane_state.last_mtime = mtime
            pane_state.loaded_file = str(fp)
            pane_state.file_path = fp
            pane_state.restored_indicator = None
            _render_batch_tab_content.refresh()
            logger.info("on_select END (%.3fs)", _time.perf_counter() - _t0)

        ui.select(
            file_names,
            value=current_val,
            label='File',
            on_change=on_select,
        ).classes('w-full')

    async def load_file(file_name: str):
        """Load a JSON file and refresh the main content."""
        import time as _time
        _t0 = _time.perf_counter()
        logger.info("load_file START: %s", file_name)
        fp = state.current_dir / file_name
        if state.loaded_file == str(fp):
            return
        data, mtime = await asyncio.to_thread(load_json, fp)
        state.data_cache = data
        state.last_mtime = mtime
        state.loaded_file = str(fp)
        state.file_path = fp
        state.restored_indicator = None
        if state._main_rendered:
            render_main_content.refresh()
        logger.info("load_file END (%.3fs)", _time.perf_counter() - _t0)

    # Attach helpers to state so sidebar can call them
    state._load_file = load_file
    state._render_main = render_main_content
    state._main_rendered = False

    # ------------------------------------------------------------------
    # Sidebar (rendered AFTER helpers are attached)
    # ------------------------------------------------------------------
    with ui.left_drawer(value=True).classes('q-pa-md').style('width: 320px'):
        render_sidebar(state, dual_pane)

    # ------------------------------------------------------------------
    # Main content area
    # ------------------------------------------------------------------
    render_main_content()
    state._main_rendered = True


# ======================================================================
# Sidebar
# ======================================================================

def render_sidebar(state: AppState, dual_pane: dict):
    ui.label('Navigator').classes('text-h6')

    # --- Path input + Pin ---
    with ui.card().classes('w-full q-pa-md q-mb-md'):
        path_input = ui.input(
            'Current Path',
            value=str(state.current_dir),
        ).classes('w-full')

        def on_path_enter():
            p = resolve_path_case_insensitive(path_input.value)
            if p is not None and p.is_dir():
                state.current_dir = p
                if dual_pane['state']:
                    dual_pane['state'].current_dir = state.current_dir
                    dual_pane['state'].file_path = None
                    dual_pane['state'].loaded_file = None
                    dual_pane['state'].data_cache = {}
                state.config['last_dir'] = str(p)
                save_config(state.current_dir, state.config['favorites'], state.config)
                state.loaded_file = None
                state.file_path = None
                path_input.set_value(str(p))
                render_file_list.refresh()
                # Auto-load inside render_file_list already refreshed main content
                # if files exist; only refresh here for the empty-directory case.
                if not state.loaded_file:
                    state._render_main.refresh()

        path_input.on('keydown.enter', lambda _: on_path_enter())

        def pin_folder():
            d = str(state.current_dir)
            if d not in state.config['favorites']:
                state.config['favorites'].append(d)
                save_config(state.current_dir, state.config['favorites'], state.config)
                render_favorites.refresh()

        ui.button('Pin Folder', icon='push_pin', on_click=pin_folder).classes('w-full')

    # --- Favorites ---
    with ui.card().classes('w-full q-pa-md q-mb-md'):
        ui.label('Favorites').classes('section-header')

        @ui.refreshable
        def render_favorites():
            for fav in list(state.config['favorites']):
                with ui.row().classes('w-full items-center'):
                    ui.button(
                        fav,
                        on_click=lambda f=fav: _jump_to(f),
                    ).props('flat dense').classes('col')
                    ui.button(
                        icon='close',
                        on_click=lambda f=fav: _unpin(f),
                    ).props('flat dense color=negative')

        def _jump_to(fav: str):
            state.current_dir = Path(fav)
            if dual_pane['state']:
                dual_pane['state'].current_dir = state.current_dir
                dual_pane['state'].file_path = None
                dual_pane['state'].loaded_file = None
                dual_pane['state'].data_cache = {}
            state.config['last_dir'] = fav
            save_config(state.current_dir, state.config['favorites'], state.config)
            state.loaded_file = None
            state.file_path = None
            path_input.set_value(fav)
            render_file_list.refresh()
            if not state.loaded_file:
                state._render_main.refresh()

        def _unpin(fav: str):
            if fav in state.config['favorites']:
                state.config['favorites'].remove(fav)
                save_config(state.current_dir, state.config['favorites'], state.config)
                render_favorites.refresh()

        render_favorites()

    # --- Snippet Library ---
    with ui.card().classes('w-full q-pa-md q-mb-md'):
        ui.label('Snippet Library').classes('section-header')

        with ui.expansion('Add New Snippet'):
            snip_name_input = ui.input('Name', placeholder='e.g. Cinematic').classes('w-full')
            snip_content_input = ui.textarea('Content', placeholder='4k, high quality...').classes('w-full')

            def save_snippet():
                name = snip_name_input.value
                content = snip_content_input.value
                if name and content:
                    state.snippets[name] = content
                    save_snippets(state.snippets)
                    snip_name_input.set_value('')
                    snip_content_input.set_value('')
                    ui.notify(f"Saved '{name}'")
                    render_snippet_list.refresh()

            ui.button('Save Snippet', on_click=save_snippet).classes('w-full')

        @ui.refreshable
        def render_snippet_list():
            if not state.snippets:
                return
            ui.label('Click to copy snippet text:').classes('text-caption')
            for name, content in list(state.snippets.items()):
                with ui.row().classes('w-full items-center'):
                    async def copy_snippet(c=content):
                        await ui.run_javascript(
                            f'navigator.clipboard.writeText({json.dumps(c)})', timeout=3.0)
                        ui.notify('Copied to clipboard')

                    ui.button(
                        f'{name}',
                        on_click=copy_snippet,
                    ).props('flat dense').classes('col')
                    ui.button(
                        icon='delete',
                        on_click=lambda n=name: _del_snippet(n),
                    ).props('flat dense color=negative')

        def _del_snippet(name: str):
            if name in state.snippets:
                del state.snippets[name]
                save_snippets(state.snippets)
                render_snippet_list.refresh()

        render_snippet_list()

    # --- File List ---
    with ui.card().classes('w-full q-pa-md q-mb-md'):
        @ui.refreshable
        def render_file_list():
            if not state.current_dir.exists():
                ui.label('Directory not found.').classes('text-warning')
                return
            json_files = sorted(state.current_dir.glob('*.json'))
            json_files = [f for f in json_files if f.name not in ('.editor_config.json', '.editor_snippets.json')]

            if not json_files:
                ui.label('No JSON files in this folder.').classes('text-caption')
                ui.button('Generate Templates', on_click=lambda: _gen_templates()).classes('w-full')
                return

            with ui.expansion('Create New JSON'):
                new_fn_input = ui.input('Filename', placeholder='my_prompt_vace').classes('w-full')

                async def create_new():
                    fn = new_fn_input.value
                    if not fn:
                        return
                    if not fn.endswith('.json'):
                        fn += '.json'
                    path = state.current_dir / fn
                    first_item = copy.deepcopy(DEFAULTS)
                    first_item[KEY_SEQUENCE_NUMBER] = 1
                    await asyncio.to_thread(save_json, path, {KEY_BATCH_DATA: [first_item]})
                    new_fn_input.set_value('')
                    render_file_list.refresh()

                ui.button('Create', on_click=create_new).classes('w-full')

            ui.label('Select File').classes('subsection-header q-mt-sm')
            file_names = [f.name for f in json_files]
            current = Path(state.loaded_file).name if state.loaded_file else None
            selected = current if current in file_names else (file_names[0] if file_names else None)
            ui.radio(
                file_names,
                value=selected,
                on_change=lambda e: state._load_file(e.value) if e.value else None,
            ).classes('w-full')

            # Auto-load first file if nothing loaded yet
            if file_names and not state.loaded_file:
                state._load_file(file_names[0])

        def _gen_templates():
            generate_templates(state.current_dir)
            render_file_list.refresh()

        render_file_list()

    # --- Comfy Monitor toggle ---
    def on_monitor_toggle(e):
        state.show_comfy_monitor = e.value
        state._render_main.refresh()

    ui.checkbox('Show Comfy Monitor', value=state.show_comfy_monitor, on_change=on_monitor_toggle)


# Register REST API routes for ComfyUI connectivity (uses the shared DB instance)
if _shared_db is not None:
    register_api_routes(_shared_db)

ui.run(title='AI Settings Manager', port=8080, reload=False)
