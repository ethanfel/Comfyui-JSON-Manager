import gradio as gr
import sqlite3
import json
import os
import time
from datetime import datetime

# ==========================================
# 1. DATABASE & PERSISTENCE LAYER
# ==========================================

DB_FILE = "app_data.db"
LEGACY_JSON_FILE = "settings.json"  # File to import from if DB is empty

def get_db():
    """Connect to SQLite and return connection."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

def init_db():
    """Initialize tables and migrate legacy JSON if needed."""
    conn = get_db()
    c = conn.cursor()

    # Table 1: Single Tab Settings (Keyed by file path)
    c.execute('''
        CREATE TABLE IF NOT EXISTS path_settings (
            path TEXT PRIMARY KEY,
            settings_json TEXT,
            updated_at TIMESTAMP
        )
    ''')

    # Table 2: Batch History (Logs of batch runs)
    c.execute('''
        CREATE TABLE IF NOT EXISTS batch_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP,
            folder_path TEXT,
            log_data TEXT
        )
    ''')
    
    conn.commit()

    # --- MIGRATION LOGIC ---
    # Check if DB is empty
    c.execute("SELECT COUNT(*) FROM path_settings")
    count = c.fetchone()[0]

    if count == 0 and os.path.exists(LEGACY_JSON_FILE):
        print(f"[DB] Database empty. Found {LEGACY_JSON_FILE}, migrating...")
        try:
            with open(LEGACY_JSON_FILE, 'r') as f:
                legacy_data = json.load(f)
            
            # Assuming JSON structure: {"/path/to/img.png": {"threshold": 0.5, ...}}
            # If your JSON is flat, you might need to adjust this loop.
            if isinstance(legacy_data, dict):
                for path, data in legacy_data.items():
                    c.execute(
                        "INSERT OR IGNORE INTO path_settings (path, settings_json, updated_at) VALUES (?, ?, ?)",
                        (path, json.dumps(data), datetime.now())
                    )
                conn.commit()
                print("[DB] Migration complete.")
        except Exception as e:
            print(f"[DB] Migration failed: {e}")
    
    conn.close()

# --- DB Helper Functions ---

def load_settings(path):
    """Load settings for a specific path from DB."""
    if not path:
        return None
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT settings_json FROM path_settings WHERE path = ?", (path,))
    row = c.fetchone()
    conn.close()

    if row:
        return json.loads(row['settings_json'])
    return None

def save_settings(path, settings_dict):
    """Save/Update settings for a specific path."""
    if not path:
        return
    
    conn = get_db()
    c = conn.cursor()
    json_str = json.dumps(settings_dict)
    
    # Upsert: Insert, or Update if path exists
    c.execute('''
        INSERT INTO path_settings (path, settings_json, updated_at) 
        VALUES (?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            settings_json=excluded.settings_json,
            updated_at=excluded.updated_at
    ''', (path, json_str, datetime.now()))
    
    conn.commit()
    conn.close()
    print(f"[DB] Saved settings for {path}")

def save_batch_log(folder_path, logs):
    """Save batch run details to DB."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO batch_history (timestamp, folder_path, log_data)
        VALUES (?, ?, ?)
    ''', (datetime.now(), folder_path, json.dumps(logs)))
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()


# ==========================================
# 2. APP LOGIC
# ==========================================

# Default settings to fall back on
DEFAULTS = {
    "threshold": 0.5,
    "invert": False,
    "scale": 1.0
}

def on_path_load(path):
    """
    Triggered when user enters a path or clicks Load.
    Fetches specific settings for this path from DB.
    """
    data = load_settings(path)
    if data:
        msg = f"Loaded saved settings for: {os.path.basename(path)}"
        # Return values to update UI components
        return msg, data.get("threshold", DEFAULTS["threshold"]), data.get("invert", DEFAULTS["invert"]), data.get("scale", DEFAULTS["scale"])
    else:
        msg = "No saved settings found (using defaults)"
        return msg, DEFAULTS["threshold"], DEFAULTS["invert"], DEFAULTS["scale"]

def process_single_image(path, threshold, invert, scale):
    """
    Simulates processing. 
    Critically: SAVES the settings used to the DB.
    """
    if not path:
        return "Error: No path provided"

    # 1. Save these settings to DB so they are remembered next time
    current_settings = {
        "threshold": threshold,
        "invert": invert,
        "scale": scale
    }
    save_settings(path, current_settings)

    # 2. Run actual processing (Place your real code here)
    time.sleep(0.5) # Simulate work
    return f"Success! Processed {os.path.basename(path)} with Threshold={threshold}. Settings Saved."

def process_batch(folder_path, threshold):
    """
    Simulates batch processing.
    Logs the result to the 'batch_history' table.
    """
    if not os.path.isdir(folder_path):
        return "Error: Invalid folder path"

    files = [f for f in os.listdir(folder_path) if f.endswith(('.png', '.jpg'))]
    log_messages = []

    for f in files:
        # Simulate processing each file
        # You could also load individual file settings here if needed
        log_messages.append(f"Processed {f} (Threshold: {threshold})")
    
    result_text = "\n".join(log_messages)
    
    # Save to Batch DB
    save_batch_log(folder_path, log_messages)
    
    return f"Batch Complete. {len(files)} files processed.\n\nLOG:\n{result_text}"


# ==========================================
# 3. GRADIO INTERFACE
# ==========================================

with gr.Blocks(title="App with DB Persistence") as app:
    gr.Markdown("## Image Processor (SQLite Powered)")
    
    with gr.Tabs():
        
        # --- TAB 1: SINGLE IMAGE ---
        with gr.Tab("Single Image"):
            gr.Markdown("Settings are saved automatically per file path.")
            
            with gr.Row():
                # The 'Key' for our database
                path_input = gr.Textbox(label="Image File Path", placeholder="C:/Images/photo1.png", scale=3)
                load_btn = gr.Button("Load Settings", scale=1)
            
            with gr.Row():
                # Settings Inputs
                thresh_slider = gr.Slider(0.0, 1.0, value=DEFAULTS["threshold"], label="Threshold")
                scale_num = gr.Number(value=DEFAULTS["scale"], label="Scale Factor")
                invert_chk = gr.Checkbox(value=DEFAULTS["invert"], label="Invert Colors")

            status_output = gr.Textbox(label="Status / Output", lines=2)
            run_btn = gr.Button("Process & Save", variant="primary")

            # Interactions
            # 1. Loading settings when button clicked
            load_btn.click(
                fn=on_path_load,
                inputs=[path_input],
                outputs=[status_output, thresh_slider, invert_chk, scale_num]
            )
            
            # 2. (Optional) Auto-load when path input loses focus (blur)
            path_input.blur(
                fn=on_path_load,
                inputs=[path_input],
                outputs=[status_output, thresh_slider, invert_chk, scale_num]
            )

            # 3. Processing
            run_btn.click(
                fn=process_single_image,
                inputs=[path_input, thresh_slider, invert_chk, scale_num],
                outputs=[status_output]
            )

        # --- TAB 2: BATCH PROCESS ---
        with gr.Tab("Batch Processing"):
            gr.Markdown("Batch runs are logged to history.")
            
            batch_input = gr.Textbox(label="Input Folder", placeholder="C:/Images/Batch_Folder")
            
            # Example: Global override for batch, or you could load per file
            batch_thresh = gr.Slider(0.0, 1.0, value=0.5, label="Global Threshold Override")
            
            batch_run_btn = gr.Button("Run Batch", variant="primary")
            batch_output = gr.TextArea(label="Batch Log", lines=10)

            batch_run_btn.click(
                fn=process_batch,
                inputs=[batch_input, batch_thresh],
                outputs=[batch_output]
            )

if __name__ == "__main__":
    app.launch()
