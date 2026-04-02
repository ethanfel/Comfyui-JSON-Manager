# Resolution Series Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `ProjectResolution` ComfyUI node and NiceGUI editor that let users define N `(width, height)` pairs per sequence and retrieve them by loop index.

**Architecture:** Resolution series are stored as a JSON array of `[width, height]` pairs under a user-chosen key in sequence data (e.g. `"upscale_resolutions": [[512,512],[768,1344]]`). A new `ProjectResolution` ComfyUI node (sibling of `ProjectKey`) accepts a `source_label`, `key_name`, and `index` INT from a loop node, and returns `width` + `height`. The NiceGUI sequence card gets an inline table editor placed directly below the "Specific Negative" textarea.

**Tech Stack:** Python (ComfyUI node), NiceGUI (UI), JavaScript (ComfyUI frontend extension), pytest

**Branch:** Create and work on `feat/resolution-series` branched from `main`:
```bash
git checkout main && git checkout -b feat/resolution-series
```

---

### Task 0: Fix pre-existing test failures on `main`

When `file_name` was added as a second output to `ProjectSource`, two tests were not updated.
They fail on `main` before any new code is written.

**Files:**
- Modify: `tests/test_project_loader.py` (`TestProjectSource` class, lines ~216-231)

**Step 1: Update the two broken tests**

```python
def test_outputs_sequence_number(self):
    from project_loader import ProjectSource
    assert ProjectSource.RETURN_TYPES == ("INT", "STRING",)
    assert ProjectSource.RETURN_NAMES == ("sequence_number", "file_name",)

def test_hold_config_returns_sequence_number(self):
    from project_loader import ProjectSource
    node = ProjectSource()
    result = node.hold_config(
        manager_url="http://localhost:8080",
        project_name="proj1",
        file_name="batch_i2v",
        sequence_number=42,
        label="my_source"
    )
    assert result == (42, "batch_i2v")
```

**Step 2: Verify they now pass**

```bash
pytest tests/test_project_loader.py::TestProjectSource -v
```
Expected: all 4 PASS

**Step 3: Commit**

```bash
git add tests/test_project_loader.py
git commit -m "fix: update ProjectSource tests for file_name output"
```

---

### Task 1: Python node — `ProjectResolution`

**Files:**
- Modify: `project_loader.py` (after the `ProjectKey` class, before `# --- Mappings ---`)
- Modify: `tests/test_project_loader.py` (add `TestProjectResolution` class)

**Step 1: Write failing tests**

Add this class to `tests/test_project_loader.py`:

```python
class TestProjectResolution:
    def test_input_types(self):
        from project_loader import ProjectResolution
        inputs = ProjectResolution.INPUT_TYPES()
        assert "source_label" in inputs["required"]
        assert "key_name" in inputs["required"]
        assert "index" in inputs["required"]
        assert inputs["required"]["index"][0] == "INT"

    def test_two_outputs(self):
        from project_loader import ProjectResolution
        assert ProjectResolution.RETURN_TYPES == ("INT", "INT")
        assert ProjectResolution.RETURN_NAMES == ("width", "height")

    def test_fetch_resolution_basic(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        data = {"resolutions": [[512, 512], [768, 1344], [1344, 768]]}
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_resolution(
                source_label="src", key_name="resolutions", index=1,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (768, 1344)

    def test_fetch_resolution_index_zero(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        data = {"resolutions": [[512, 512], [1024, 1024]]}
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_resolution(
                source_label="src", key_name="resolutions", index=0,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (512, 512)

    def test_fetch_resolution_clamps_on_out_of_bounds(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        data = {"resolutions": [[512, 512], [1024, 1024]]}
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_resolution(
                source_label="src", key_name="resolutions", index=99,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (1024, 1024)  # last entry

    def test_fetch_resolution_missing_key_returns_defaults(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        with patch("project_loader._fetch_data", return_value={}):
            result = node.fetch_resolution(
                source_label="src", key_name="nonexistent", index=0,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (512, 512)

    def test_fetch_resolution_network_error_returns_defaults(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        error_resp = {"error": "network_error", "message": "Connection refused"}
        with patch("project_loader._fetch_data", return_value=error_resp):
            result = node.fetch_resolution(
                source_label="src", key_name="resolutions", index=0,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (512, 512)

    def test_category(self):
        from project_loader import ProjectResolution
        assert ProjectResolution.CATEGORY == "utils/json/project"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_project_loader.py::TestProjectResolution -v
```
Expected: `ImportError: cannot import name 'ProjectResolution'`

