import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import streamlit as st

# --- Magic String Keys ---
KEY_BATCH_DATA = "batch_data"
KEY_HISTORY_TREE = "history_tree"
KEY_PROMPT_HISTORY = "prompt_history"
KEY_SEQUENCE_NUMBER = "sequence_number"

# Configure logging for the application
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Default structure for new files
DEFAULTS = {
    # --- Prompts ---
    "general_prompt": "",
    "general_negative": "Vivid tones, overexposed, static, blurry details, subtitles, style, artwork, painting, picture, still image, overall gray, worst quality, low quality, JPEG compression artifacts, ugly, deformed, extra fingers, poorly drawn hands, poorly drawn face, distorted, disfigured, malformed limbs, fused fingers, unmoving frame, cluttered background, three legs",
    "current_prompt": "",
    "negative": "",
    "seed": -1,
    "cfg": 1.5,

    # --- Settings ---
    "camera": "static",
    "flf": 0.0,

    # --- I2V / VACE Specifics ---
    "frame_to_skip": 81,
    "end_frame": 0,
    "transition": "1-2",
    "vace_length": 49,
    "vace schedule": 1,
    "input_a_frames": 16,
    "input_b_frames": 16,
    "reference switch": 1,
    "video file path": "",
    "reference image path": "",
    "reference path": "",
    "flf image path": "",

    # --- LoRAs ---
    "lora 1 high": "", "lora 1 low": "",
    "lora 2 high": "", "lora 2 low": "",
    "lora 3 high": "", "lora 3 low": ""
}

CONFIG_FILE = Path(".editor_config.json")
SNIPPETS_FILE = Path(".editor_snippets.json")

# No restriction on directory navigation
ALLOWED_BASE_DIR = Path("/").resolve()

def resolve_path_case_insensitive(path: str | Path) -> Path | None:
    """Resolve a path with case-insensitive component matching on Linux.

    Walks each component of the path and matches against actual directory
    entries when an exact match fails. Returns the corrected Path, or None
    if no match is found.
    """
    p = Path(path)
    if p.exists():
        return p.resolve()

    # Start from the root / anchor
    parts = p.resolve().parts  # resolve to get absolute parts
    built = Path(parts[0])     # root "/"
    for component in parts[1:]:
        candidate = built / component
        if candidate.exists():
            built = candidate
            continue
        # Case-insensitive scan of the parent directory
        try:
            lower = component.lower()
            match = next(
                (entry for entry in built.iterdir() if entry.name.lower() == lower),
                None,
            )
        except PermissionError:
            return None
        if match is None:
            return None
        built = match
    return built.resolve()


def load_config():
    """Loads the main editor configuration (Favorites, Last Dir, Servers)."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load config: {e}")
    return {"favorites": [], "last_dir": str(Path.cwd()), "comfy_instances": []}

def save_config(current_dir, favorites, extra_data=None):
    """Saves configuration to disk. Supports extra keys like 'comfy_instances'."""
    data = {
        "last_dir": str(current_dir),
        "favorites": favorites
    }
    existing = load_config()
    data.update(existing)
    
    data["last_dir"] = str(current_dir)
    data["favorites"] = favorites
    
    if extra_data:
        data.update(extra_data)
        
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def load_snippets():
    if SNIPPETS_FILE.exists():
        try:
            with open(SNIPPETS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load snippets: {e}")
    return {}

def save_snippets(snippets):
    with open(SNIPPETS_FILE, 'w') as f:
        json.dump(snippets, f, indent=4)

def load_json(path: str | Path) -> tuple[dict[str, Any], float]:
    path = Path(path)
    if not path.exists():
        return DEFAULTS.copy(), 0
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return data, path.stat().st_mtime
    except Exception as e:
        st.error(f"Error loading JSON: {e}")
        return DEFAULTS.copy(), 0

def save_json(path: str | Path, data: dict[str, Any]) -> None:
    path = Path(path)
    tmp = path.with_suffix('.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=4)
    os.replace(tmp, path)

def get_file_mtime(path: str | Path) -> float:
    """Returns the modification time of a file, or 0 if it doesn't exist."""
    path = Path(path)
    if path.exists():
        return path.stat().st_mtime
    return 0

def generate_templates(current_dir: Path) -> None:
    """Creates batch template files if folder is empty."""
    first = DEFAULTS.copy()
    first[KEY_SEQUENCE_NUMBER] = 1
    save_json(current_dir / "batch_prompt_i2v.json", {KEY_BATCH_DATA: [first]})

    first2 = DEFAULTS.copy()
    first2[KEY_SEQUENCE_NUMBER] = 1
    save_json(current_dir / "batch_prompt_vace_extend.json", {KEY_BATCH_DATA: [first2]})
