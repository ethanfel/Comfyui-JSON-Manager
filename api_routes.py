"""REST API endpoints for ComfyUI to query project data from SQLite.

All endpoints are read-only. Mounted on the NiceGUI/FastAPI server.
"""

import logging
from typing import Any

from fastapi import HTTPException, Query
from nicegui import app

from db import ProjectDB

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


def _get_data(name: str, file_name: str, seq: int = Query(default=1)) -> dict[str, Any]:
    db = _get_db()
    proj = db.get_project(name)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
    df = db.get_data_file_by_names(name, file_name)
    if not df:
        raise HTTPException(status_code=404, detail=f"File '{file_name}' not found in project '{name}'")
    data = db.get_sequence(df["id"], seq)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Sequence {seq} not found")
    return data


def _get_keys(name: str, file_name: str, seq: int = Query(default=1)) -> dict[str, Any]:
    db = _get_db()
    proj = db.get_project(name)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
    df = db.get_data_file_by_names(name, file_name)
    if not df:
        raise HTTPException(status_code=404, detail=f"File '{file_name}' not found in project '{name}'")
    keys, types = db.get_sequence_keys(df["id"], seq)
    total = db.count_sequences(df["id"])
    return {"keys": keys, "types": types, "total_sequences": total}
