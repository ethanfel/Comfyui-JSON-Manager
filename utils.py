import json
import time
from pathlib import Path
import streamlit as st

# Default structure for new files
DEFAULTS = {
    # --- Standard Keys for your Restored Single Tab ---
    "general_prompt": "",       # Global positive
    "general_negative": "",     # Global negative
    "current_prompt": "",       # Specific positive
    "negative": "",             # Specific negative
    "seed": -1,
    
    # --- Settings ---
    "camera": "static",
    "flf": 0.0,
    "steps": 20,
    "cfg": 7.0,
    "sampler_name": "euler",
    "scheduler": "normal",
    "denoise": 1.0,
    "model_name": "v1-5-pruned-emaonly.ckpt",
    "vae_name": "vae-ft-mse-840000-ema-pruned.ckpt",

    # --- I2V / VACE Specifics ---
    "frame_to_skip": 81,
    "vace schedule": 1,
    "input_a_frames": 0,
    "input_b_frames": 0,
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

def load_config():
    """Loads the main editor configuration (Favorites, Last Dir, Servers)."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
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
        except:
            pass
    return {}

def save_snippets(snippets):
    with open(SNIPPETS_FILE, 'w') as f:
        json.dump(snippets, f, indent=4)

def load_json(path):
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

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

def get_file_mtime(path):
    """Returns the modification time of a file, or 0 if it doesn't exist."""
    path = Path(path)
    if path.exists():
        return path.stat().st_mtime
    return 0

def generate_templates(current_dir):
    """Creates dummy template files if folder is empty."""
    save_json(current_dir / "template_i2v.json", DEFAULTS)
    
    batch_data = {"batch_data": [DEFAULTS.copy(), DEFAULTS.copy()]}
    save_json(current_dir / "template_batch.json", batch_data)