**Step 3: Implement `ProjectResolution` in `project_loader.py`**

Insert this class after `ProjectKey` (line ~294), before `# --- Mappings ---`:

```python
class ProjectResolution:
    """Fetches a (width, height) pair from a resolution series by loop index."""
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "source_label": ("STRING", {"default": "", "multiline": False}),
                "key_name": ("STRING", {"default": "resolutions", "multiline": False}),
                "index": ("INT", {"default": 0, "min": 0, "max": 9999}),
            },
            "optional": {
                "manager_url": ("STRING", {"default": "http://localhost:8080", "multiline": False}),
                "project_name": ("STRING", {"default": "", "multiline": False}),
                "file_name": ("STRING", {"default": "", "multiline": False}),
                "sequence_number": ("INT", {"default": 1, "min": 1, "max": 9999}),
            },
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "fetch_resolution"
    CATEGORY = "utils/json/project"
    OUTPUT_NODE = False

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def fetch_resolution(self, source_label, key_name, index,
                         manager_url="http://localhost:8080", project_name="",
                         file_name="", sequence_number=1):
        sequence_number = int(sequence_number)
        data = _fetch_data(manager_url, project_name, file_name, sequence_number)
        if data.get("error") in ("http_error", "network_error", "parse_error"):
            logger.warning("ProjectResolution.fetch_resolution failed: %s", data.get("message"))
            return (512, 512)

        series = data.get(key_name)
        if not isinstance(series, list) or len(series) == 0:
            logger.warning("ProjectResolution: key '%s' is not a resolution series", key_name)
            return (512, 512)

        clamped = min(index, len(series) - 1)
        entry = series[clamped]
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            logger.warning("ProjectResolution: entry at index %d is malformed: %r", clamped, entry)
            return (512, 512)

        return (to_int(entry[0]), to_int(entry[1]))
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_project_loader.py::TestProjectResolution -v
```
Expected: all 7 tests PASS

**Step 5: Commit**

```bash
git add project_loader.py tests/test_project_loader.py
git commit -m "feat: add ProjectResolution node"
```

---

### Task 2: Register `ProjectResolution` in mappings + fix mapping tests

**Files:**
- Modify: `project_loader.py` (mappings section, lines ~297-307)
- Modify: `tests/test_project_loader.py` (`TestNodeMappings` class)

**Step 1: Update mappings in `project_loader.py`**

Change the mappings at the bottom of the file:

```python
PROJECT_NODE_CLASS_MAPPINGS = {
    "ProjectLoaderDynamic": ProjectLoaderDynamic,
    "ProjectSource": ProjectSource,
    "ProjectKey": ProjectKey,
    "ProjectResolution": ProjectResolution,
}

PROJECT_NODE_DISPLAY_NAME_MAPPINGS = {
    "ProjectLoaderDynamic": "Project Loader (Dynamic)",
    "ProjectSource": "Project Source",
    "ProjectKey": "Project Key",
    "ProjectResolution": "Project Resolution",
}
```

**Step 2: Update the mapping test**

In `tests/test_project_loader.py`, update `TestNodeMappings.test_mappings_exist`:

```python
class TestNodeMappings:
    def test_mappings_exist(self):
        from project_loader import PROJECT_NODE_CLASS_MAPPINGS, PROJECT_NODE_DISPLAY_NAME_MAPPINGS
        assert "ProjectLoaderDynamic" in PROJECT_NODE_CLASS_MAPPINGS
        assert "ProjectSource" in PROJECT_NODE_CLASS_MAPPINGS
        assert "ProjectKey" in PROJECT_NODE_CLASS_MAPPINGS
        assert "ProjectResolution" in PROJECT_NODE_CLASS_MAPPINGS
        assert len(PROJECT_NODE_CLASS_MAPPINGS) == 4
        assert len(PROJECT_NODE_DISPLAY_NAME_MAPPINGS) == 4
```

