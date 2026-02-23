import json
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

KEY_BATCH_DATA = "batch_data"
MAX_DYNAMIC_OUTPUTS = 32


class AnyType(str):
    """Universal connector type that matches any ComfyUI type."""
    def __ne__(self, __value: object) -> bool:
        return False

any_type = AnyType("*")


try:
    from server import PromptServer
    from aiohttp import web
except ImportError:
    PromptServer = None


def to_float(val: Any) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def to_int(val: Any) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0

def get_batch_item(data: dict[str, Any], sequence_number: int) -> dict[str, Any]:
    """Resolve batch item by sequence_number field, falling back to array index."""
    if KEY_BATCH_DATA in data and isinstance(data[KEY_BATCH_DATA], list) and len(data[KEY_BATCH_DATA]) > 0:
        # Search by sequence_number field first
        for item in data[KEY_BATCH_DATA]:
            if int(item.get("sequence_number", 0)) == sequence_number:
                return item
        # Fallback to array index
        idx = max(0, min(sequence_number - 1, len(data[KEY_BATCH_DATA]) - 1))
        logger.warning(f"No item with sequence_number={sequence_number}, falling back to index {idx}")
        return data[KEY_BATCH_DATA][idx]
    return data

# --- Shared Helper ---
def read_json_data(json_path: str) -> dict[str, Any]:
    if not os.path.exists(json_path):
        logger.warning(f"File not found at {json_path}")
        return {}
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Error reading {json_path}: {e}")
        return {}
    if not isinstance(data, dict):
        logger.warning(f"Expected dict from {json_path}, got {type(data).__name__}")
        return {}
    return data

# --- API Route ---
if PromptServer is not None:
    @PromptServer.instance.routes.get("/json_manager/get_keys")
    async def get_keys_route(request):
        json_path = request.query.get("path", "")
        try:
            seq = int(request.query.get("sequence_number", "1"))
        except (ValueError, TypeError):
            seq = 1
        data = read_json_data(json_path)
        target = get_batch_item(data, seq)
        keys = []
        types = []
        if isinstance(target, dict):
            for k, v in target.items():
                keys.append(k)
                if isinstance(v, bool):
                    types.append("STRING")
                elif isinstance(v, int):
                    types.append("INT")
                elif isinstance(v, float):
                    types.append("FLOAT")
                else:
                    types.append("STRING")
        return web.json_response({"keys": keys, "types": types})


# ==========================================
# 0. DYNAMIC NODE
# ==========================================

class JSONLoaderDynamic:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "json_path": ("STRING", {"default": "", "multiline": False}),
                "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
            },
            "optional": {
                "output_keys": ("STRING", {"default": ""}),
                "output_types": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = tuple(any_type for _ in range(MAX_DYNAMIC_OUTPUTS))
    RETURN_NAMES = tuple(f"output_{i}" for i in range(MAX_DYNAMIC_OUTPUTS))
    FUNCTION = "load_dynamic"
    CATEGORY = "utils/json"
    OUTPUT_NODE = False

    def load_dynamic(self, json_path, sequence_number, output_keys="", output_types=""):
        data = read_json_data(json_path)
        target = get_batch_item(data, sequence_number)

        keys = [k.strip() for k in output_keys.split(",") if k.strip()] if output_keys else []

        results = []
        for key in keys:
            val = target.get(key, "")
            if isinstance(val, bool):
                results.append(str(val).lower())
            elif isinstance(val, int):
                results.append(val)
            elif isinstance(val, float):
                results.append(val)
            else:
                results.append(str(val))

        # Pad to MAX_DYNAMIC_OUTPUTS
        while len(results) < MAX_DYNAMIC_OUTPUTS:
            results.append("")

        return tuple(results)


# ==========================================
# 1. STANDARD NODES (Single File)
# ==========================================

class JSONLoaderLoRA:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"json_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("lora_1_high", "lora_1_low", "lora_2_high", "lora_2_low", "lora_3_high", "lora_3_low")
    FUNCTION = "load_loras"
    CATEGORY = "utils/json"

    def load_loras(self, json_path):
        data = read_json_data(json_path)
        return (
            str(data.get("lora 1 high", "")), str(data.get("lora 1 low", "")),
            str(data.get("lora 2 high", "")), str(data.get("lora 2 low", "")),
            str(data.get("lora 3 high", "")), str(data.get("lora 3 low", ""))
        )

class JSONLoaderStandard:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"json_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "FLOAT", "INT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("general_prompt", "general_negative", "current_prompt", "negative", "camera", "flf", "seed", "video_file_path", "reference_image_path", "flf_image_path")
    FUNCTION = "load_standard"
    CATEGORY = "utils/json"

    def load_standard(self, json_path):
        data = read_json_data(json_path)


        return (
            str(data.get("general_prompt", "")), str(data.get("general_negative", "")),
            str(data.get("current_prompt", "")), str(data.get("negative", "")),
            str(data.get("camera", "")), to_float(data.get("flf", 0.0)),
            to_int(data.get("seed", 0)), str(data.get("video file path", "")),
            str(data.get("reference image path", "")), str(data.get("flf image path", ""))
        )

class JSONLoaderVACE:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"json_path": ("STRING", {"default": "", "multiline": False})}}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "FLOAT", "INT", "INT", "INT", "INT", "STRING", "INT", "INT", "STRING", "STRING")
    RETURN_NAMES = ("general_prompt", "general_negative", "current_prompt", "negative", "camera", "flf", "seed", "frame_to_skip", "input_a_frames", "input_b_frames", "reference_path", "reference_switch", "vace_schedule", "video_file_path", "reference_image_path")
    FUNCTION = "load_vace"
    CATEGORY = "utils/json"

    def load_vace(self, json_path):
        data = read_json_data(json_path)


        return (
            str(data.get("general_prompt", "")), str(data.get("general_negative", "")),
            str(data.get("current_prompt", "")), str(data.get("negative", "")),
            str(data.get("camera", "")), to_float(data.get("flf", 0.0)),
            to_int(data.get("seed", 0)),
            to_int(data.get("frame_to_skip", 81)), to_int(data.get("input_a_frames", 0)),
            to_int(data.get("input_b_frames", 0)), str(data.get("reference path", "")),
            to_int(data.get("reference switch", 1)), to_int(data.get("vace schedule", 1)),
            str(data.get("video file path", "")), str(data.get("reference image path", ""))
        )

