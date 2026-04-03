# BinaryIndexDecoder Node — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a standalone ComfyUI node `BinaryIndexDecoder` that converts an integer index to 3 boolean outputs using binary (bit-field) encoding.

**Architecture:** Single class in `project_loader.py`, no JS extension needed, no NiceGUI changes. Takes `index` INT, returns `(flag_0, flag_1, flag_2)` as BOOLEAN using bit-shift logic. Added to existing node mappings.

**Tech Stack:** Python, ComfyUI node API, pytest

---

### Task 1: Write failing tests for BinaryIndexDecoder

**Files:**
- Modify: `tests/test_project_loader.py` (append new test class at end, before `TestNodeMappings`)
- Modify: `tests/test_project_loader.py` — update `TestNodeMappings.test_mappings_exist` to expect 5 nodes

**Step 1: Add the test class**

Append this class before `TestNodeMappings` in `tests/test_project_loader.py`:

```python
class TestBinaryIndexDecoder:
    def test_input_types(self):
        from project_loader import BinaryIndexDecoder
        inputs = BinaryIndexDecoder.INPUT_TYPES()
        assert "index" in inputs["required"]
        assert inputs["required"]["index"][0] == "INT"

    def test_three_boolean_outputs(self):
        from project_loader import BinaryIndexDecoder
        assert BinaryIndexDecoder.RETURN_TYPES == ("BOOLEAN", "BOOLEAN", "BOOLEAN")
        assert BinaryIndexDecoder.RETURN_NAMES == ("flag_0", "flag_1", "flag_2")

    def test_category(self):
        from project_loader import BinaryIndexDecoder
        assert BinaryIndexDecoder.CATEGORY == "JSON Manager/utils"

    def test_index_0(self):
        from project_loader import BinaryIndexDecoder
        assert BinaryIndexDecoder().decode(0) == (False, False, False)

    def test_index_1(self):
        from project_loader import BinaryIndexDecoder
        assert BinaryIndexDecoder().decode(1) == (True, False, False)

    def test_index_2(self):
        from project_loader import BinaryIndexDecoder
        assert BinaryIndexDecoder().decode(2) == (False, True, False)

    def test_index_3(self):
        from project_loader import BinaryIndexDecoder
        assert BinaryIndexDecoder().decode(3) == (True, True, False)

    def test_index_4(self):
        from project_loader import BinaryIndexDecoder
        assert BinaryIndexDecoder().decode(4) == (False, False, True)

    def test_index_7(self):
        from project_loader import BinaryIndexDecoder
        assert BinaryIndexDecoder().decode(7) == (True, True, True)
```

Also update `TestNodeMappings.test_mappings_exist`:

```python
def test_mappings_exist(self):
    from project_loader import PROJECT_NODE_CLASS_MAPPINGS, PROJECT_NODE_DISPLAY_NAME_MAPPINGS
    assert "ProjectLoaderDynamic" in PROJECT_NODE_CLASS_MAPPINGS
    assert "ProjectSource" in PROJECT_NODE_CLASS_MAPPINGS
    assert "ProjectKey" in PROJECT_NODE_CLASS_MAPPINGS
    assert "ProjectResolution" in PROJECT_NODE_CLASS_MAPPINGS
    assert "BinaryIndexDecoder" in PROJECT_NODE_CLASS_MAPPINGS
    assert len(PROJECT_NODE_CLASS_MAPPINGS) == 5
    assert len(PROJECT_NODE_DISPLAY_NAME_MAPPINGS) == 5
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_project_loader.py::TestBinaryIndexDecoder -v
```

Expected: FAIL with `ImportError: cannot import name 'BinaryIndexDecoder'`

**Step 3: Commit the failing tests**

```bash
git add tests/test_project_loader.py
git commit -m "test: add failing tests for BinaryIndexDecoder node"
```

---

### Task 2: Implement BinaryIndexDecoder

**Files:**
- Modify: `project_loader.py` — add class after `ProjectResolution`, update mappings

**Step 1: Add the class**

Insert after the `ProjectResolution` class (before `# --- Mappings ---`) in `project_loader.py`:

```python
class BinaryIndexDecoder:
    """Decodes an integer index into 3 boolean flags using binary (bit-field) encoding.

    index 0 → (False, False, False)
    index 1 → (True,  False, False)  # bit 0
    index 2 → (False, True,  False)  # bit 1
    index 3 → (True,  True,  False)  # bits 0+1
    index 4 → (False, False, True)   # bit 2
    ...
    index 7 → (True,  True,  True)
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "index": ("INT", {"default": 0, "min": 0, "max": 7}),
            }
        }

    RETURN_TYPES = ("BOOLEAN", "BOOLEAN", "BOOLEAN")
    RETURN_NAMES = ("flag_0", "flag_1", "flag_2")
    FUNCTION = "decode"
    CATEGORY = "JSON Manager/utils"
    OUTPUT_NODE = False

    def decode(self, index: int):
        return (
            bool((index >> 0) & 1),
            bool((index >> 1) & 1),
            bool((index >> 2) & 1),
        )
```

**Step 2: Update mappings**

In `PROJECT_NODE_CLASS_MAPPINGS`, add:
```python
"BinaryIndexDecoder": BinaryIndexDecoder,
```

In `PROJECT_NODE_DISPLAY_NAME_MAPPINGS`, add:
```python
"BinaryIndexDecoder": "Binary Index Decoder",
```

**Step 3: Run all tests**

```bash
python -m pytest tests/test_project_loader.py -v
```

Expected: all tests PASS (42 existing + 10 new = 52 total)

**Step 4: Commit**

```bash
git add project_loader.py tests/test_project_loader.py
git commit -m "feat: add BinaryIndexDecoder node (INT index → 3 BOOLEANs, binary encoding)"
git push
```
