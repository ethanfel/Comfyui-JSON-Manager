import asyncio
import json
import logging
import sqlite3
from pathlib import Path

from nicegui import ui

from state import AppState
from db import ProjectDB
from utils import save_config, sync_to_db

logger = logging.getLogger(__name__)


def render_projects_tab(state: AppState):
    """Render the Projects management tab."""

    # --- DB toggle ---
    def on_db_toggle(e):
        state.db_enabled = e.value
        state.config['db_enabled'] = e.value
        save_config(state.current_dir, state.config.get('favorites', []), state.config)
        render_project_content.refresh()

    ui.switch('Enable Project Database', value=state.db_enabled,
              on_change=on_db_toggle).classes('q-mb-md')

    @ui.refreshable
    def render_project_content():
        if not state.db_enabled:
            ui.label('Project database is disabled. Enable it above to manage projects.').classes(
                'text-caption q-pa-md')
            return

        if not state.db:
            ui.label('Database not initialized.').classes('text-warning q-pa-md')
            return

        # --- Create project form ---
        with ui.card().classes('w-full q-pa-md q-mb-md'):
            ui.label('Create New Project').classes('section-header')
            name_input = ui.input('Project Name', placeholder='my_project').classes('w-full')
            desc_input = ui.input('Description (optional)', placeholder='A short description').classes('w-full')

            async def create_project():
                name = name_input.value.strip()
                if not name:
                    ui.notify('Please enter a project name', type='warning')
                    return
                try:
                    await asyncio.to_thread(state.db.create_project, name, str(state.current_dir), desc_input.value.strip())
                    name_input.set_value('')
                    desc_input.set_value('')
                    ui.notify(f'Created project "{name}"', type='positive')
                    render_project_list.refresh()
                except Exception as e:
                    ui.notify(f'Error: {e}', type='negative')

            ui.button('Create Project', icon='add', on_click=create_project).classes('w-full')

        # --- Active project indicator ---
        # Fetch once with file counts and reuse in render_project_list
        _cached_projects = state.db.list_projects_with_file_counts()

        if state.current_project:
            # Check if active project actually exists in the database
            project_exists = any(p['name'] == state.current_project for p in _cached_projects)
            if project_exists:
                ui.label(f'Active Project: {state.current_project}').classes(
                    'text-bold text-primary q-pa-sm')
            else:
                with ui.card().classes('w-full q-pa-sm q-mb-sm').style(
                        'border-left: 3px solid orange;'):
                    ui.label(f'Stale project reference: "{state.current_project}" '
                             '(not found in database)').classes('text-warning')
                    with ui.row().classes('q-gutter-sm'):
                        def clear_stale():
                            state.current_project = ''
                            state.config['current_project'] = ''
                            save_config(state.current_dir,
                                        state.config.get('favorites', []),
                                        state.config)
                            ui.notify('Cleared stale project reference', type='info')
                            render_project_content.refresh()

                        def recreate_project():
                            name = state.current_project
                            try:
                                state.db.create_project(name, str(state.current_dir))
                                ui.notify(f'Recreated project "{name}"', type='positive')
                                render_project_content.refresh()
                            except Exception as e:
                                ui.notify(f'Error: {e}', type='negative')

                        ui.button('Clear Reference', icon='clear',
                                  on_click=clear_stale).props('flat dense')
                        ui.button('Recreate Project', icon='add_circle',
                                  on_click=recreate_project).props('flat dense color=primary')

        # --- Project list ---
        @ui.refreshable
        def render_project_list():
            nonlocal _cached_projects
            projects = state.db.list_projects_with_file_counts()
            _cached_projects = projects
            if not projects:
                ui.label('No projects yet. Create one above.').classes('text-caption q-pa-md')
                return

            for proj in projects:
                is_active = proj['name'] == state.current_project
                card_style = 'border-left: 3px solid var(--accent);' if is_active else ''

                with ui.card().classes('w-full q-pa-sm q-mb-sm').style(card_style):
                    with ui.row().classes('w-full items-center'):
                        with ui.column().classes('col'):
                            ui.label(proj['name']).classes('text-bold')
                            if proj['description']:
                                ui.label(proj['description']).classes('text-caption')
                            ui.label(f'Path: {proj["folder_path"]}').classes('text-caption')
                            ui.label(f'{proj["file_count"]} data file(s)').classes('text-caption')

                        with ui.row().classes('q-gutter-xs'):
                            if not is_active:
                                def activate(name=proj['name']):
                                    state.current_project = name
                                    state.config['current_project'] = name
                                    save_config(state.current_dir,
                                                state.config.get('favorites', []),
                                                state.config)
                                    ui.notify(f'Activated project "{name}"', type='positive')
                                    render_project_list.refresh()

                                ui.button('Activate', icon='check_circle',
                                          on_click=activate).props('flat dense color=primary')
                            else:
                                def deactivate():
                                    state.current_project = ''
                                    state.config['current_project'] = ''
                                    save_config(state.current_dir,
                                                state.config.get('favorites', []),
                                                state.config)
                                    ui.notify('Deactivated project', type='info')
                                    render_project_list.refresh()

                                ui.button('Deactivate', icon='cancel',
                                          on_click=deactivate).props('flat dense')

                            async def rename_proj(name=proj['name']):
                                new_name = await ui.run_javascript(
                                    f'prompt("Rename project:", {json.dumps(name)})',
                                    timeout=30.0,
                                )
                                if new_name and new_name.strip() and new_name.strip() != name:
                                    new_name = new_name.strip()
                                    try:
                                        await asyncio.to_thread(state.db.rename_project, name, new_name)
                                        if state.current_project == name:
                                            state.current_project = new_name
                                            state.config['current_project'] = new_name
                                            save_config(state.current_dir,
                                                        state.config.get('favorites', []),
                                                        state.config)
                                        ui.notify(f'Renamed to "{new_name}"', type='positive')
                                        render_project_list.refresh()
                                    except sqlite3.IntegrityError:
                                        ui.notify(f'A project named "{new_name}" already exists',
                                                  type='warning')
                                    except Exception as e:
                                        ui.notify(f'Error: {e}', type='negative')

                            ui.button('Rename', icon='edit',
                                      on_click=rename_proj).props('flat dense')

                            async def change_path(name=proj['name'], path=proj['folder_path']):
                                new_path = await ui.run_javascript(
                                    f'prompt("New path for project:", {json.dumps(path)})',
                                    timeout=30.0,
                                )
                                if new_path and new_path.strip() and new_path.strip() != path:
                                    new_path = new_path.strip()
                                    if not Path(new_path).is_dir():
                                        ui.notify(f'Warning: "{new_path}" does not exist',
                                                  type='warning')
                                    await asyncio.to_thread(state.db.update_project_path, name, new_path)
                                    ui.notify(f'Path updated to "{new_path}"', type='positive')
                                    render_project_list.refresh()

                            ui.button('Path', icon='folder',
                                      on_click=change_path).props('flat dense')

                            def import_folder(pid=proj['id'], pname=proj['name']):
                                _import_folder(state, pid, pname, render_project_list)

                            ui.button('Import Folder', icon='folder_open',
                                      on_click=import_folder).props('flat dense')

                            async def delete_proj(name=proj['name']):
                                await asyncio.to_thread(state.db.delete_project, name)
                                if state.current_project == name:
                                    state.current_project = ''
                                    state.config['current_project'] = ''
                                    save_config(state.current_dir,
                                                state.config.get('favorites', []),
                                                state.config)
                                ui.notify(f'Deleted project "{name}"', type='positive')
                                render_project_list.refresh()

                            ui.button(icon='delete',
                                      on_click=delete_proj).props('flat dense color=negative')

        render_project_list()

    render_project_content()


async def _import_folder(state: AppState, project_id: int, project_name: str, refresh_fn):
    """Bulk import all .json files from current directory into a project."""
    json_files = sorted(state.current_dir.glob('*.json'))
    json_files = [f for f in json_files if f.name not in (
        '.editor_config.json', '.editor_snippets.json')]

    if not json_files:
        ui.notify('No JSON files in current directory', type='warning')
        return

    def _do_import():
        imported = 0
        skipped = 0
        for jf in json_files:
            file_name = jf.stem
            existing = state.db.get_data_file(project_id, file_name)
            if existing:
                skipped += 1
                continue
            try:
                state.db.import_json_file(project_id, jf)
                imported += 1
            except Exception as e:
                logger.warning(f"Failed to import {jf}: {e}")
        return imported, skipped

    imported, skipped = await asyncio.to_thread(_do_import)

    msg = f'Imported {imported} file(s)'
    if skipped:
        msg += f', skipped {skipped} existing'
    ui.notify(msg, type='positive')
    refresh_fn.refresh()
