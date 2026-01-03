import sqlite3
import json
import os
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_name="app_data.db"):
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        self.connect()
        self.create_tables()

    def connect(self):
        """Establish connection to the SQLite database."""
        self.conn = sqlite3.connect(self.db_name)
        # Return rows as dictionaries for easier access (e.g., row['path'])
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def create_tables(self):
        """Initialize the database schema."""
        # Table for Single Tab Settings (keyed by Path)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS path_settings (
                path TEXT PRIMARY KEY,
                config_data TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table for Batch Tab History
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS batch_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_name TEXT,
                batch_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    # --- SETTINGS / SINGLE TAB OPERATIONS ---

    def save_setting(self, path, data_dict):
        """
        Saves settings for a specific path. 
        Upsert: Inserts if new, Updates if exists.
        """
        # Convert dictionary to JSON string for storage
        json_data = json.dumps(data_dict)
        
        query = '''
            INSERT INTO path_settings (path, config_data, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
            config_data=excluded.config_data,
            updated_at=excluded.updated_at
        '''
        self.cursor.execute(query, (path, json_data, datetime.now()))
        self.conn.commit()
        print(f"[DB] Settings saved for path: {path}")

    def get_setting(self, path):
        """Retrieves settings for a specific path."""
        query = "SELECT config_data FROM path_settings WHERE path = ?"
        self.cursor.execute(query, (path,))
        row = self.cursor.fetchone()
        
        if row:
            # Convert JSON string back to Python Dictionary
            return json.loads(row['config_data'])
        return None

    # --- BATCH TAB OPERATIONS ---

    def save_batch(self, batch_name, batch_data_dict):
        """Saves a batch job result."""
        json_data = json.dumps(batch_data_dict)
        query = "INSERT INTO batch_history (batch_name, batch_data) VALUES (?, ?)"
        self.cursor.execute(query, (batch_name, json_data))
        self.conn.commit()
        print(f"[DB] Batch '{batch_name}' saved.")

    def get_all_batches(self):
        """Retrieves all batch history."""
        self.cursor.execute("SELECT * FROM batch_history ORDER BY created_at DESC")
        rows = self.cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "id": row['id'],
                "name": row['batch_name'],
                "data": json.loads(row['batch_data']),
                "date": row['created_at']
            })
        return results

    # --- MIGRATION LOGIC ---

    def is_db_empty(self):
        """Checks if the settings table is empty."""
        self.cursor.execute("SELECT COUNT(*) FROM path_settings")
        return self.cursor.fetchone()[0] == 0

    def import_from_json(self, json_file_path):
        """
        Reads a legacy JSON file and populates the database.
        Assumes JSON structure: { "path_to_file": {setting_dict}, ... }
        """
        if not os.path.exists(json_file_path):
            print("[DB] No legacy JSON file found to import.")
            return

        print(f"[DB] Importing legacy data from {json_file_path}...")
        try:
            with open(json_file_path, 'r') as f:
                legacy_data = json.load(f)
            
            # Iterate through the JSON and save to DB
            # Adjust this loop based on your exact JSON structure
            if isinstance(legacy_data, dict):
                for path_key, settings in legacy_data.items():
                    self.save_setting(path_key, settings)
                print("[DB] Migration complete.")
            else:
                print("[DB] JSON format not recognized (expected dict).")

        except Exception as e:
            print(f"[DB] Error importing JSON: {e}")

    def close(self):
        self.conn.close()
