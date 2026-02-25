import asyncio
import html
import time
import urllib.parse

import requests
from nicegui import ui

from state import AppState
from utils import save_config


def render_comfy_monitor(state: AppState):
    config = state.config

    # --- Global Monitor Settings ---
    with ui.expansion('Monitor Settings', icon='settings').classes('w-full'):
        with ui.row().classes('w-full items-end'):
            viewer_input = ui.input(
                'Remote Browser URL',
                value=config.get('viewer_url', ''),
                placeholder='e.g., http://localhost:5800',
            ).classes('col')
            timeout_slider = ui.slider(
                min=0, max=60, step=1,
                value=config.get('monitor_timeout', 0),
            ).classes('col')
            ui.label().bind_text_from(timeout_slider, 'value',
                                      backward=lambda v: f'Timeout: {v} min')

        def save_monitor_settings():
            config['viewer_url'] = viewer_input.value
            config['monitor_timeout'] = int(timeout_slider.value)
            save_config(state.current_dir, config['favorites'], config)
            ui.notify('Monitor settings saved!', type='positive')

        ui.button('Save Monitor Settings', icon='save', on_click=save_monitor_settings)

    # --- Instance Management ---
    if 'comfy_instances' not in config:
        config['comfy_instances'] = [
            {'name': 'Main Server', 'url': 'http://192.168.1.100:8188'}
        ]

    instances = config['comfy_instances']

    @ui.refreshable
    def render_instance_tabs():
        if not instances:
            ui.label('No servers configured. Add one below.')

        for idx, inst in enumerate(instances):
            with ui.expansion(inst.get('name', f'Server {idx+1}'), icon='dns').classes('w-full'):
                _render_single_instance(state, inst, idx, instances, render_instance_tabs)

        # Add server section
        ui.separator()
        ui.label('Add New Server').classes('text-subtitle1')
        with ui.row().classes('w-full items-end'):
            new_name = ui.input('Server Name', placeholder='e.g. Render Node 2').classes('col')
            new_url = ui.input('URL', placeholder='http://192.168.1.50:8188').classes('col')

            def add_instance():
                if new_name.value and new_url.value:
                    instances.append({'name': new_name.value, 'url': new_url.value})
                    config['comfy_instances'] = instances
                    save_config(state.current_dir, config['favorites'], config)
                    ui.notify('Server Added!', type='positive')
                    new_name.set_value('')
                    new_url.set_value('')
                    render_instance_tabs.refresh()
                else:
                    ui.notify('Please fill in both Name and URL.', type='warning')

            ui.button('Add Instance', icon='add', on_click=add_instance)

    render_instance_tabs()

    # --- Auto-poll timer (every 300s) ---
    # Store live_checkbox references so the timer can update them
    _live_checkboxes = state._live_checkboxes = getattr(state, '_live_checkboxes', {})
    _live_refreshables = state._live_refreshables = getattr(state, '_live_refreshables', {})

    def poll_all():
        timeout_val = config.get('monitor_timeout', 0)
        if timeout_val > 0:
            for key, start_time in list(state.live_toggles.items()):
                if start_time and (time.time() - start_time) > (timeout_val * 60):
                    state.live_toggles[key] = None
                    if key in _live_checkboxes:
                        _live_checkboxes[key].set_value(False)
                    if key in _live_refreshables:
                        _live_refreshables[key].refresh()

    ui.timer(300, poll_all)


def _fetch_blocking(url, timeout=1.5):
    """Run a blocking GET request; returns (response, error)."""
    try:
        res = requests.get(url, timeout=timeout)
        return res, None
    except Exception as e:
        return None, e


