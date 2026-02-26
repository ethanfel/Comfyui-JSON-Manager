from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class AppState:
    config: dict
    current_dir: Path
    loaded_file: str | None = None
    last_mtime: float = 0
    data_cache: dict = field(default_factory=dict)
    snippets: dict = field(default_factory=dict)
    file_path: Path | None = None
    restored_indicator: str | None = None
    timeline_selected_nodes: set = field(default_factory=set)
    live_toggles: dict = field(default_factory=dict)
    show_comfy_monitor: bool = True

    # Set at runtime by main.py / tab_comfy_ng.py
    _render_main: Any = None
    _load_file: Callable | None = None
    _main_rendered: bool = False
    _live_checkboxes: dict = field(default_factory=dict)
    _live_refreshables: dict = field(default_factory=dict)
