# 🎛️ AI Settings Manager for ComfyUI

A 100% vibecoded, visual dashboard for managing, versioning, and batch-processing JSON configuration files used in AI video generation workflows (I2V, VACE).

This tool consists of two parts:
1.  **Streamlit Web Interface:** A Dockerized editor to manage prompts, LoRAs, and settings.
2.  **ComfyUI Custom Nodes:** A set of nodes to read these JSON files directly into your workflows.

---

## ✨ Features

### 📝 Single File Editor
* **Visual Interface:** Edit Prompts, Negative Prompts, Seeds, LoRAs, and advanced settings (Camera, FLF, VACE params) without touching raw JSON.
* **Smart History:** Every save allows you to create a "Snapshot." You can view, restore, or edit historical versions of your prompts instantly.
* **Conflict Protection:** Prevents accidental overwrites if the file is modified by another tab or process.
* **Snippet Library:** Save reusable prompt fragments (e.g., "Cinematic Lighting", "Anime Style") and append them with one click.

### 🚀 Batch Processor
* **Sequence Management:** Create unlimited sequences within a single JSON file.
* **Import Tools:** Copy settings from **any other file** or **history entry** into your current batch sequence.
* **Promote to Single:** Liked a specific shot in your batch? One-click convert a sequence back into a standalone Single File.
* **Infinite Looping:** ComfyUI nodes automatically loop through sequences (modulo logic), allowing for infinite generation runs.

---

## 🛠️ Installation

### 1. Unraid / Docker Setup (The Manager)
This tool is designed to run as a lightweight container on Unraid.

1.  **Prepare a Folder:** Create a folder on your server (e.g., `/mnt/user/appdata/ai-manager/`) and place the following files inside:
    * `app.py`
    * `utils.py`
    * `tab_single.py`
    * `tab_batch.py`
2.  **Add Container in Unraid:**
    * **Repository:** `python:3.12-slim`
    * **Network:** `Bridge`
    * **WebUI:** `http://[IP]:[PORT:8501]`
3.  **Path Mappings:**
    * **App Location:** Container `/app` ↔ Host `/mnt/user/appdata/ai-manager/`
    * **Project Data:** Container `/mnt/user/` ↔ Host `/mnt/user/` (Your media/JSON location)
4.  **Post Arguments (Crucial):**
    Enable "Advanced View" and paste this into **Post Arguments**:
    ```bash
    /bin/sh -c "pip install streamlit opencv-python-headless && cd /app && streamlit run app.py --server.headless true --server.port 8501"
    ```

### 2. ComfyUI Setup (The Nodes)
1.  Navigate to your ComfyUI installation: `ComfyUI/custom_nodes/`
2.  Create a folder named `ComfyUI-JSON-Loader`.
3.  Place the `json_loader.py` file inside.
4.  Restart ComfyUI.

---

## 🖥️ Usage Guide

### The Web Interface
Navigate to your container's IP (e.g., `http://192.168.1.100:8501`).

* **Navigator:** Use the sidebar to browse folders and "Pin" favorites for quick access.
* **Editing:** Select a JSON file. If it's a batch file, the app will auto-detect it and ask you to switch to the **Batch Tab**.
* **Saving:**
    * **Update File:** Saves changes to disk.
    * **Snapshot:** Saves changes AND creates a history entry with a custom note.

### ComfyUI Workflow
Search for "JSON" in ComfyUI to find the new nodes.

#### Standard Nodes (For Single Files)
| Node Name | Description |
| :--- | :--- |
| **JSON Loader (Standard/I2V)** | Outputs prompts, FLF, Seed, and paths for Image-to-Video workflows. |
| **JSON Loader (VACE Full)** | Outputs everything above plus specific VACE integers (frames to skip, schedule, etc.). |
| **JSON Loader (LoRAs Only)** | Outputs the 6 LoRA strings. Keeps your main graph clean. |

#### Batch Nodes (For Sequences)
These nodes accept a `sequence_number` integer input.
* **Input:** Connect a `Primitive` node (set to increment) or a `Batch Indexer` to the `sequence_number` input.
* **Logic:** If you request Sequence #5 but the file only has 3 sequences, it wraps around (Sequence #2). This allows infinite loops.

| Node Name | Description |
| :--- | :--- |
| **JSON Batch Loader (I2V)** | Loads specific sequence data for I2V. |
| **JSON Batch Loader (VACE)** | Loads specific sequence data for VACE. |
| **JSON Batch Loader (LoRAs)** | Loads the specific LoRAs assigned to that sequence. |

---

## 📂 File Structure

```text
/ai-manager
├── app.py              # Main Streamlit entry point
├── utils.py            # Configuration, I/O logic, and Defaults
├── tab_single.py       # UI Logic for Single File Editor
├── tab_batch.py        # UI Logic for Batch Processor
└── json_loader.py      # ComfyUI Custom Node script