**Step 3: Run all project_loader tests**

```bash
pytest tests/test_project_loader.py -v
```
Expected: all tests PASS

**Step 4: Commit**

```bash
git add project_loader.py tests/test_project_loader.py
git commit -m "feat: register ProjectResolution in node mappings"
```

---

### Task 3: NiceGUI resolution series editor in `tab_batch_ng.py`

**Files:**
- Modify: `tab_batch_ng.py`

The resolution series editor goes inside `splitter.before`, directly after the "Specific Negative" textarea (currently line ~552-553). No new file needed.

**Step 1: Add the helper function**

Add this function near the other helper functions at the top of the render section (before `_render_sequence_card`):

```python
def _is_resolution_series(val) -> bool:
    """Return True if val is a list of [width, height] int pairs."""
    if not isinstance(val, list) or len(val) == 0:
        return False
    return all(
        isinstance(entry, (list, tuple)) and len(entry) == 2
        and all(isinstance(v, (int, float)) for v in entry)
        for entry in val
    )
```

Note: `Any` is intentionally omitted — `tab_batch_ng.py` does not import `typing.Any`.

**Step 2: Add the resolution series render section**

After the "Specific Negative" textarea in `splitter.before` (after line ~553), add:

```python
                # --- Resolution Series ---
                res_keys = [k for k, v in seq.items() if _is_resolution_series(v)]
                if res_keys:
                    ui.label('Resolution Series').classes('text-caption text-weight-bold q-mt-md')
                    for res_key in res_keys:
                        series: list = seq[res_key]
                        with ui.card().classes('w-full q-pa-sm q-mt-xs').props('flat bordered'):
                            with ui.row().classes('items-center q-mb-xs'):
                                ui.label(res_key).classes('text-caption col')
                                def del_series(k=res_key):
                                    del seq[k]
                                    commit()
                                ui.button(icon='delete', on_click=del_series).props(
                                    'flat dense round size=xs color=negative')
                            with ui.row().classes('text-caption text-grey q-mb-xs'):
                                ui.label('#').style('width:24px')
                                ui.label('Width').classes('col')
                                ui.label('Height').classes('col')
                                ui.label('').style('width:28px')
                            for idx, entry in enumerate(series):
                                with ui.row().classes('items-center w-full'):
                                    ui.label(str(idx + 1)).classes('text-caption').style('width:24px')
                                    w_inp = ui.number(value=int(entry[0]), min=1, step=1).classes(
                                        'col').props('outlined dense hide-bottom-space')
                                    h_inp = ui.number(value=int(entry[1]), min=1, step=1).classes(
                                        'col').props('outlined dense hide-bottom-space')

                                    def _sync_wh(i=idx, k=res_key, wi=w_inp, hi=h_inp):
                                        seq[k][i] = [
                                            int(wi.value) if wi.value else 512,
                                            int(hi.value) if hi.value else 512,
                                        ]
                                        commit()

                                    w_inp.on('blur', lambda _, s=_sync_wh: s())
                                    h_inp.on('blur', lambda _, s=_sync_wh: s())

                                    def del_row(i=idx, k=res_key):
                                        seq[k].pop(i)
                                        commit()
                                    ui.button(icon='remove', on_click=del_row).props(
                                        'flat dense round size=xs')

                            def add_row(k=res_key):
                                seq[k].append([512, 512])
                                commit()
                            ui.button('+ Add row', icon='add', on_click=add_row).props(
                                'flat dense size=sm').classes('q-mt-xs')

                with ui.expansion('Add Resolution Series', icon='straighten').classes('w-full q-mt-sm'):
                    new_res_key = ui.input('Key name', value='resolutions').props('outlined dense')
                    def add_res_series():
                        k = new_res_key.value.strip()
                        if k and k not in seq:
                            seq[k] = [[512, 512], [1024, 1024]]
                            commit()
                    ui.button('Add', icon='add', on_click=add_res_series).props('outlined dense')
```

