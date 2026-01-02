import json
import os
from pathlib import Path

CONFIG_FILE = Path(".editor_config.json")
SNIPPETS_FILE = Path(".editor_snippets.json")

# --- Defaults ---
DEFAULTS = {
    "camera": "Camera stand still. Motion starts immediately.",
    "flf": 0,
    "seed": 0,
    "frame_to_skip": 81,
    "input_a_frames": 0,
    "input_b_frames": 0,
    "reference path": "",
    "reference switch": 1,
    "vace schedule": 1,
    "video file path": "",
    "reference image path": "",
    "flf image path": "",
    
    # --- PROMPTS ---
    "general_prompt": "",
    "general_negative": "Vivid tones, overexposed, static, blurry details, subtitles, style, artwork, painting, picture, still image, overall gray, worst quality, low quality, JPEG compression artifacts, ugly, deformed, extra fingers, poorly drawn hands, poorly drawn face, distorted, disfigured, malformed limbs, fused fingers, unmoving frame, cluttered background, three legs,",
    "current_prompt": "",
    "negative": "",
    
    # --- LORAS ---
    "lora 1 high": "", "lora 1 low": "",
    "lora 2 high": "", "lora 2 low": "",
    "lora 3 high": "", "lora 3 low": "",
    "prompt_history": []
}

GENERIC_TEMPLATES = ["prompt_i2v.json", "prompt_vace_extend.json", "batch_i2v.json", "batch_vace.json"]

# --- I/O Functions ---
def get_file_mtime(path):
    if path.exists(): return os.path.getmtime(path)
    return 0

def load_json(path):
    if not path.exists(): return DEFAULTS.copy(), 0
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            
        # Ensure migration happens if loading old file
        # We don't change structure here, HistoryTree class handles logic
        
        return data, get_file_mtime(path)
    except:
        return DEFAULTS.copy(), 0

def save_json(path, data):
    if path.exists():
        try:
            with open(path, 'r') as f:
                existing = json.load(f)
            if isinstance(existing, dict) and isinstance(data, dict):
                existing.update(data)
                data = existing
        except: pass
        
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)
    return get_file_mtime(path)

def load_config():
    if CONFIG_FILE.exists():
        try: 
            with open(CONFIG_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"last_dir": str(Path.cwd()), "favorites": []}

def save_config(current_dir, favorites):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"last_dir": str(current_dir), "favorites": favorites}, f, indent=4)

def load_snippets():
    if SNIPPETS_FILE.exists():
        try: 
            with open(SNIPPETS_FILE, 'r') as f: return json.load(f)
        except: pass
    return {}

def save_snippets(snippets):
    with open(SNIPPETS_FILE, 'w') as f:
        json.dump(snippets, f, indent=4)

def generate_templates(directory):
    for filename in GENERIC_TEMPLATES:
        path = directory / filename
        if "batch" in filename:
            data = {"batch_data": []} 
        else:
            data = DEFAULTS.copy()
            if "vace" in filename: 
                data.update({"frame_to_skip": 81, "vace schedule": 1, "video file path": ""})
            elif "i2v" in filename: 
                data.update({"reference image path": "", "flf image path": ""})
        save_json(path, data)
