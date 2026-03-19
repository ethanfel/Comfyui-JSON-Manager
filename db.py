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

CREATE TABLE IF NOT EXISTS history_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    data_file_id  INTEGER NOT NULL REFERENCES data_files(id) ON DELETE CASCADE,
    node_id       TEXT NOT NULL,
    snapshot_data TEXT NOT NULL,
    updated_at    REAL NOT NULL,
    UNIQUE(data_file_id, node_id)
);

CREATE INDEX IF NOT EXISTS idx_data_files_project_id ON data_files(project_id);
CREATE INDEX IF NOT EXISTS idx_sequences_data_file_id ON sequences(data_file_id);
CREATE INDEX IF NOT EXISTS idx_history_snapshots_df ON history_snapshots(data_file_id);
"""


class ProjectDB:
    """SQLite database for project-based data management."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit — explicit BEGIN/COMMIT only
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA_SQL)
        self._migrate_all_lora_data()

    def _migrate_all_lora_data(self) -> None:
        """One-time bulk migration: merge separate lora strength keys in all stored sequences."""
        rows = self.conn.execute("SELECT id, data FROM sequences").fetchall()
        updated = 0
        self.conn.execute("BEGIN")
        try:
            for row in rows:
                data = json.loads(row["data"])
                original = row["data"]
                migrated = self._migrate_lora_keys(data)
                new_json = json.dumps(migrated)
                if new_json != original:
                    self.conn.execute(
                        "UPDATE sequences SET data = ? WHERE id = ?",
                        (new_json, row["id"]),
                    )
                    updated += 1
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        if updated:
            logger.info("Migrated lora keys in %d/%d sequences", updated, len(rows))

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

    def list_projects_with_file_counts(self) -> list[dict]:
        """List projects with data file counts in a single query."""
        rows = self.conn.execute(
            "SELECT p.id, p.name, p.folder_path, p.description, p.created_at, p.updated_at, "
            "COUNT(df.id) AS file_count "
            "FROM projects p LEFT JOIN data_files df ON df.project_id = p.id "
            "GROUP BY p.id ORDER BY p.name"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_project(self, name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, name, folder_path, description, created_at, updated_at "
            "FROM projects WHERE name = ?",
            (name,),
        ).fetchone()
        return dict(row) if row else None

    def rename_project(self, old_name: str, new_name: str) -> bool:
        now = time.time()
        cur = self.conn.execute(
            "UPDATE projects SET name = ?, updated_at = ? WHERE name = ?",
            (new_name, now, old_name),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def update_project_path(self, name: str, folder_path: str) -> bool:
        now = time.time()
        cur = self.conn.execute(
            "UPDATE projects SET folder_path = ?, updated_at = ? WHERE name = ?",
            (folder_path, now, name),
        )
        self.conn.commit()
        return cur.rowcount > 0

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

    def count_data_files(self, project_id: int) -> int:
        """Return the number of data files for a project."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM data_files WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return row["cnt"]

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

    @staticmethod
    def _migrate_lora_keys(data: dict) -> dict:
        """Merge lora name + strength into single 'name:strength' key, remove separate strength keys."""
        for idx in range(1, 4):
            for tier in ('high', 'low'):
                name_key = f'lora {idx} {tier}'
                str_key = f'lora {idx} {tier} strength'
                raw = str(data.get(name_key, ''))
                if raw.startswith('<lora:'):
                    inner = raw.replace('<lora:', '').replace('>', '')
                    data[name_key] = inner
                    if ':' not in inner:
                        strength = data.pop(str_key, 1.0)
                        data[name_key] = f'{inner}:{float(strength)}' if inner else ''
                    else:
                        data.pop(str_key, None)
                elif str_key in data:
                    strength = float(data.pop(str_key))
                    if raw and ':' not in raw:
                        data[name_key] = f'{raw}:{strength}'
        return data

    def get_sequence(self, data_file_id: int, sequence_number: int) -> dict | None:
        row = self.conn.execute(
            "SELECT data FROM sequences WHERE data_file_id = ? AND sequence_number = ?",
            (data_file_id, sequence_number),
        ).fetchone()
        if not row:
            return None
        data = json.loads(row["data"])
        return self._migrate_lora_keys(data)

    def list_sequences(self, data_file_id: int) -> list[int]:
        rows = self.conn.execute(
            "SELECT sequence_number FROM sequences WHERE data_file_id = ? ORDER BY sequence_number",
            (data_file_id,),
        ).fetchall()
        return [r["sequence_number"] for r in rows]

    def count_sequences(self, data_file_id: int) -> int:
        """Return the number of sequences for a data file."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM sequences WHERE data_file_id = ?",
            (data_file_id,),
        ).fetchone()
        return row["cnt"]

    def query_total_sequences(self, project_name: str, file_name: str) -> int:
        """Return total sequence count by project and file names."""
        df = self.get_data_file_by_names(project_name, file_name)
        if not df:
            return 0
        return self.count_sequences(df["id"])

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
        """Save history tree, extracting node snapshots into separate table."""
        now = time.time()
        nodes = tree_data.get("nodes", {})
        slim_tree = dict(tree_data)
        slim_nodes = {}
        for nid, node in nodes.items():
            slim_nodes[nid] = {k: v for k, v in node.items() if k != "data"}
        slim_tree["nodes"] = slim_nodes

        self.conn.execute("BEGIN IMMEDIATE")
        try:
            # Extract snapshot data from nodes into history_snapshots table
            for nid, node in nodes.items():
                snap = node.get("data")
                if snap:
                    self.conn.execute(
                        "INSERT INTO history_snapshots (data_file_id, node_id, snapshot_data, updated_at) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(data_file_id, node_id) DO UPDATE SET "
                        "snapshot_data=excluded.snapshot_data, updated_at=excluded.updated_at",
                        (data_file_id, nid, json.dumps(snap), now),
                    )
            self.conn.execute(
                "INSERT INTO history_trees (data_file_id, tree_data, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(data_file_id) DO UPDATE SET tree_data=excluded.tree_data, updated_at=excluded.updated_at",
                (data_file_id, json.dumps(slim_tree), now),
            )
            self.conn.execute("COMMIT")
        except Exception:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass
            raise

    def get_history_tree(self, data_file_id: int) -> dict | None:
        """Load history tree metadata (without snapshot data)."""
        row = self.conn.execute(
            "SELECT tree_data FROM history_trees WHERE data_file_id = ?",
            (data_file_id,),
        ).fetchone()
        return json.loads(row["tree_data"]) if row else None

    # ------------------------------------------------------------------
    # History snapshots (per-node data, loaded on demand)
    # ------------------------------------------------------------------

    def get_node_snapshot(self, data_file_id: int, node_id: str) -> dict | None:
        """Load a single node's snapshot data on demand."""
        row = self.conn.execute(
            "SELECT snapshot_data FROM history_snapshots WHERE data_file_id = ? AND node_id = ?",
            (data_file_id, node_id),
        ).fetchone()
        return json.loads(row["snapshot_data"]) if row else None

    def delete_node_snapshots(self, data_file_id: int, node_ids: set) -> None:
        """Delete snapshots for removed nodes."""
        if not node_ids:
            return
        placeholders = ",".join("?" for _ in node_ids)
        self.conn.execute(
            f"DELETE FROM history_snapshots WHERE data_file_id = ? AND node_id IN ({placeholders})",
            (data_file_id, *node_ids),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def import_json_file(self, project_id: int, json_path: str | Path, data_type: str = "generic") -> int:
        """Import a JSON file into the database, splitting batch_data into sequences.

        Safe to call repeatedly — existing data_file is updated, sequences are
        replaced, and history_tree is upserted. Atomic: all-or-nothing.
        """
        json_path = Path(json_path)
        data, _ = load_json(json_path)
        file_name = json_path.stem

        top_level = {k: v for k, v in data.items() if k not in (KEY_BATCH_DATA, KEY_HISTORY_TREE)}

        self.conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self.conn.execute(
                "SELECT id FROM data_files WHERE project_id = ? AND name = ?",
                (project_id, file_name),
            ).fetchone()

            if existing:
                df_id = existing["id"]
                now = time.time()
                self.conn.execute(
                    "UPDATE data_files SET data_type = ?, top_level = ?, updated_at = ? WHERE id = ?",
                    (data_type, json.dumps(top_level), now, df_id),
                )
                self.conn.execute("DELETE FROM sequences WHERE data_file_id = ?", (df_id,))
            else:
                now = time.time()
                cur = self.conn.execute(
                    "INSERT INTO data_files (project_id, name, data_type, top_level, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (project_id, file_name, data_type, json.dumps(top_level), now, now),
                )
                df_id = cur.lastrowid

            # Import sequences from batch_data
            batch_data = data.get(KEY_BATCH_DATA, [])
            if isinstance(batch_data, list):
                for item in batch_data:
                    if not isinstance(item, dict):
                        continue
                    seq_num = int(item.get("sequence_number", 0))
                    now = time.time()
                    self.conn.execute(
                        "INSERT INTO sequences (data_file_id, sequence_number, data, updated_at) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(data_file_id, sequence_number) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                        (df_id, seq_num, json.dumps(item), now),
                    )

            # Import history tree (extract snapshots into separate table)
            history_tree = data.get(KEY_HISTORY_TREE)
            if history_tree and isinstance(history_tree, dict):
                now = time.time()
                nodes = history_tree.get("nodes", {})
                slim_tree = dict(history_tree)
                slim_nodes = {}
                for nid, node in nodes.items():
                    snap = node.get("data")
                    if snap:
                        self.conn.execute(
                            "INSERT INTO history_snapshots (data_file_id, node_id, snapshot_data, updated_at) "
                            "VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(data_file_id, node_id) DO UPDATE SET "
                            "snapshot_data=excluded.snapshot_data, updated_at=excluded.updated_at",
                            (df_id, nid, json.dumps(snap), now),
                        )
                    slim_nodes[nid] = {k: v for k, v in node.items() if k != "data"}
                slim_tree["nodes"] = slim_nodes
                self.conn.execute(
                    "INSERT INTO history_trees (data_file_id, tree_data, updated_at) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(data_file_id) DO UPDATE SET tree_data=excluded.tree_data, updated_at=excluded.updated_at",
                    (df_id, json.dumps(slim_tree), now),
                )

            self.conn.execute("COMMIT")
            return df_id
        except Exception:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass
            raise

    # ------------------------------------------------------------------
    # Full data reconstruction (replaces load_json for DB-backed files)
    # ------------------------------------------------------------------

    def load_full_data(self, project_name: str, file_name: str) -> dict | None:
        """Reconstruct the full data dict from DB, matching load_json format.

        Returns None if the project or file doesn't exist in the DB.
        Result has the same structure as a JSON file: top-level keys +
        batch_data list + history_tree dict.
        """
        t0 = time.time()
        df = self.get_data_file_by_names(project_name, file_name)
        if not df:
            return None
        t1 = time.time()

        # Start with top-level keys
        data = df.get("top_level", {})
        if isinstance(data, str):
            data = json.loads(data)

        # Load all sequences as batch_data
        # Group sub-segments (>=1000) after their parent: parent = seq_num / 1000
        rows = self.conn.execute(
            "SELECT data FROM sequences WHERE data_file_id = ? "
            "ORDER BY CASE WHEN sequence_number >= 1000 THEN sequence_number / 1000 "
            "ELSE sequence_number END, "
            "CASE WHEN sequence_number >= 1000 THEN 1 ELSE 0 END, "
            "sequence_number",
            (df["id"],),
        ).fetchall()
        batch_data = []
        for row in rows:
            seq = json.loads(row["data"])
            self._migrate_lora_keys(seq)
            batch_data.append(seq)
        data["batch_data"] = batch_data
        t2 = time.time()

        # Load history tree (metadata only, no snapshot data)
        tree = self.get_history_tree(df["id"])
        if tree:
            # Strip any residual snapshot data from nodes
            for node in tree.get("nodes", {}).values():
                node.pop("data", None)
            data["history_tree"] = tree
        t3 = time.time()

        logger.info("load_full_data %s/%s (%d seqs): lookup=%.3fs seqs=%.3fs tree=%.3fs total=%.3fs",
                     project_name, file_name, len(batch_data),
                     t1 - t0, t2 - t1, t3 - t2, t3 - t0)
        return data

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
