# 🎛️ AI Settings Manager for ComfyUI

A 100% vibecoded, visual dashboard for managing, versioning, and batch-processing JSON configuration files used in AI video generation workflows (I2V, VACE).

This tool consists of two parts:
1.  **Streamlit Web Interface:** A Dockerized editor to manage prompts, LoRAs, settings, and **branching history**.
2.  **ComfyUI Custom Nodes:** A set of nodes to read these JSON files (including custom keys) directly into your workflows.

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg) ![Python](https://img.shields.io/badge/Python-3.10%2B-green) ![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-red)
---

## ✨ Features

### 📝 Single File Editor
* **Visual Interface:** Edit Prompts, Negative Prompts, Seeds, LoRAs, and advanced settings (Camera, FLF, VACE params) without touching raw JSON.
* **🔧 Custom Parameters:** Add arbitrary key-value pairs (e.g., `controlnet_strength`, `my_custom_value`) that persist and can be read by ComfyUI.
* **Conflict Protection:** Prevents accidental overwrites if the file is modified by another tab or process.
* **Snippet Library:** Save reusable prompt fragments (e.g., "Cinematic Lighting", "Anime Style") and append them with one click.

### 🚀 Batch Processor
* **Sequence Management:** Create unlimited sequences within a single JSON file.
* **Smart Import:** Copy settings from **any other file** or **history entry** into your current batch sequence.
* **Custom Keys per Shot:** Define unique parameters for specific shots in a batch (e.g., Shot 1 has `fog: 0.5`, Shot 2 has `fog: 0.0`).
* **Promote to Single:** One-click convert a specific batch sequence back into a standalone Single File.

### 🕒 Visual Timeline (New!)
* **Git-Style Branching:** A dedicated tab visualizes your edit history as a **horizontal node graph**.
* **Non-Destructive:** If you jump back to an old version and make changes, the system automatically **forks a new branch** so you never lose history.
* **Visual Diff:** Inspect any past version and see a "Delta View" highlighting exactly what changed (e.g., `Seed: 100 -> 555`) compared to your current state.
* **Interactive Mode (WIP):** A zoomed-out, interactive canvas to explore complex history trees.

---

## 🛠️ Installation

### 1. Unraid / Docker Setup (The Manager)
This tool is designed to run as a lightweight container on Unraid.

1.  **Prepare a Folder:** Create a folder on your server (e.g., `/mnt/user/appdata/ai-manager/`) and place the following files inside:
    * `app.py`
    * `utils.py`
    * `history_tree.py` (New logic engine)
    * `tab_single.py`
    * `tab_batch.py`
    * `tab_timeline.py`
    * `tab_timeline_wip.py`
2.  **Add Container in Unraid:**
    * **Repository:** `python:3.12-slim`
    * **Network:** `Bridge`
    * **WebUI:** `http://[IP]:[PORT:8501]`
3.  **Path Mappings:**
    * **App Location:** Container `/app` ↔ Host `/mnt/user/appdata/ai-manager/`
    * **Project Data:** Container `/mnt/user/` ↔ Host `/mnt/user/` (Your media/JSON location)
4.  **Post Arguments (Crucial):**
    Enable "Advanced View" and paste this command to install the required graph engines:
    ```bash
    /bin/sh -c "apt-get update && apt-get install -y graphviz && pip install streamlit opencv-python-headless graphviz streamlit-agraph && cd /app && streamlit run app.py --server.headless true --server.port 8501"
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

* **Custom Parameters:** Scroll to the bottom of the editor (Single or Batch) to find the "🔧 Custom Parameters" section. Type a Key (e.g., `strength`) and Value (e.g., `0.8`) and click "Add".
* **Timeline:** Switch to the **Timeline Tab** to see your version history.
    * **Restore:** Select a node from the list or click on the graph (WIP tab) to view details. Click "Restore" to revert settings to that point.
    * **Branching:** If you restore an old node and click "Save/Snap", a new branch is created automatically.

### ComfyUI Workflow
Search for "JSON" in ComfyUI to find the new nodes.

<img width="1251" height="921" alt="image" src="https://github.com/user-attachments/assets/06d567f8-15ee-4011-9b86-d0b43ce1ba74" />
#### Standard Nodes
| Node Name | Description |
| :--- | :--- |
| **JSON Loader (Standard/I2V)** | Outputs prompts, FLF, Seed, and paths for I2V. |
| **JSON Loader (VACE Full)** | Outputs everything above plus VACE integers (frames to skip, schedule, etc.). |
| **JSON Loader (LoRAs Only)** | Outputs the 6 LoRA strings. |

#### Universal Custom Nodes (New!)
These nodes read *any* key you added in the "Custom Parameters" section. They work for both Single files (ignores sequence input) and Batch files (reads specific sequence).

| Node Name | Description |
| :--- | :--- |
| **JSON Loader (Custom 1)** | Reads 1 custom key. Input the key name (e.g., "strength"), outputs the value string. |
| **JSON Loader (Custom 3)** | Reads 3 custom keys. |
| **JSON Loader (Custom 6)** | Reads 6 custom keys. |

#### Batch Nodes
These nodes require an integer input (Primitive or Batch Indexer) for `sequence_number`.

| Node Name | Description |
| :--- | :--- |
| **JSON Batch Loader (I2V)** | Loads specific sequence data for I2V. |
| **JSON Batch Loader (VACE)** | Loads specific sequence data for VACE. |
| **JSON Batch Loader (LoRAs)** | Loads specific LoRAs for that sequence. |

---

## 📂 File Structure

```text
/ai-manager
├── app.py                  # Main entry point & Tab controller
├── utils.py                # I/O logic, Config, and Defaults
├── history_tree.py         # Graph logic, Branching engine, Graphviz generator
├── tab_single.py           # Single Editor UI
├── tab_batch.py            # Batch Processor UI
├── tab_timeline.py         # Stable Timeline UI (Compact Graphviz + Diff Inspector)
├── tab_timeline_wip.py     # Interactive Timeline UI (Streamlit Agraph)
└── json_loader.py          # ComfyUI Custom Node script
