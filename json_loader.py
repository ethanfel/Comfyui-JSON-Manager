import json
import os

# --- Shared Helper ---
def read_json_data(json_path):
    if not os.path.exists(json_path):
        print(f"[JSON Loader] Warning: File not found at {json_path}")
        return {}
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[JSON Loader] Error: {e}")
        return {}

# ==========================================
# 1. NEW DEDICATED LORA NODE
# ==========================================
class JSONLoaderLoRA:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"json_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "lora_1_high", "lora_1_low", 
        "lora_2_high", "lora_2_low", 
        "lora_3_high", "lora_3_low"
    )
    FUNCTION = "load_loras"
    CATEGORY = "utils/json"

    def load_loras(self, json_path):
        data = read_json_data(json_path)
        return (
            str(data.get("lora 1 high", "")),
            str(data.get("lora 1 low", "")),
            str(data.get("lora 2 high", "")),
            str(data.get("lora 2 low", "")),
            str(data.get("lora 3 high", "")),
            str(data.get("lora 3 low", ""))
        )

# ==========================================
# 2. MAIN NODES (STRIPPED OF LORAS)
# ==========================================

# --- Node A: Simple (Global) ---
# Unchanged, as it never had LoRAs.
class JSONLoaderSimple:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"json_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("current_prompt", "negative", "camera")
    FUNCTION = "load_simple"
    CATEGORY = "utils/json"

    def load_simple(self, json_path):
        data = read_json_data(json_path)
        return (
            str(data.get("current_prompt", "")),
            str(data.get("negative", "")),
            str(data.get("camera", ""))
        )

# --- Node B: Standard (I2V / Global Extend) ---
# Removed LoRAs. Kept FLF Image Path.
class JSONLoaderStandard:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"json_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = (
        "STRING", "STRING", "STRING", "FLOAT", 
        "STRING", "STRING", "STRING"
    )
    RETURN_NAMES = (
        "current_prompt", "negative", "camera", "flf",
        "video_file_path", "reference_image_path", "flf_image_path"
    )
    FUNCTION = "load_standard"
    CATEGORY = "utils/json"

    def load_standard(self, json_path):
        data = read_json_data(json_path)
        def to_float(val):
            try: return float(val)
            except: return 0.0

        return (
            str(data.get("current_prompt", "")),
            str(data.get("negative", "")),
            str(data.get("camera", "")),
            to_float(data.get("flf", 0.0)),
            str(data.get("video file path", "")),
            str(data.get("reference image path", "")),
            str(data.get("flf image path", ""))
        )

# --- Node C: VACE Full ---
# Removed LoRAs. Kept all VACE settings.
class JSONLoaderVACE:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"json_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = (
        "STRING", "STRING", "STRING", "FLOAT",
        "INT", "STRING", "STRING", "STRING", "INT", "INT",
        "STRING", "STRING"
    )
    RETURN_NAMES = (
        "current_prompt", "negative", "camera", "flf",
        "frame_to_skip", "input_a_frames", "input_b_frames", "reference_path", "reference_switch", "vace_schedule",
        "video_file_path", "reference_image_path"
    )
    FUNCTION = "load_vace"
    CATEGORY = "utils/json"

    def load_vace(self, json_path):
        data = read_json_data(json_path)
        def to_float(val):
            try: return float(val)
            except: return 0.0
        def to_int(val):
            try: return int(float(val))
            except: return 0

        return (
            str(data.get("current_prompt", "")),
            str(data.get("negative", "")),
            str(data.get("camera", "")),
            to_float(data.get("flf", 0.0)),
            
            to_int(data.get("frame_to_skip", 81)),
            str(data.get("input_a_frames", "")),
            str(data.get("input_b_frames", "")),
            str(data.get("reference path", "")),
            to_int(data.get("reference switch", 1)),
            to_int(data.get("vace schedule", 1)),
            
            str(data.get("video file path", "")),
            str(data.get("reference image path", ""))
        )

# --- Mappings ---
NODE_CLASS_MAPPINGS = {
    "JSONLoaderLoRA": JSONLoaderLoRA,
    "JSONLoaderSimple": JSONLoaderSimple,
    "JSONLoaderStandard": JSONLoaderStandard,
    "JSONLoaderVACE": JSONLoaderVACE
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "JSONLoaderLoRA": "JSON Loader (LoRAs Only)",
    "JSONLoaderSimple": "JSON Loader (Simple/Global)",
    "JSONLoaderStandard": "JSON Loader (Standard/I2V)",
    "JSONLoaderVACE": "JSON Loader (VACE Full)"
}
