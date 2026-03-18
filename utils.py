import copy
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

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
    "mode": 0,
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
    "lora 1 high": "", "lora 1 high strength": 1.0,
    "lora 1 low": "", "lora 1 low strength": 1.0,
    "lora 2 high": "", "lora 2 high strength": 1.0,
    "lora 2 low": "", "lora 2 low strength": 1.0,
    "lora 3 high": "", "lora 3 high strength": 1.0,
    "lora 3 low": "", "lora 3 low strength": 1.0
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
    
    if extra_data:
        data.update(extra_data)

    # Force-set explicit params last so extra_data can't override them
    data["last_dir"] = str(current_dir)
    data["favorites"] = favorites

    tmp = CONFIG_FILE.with_suffix('.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=4)
    os.replace(tmp, CONFIG_FILE)

def load_snippets():
    if SNIPPETS_FILE.exists():
        try:
            with open(SNIPPETS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load snippets: {e}")
    return {}

def save_snippets(snippets):
    tmp = SNIPPETS_FILE.with_suffix('.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(snippets, f, indent=4)
    os.replace(tmp, SNIPPETS_FILE)

def _migrate_lora_keys(data: dict) -> None:
    """Split legacy <lora:name:strength> values into separate name/strength keys in-place."""
    for item in data.get(KEY_BATCH_DATA, []):
        if not isinstance(item, dict):
            continue
        for idx in range(1, 4):
            for tier in ('high', 'low'):
                name_key = f'lora {idx} {tier}'
                str_key = f'lora {idx} {tier} strength'
                raw = str(item.get(name_key, ''))
                if raw.startswith('<lora:'):
                    inner = raw.replace('<lora:', '').replace('>', '')
                    if ':' in inner:
                        parts = inner.rsplit(':', 1)
                        item[name_key] = parts[0]
                        try:
                            item[str_key] = float(parts[1])
                        except ValueError:
                            item.setdefault(str_key, 1.0)
                    else:
                        item[name_key] = inner
                        item.setdefault(str_key, 1.0)
                elif name_key in item and str_key not in item:
                    item[str_key] = 1.0


def load_json(path: str | Path) -> tuple[dict[str, Any], float]:
    path = Path(path)
    if not path.exists():
        return DEFAULTS.copy(), 0
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        _migrate_lora_keys(data)
        return data, path.stat().st_mtime
    except Exception as e:
        logger.error(f"Error loading JSON: {e}")
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

def sync_to_db(db, project_name: str, file_path: Path, data: dict) -> None:
    """Dual-write helper: sync JSON data to the project database.

    Resolves (or creates) the data_file, upserts all sequences from batch_data,
    and saves the history_tree. All writes happen in a single transaction.
    """
    if not db or not project_name:
        return
    try:
        proj = db.get_project(project_name)
        if not proj:
            return
        file_name = Path(file_path).stem

        # Use a single transaction for atomicity
        db.conn.execute("BEGIN IMMEDIATE")
        try:
            now = time.time()
            df = db.get_data_file(proj["id"], file_name)
            top_level = {k: v for k, v in data.items()
                         if k not in (KEY_BATCH_DATA, KEY_HISTORY_TREE)}
            if not df:
                cur = db.conn.execute(
                    "INSERT INTO data_files (project_id, name, data_type, top_level, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (proj["id"], file_name, "generic", json.dumps(top_level), now, now),
                )
                df_id = cur.lastrowid
            else:
                df_id = df["id"]
                # Update top_level metadata
                db.conn.execute(
                    "UPDATE data_files SET top_level = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(top_level), now, df_id),
                )

            # Sync sequences
            batch_data = data.get(KEY_BATCH_DATA, [])
            if isinstance(batch_data, list):
                new_seq_nums = set()
                for item in batch_data:
                    if not isinstance(item, dict):
                        continue
                    seq_num = int(item.get(KEY_SEQUENCE_NUMBER, 0))
                    new_seq_nums.add(seq_num)
                    db.conn.execute(
                        "INSERT INTO sequences (data_file_id, sequence_number, data, updated_at) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(data_file_id, sequence_number) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                        (df_id, seq_num, json.dumps(item), now),
                    )
                # Remove sequences that no longer exist
                if new_seq_nums:
                    placeholders = ','.join('?' * len(new_seq_nums))
                    db.conn.execute(
                        f"DELETE FROM sequences WHERE data_file_id = ? AND sequence_number NOT IN ({placeholders})",
                        (df_id, *new_seq_nums),
                    )
                else:
                    db.conn.execute("DELETE FROM sequences WHERE data_file_id = ?", (df_id,))

            # Sync history tree
            history_tree = data.get(KEY_HISTORY_TREE)
            if history_tree and isinstance(history_tree, dict):
                db.conn.execute(
                    "INSERT INTO history_trees (data_file_id, tree_data, updated_at) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(data_file_id) DO UPDATE SET tree_data=excluded.tree_data, updated_at=excluded.updated_at",
                    (df_id, json.dumps(history_tree), now),
                )

            db.conn.execute("COMMIT")
        except Exception:
            try:
                db.conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
    except Exception as e:
        logger.warning(f"sync_to_db failed: {e}")


def generate_templates(current_dir: Path) -> None:
    """Creates batch template files if folder is empty."""
    first = copy.deepcopy(DEFAULTS)
    first[KEY_SEQUENCE_NUMBER] = 1
    save_json(current_dir / "batch_prompt_i2v.json", {KEY_BATCH_DATA: [first]})

    first2 = copy.deepcopy(DEFAULTS)
    first2[KEY_SEQUENCE_NUMBER] = 1
    save_json(current_dir / "batch_prompt_vace_extend.json", {KEY_BATCH_DATA: [first2]})
