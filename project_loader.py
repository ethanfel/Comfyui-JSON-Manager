import json
import logging
import urllib.parse
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)

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


def _fetch_json(url: str) -> dict:
    """Fetch JSON from a URL using stdlib urllib."""
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return {}


def _fetch_data(manager_url: str, project: str, file: str, seq: int) -> dict:
    """Fetch sequence data from the NiceGUI REST API."""
    p = urllib.parse.quote(project, safe='')
    f = urllib.parse.quote(file, safe='')
    url = f"{manager_url.rstrip('/')}/api/projects/{p}/files/{f}/data?seq={seq}"
    return _fetch_json(url)


def _fetch_keys(manager_url: str, project: str, file: str, seq: int) -> dict:
    """Fetch keys/types from the NiceGUI REST API."""
    p = urllib.parse.quote(project, safe='')
    f = urllib.parse.quote(file, safe='')
    url = f"{manager_url.rstrip('/')}/api/projects/{p}/files/{f}/keys?seq={seq}"
    return _fetch_json(url)


# --- ComfyUI-side proxy endpoints (for frontend JS) ---
if PromptServer is not None:
    @PromptServer.instance.routes.get("/json_manager/list_projects")
    async def list_projects_proxy(request):
        manager_url = request.query.get("url", "http://localhost:8080")
        url = f"{manager_url.rstrip('/')}/api/projects"
        data = _fetch_json(url)
        return web.json_response(data)

    @PromptServer.instance.routes.get("/json_manager/list_project_files")
    async def list_project_files_proxy(request):
        manager_url = request.query.get("url", "http://localhost:8080")
        project = urllib.parse.quote(request.query.get("project", ""), safe='')
        url = f"{manager_url.rstrip('/')}/api/projects/{project}/files"
        data = _fetch_json(url)
        return web.json_response(data)

    @PromptServer.instance.routes.get("/json_manager/list_project_sequences")
    async def list_project_sequences_proxy(request):
        manager_url = request.query.get("url", "http://localhost:8080")
        project = urllib.parse.quote(request.query.get("project", ""), safe='')
        file_name = urllib.parse.quote(request.query.get("file", ""), safe='')
        url = f"{manager_url.rstrip('/')}/api/projects/{project}/files/{file_name}/sequences"
        data = _fetch_json(url)
        return web.json_response(data)

    @PromptServer.instance.routes.get("/json_manager/get_project_keys")
    async def get_project_keys_proxy(request):
        manager_url = request.query.get("url", "http://localhost:8080")
        project = request.query.get("project", "")
        file_name = request.query.get("file", "")
        try:
            seq = int(request.query.get("seq", "1"))
        except (ValueError, TypeError):
            seq = 1
        data = _fetch_keys(manager_url, project, file_name, seq)
        return web.json_response(data)



# ==========================================
# 0. DYNAMIC NODE (Project-based)
# ==========================================

class ProjectLoaderDynamic:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "manager_url": ("STRING", {"default": "http://localhost:8080", "multiline": False}),
                "project_name": ("STRING", {"default": "", "multiline": False}),
                "file_name": ("STRING", {"default": "", "multiline": False}),
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
    CATEGORY = "utils/json/project"
    OUTPUT_NODE = False

    def load_dynamic(self, manager_url, project_name, file_name, sequence_number,
                     output_keys="", output_types=""):
        data = _fetch_data(manager_url, project_name, file_name, sequence_number)

        # Parse keys — try JSON array first, fall back to comma-split for compat
        keys = []
        if output_keys:
            try:
                keys = json.loads(output_keys)
            except (json.JSONDecodeError, TypeError):
                keys = [k.strip() for k in output_keys.split(",") if k.strip()]

        # Parse types for coercion
        types = []
        if output_types:
            try:
                types = json.loads(output_types)
            except (json.JSONDecodeError, TypeError):
                types = [t.strip() for t in output_types.split(",")]

        results = []
        for i, key in enumerate(keys):
            val = data.get(key, "")
            declared_type = types[i] if i < len(types) else ""
            # Coerce based on declared output type when possible
            if declared_type == "INT":
                results.append(to_int(val))
            elif declared_type == "FLOAT":
                results.append(to_float(val))
            elif isinstance(val, bool):
                results.append(str(val).lower())
            elif isinstance(val, int):
                results.append(val)
            elif isinstance(val, float):
                results.append(val)
            else:
                results.append(str(val))

        while len(results) < MAX_DYNAMIC_OUTPUTS:
            results.append("")

        return tuple(results)