# ==========================================
# 2. BATCH NODES
# ==========================================

class JSONLoaderBatchLoRA:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"json_path": ("STRING", {"default": "", "multiline": False}), "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999})}}
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("lora_1_high", "lora_1_low", "lora_2_high", "lora_2_low", "lora_3_high", "lora_3_low")
    FUNCTION = "load_batch_loras"
    CATEGORY = "utils/json"

    def load_batch_loras(self, json_path, sequence_number):
        data = read_json_data(json_path)
        target_data = get_batch_item(data, sequence_number)
        return (
            str(target_data.get("lora 1 high", "")), str(target_data.get("lora 1 low", "")),
            str(target_data.get("lora 2 high", "")), str(target_data.get("lora 2 low", "")),
            str(target_data.get("lora 3 high", "")), str(target_data.get("lora 3 low", ""))
        )

class JSONLoaderBatchI2V:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"json_path": ("STRING", {"default": "", "multiline": False}), "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999})}}
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "FLOAT", "INT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("general_prompt", "general_negative", "current_prompt", "negative", "camera", "flf", "seed", "video_file_path", "reference_image_path", "flf_image_path")
    FUNCTION = "load_batch_i2v"
    CATEGORY = "utils/json"

    def load_batch_i2v(self, json_path, sequence_number):
        data = read_json_data(json_path)
        target_data = get_batch_item(data, sequence_number)

        return (
            str(target_data.get("general_prompt", "")), str(target_data.get("general_negative", "")),
            str(target_data.get("current_prompt", "")), str(target_data.get("negative", "")),
            str(target_data.get("camera", "")), to_float(target_data.get("flf", 0.0)),
            to_int(target_data.get("seed", 0)), str(target_data.get("video file path", "")),
            str(target_data.get("reference image path", "")), str(target_data.get("flf image path", ""))
        )

class JSONLoaderBatchVACE:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"json_path": ("STRING", {"default": "", "multiline": False}), "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999})}}
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "FLOAT", "INT", "INT", "INT", "INT", "STRING", "INT", "INT", "STRING", "STRING")
    RETURN_NAMES = ("general_prompt", "general_negative", "current_prompt", "negative", "camera", "flf", "seed", "frame_to_skip", "input_a_frames", "input_b_frames", "reference_path", "reference_switch", "vace_schedule", "video_file_path", "reference_image_path")
    FUNCTION = "load_batch_vace"
    CATEGORY = "utils/json"

    def load_batch_vace(self, json_path, sequence_number):
        data = read_json_data(json_path)
        target_data = get_batch_item(data, sequence_number)

        return (
            str(target_data.get("general_prompt", "")), str(target_data.get("general_negative", "")),
            str(target_data.get("current_prompt", "")), str(target_data.get("negative", "")),
            str(target_data.get("camera", "")), to_float(target_data.get("flf", 0.0)),
            to_int(target_data.get("seed", 0)), to_int(target_data.get("frame_to_skip", 81)),
            to_int(target_data.get("input_a_frames", 0)), to_int(target_data.get("input_b_frames", 0)),
            str(target_data.get("reference path", "")), to_int(target_data.get("reference switch", 1)),
            to_int(target_data.get("vace schedule", 1)), str(target_data.get("video file path", "")),
            str(target_data.get("reference image path", ""))
        )

