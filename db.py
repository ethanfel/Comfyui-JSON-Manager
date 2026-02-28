import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from utils import load_json, KEY_BATCH_DATA, KEY_HISTORY_TREE

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".comfyui_json_manager" / "projects.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    folder_path TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS data_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    data_type   TEXT NOT NULL DEFAULT 'generic',
    top_level   TEXT NOT NULL DEFAULT '{}',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS sequences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    data_file_id    INTEGER NOT NULL REFERENCES data_files(id) ON DELETE CASCADE,
    sequence_number INTEGER NOT NULL,
    data            TEXT NOT NULL DEFAULT '{}',
    updated_at      REAL NOT NULL,
    UNIQUE(data_file_id, sequence_number)
);

CREATE TABLE IF NOT EXISTS history_trees (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    data_file_id  INTEGER NOT NULL UNIQUE REFERENCES data_files(id) ON DELETE CASCADE,
    tree_data     TEXT NOT NULL DEFAULT '{}',
    updated_at    REAL NOT NULL
);
"""


class ProjectDB:
    """SQLite database for project-based data management."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------------
    # Projects CRUD
    # ------------------------------------------------------------------

    def create_project(self, name: str, folder_path: str, description: str = "") -> int:
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO projects (name, folder_path, description, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, folder_path, description, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_projects(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, folder_path, description, created_at, updated_at "
            "FROM projects ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_project(self, name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, name, folder_path, description, created_at, updated_at "
            "FROM projects WHERE name = ?",
            (name,),
        ).fetchone()
        return dict(row) if row else None

    def delete_project(self, name: str) -> bool:
        cur = self.conn.execute("DELETE FROM projects WHERE name = ?", (name,))
        self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Data files
    # ------------------------------------------------------------------

    def create_data_file(
        self, project_id: int, name: str, data_type: str = "generic", top_level: dict | None = None
    ) -> int:
        now = time.time()
        tl = json.dumps(top_level or {})
        cur = self.conn.execute(
            "INSERT INTO data_files (project_id, name, data_type, top_level, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, name, data_type, tl, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_data_files(self, project_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, project_id, name, data_type, created_at, updated_at "
            "FROM data_files WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_data_file(self, project_id: int, name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, project_id, name, data_type, top_level, created_at, updated_at "
            "FROM data_files WHERE project_id = ? AND name = ?",
            (project_id, name),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["top_level"] = json.loads(d["top_level"])
        return d

    def get_data_file_by_names(self, project_name: str, file_name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT df.id, df.project_id, df.name, df.data_type, df.top_level, "
            "df.created_at, df.updated_at "
            "FROM data_files df JOIN projects p ON df.project_id = p.id "
            "WHERE p.name = ? AND df.name = ?",
            (project_name, file_name),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["top_level"] = json.loads(d["top_level"])
        return d

    # ------------------------------------------------------------------
    # Sequences
    # ------------------------------------------------------------------

    def upsert_sequence(self, data_file_id: int, sequence_number: int, data: dict) -> None:
        now = time.time()
        self.conn.execute(
            "INSERT INTO sequences (data_file_id, sequence_number, data, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(data_file_id, sequence_number) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (data_file_id, sequence_number, json.dumps(data), now),
        )
        self.conn.commit()

    def get_sequence(self, data_file_id: int, sequence_number: int) -> dict | None:
        row = self.conn.execute(
            "SELECT data FROM sequences WHERE data_file_id = ? AND sequence_number = ?",
            (data_file_id, sequence_number),
        ).fetchone()
        return json.loads(row["data"]) if row else None

    def list_sequences(self, data_file_id: int) -> list[int]:
        rows = self.conn.execute(
            "SELECT sequence_number FROM sequences WHERE data_file_id = ? ORDER BY sequence_number",
            (data_file_id,),
        ).fetchall()
        return [r["sequence_number"] for r in rows]

    def get_sequence_keys(self, data_file_id: int, sequence_number: int) -> tuple[list[str], list[str]]:
        """Returns (keys, types) for a sequence's data dict."""
        data = self.get_sequence(data_file_id, sequence_number)
        if not data:
            return [], []
        keys = []
        types = []
        for k, v in data.items():
            keys.append(k)
            if isinstance(v, bool):
                types.append("STRING")
            elif isinstance(v, int):
                types.append("INT")
            elif isinstance(v, float):
                types.append("FLOAT")
            else:
                types.append("STRING")
        return keys, types

    def delete_sequences_for_file(self, data_file_id: int) -> None:
        self.conn.execute("DELETE FROM sequences WHERE data_file_id = ?", (data_file_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # History trees
    # ------------------------------------------------------------------

    def save_history_tree(self, data_file_id: int, tree_data: dict) -> None:
        now = time.time()
        self.conn.execute(
            "INSERT INTO history_trees (data_file_id, tree_data, updated_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(data_file_id) DO UPDATE SET tree_data=excluded.tree_data, updated_at=excluded.updated_at",
            (data_file_id, json.dumps(tree_data), now),
        )
        self.conn.commit()

    def get_history_tree(self, data_file_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT tree_data FROM history_trees WHERE data_file_id = ?",
            (data_file_id,),
        ).fetchone()
        return json.loads(row["tree_data"]) if row else None

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def import_json_file(self, project_id: int, json_path: str | Path, data_type: str = "generic") -> int:
        """Import a JSON file into the database, splitting batch_data into sequences."""
        json_path = Path(json_path)
        data, _ = load_json(json_path)
        file_name = json_path.stem

        # Extract top-level keys that aren't batch_data or history_tree
        top_level = {k: v for k, v in data.items() if k not in (KEY_BATCH_DATA, KEY_HISTORY_TREE)}

        df_id = self.create_data_file(project_id, file_name, data_type, top_level)

        # Import sequences from batch_data
        batch_data = data.get(KEY_BATCH_DATA, [])
        if isinstance(batch_data, list):
            for item in batch_data:
                seq_num = int(item.get("sequence_number", 0))
                self.upsert_sequence(df_id, seq_num, item)

        # Import history tree
        history_tree = data.get(KEY_HISTORY_TREE)
        if history_tree and isinstance(history_tree, dict):
            self.save_history_tree(df_id, history_tree)

        return df_id

    # ------------------------------------------------------------------
    # Query helpers (for REST API)
    # ------------------------------------------------------------------

    def query_sequence_data(self, project_name: str, file_name: str, sequence_number: int) -> dict | None:
        """Query a single sequence by project name, file name, and sequence number."""
        df = self.get_data_file_by_names(project_name, file_name)
        if not df:
            return None
        return self.get_sequence(df["id"], sequence_number)

    def query_sequence_keys(self, project_name: str, file_name: str, sequence_number: int) -> tuple[list[str], list[str]]:
        """Query keys and types for a sequence."""
        df = self.get_data_file_by_names(project_name, file_name)
        if not df:
            return [], []
        return self.get_sequence_keys(df["id"], sequence_number)

    def list_project_files(self, project_name: str) -> list[dict]:
        """List data files for a project by name."""
        proj = self.get_project(project_name)
        if not proj:
            return []
        return self.list_data_files(proj["id"])

    def list_project_sequences(self, project_name: str, file_name: str) -> list[int]:
        """List sequence numbers for a file in a project."""
        df = self.get_data_file_by_names(project_name, file_name)
        if not df:
            return []
        return self.list_sequences(df["id"])
