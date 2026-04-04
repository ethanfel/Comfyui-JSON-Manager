# BinaryIndexDecoder Node — Design

## Summary

A standalone ComfyUI utility node that converts an integer index into 3 boolean
outputs using binary (bit-field) encoding. Intended for use with loop counters to
gate multiple processing branches simultaneously.

## Node Spec

| Field | Value |
|---|---|
| Class name | `BinaryIndexDecoder` |
| Display name | `Binary Index Decoder` |
| Category | `JSON Manager/utils` |
| Function | `decode` |

### Inputs

| Name | Type | Default | Range |
|---|---|---|---|
| `index` | INT | 0 | 0–7 |

### Outputs

| Name | Type |
|---|---|
| `flag_0` | BOOLEAN |
| `flag_1` | BOOLEAN |
| `flag_2` | BOOLEAN |

### Logic

```
flag_0 = bool((index >> 0) & 1)
flag_1 = bool((index >> 1) & 1)
flag_2 = bool((index >> 2) & 1)
```

### Truth table

| index | flag_0 | flag_1 | flag_2 |
|---|---|---|---|
| 0 | F | F | F |
| 1 | T | F | F |
| 2 | F | T | F |
| 3 | T | T | F |
| 4 | F | F | T |
| 5 | T | F | T |
| 6 | F | T | T |
| 7 | T | T | T |

## Implementation Notes

- Lives in `project_loader.py` alongside other project nodes
- Added to `PROJECT_NODE_CLASS_MAPPINGS` and `PROJECT_NODE_DISPLAY_NAME_MAPPINGS`
- No JavaScript extension needed (no source sync, no dynamic widgets)
- No NiceGUI UI changes needed
- `IS_CHANGED` not needed (output is deterministic from input)

## Testing

9 tests in `tests/test_project_loader.py::TestBinaryIndexDecoder`:
- Input types include `index` as INT
- All 8 index values (0–7) produce correct boolean tuple
- Out-of-range index (e.g. 8) clamps to 0–7 or wraps gracefully
- `NodeMappings` test updated: 5 nodes, mappings length == 5
