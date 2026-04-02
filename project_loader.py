import asyncio
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
    """Fetch JSON from a URL using stdlib urllib.

    On error, returns a dict with an "error" key describing the failure.
    """
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # HTTPError is a subclass of URLError — must be caught first
        body = ""
        try:
            raw = e.read()
            detail = json.loads(raw)
            body = detail.get("detail", str(raw, "utf-8", errors="replace"))
        except Exception:
            body = str(e)
        logger.warning(f"HTTP {e.code} from {url}: {body}")
        return {"error": "http_error", "status": e.code, "message": body}
    except (urllib.error.URLError, OSError) as e:
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        logger.warning(f"Network error fetching {url}: {reason}")
        return {"error": "network_error", "message": reason}
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON from {url}: {e}")
        return {"error": "parse_error", "message": str(e)}


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
        data = await asyncio.to_thread(_fetch_json, url)
        return web.json_response(data)

    @PromptServer.instance.routes.get("/json_manager/list_project_files")
    async def list_project_files_proxy(request):
        manager_url = request.query.get("url", "http://localhost:8080")
        project = urllib.parse.quote(request.query.get("project", ""), safe='')
        url = f"{manager_url.rstrip('/')}/api/projects/{project}/files"
        data = await asyncio.to_thread(_fetch_json, url)
        return web.json_response(data)

    @PromptServer.instance.routes.get("/json_manager/list_project_sequences")
    async def list_project_sequences_proxy(request):
        manager_url = request.query.get("url", "http://localhost:8080")
        project = urllib.parse.quote(request.query.get("project", ""), safe='')
        file_name = urllib.parse.quote(request.query.get("file", ""), safe='')
        url = f"{manager_url.rstrip('/')}/api/projects/{project}/files/{file_name}/sequences"
        data = await asyncio.to_thread(_fetch_json, url)
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
        data = await asyncio.to_thread(_fetch_keys, manager_url, project, file_name, seq)
        if data.get("error") in ("http_error", "network_error", "parse_error"):
            status = data.get("status", 502)
            return web.json_response(data, status=status)
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
                "refresh": (["off", "on"],),
            },
            "optional": {
                "output_keys": ("STRING", {"default": ""}),
                "output_types": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("INT",) + tuple(any_type for _ in range(MAX_DYNAMIC_OUTPUTS))
    RETURN_NAMES = ("total_sequences",) + tuple(f"output_{i}" for i in range(MAX_DYNAMIC_OUTPUTS))
    FUNCTION = "load_dynamic"
    CATEGORY = "utils/json/project"
    OUTPUT_NODE = False

    def load_dynamic(self, manager_url, project_name, file_name, sequence_number,
                     refresh="off", output_keys="", output_types=""):
        # Fetch keys metadata (includes total_sequences count)
        keys_meta = _fetch_keys(manager_url, project_name, file_name, sequence_number)
        if keys_meta.get("error") in ("http_error", "network_error", "parse_error"):
            msg = keys_meta.get("message", "Unknown error")
            raise RuntimeError(f"Failed to fetch project keys: {msg}")
        total_sequences = keys_meta.get("total_sequences", 0)

        data = _fetch_data(manager_url, project_name, file_name, sequence_number)
        if data.get("error") in ("http_error", "network_error", "parse_error"):
            msg = data.get("message", "Unknown error")
            raise RuntimeError(f"Failed to fetch sequence data: {msg}")

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

        return (total_sequences,) + tuple(results)


class ProjectSource:
    """Config node — holds project connection settings, outputs sequence_number."""
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "manager_url": ("STRING", {"default": "http://localhost:8080", "multiline": False}),
                "project_name": ("STRING", {"default": "", "multiline": False}),
                "file_name": ("STRING", {"default": "", "multiline": False}),
                "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
                "label": ("STRING", {"default": "source", "multiline": False}),
            },
        }

    RETURN_TYPES = ("INT", "STRING",)
    RETURN_NAMES = ("sequence_number", "file_name",)
    FUNCTION = "hold_config"
    CATEGORY = "utils/json/project"
    OUTPUT_NODE = True

    def hold_config(self, manager_url, project_name, file_name, sequence_number, label):
        return (sequence_number, file_name,)


