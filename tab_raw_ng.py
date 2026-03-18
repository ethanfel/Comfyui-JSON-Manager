import asyncio
import json

from nicegui import ui

from state import AppState
from utils import save_json, sync_to_db, get_file_mtime, KEY_HISTORY_TREE, KEY_PROMPT_HISTORY


def render_raw_editor(state: AppState):
    data = state.data_cache
    file_path = state.file_path

    with ui.card().classes('w-full q-pa-md'):
        ui.label(f'Raw Editor: {file_path.name}').classes('text-h6 q-mb-md')

        hide_history = ui.checkbox(
            'Hide History (Safe Mode)',
            value=True,
        )

        @ui.refreshable
        def render_editor():
            # Prepare display data — shallow copy, just pop keys
            if hide_history.value:
                display_data = {k: v for k, v in data.items()
                                if k not in (KEY_HISTORY_TREE, KEY_PROMPT_HISTORY)}
            else:
                display_data = data

            try:
                json_str = json.dumps(display_data, indent=4, ensure_ascii=False)
            except Exception as e:
                ui.notify(f'Error serializing JSON: {e}', type='negative')
                json_str = '{}'

            text_area = ui.textarea(
                'JSON Content',
                value=json_str,
            ).classes('w-full font-mono').props('outlined rows=30')

            async def do_save():
                try:
                    input_data = json.loads(text_area.value)

                    # Merge hidden history back in if safe mode
                    if hide_history.value:
                        if KEY_HISTORY_TREE in data:
                            input_data[KEY_HISTORY_TREE] = data[KEY_HISTORY_TREE]
                        if KEY_PROMPT_HISTORY in data:
                            input_data[KEY_PROMPT_HISTORY] = data[KEY_PROMPT_HISTORY]

                    await asyncio.to_thread(save_json, file_path, input_data)
                    if state.db_enabled and state.current_project and state.db:
                        await asyncio.to_thread(sync_to_db, state.db, state.current_project, file_path, input_data)

                    data.clear()
                    data.update(input_data)
                    state.last_mtime = get_file_mtime(file_path)

                    ui.notify('Raw JSON Saved Successfully!', type='positive')
                    render_editor.refresh()

                except json.JSONDecodeError as e:
                    ui.notify(f'Invalid JSON Syntax: {e}', type='negative')
                except Exception as e:
                    ui.notify(f'Unexpected Error: {e}', type='negative')

            ui.button('Save Raw Changes', icon='save', on_click=do_save).props(
                'color=primary'
            ).classes('w-full q-mt-md')

        hide_history.on_value_change(lambda _: render_editor.refresh())
        render_editor()