# ==========================================
# 1. STANDARD NODE (Project-based I2V)
# ==========================================

class ProjectLoaderStandard:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "manager_url": ("STRING", {"default": "http://localhost:8080", "multiline": False}),
            "project_name": ("STRING", {"default": "", "multiline": False}),
            "file_name": ("STRING", {"default": "", "multiline": False}),
            "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "FLOAT", "INT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("general_prompt", "general_negative", "current_prompt", "negative", "camera", "flf", "seed", "video_file_path", "reference_image_path", "flf_image_path")
    FUNCTION = "load_standard"
    CATEGORY = "utils/json/project"

    def load_standard(self, manager_url, project_name, file_name, sequence_number):
        data = _fetch_data(manager_url, project_name, file_name, sequence_number)
        return (
            str(data.get("general_prompt", "")), str(data.get("general_negative", "")),
            str(data.get("current_prompt", "")), str(data.get("negative", "")),
            str(data.get("camera", "")), to_float(data.get("flf", 0.0)),
            to_int(data.get("seed", 0)), str(data.get("video file path", "")),
            str(data.get("reference image path", "")), str(data.get("flf image path", ""))
        )


# ==========================================
# 2. VACE NODE (Project-based)
# ==========================================

class ProjectLoaderVACE:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "manager_url": ("STRING", {"default": "http://localhost:8080", "multiline": False}),
            "project_name": ("STRING", {"default": "", "multiline": False}),
            "file_name": ("STRING", {"default": "", "multiline": False}),
            "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "FLOAT", "INT", "INT", "INT", "INT", "STRING", "INT", "INT", "STRING", "STRING")
    RETURN_NAMES = ("general_prompt", "general_negative", "current_prompt", "negative", "camera", "flf", "seed", "frame_to_skip", "input_a_frames", "input_b_frames", "reference_path", "reference_switch", "vace_schedule", "video_file_path", "reference_image_path")
    FUNCTION = "load_vace"
    CATEGORY = "utils/json/project"

    def load_vace(self, manager_url, project_name, file_name, sequence_number):
        data = _fetch_data(manager_url, project_name, file_name, sequence_number)
        return (
            str(data.get("general_prompt", "")), str(data.get("general_negative", "")),
            str(data.get("current_prompt", "")), str(data.get("negative", "")),
            str(data.get("camera", "")), to_float(data.get("flf", 0.0)),
            to_int(data.get("seed", 0)), to_int(data.get("frame_to_skip", 81)),
            to_int(data.get("input_a_frames", 16)), to_int(data.get("input_b_frames", 16)),
            str(data.get("reference path", "")), to_int(data.get("reference switch", 1)),
            to_int(data.get("vace schedule", 1)), str(data.get("video file path", "")),
            str(data.get("reference image path", ""))
        )


# ==========================================
# 3. LoRA NODE (Project-based)
# ==========================================

class ProjectLoaderLoRA:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "manager_url": ("STRING", {"default": "http://localhost:8080", "multiline": False}),
            "project_name": ("STRING", {"default": "", "multiline": False}),
            "file_name": ("STRING", {"default": "", "multiline": False}),
            "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("lora_1_high", "lora_1_low", "lora_2_high", "lora_2_low", "lora_3_high", "lora_3_low")
    FUNCTION = "load_loras"
    CATEGORY = "utils/json/project"

    def load_loras(self, manager_url, project_name, file_name, sequence_number):
        data = _fetch_data(manager_url, project_name, file_name, sequence_number)
        return (
            str(data.get("lora 1 high", "")), str(data.get("lora 1 low", "")),
            str(data.get("lora 2 high", "")), str(data.get("lora 2 low", "")),
            str(data.get("lora 3 high", "")), str(data.get("lora 3 low", ""))
        )


# --- Mappings ---
PROJECT_NODE_CLASS_MAPPINGS = {
    "ProjectLoaderDynamic": ProjectLoaderDynamic,
    "ProjectLoaderStandard": ProjectLoaderStandard,
    "ProjectLoaderVACE": ProjectLoaderVACE,
    "ProjectLoaderLoRA": ProjectLoaderLoRA,
}

PROJECT_NODE_DISPLAY_NAME_MAPPINGS = {
    "ProjectLoaderDynamic": "Project Loader (Dynamic)",
    "ProjectLoaderStandard": "Project Loader (Standard/I2V)",
    "ProjectLoaderVACE": "Project Loader (VACE Full)",
    "ProjectLoaderLoRA": "Project Loader (LoRAs)",
}