**Step 3: Run all tests**

```bash
pytest tests/ -q
```
Expected: all tests PASS (no Python tests cover the NiceGUI render path, but no regressions)

**Important:** Also update the `custom_keys` filter in `_render_sequence_card` (line ~648) to exclude
resolution series keys — otherwise they'd render in both the resolution editor AND "Custom Parameters":

```python
# Find this line:
custom_keys = [k for k in seq.keys() if k not in standard_keys]
# Replace with:
custom_keys = [k for k in seq.keys() if k not in standard_keys and not _is_resolution_series(seq.get(k))]
```

**Step 4: Commit**

```bash
git add tab_batch_ng.py
git commit -m "feat: resolution series editor in sequence card"
```

---

### Task 4: JS extension `web/project_resolution.js`

**Files:**
- Create: `web/project_resolution.js`

This file mirrors `web/project_key.js` exactly, with two differences:
1. It targets `"ProjectResolution"` instead of `"ProjectKey"`
2. `_refreshKeys` filters to only show keys whose value is a resolution series (list of `[int, int]` pairs) — but since the keys API only returns key names (not values), the filter is done by naming convention or we just show all keys and let the user pick. For simplicity, show all keys (same as ProjectKey) and let the user pick.
3. The `index` widget is **not** hidden — the user wires it from a loop node
4. The node has two outputs (`width`, `height`) so no output slot name update is needed

**Step 1: Create `web/project_resolution.js`**