def _render_single_instance(state: AppState, instance_config: dict, index: int,
                            all_instances: list, refresh_fn):
    config = state.config
    url = instance_config.get('url', 'http://127.0.0.1:8188')
    name = instance_config.get('name', f'Server {index+1}')
    comfy_url = url.rstrip('/')

    # --- Settings popover ---
    with ui.expansion('Settings', icon='settings'):
        name_input = ui.input('Name', value=name).classes('w-full')
        url_input = ui.input('URL', value=url).classes('w-full')

        def update_server():
            all_instances[index]['name'] = name_input.value
            all_instances[index]['url'] = url_input.value
            config['comfy_instances'] = all_instances
            save_config(state.current_dir, config['favorites'], config)
            ui.notify('Server config saved!', type='positive')
            refresh_fn.refresh()

        def remove_server():
            all_instances.pop(index)
            config['comfy_instances'] = all_instances
            save_config(state.current_dir, config['favorites'], config)
            ui.notify('Server removed', type='info')
            refresh_fn.refresh()

        ui.button('Update & Save', icon='save', on_click=update_server).props('color=primary')
        ui.button('Remove Server', icon='delete', on_click=remove_server).props('color=negative')

    # --- Status Dashboard ---
    status_container = ui.row().classes('w-full items-center q-gutter-md')

    async def refresh_status():
        status_container.clear()
        loop = asyncio.get_event_loop()
        res, err = await loop.run_in_executor(
            None, lambda: _fetch_blocking(f'{comfy_url}/queue'))
        with status_container:
            if res is not None:
                try:
                    queue_data = res.json()
                except (ValueError, Exception):
                    ui.label('Invalid response from server').classes('text-negative')
                    return
                running_cnt = len(queue_data.get('queue_running', []))
                pending_cnt = len(queue_data.get('queue_pending', []))

                with ui.card().classes('q-pa-sm'):
                    ui.label('Status')
                    ui.label('Online' if running_cnt > 0 else 'Idle').classes(
                        'text-positive' if running_cnt > 0 else 'text-grey')
                with ui.card().classes('q-pa-sm'):
                    ui.label('Pending')
                    ui.label(str(pending_cnt))
                with ui.card().classes('q-pa-sm'):
                    ui.label('Running')
                    ui.label(str(running_cnt))
            else:
                with ui.card().classes('q-pa-sm'):
                    ui.label('Status')
                    ui.label('Offline').classes('text-negative')
                ui.label(f'Could not connect to {comfy_url}').classes('text-negative')

    # Initial status fetch (non-blocking via button click handler pattern)
    ui.timer(0.1, refresh_status, once=True)
    ui.button('Refresh Status', icon='refresh', on_click=refresh_status).props('flat dense')

    # --- Live View ---
    ui.label('Live View').classes('text-subtitle1 q-mt-md')
    toggle_key = f'live_toggle_{index}'

    live_checkbox = ui.checkbox('Enable Live Preview', value=False)
    # Store reference so poll_all timer can disable it on timeout
    state._live_checkboxes[toggle_key] = live_checkbox

    @ui.refreshable
    def render_live_view():
        if not live_checkbox.value:
            ui.label('Live Preview is disabled.').classes('text-caption')
            return

        # Record start time
        if toggle_key not in state.live_toggles or state.live_toggles.get(toggle_key) is None:
            state.live_toggles[toggle_key] = time.time()

        timeout_val = config.get('monitor_timeout', 0)
        if timeout_val > 0:
            start = state.live_toggles.get(toggle_key, time.time())
            remaining = (timeout_val * 60) - (time.time() - start)
            if remaining <= 0:
                live_checkbox.set_value(False)
                state.live_toggles[toggle_key] = None
                ui.label('Preview timed out.').classes('text-caption')
                return
            ui.label(f'Auto-off in: {int(remaining)}s').classes('text-caption')

        iframe_h = ui.slider(min=600, max=2500, step=50, value=1000).classes('w-full')
        ui.label().bind_text_from(iframe_h, 'value', backward=lambda v: f'Height: {v}px')

        viewer_base = config.get('viewer_url', '').strip()
        parsed = urllib.parse.urlparse(viewer_base)
        if viewer_base and parsed.scheme in ('http', 'https'):
            safe_src = html.escape(viewer_base, quote=True)
            ui.label(f'Viewing: {viewer_base}').classes('text-caption')

            iframe_container = ui.column().classes('w-full')

            def update_iframe():
                iframe_container.clear()
                with iframe_container:
                    ui.html(
                        f'<iframe src="{safe_src}" width="100%" height="{int(iframe_h.value)}px"'
                        f' style="border: 2px solid #666; border-radius: 8px;"></iframe>'
                    )

            iframe_h.on_value_change(lambda _: update_iframe())
            update_iframe()
        else:
            ui.label('No valid viewer URL configured.').classes('text-warning')

    state._live_refreshables[toggle_key] = render_live_view
    live_checkbox.on_value_change(lambda _: render_live_view.refresh())
    render_live_view()

    # --- Latest Output ---
    ui.label('Latest Output').classes('text-subtitle1 q-mt-md')
    img_container = ui.column().classes('w-full')

    async def check_image():
        img_container.clear()
        loop = asyncio.get_event_loop()
        res, err = await loop.run_in_executor(
            None, lambda: _fetch_blocking(f'{comfy_url}/history', timeout=2))
        with img_container:
            if err is not None:
                ui.label(f'Error fetching image: {err}').classes('text-negative')
                return
            try:
                history = res.json()
            except (ValueError, Exception):
                ui.label('Invalid response from server').classes('text-negative')
                return
            if not history:
                ui.label('No history found.').classes('text-caption')
                return
            last_prompt_id = list(history.keys())[-1]
            outputs = history[last_prompt_id].get('outputs', {})
            found_img = None
            for node_output in outputs.values():
                if 'images' in node_output:
                    for img_info in node_output['images']:
                        if img_info['type'] == 'output':
                            found_img = img_info
                            break
                if found_img:
                    break
            if found_img:
                params = urllib.parse.urlencode({
                    'filename': found_img['filename'],
                    'subfolder': found_img['subfolder'],
                    'type': found_img['type'],
                })
                img_url = f'{comfy_url}/view?{params}'
                ui.image(img_url).classes('w-full').style('max-width: 600px')
                ui.label(f'Last Output: {found_img["filename"]}').classes('text-caption')
            else:
                ui.label('Last run had no image output.').classes('text-caption')

    ui.button('Check Latest Image', icon='image', on_click=check_image).props('flat')
