# Resolution Series Design

## Problem

When running ComfyUI loop nodes for multi-step upscaling (e.g. 3+ resolutions at different sizes),
managing portrait vs landscape width/height per iteration is tedious. Users need a structured way
to define N resolution pairs in the manager UI and retrieve them by loop index in ComfyUI.

## Design

### Data Model

Resolution series are stored as a JSON array under a user-chosen key in the sequence data:

```json
"upscale_resolutions": [[512, 512], [768, 1344], [1344, 768], [2048, 2048]]
```

- Each element is `[width, height]` (both INT)
- Key name is chosen by the user (any string)
- Number of entries is configurable (add/remove rows)
- Stored in the same project JSON file and sequence — no schema change required
- Index out of bounds → clamp to last entry

### NiceGUI UI (tab_batch_ng.py)

A resolution series editor is rendered in the left column of the sequence card, directly below
the "Specific Negative" textarea.

Layout:

```
── Resolution Series ──────────────────
  key name: [upscale_resolutions    ]
  #  Width    Height
  1  [2048]   [2048]   [x]
  2  [768 ]   [1344]   [x]
  3  [1344]   [768 ]   [x]
  [+ Add row]
```

- Key name is editable (defaults to `resolutions`)
- Rows added/removed inline; each change calls `commit()` immediately
- Hidden behind an "Add Resolution Series" button when no resolution key exists yet
- A value is detected as a resolution series if it is a list of `[int, int]` pairs

### ComfyUI Node (`ProjectResolution`)

New node class in `project_loader.py`, sibling to `ProjectKey`.

**Inputs:**
- `source_label` (STRING) — references a `ProjectSource` by label
- `key_name` (STRING) — the resolution series key name
- `index` (INT, min 0) — wired from loop node's current index output
- `manager_url`, `project_name`, `file_name`, `sequence_number` — optional, synced from `ProjectSource` via JS

**Outputs:** `width` (INT), `height` (INT)

**Execution:** fetches the sequence data, reads `data[key_name]`, indexes into the array with
clamp-to-last on out-of-bounds, returns `(width, height)`.

**JS (`web/project_resolution.js`):**
- Same `_syncFromSource` mechanism as `project_key.js`
- `key_name` widget is replaced with a combo dropdown populated with keys whose value is a
  resolution series (list of `[int, int]` pairs), detected via the existing keys API
- Registered in `PROJECT_NODE_CLASS_MAPPINGS` and `PROJECT_NODE_DISPLAY_NAME_MAPPINGS`

### API

No new endpoints. Uses existing:
- `/json_manager/get_project_keys` — for key discovery (JS combo population)
- `_fetch_data()` — for execution-time data fetch

### Files Changed

| File | Change |
|------|--------|
| `project_loader.py` | Add `ProjectResolution` class + register in mappings |
| `web/project_resolution.js` | New JS extension for the node |
| `tab_batch_ng.py` | Resolution series editor below Specific Negative |
| `__init__.py` | Register new JS file if needed |
