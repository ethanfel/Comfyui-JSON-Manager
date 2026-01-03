import sqlite3
import json
import os
from datetime import datetime

DB_FILE = "app_data.db"
JSON_BACKUP = "settings.json"  # The old file you want to import from

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

def init_db():
    """Creates tables and imports JSON if DB is new."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Create Settings Table (Keyed by Path)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            path TEXT PRIMARY KEY,
            params TEXT,
            updated_at TIMESTAMP
        )
    ''')
    
    # 2. Create Batch History Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS batch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            path TEXT,
            status TEXT,
            details TEXT
        )
    ''')
    
    # 3. Check for Migration (If DB is empty but JSON exists)
    cursor.execute('SELECT count(*) FROM settings')
    count = cursor.fetchone()[0]
    
    if count == 0 and os.path.exists(JSON_BACKUP):
        print(f"Migration: Database empty. Importing from {JSON_BACKUP}...")
        try:
            with open(JSON_BACKUP, 'r') as f:
                data = json.load(f)
                # Assumes JSON structure: {"/path/to/img1": {config}, "/path/to/img2": {config}}
                for path, config in data.items():
                    cursor.execute(
                        'INSERT OR REPLACE INTO settings (path, params, updated_at) VALUES (?, ?, ?)',
                        (path, json.dumps(config), datetime.now())
                    )
            conn.commit()
            print("Migration successful.")
        except Exception as e:
            print(f"Migration failed: {e}")

    conn.commit()
    conn.close()

# --- SETTINGS FUNCTIONS ---

def load_settings_for_path(path):
    """Returns a dict of settings for the specific path, or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT params FROM settings WHERE path = ?", (path,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return json.loads(row['params'])
    return None

def save_settings_for_path(path, settings_dict):
    """Saves the settings dict into the DB associated with the path."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    json_str = json.dumps(settings_dict)
    timestamp = datetime.now()
    
    cursor.execute('''
        INSERT INTO settings (path, params, updated_at) 
        VALUES (?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            params=excluded.params,
            updated_at=excluded.updated_at
    ''', (path, json_str, timestamp))
    
    conn.commit()
    conn.close()
    return f"Saved settings for: {path}"

# --- BATCH FUNCTIONS ---

def log_batch_run(path, status, details_dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO batch_log (timestamp, path, status, details)
        VALUES (?, ?, ?, ?)
    ''', (datetime.now(), path, status, json.dumps(details_dict)))
    
    conn.commit()
    conn.close()

# Initialize DB immediately when this module is imported
init_db()
