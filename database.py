import sqlite3
import json
import os

DB_FILE = "comfy_settings.db"

def init_db():
    """Initialize the database table if it doesn't exist."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # We store the unique name of the file and the entire JSON blob
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                    filename TEXT PRIMARY KEY,
                    data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    conn.close()

def save_setting(filename, data):
    """Save settings to DB and then export to JSON file."""
    # 1. Save to Database
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    json_str = json.dumps(data)
    c.execute("INSERT OR REPLACE INTO settings (filename, data) VALUES (?, ?)", 
              (filename, json_str))
    conn.commit()
    conn.close()

    # 2. Produce JSON File (The artifact for ComfyUI)
    # Ensure the directory exists if filename has a path
    if os.path.dirname(filename):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def load_setting(filename):
    """Load settings from DB. Fallback to file if not in DB."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT data FROM settings WHERE filename=?", (filename,))
    row = c.fetchone()
    conn.close()

    if row:
        return json.loads(row[0])
    else:
        # Fallback: If not in DB, try reading the file and import it
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Auto-import to DB
                save_setting(filename, data) 
                return data
            except Exception as e:
                print(f"Error loading file {filename}: {e}")
                return {}
        return {}

def get_all_filenames():
    """Retrieve all filenames stored in the DB."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT filename FROM settings")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]
