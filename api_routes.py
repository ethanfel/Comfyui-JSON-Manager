"""REST API endpoints for ComfyUI to query project data from JSON files.

All endpoints are read-only. Mounted on the NiceGUI/FastAPI server.
"""

import logging
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Query
from nicegui import app

from db import ProjectDB
from utils import load_json, KEY_BATCH_DATA, KEY_SEQUENCE_NUMBER

logger = logging.getLogger(__name__)

# The DB instance is set by register_api_routes()
_db: ProjectDB | None = None


def register_api_routes(db: ProjectDB) -> None:
    """Register all REST API routes with the NiceGUI/FastAPI app."""
    global _db
    _db = db

    app.add_api_route("/api/projects", _list_projects, methods=["GET"])
    app.add_api_route("/api/projects/{name}/files", _list_files, methods=["GET"])
    app.add_api_route("/api/projects/{name}/files/{file_name}/sequences", _list_sequences, methods=["GET"])
    app.add_api_route("/api/projects/{name}/files/{file_name}/data", _get_data, methods=["GET"])
    app.add_api_route("/api/projects/{name}/files/{file_name}/keys", _get_keys, methods=["GET"])


def _get_db() -> ProjectDB:
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return _db


def _list_projects() -> dict[str, Any]:
    db = _get_db()
    projects = db.list_projects()
    return {"projects": [p["name"] for p in projects]}


def _list_files(name: str) -> dict[str, Any]:
    db = _get_db()
    files = db.list_project_files(name)
    return {"files": [{"name": f["name"], "data_type": f["data_type"]} for f in files]}


def _list_sequences(name: str, file_name: str) -> dict[str, Any]:
    db = _get_db()
    seqs = db.list_project_sequences(name, file_name)
    return {"sequences": seqs}


def _load_sequences(name: str, file_name: str) -> list[dict]:
    """Load the batch_data list directly from the JSON file."""
    db = _get_db()
    proj = db.get_project(name)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
    json_path = Path(proj["folder_path"]) / f"{file_name}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{file_name}' not found in project '{name}'")
    data, _ = load_json(json_path)
    return data.get(KEY_BATCH_DATA, [])


def _get_data(name: str, file_name: str, seq: int = Query(default=1)) -> dict[str, Any]:
    t0 = time.perf_counter()
    sequences = _load_sequences(name, file_name)
    match = next((s for s in sequences if int(s.get(KEY_SEQUENCE_NUMBER, 0)) == seq), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Sequence {seq} not found")
    logger.info("API _get_data %s/%s seq=%d (%d keys): %.3fs",
                 name, file_name, seq, len(match), time.perf_counter() - t0)
    return match


def _get_keys(name: str, file_name: str, seq: int = Query(default=1)) -> dict[str, Any]:
    t0 = time.perf_counter()
    sequences = _load_sequences(name, file_name)
    match = next((s for s in sequences if int(s.get(KEY_SEQUENCE_NUMBER, 0)) == seq), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Sequence {seq} not found")
    keys = [k for k in match.keys() if k != KEY_SEQUENCE_NUMBER]
    types = []
    for k in keys:
        v = match[k]
        if isinstance(v, bool):
            types.append("BOOLEAN")
        elif isinstance(v, int):
            types.append("INT")
        elif isinstance(v, float):
            types.append("FLOAT")
        else:
            types.append("STRING")
    total = len(sequences)
    logger.info("API _get_keys %s/%s seq=%d (%d keys): %.3fs",
                 name, file_name, seq, len(keys), time.perf_counter() - t0)
    return {"keys": keys, "types": types, "total_sequences": total}
