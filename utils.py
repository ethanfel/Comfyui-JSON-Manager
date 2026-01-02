import json
import time
from pathlib import Path
import streamlit as st
import requests  # <--- NEW DEPENDENCY

# Default structure for new files
DEFAULTS = {
    "positive_prompt": "",
    "negative_prompt": "",
    "seed": -1,
    "steps": 20,
    "cfg": 7.0,
    "sampler_name": "euler",
    "scheduler": "normal",
    "denoise": 1.0,
    "model_name": "v1-5-pruned-emaonly.ckpt",
    "vae_name": "vae-ft-mse-840000-ema-pruned.ckpt",
    # I2V / VACE Specifics
    "frame_to_skip": 81,
    "vace schedule": 1,
    "video file path": "",
    "reference image path": "",
    "flf": 0.0,
    "camera": "static",
    # LoRAs
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
    # Merge existing config to prevent data loss
    existing = load_config()
    data.update(existing)
    
    # Update with new 'last_dir' and 'favorites'
    data["last_dir"] = str(current_dir)
    data["favorites"] = favorites
    
    # Update with any extra data passed (like server lists)
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

# --- NEW: COMFY METADATA FETCHER ---
def fetch_comfy_metadata(base_url):
    """Queries ComfyUI for available Models, VAEs, and LoRAs."""
    url = base_url.rstrip("/")
    meta = {"checkpoints": [], "loras": [], "vaes": []}
    
    try:
        # Get Node Info to find input lists
        res = requests.get(f"{url}/object_info", timeout=2)
        if res.status_code == 200:
            data = res.json()
            
            # Checkpoints
            if "CheckpointLoaderSimple" in data:
                meta["checkpoints"] = data["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
            
            # LoRAs
            if "LoraLoader" in data:
                meta["loras"] = data["LoraLoader"]["input"]["required"]["lora_name"][0]
                
            # VAEs
            if "VAELoader" in data:
                meta["vaes"] = data["VAELoader"]["input"]["required"]["vae_name"][0]
                
        return meta
    except Exception:
        # Fail silently so the app still works offline
        return meta

# --- NEW: SMART INPUT WIDGET ---
def render_smart_input(label, key, value, options, help_text=None):
    """
    Renders a Selectbox if options are available, otherwise a Text Input.
    Handles the case where the current 'value' might not be in the 'options' list.
    """
    if options and len(options) > 0:
        # If current value is not in the list (e.g. new file added), add it temporarily
        safe_options = options.copy()
        if value and value not in safe_options:
            safe_options.insert(0, value)
        elif not value and safe_options:
            # Default to first if empty
            value = safe_options[0]
            
        # Try to find index
        try:
            idx = safe_options.index(value)
        except ValueError:
            idx = 0
            
        return st.selectbox(label, safe_options, index=idx, key=key, help=help_text)
    else:
        # Fallback to text input if Comfy is offline or list empty
        return st.text_input(label, value=value, key=key, help=help_text)
