import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path="app_data.db"):
        self.db_path = db_path
        self.conn = None
        self.connect()
        self.init_tables()

    def connect(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def init_tables(self):
        """Create tables for App Config, Project Settings, and Snippets."""
        cursor = self.conn.cursor()
        
        # 1. Project Settings (Replaces your per-file JSONs)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                path TEXT PRIMARY KEY,
                parent_dir TEXT,
                filename TEXT,
                data TEXT,
                is_batch INTEGER,
                updated_at TIMESTAMP
            )
        ''')

        # 2. Global App Config (Replaces config.json)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # 3. Snippets (Replaces snippets.json)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS snippets (
                name TEXT PRIMARY KEY,
                content TEXT
            )
        ''')
        self.conn.commit()

    # --- MIGRATION LOGIC ---
    def is_empty(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM projects")
        return cursor.fetchone()[0] == 0

    def migrate_from_json(self, root_dir):
        """Scans folder for .json files and imports them if DB is empty."""
        print("Starting Migration from JSON...")
        root = Path(root_dir)
        count = 0
        
        # 1. Migrate Projects
        for json_file in root.glob("*.json"):
            if json_file.name in [".editor_config.json", ".editor_snippets.json"]:
                continue
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                is_batch = 1 if "batch_data" in data or isinstance(data, list) else 0
                self.save_project(json_file, data, is_batch)
                count += 1
            except Exception as e:
                print(f"Failed to migrate {json_file}: {e}")

        # 2. Migrate Config
        config_path = root / ".editor_config.json"
        if config_path.exists():
            with open(config_path, 'r') as f:
                self.save_app_config(json.load(f))

        # 3. Migrate Snippets
        snip_path = root / ".editor_snippets.json"
        if snip_path.exists():
            with open(snip_path, 'r') as f:
                snippets = json.load(f)
                for k, v in snippets.items():
                    self.save_snippet(k, v)
        
        print(f"Migration complete. Imported {count} files.")

    # --- PROJECT OPERATIONS ---
    def get_projects_in_dir(self, directory):
        """Returns list of filenames for a specific directory."""
        cursor = self.conn.cursor()
        # Ensure directory path format matches how we save it
        dir_str = str(Path(directory).absolute())
        
        cursor.execute("SELECT filename FROM projects WHERE parent_dir = ?", (dir_str,))
        return [row['filename'] for row in cursor.fetchall()]

    def load_project(self, full_path):
        cursor = self.conn.cursor()
        cursor.execute("SELECT data FROM projects WHERE path = ?", (str(full_path),))
        row = cursor.fetchone()
        if row:
            return json.loads(row['data'])
        return None

    def save_project(self, full_path, data, is_batch=False):
        path_obj = Path(full_path)
        path_str = str(path_obj.absolute())
        parent_str = str(path_obj.parent.absolute())
        filename = path_obj.name
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO projects (path, parent_dir, filename, data, is_batch, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
            data=excluded.data,
            is_batch=excluded.is_batch,
            updated_at=excluded.updated_at
        ''', (path_str, parent_str, filename, json.dumps(data), int(is_batch), datetime.now()))
        self.conn.commit()

    def delete_project(self, full_path):
        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) FROM projects WHERE path = ?", (str(full_path),)) # Check existence
        cursor.execute("DELETE FROM projects WHERE path = ?", (str(full_path),))
        self.conn.commit()

    # --- CONFIG OPERATIONS ---
    def load_app_config(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM app_config WHERE key = 'main_config'")
        row = cursor.fetchone()
        if row:
            return json.loads(row['value'])
        # Default Config
        return {"last_dir": str(Path.cwd()), "favorites": []}

    def save_app_config(self, config_dict):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO app_config (key, value) VALUES ('main_config', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        ''', (json.dumps(config_dict),))
        self.conn.commit()

    # --- SNIPPET OPERATIONS ---
    def load_snippets(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM snippets")
        return {row['name']: row['content'] for row in cursor.fetchall()}

    def save_snippet(self, name, content):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO snippets (name, content) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET content=excluded.content
        ''', (name, content))
        self.conn.commit()

    def delete_snippet(self, name):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM snippets WHERE name = ?", (name,))
        self.conn.commit()
