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


async def _list_projects() -> dict[str, Any]:
    db = _get_db()
    projects = db.list_projects()
    return {"projects": [p["name"] for p in projects]}


async def _list_files(name: str) -> dict[str, Any]:
    db = _get_db()
    files = db.list_project_files(name)
    return {"files": [{"name": f["name"], "data_type": f["data_type"]} for f in files]}


async def _list_sequences(name: str, file_name: str) -> dict[str, Any]:
    db = _get_db()
    seqs = db.list_project_sequences(name, file_name)
    return {"sequences": seqs}


async def _get_data(name: str, file_name: str, seq: int = Query(default=1)) -> dict[str, Any]:
    db = _get_db()
    data = db.query_sequence_data(name, file_name, seq)
    if data is None:
        raise HTTPException(status_code=404, detail="Sequence not found")
    return data


async def _get_keys(name: str, file_name: str, seq: int = Query(default=1)) -> dict[str, Any]:
    db = _get_db()
    keys, types = db.query_sequence_keys(name, file_name, seq)
    return {"keys": keys, "types": types}