```javascript
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "json.manager.project.resolution",

    async beforeQueuePrompt() {
        if (!app.graph?._nodes) return;
        for (const node of app.graph._nodes) {
            if (node.type === "ProjectResolution" && node._syncFromSource) {
                node._syncFromSource();
            }
        }
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "ProjectResolution") return;

        function hideWidget(widget) {
            if (widget.origType === undefined) widget.origType = widget.type;
            widget.type = "hidden";
            widget.hidden = true;
            widget.computeSize = () => [0, -4];
        }

        function replaceWithCombo(node, name, values, callback) {
            const idx = node.widgets?.findIndex(w => w.name === name);
            if (idx === -1 || idx === undefined) return null;
            const oldWidget = node.widgets[idx];
            const savedValue = oldWidget.value || "";
            const comboValues = values.length > 0 ? values : [""];
            if (savedValue && !comboValues.includes(savedValue)) {
                comboValues.unshift(savedValue);
            }
            const defaultValue = savedValue || comboValues[0];
            node.widgets.splice(idx, 1);
            const combo = node.addWidget("combo", name, defaultValue, callback, { values: comboValues });
            if (node.widgets.length > 1) {
                node.widgets.splice(node.widgets.length - 1, 1);
                node.widgets.splice(idx, 0, combo);
            }
            return combo;
        }

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);
            this._configured = false;

            // Hide synced config widgets (index stays visible — user wires it)
            for (const name of ["manager_url", "project_name", "file_name", "sequence_number"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) hideWidget(w);
            }

            const node = this;
            const sourceLabels = this._getSourceLabels?.() || [];
            const srcCombo = replaceWithCombo(this, "source_label", sourceLabels, function (value) {
                node._syncFromSource();
                node._refreshKeys();
            });
            if (srcCombo) srcCombo.value = sourceLabels[0] || "";

            const keyCombo = replaceWithCombo(this, "key_name", [], function (value) {
                node.title = value ? `Resolution: ${value}` : "Project Resolution";
                app.graph?.setDirtyCanvas(true, true);
            });
            if (keyCombo) keyCombo.value = "";

            queueMicrotask(() => {
                if (!this._configured) {
                    this.setSize(this.computeSize());
                }
            });
        };

        nodeType.prototype._getSourceLabels = function () {
            const seen = new Set();
            const labels = [];
            if (!this.graph) return labels;
            for (const node of this.graph._nodes) {
                if (node.type === "ProjectSource") {
                    const lw = node.widgets?.find(w => w.name === "label");
                    if (lw?.value && !seen.has(lw.value)) {
                        seen.add(lw.value);
                        labels.push(lw.value);
                    }
                }
            }
            return labels;
        };

        nodeType.prototype._findSource = function (label) {
            if (!this.graph || !label) return null;
            for (const node of this.graph._nodes) {
                if (node.type === "ProjectSource") {
                    const lw = node.widgets?.find(w => w.name === "label");
                    if (lw?.value === label) return node;
                }
            }
            return null;
        };

        nodeType.prototype._syncFromSource = function () {
            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            const source = this._findSource(srcWidget?.value);
            if (!source) return;
            for (const name of ["manager_url", "project_name", "file_name", "sequence_number"]) {
                const dst = this.widgets?.find(w => w.name === name);
                const src = source.widgets?.find(w => w.name === name);
                if (dst && src) dst.value = src.value;
            }
        };

        nodeType.prototype._refreshKeys = async function () {
            const urlW = this.widgets?.find(w => w.name === "manager_url");
            const projW = this.widgets?.find(w => w.name === "project_name");
            const fileW = this.widgets?.find(w => w.name === "file_name");
            const seqW = this.widgets?.find(w => w.name === "sequence_number");
            if (!urlW?.value || !projW?.value || !fileW?.value) return;

            try {
                const resp = await api.fetchApi(
                    `/json_manager/get_project_keys?url=${encodeURIComponent(urlW.value)}&project=${encodeURIComponent(projW.value)}&file=${encodeURIComponent(fileW.value)}&seq=${seqW?.value || 1}`
                );
                if (!resp.ok) return;
                const data = await resp.json();
                if (data.error || !Array.isArray(data.keys)) return;

                const keyWidget = this.widgets?.find(w => w.name === "key_name");
                if (keyWidget) {
                    keyWidget.options.values = data.keys.length > 0 ? data.keys : [""];
                }
            } catch (e) {
                console.error("[ProjectResolution] Failed to refresh keys:", e);
            }
        };

        const origOnMouseDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (e, localPos, graphCanvas) {
            origOnMouseDown?.apply(this, arguments);
            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            if (srcWidget) srcWidget.options.values = this._getSourceLabels();
            this._syncFromSource();
        };

        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            origOnConfigure?.apply(this, arguments);
            this._configured = true;

            for (const name of ["manager_url", "project_name", "file_name", "sequence_number"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) hideWidget(w);
            }

            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            if (srcWidget && srcWidget.type !== "combo") {
                const node = this;
                replaceWithCombo(this, "source_label", this._getSourceLabels(), function (value) {
                    node._syncFromSource();
                    node._refreshKeys();
                });
            } else if (srcWidget) {
                srcWidget.options.values = this._getSourceLabels();
            }

            const keyWidget = this.widgets?.find(w => w.name === "key_name");
            if (keyWidget && keyWidget.type !== "combo") {
                const node = this;
                replaceWithCombo(this, "key_name", [], function (value) {
                    node.title = value ? `Resolution: ${value}` : "Project Resolution";
                    app.graph?.setDirtyCanvas(true, true);
                });
            }

            const finalKeyWidget = this.widgets?.find(w => w.name === "key_name");
            if (finalKeyWidget?.value) {
                this.title = `Resolution: ${finalKeyWidget.value}`;
            }

            this.setSize(this.computeSize());

            const node = this;
            queueMicrotask(() => {
                node._syncFromSource();
                node._refreshKeys();
            });
        };
    },
});
```

**Step 2: Run all tests**

```bash
pytest tests/ -q
```
Expected: all tests PASS (JS has no Python tests)

**Step 3: Commit**

```bash
git add web/project_resolution.js
git commit -m "feat: ProjectResolution JS extension for ComfyUI frontend"
```

---

### Task 5: Final verification and push

**Step 1: Run full test suite**

```bash
pytest tests/ -v
```
Expected: all tests PASS

**Step 2: Push branch**

```bash
git push origin HEAD
```