class ProjectKey:
    """Single-output relay — fetches one key from a ProjectSource."""
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "source_label": ("STRING", {"default": "", "multiline": False}),
                "key_name": ("STRING", {"default": "", "multiline": False}),
                "key_type": ("STRING", {"default": "STRING", "multiline": False}),
            },
            "optional": {
                "manager_url": ("STRING", {"default": "http://localhost:8080", "multiline": False}),
                "project_name": ("STRING", {"default": "", "multiline": False}),
                "file_name": ("STRING", {"default": "", "multiline": False}),
                "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
            },
        }

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("value",)
    FUNCTION = "fetch_key"
    CATEGORY = "utils/json/project"
    OUTPUT_NODE = False

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")  # Always re-fetch from API

    def fetch_key(self, source_label, key_name, key_type,
                  manager_url="http://localhost:8080", project_name="",
                  file_name="", sequence_number=1):
        # source_label is used by JS to identify which ProjectSource to sync
        # config from. The actual config arrives via the optional widgets below.
        sequence_number = int(sequence_number)
        logger.info("ProjectKey.fetch_key: source=%s key=%s url=%s project=%s file=%s seq=%s",
                     source_label, key_name, manager_url, project_name, file_name, sequence_number)
        data = _fetch_data(manager_url, project_name, file_name, sequence_number)
        if data.get("error") in ("http_error", "network_error", "parse_error"):
            msg = data.get("message", "Unknown error")
            logger.warning("ProjectKey.fetch_key failed: %s", msg)
            # Return empty/default instead of crashing the workflow
            if key_type == "INT":
                return (0,)
            elif key_type == "FLOAT":
                return (0.0,)
            else:
                return ("",)

        val = data.get(key_name, "")

        if key_type == "INT":
            return (to_int(val),)
        elif key_type == "FLOAT":
            return (to_float(val),)
        elif isinstance(val, bool):
            return (str(val).lower(),)
        elif isinstance(val, (int, float)):
            return (val,)
        else:
            return (str(val),)


class ProjectResolution:
    """Fetches a (width, height) pair from a resolution series by loop index."""
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "source_label": ("STRING", {"default": "", "multiline": False}),
                "key_name": ("STRING", {"default": "resolutions", "multiline": False}),
                "index": ("INT", {"default": 0, "min": 0, "max": 9999}),
            },
            "optional": {
                "manager_url": ("STRING", {"default": "http://localhost:8080", "multiline": False}),
                "project_name": ("STRING", {"default": "", "multiline": False}),
                "file_name": ("STRING", {"default": "", "multiline": False}),
                "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
            },
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "fetch_resolution"
    CATEGORY = "utils/json/project"
    OUTPUT_NODE = False

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def fetch_resolution(self, source_label, key_name, index,
                         manager_url="http://localhost:8080", project_name="",
                         file_name="", sequence_number=1):
        sequence_number = int(sequence_number)
        logger.info("ProjectResolution.fetch_resolution: source=%s key=%s url=%s project=%s file=%s seq=%s index=%s",
                     source_label, key_name, manager_url, project_name, file_name, sequence_number, index)
        # source_label is used by JS to identify which ProjectSource to sync
        # config from. The actual config arrives via the optional widgets below.
        data = _fetch_data(manager_url, project_name, file_name, sequence_number)
        if data.get("error") in ("http_error", "network_error", "parse_error"):
            logger.warning("ProjectResolution.fetch_resolution failed: %s", data.get("message"))
            return (512, 512)

        series = data.get(key_name)
        if not isinstance(series, list) or len(series) == 0:
            logger.warning("ProjectResolution: key '%s' is not a resolution series", key_name)
            return (512, 512)

        clamped = max(0, min(index, len(series) - 1))
        entry = series[clamped]
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            logger.warning("ProjectResolution: entry at index %d is malformed: %r", clamped, entry)
            return (512, 512)

        return (to_int(entry[0]), to_int(entry[1]))


# --- Mappings ---
PROJECT_NODE_CLASS_MAPPINGS = {
    "ProjectLoaderDynamic": ProjectLoaderDynamic,
    "ProjectSource": ProjectSource,
    "ProjectKey": ProjectKey,
    "ProjectResolution": ProjectResolution,
}

PROJECT_NODE_DISPLAY_NAME_MAPPINGS = {
    "ProjectLoaderDynamic": "Project Loader (Dynamic)",
    "ProjectSource": "Project Source",
    "ProjectKey": "Project Key",
    "ProjectResolution": "Project Resolution",
}