# ==========================================
# 3. UNIVERSAL CUSTOM NODES (1, 3, 6 Slots)
# ==========================================

class JSONLoaderCustom1:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "json_path": ("STRING", {"default": "", "multiline": False}),
                "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
            },
            "optional": { "key_1": ("STRING", {"default": "", "multiline": False}) }
        }
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("val_1",)
    FUNCTION = "load_custom"
    CATEGORY = "utils/json"

    def load_custom(self, json_path, sequence_number, key_1=""):
        data = read_json_data(json_path)
        target_data = get_batch_item(data, sequence_number)
        return (str(target_data.get(key_1, "")),)

class JSONLoaderCustom3:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "json_path": ("STRING", {"default": "", "multiline": False}),
                "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
            },
            "optional": {
                "key_1": ("STRING", {"default": "", "multiline": False}),
                "key_2": ("STRING", {"default": "", "multiline": False}),
                "key_3": ("STRING", {"default": "", "multiline": False})
            }
        }
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("val_1", "val_2", "val_3")
    FUNCTION = "load_custom"
    CATEGORY = "utils/json"

    def load_custom(self, json_path, sequence_number, key_1="", key_2="", key_3=""):
        data = read_json_data(json_path)
        target_data = get_batch_item(data, sequence_number)
        return (
            str(target_data.get(key_1, "")),
            str(target_data.get(key_2, "")),
            str(target_data.get(key_3, ""))
        )

class JSONLoaderCustom6:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "json_path": ("STRING", {"default": "", "multiline": False}),
                "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
            },
            "optional": {
                "key_1": ("STRING", {"default": "", "multiline": False}),
                "key_2": ("STRING", {"default": "", "multiline": False}),
                "key_3": ("STRING", {"default": "", "multiline": False}),
                "key_4": ("STRING", {"default": "", "multiline": False}),
                "key_5": ("STRING", {"default": "", "multiline": False}),
                "key_6": ("STRING", {"default": "", "multiline": False})
            }
        }
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("val_1", "val_2", "val_3", "val_4", "val_5", "val_6")
    FUNCTION = "load_custom"
    CATEGORY = "utils/json"

    def load_custom(self, json_path, sequence_number, key_1="", key_2="", key_3="", key_4="", key_5="", key_6=""):
        data = read_json_data(json_path)
        target_data = get_batch_item(data, sequence_number)
        return (
            str(target_data.get(key_1, "")), str(target_data.get(key_2, "")),
            str(target_data.get(key_3, "")), str(target_data.get(key_4, "")),
            str(target_data.get(key_5, "")), str(target_data.get(key_6, ""))
        )

# --- Mappings ---
NODE_CLASS_MAPPINGS = {
    "JSONLoaderDynamic": JSONLoaderDynamic,
    "JSONLoaderLoRA": JSONLoaderLoRA,
    "JSONLoaderStandard": JSONLoaderStandard,
    "JSONLoaderVACE": JSONLoaderVACE,
    "JSONLoaderBatchLoRA": JSONLoaderBatchLoRA,
    "JSONLoaderBatchI2V": JSONLoaderBatchI2V,
    "JSONLoaderBatchVACE": JSONLoaderBatchVACE,
    "JSONLoaderCustom1": JSONLoaderCustom1,
    "JSONLoaderCustom3": JSONLoaderCustom3,
    "JSONLoaderCustom6": JSONLoaderCustom6
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "JSONLoaderDynamic": "JSON Loader (Dynamic)",
    "JSONLoaderLoRA": "JSON Loader (LoRAs Only)",
    "JSONLoaderStandard": "JSON Loader (Standard/I2V)",
    "JSONLoaderVACE": "JSON Loader (VACE Full)",
    "JSONLoaderBatchLoRA": "JSON Batch Loader (LoRAs)",
    "JSONLoaderBatchI2V": "JSON Batch Loader (I2V)",
    "JSONLoaderBatchVACE": "JSON Batch Loader (VACE)",
    "JSONLoaderCustom1": "JSON Loader (Custom 1)",
    "JSONLoaderCustom3": "JSON Loader (Custom 3)",
    "JSONLoaderCustom6": "JSON Loader (Custom 6)"
}
