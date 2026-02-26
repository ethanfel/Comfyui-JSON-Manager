import json
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


@ui.page('/')
def index():
    # -- Streamlit dark theme --
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
    ''')

    config = load_config()
    state = AppState(
        config=config,
        current_dir=Path(config.get('last_dir', str(Path.cwd()))),
        snippets=load_snippets(),
    )

    # ------------------------------------------------------------------
    # Define helpers FIRST (before sidebar, which needs them)
    # ------------------------------------------------------------------

    @ui.refreshable
    def render_main_content():
        if not state.file_path or not state.file_path.exists():
            ui.label('Select a file from the sidebar to begin.').classes(
                'text-subtitle1 q-pa-lg')
            return

        ui.label(f'Editing: {state.file_path.name}').classes('text-h5 q-mb-lg').style('font-weight: 600')

        with ui.tabs().classes('w-full').style('border-bottom: 1px solid var(--border)') as tabs:
            ui.tab('batch', label='Batch Processor')
            ui.tab('timeline', label='Timeline')
            ui.tab('raw', label='Raw Editor')

        with ui.tab_panels(tabs, value='batch').classes('w-full'):
            with ui.tab_panel('batch'):
                render_batch_processor(state)
            with ui.tab_panel('timeline'):
                render_timeline_tab(state)
            with ui.tab_panel('raw'):
                render_raw_editor(state)

        if state.show_comfy_monitor:
            ui.separator()
            with ui.expansion('ComfyUI Monitor', icon='dns').classes('w-full'):
                render_comfy_monitor(state)

    def load_file(file_name: str):
        """Load a JSON file and refresh the main content."""
        fp = state.current_dir / file_name
        if state.loaded_file == str(fp):
            return
        data, mtime = load_json(fp)
        state.data_cache = data
        state.last_mtime = mtime
        state.loaded_file = str(fp)
        state.file_path = fp
        state.restored_indicator = None
        if state._main_rendered:
            render_main_content.refresh()

    # Attach helpers to state so sidebar can call them
    state._load_file = load_file
    state._render_main = render_main_content
    state._main_rendered = False

    # ------------------------------------------------------------------
    # Sidebar (rendered AFTER helpers are attached)
    # ------------------------------------------------------------------
    with ui.left_drawer(value=True).classes('q-pa-md').style('width: 320px'):
        render_sidebar(state)

    # ------------------------------------------------------------------
    # Main content area
    # ------------------------------------------------------------------
    render_main_content()
    state._main_rendered = True


# ======================================================================
# Sidebar
# ======================================================================

def render_sidebar(state: AppState):
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
            json_files = sorted(state.current_dir.glob('*.json'))
            json_files = [f for f in json_files if f.name not in ('.editor_config.json', '.editor_snippets.json')]

            if not json_files:
                ui.label('No JSON files in this folder.').classes('text-caption')
                ui.button('Generate Templates', on_click=lambda: _gen_templates()).classes('w-full')
                return

            with ui.expansion('Create New JSON'):
                new_fn_input = ui.input('Filename', placeholder='my_prompt_vace').classes('w-full')

                def create_new():
                    fn = new_fn_input.value
                    if not fn:
                        return
                    if not fn.endswith('.json'):
                        fn += '.json'
                    path = state.current_dir / fn
                    first_item = DEFAULTS.copy()
                    first_item[KEY_SEQUENCE_NUMBER] = 1
                    save_json(path, {KEY_BATCH_DATA: [first_item]})
                    new_fn_input.set_value('')
                    render_file_list.refresh()

                ui.button('Create', on_click=create_new).classes('w-full')

            ui.label('Select File').classes('subsection-header q-mt-sm')
            file_names = [f.name for f in json_files]
            ui.radio(
                file_names,
                value=file_names[0] if file_names else None,
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

    ui.checkbox('Show Comfy Monitor', value=True, on_change=on_monitor_toggle)


ui.run(title='AI Settings Manager', port=8080, reload=True)
