import pytest
from snapshot_timeline import SnapshotTimeline, diff_snapshots


def test_record_creates_snapshot():
    tl = SnapshotTimeline({})
    sid = tl.record({"batch_data": [{"seed": 42}]}, note="first")
    assert sid in tl.snapshots
    assert tl.current_id == sid
    assert tl.snapshots[sid]["note"] == "first"
    assert tl.snapshots[sid]["auto"] is False
    assert tl.snapshots[sid]["seq_count"] == 1


def test_record_auto_flag():
    tl = SnapshotTimeline({})
    sid = tl.record({"batch_data": []}, note="auto save", auto=True)
    assert tl.snapshots[sid]["auto"] is True


def test_multiple_records():
    tl = SnapshotTimeline({})
    id1 = tl.record({"batch_data": [{"a": 1}]}, note="one")
    id2 = tl.record({"batch_data": [{"b": 2}]}, note="two")
    assert len(tl.snapshots) == 2
    assert tl.current_id == id2


def test_to_dict_roundtrip():
    tl = SnapshotTimeline({})
    tl.record({"batch_data": [{"x": 1}]}, note="test")
    d = tl.to_dict()
    tl2 = SnapshotTimeline(d)
    assert tl2.current_id == tl.current_id
    assert set(tl2.snapshots.keys()) == set(tl.snapshots.keys())


def test_migrate_from_history_tree():
    """Old HistoryTree format should be flattened into snapshots."""
    old_data = {
        "nodes": {
            "aaa": {"id": "aaa", "parent": None, "timestamp": 1000, "note": "First", "data": {"batch_data": [{"seed": 1}]}},
            "bbb": {"id": "bbb", "parent": "aaa", "timestamp": 2000, "note": "Second", "data": {"batch_data": [{"seed": 2}]}},
        },
        "branches": {"main": "bbb"},
        "head_id": "bbb",
    }
    tl = SnapshotTimeline(old_data)
    assert len(tl.snapshots) == 2
    assert tl.current_id == "bbb"
    assert tl.snapshots["aaa"]["note"] == "First"
    assert tl.snapshots["bbb"]["note"] == "Second"
    # Data should be preserved
    assert tl.snapshots["aaa"]["data"]["batch_data"] == [{"seed": 1}]


def test_migrate_from_history_tree_no_data():
    """Slim tree nodes (no inline data) should still migrate."""
    old_data = {
        "nodes": {
            "aaa": {"id": "aaa", "parent": None, "timestamp": 1000, "note": "First"},
        },
        "branches": {"main": "aaa"},
        "head_id": "aaa",
    }
    tl = SnapshotTimeline(old_data)
    assert len(tl.snapshots) == 1
    assert tl.snapshots["aaa"]["seq_count"] == 0


def test_migrate_legacy_prompt_history():
    legacy = {
        "prompt_history": [
            {"note": "A", "seed": 1},
            {"note": "B", "seed": 2},
        ]
    }
    tl = SnapshotTimeline(legacy)
    assert len(tl.snapshots) == 2
    assert tl.current_id is not None


def test_toggle_pin():
    tl = SnapshotTimeline({})
    sid = tl.record({"batch_data": []}, note="test")
    assert tl.snapshots[sid]["pinned"] is False
    result = tl.toggle_pin(sid)
    assert result is True
    assert tl.snapshots[sid]["pinned"] is True
    result = tl.toggle_pin(sid)
    assert result is False


def test_delete_snapshot():
    tl = SnapshotTimeline({})
    id1 = tl.record({"batch_data": []}, note="one")
    id2 = tl.record({"batch_data": []}, note="two")
    tl.delete(id2)
    assert id2 not in tl.snapshots
    assert tl.current_id == id1


def test_delete_all_snapshots():
    tl = SnapshotTimeline({})
    sid = tl.record({"batch_data": []}, note="only")
    tl.delete(sid)
    assert len(tl.snapshots) == 0
    assert tl.current_id is None


def test_strip_snapshots():
    tl = SnapshotTimeline({})
    tl.record({"batch_data": [{"a": 1}]}, note="test")
    tl.strip_snapshots()
    for snap in tl.snapshots.values():
        assert "data" not in snap


def test_get_snapshot_data():
    tl = SnapshotTimeline({})
    sid = tl.record({"batch_data": [{"x": 1}]}, note="test")
    data = tl.get_snapshot_data(sid)
    assert data == {"batch_data": [{"x": 1}]}
    assert tl.get_snapshot_data("nonexistent") is None


# --- diff_snapshots tests ---

def test_diff_unchanged():
    batch = [{"sequence_number": 1, "seed": 42}]
    result = diff_snapshots(batch, batch)
    assert len(result) == 1
    assert result[0]["status"] == "unchanged"
    assert result[0]["changes"] == []


def test_diff_changed():
    old = [{"sequence_number": 1, "seed": 42, "cfg": 1.5}]
    new = [{"sequence_number": 1, "seed": 99, "cfg": 1.5}]
    result = diff_snapshots(old, new)
    assert result[0]["status"] == "changed"
    assert len(result[0]["changes"]) == 1
    assert result[0]["changes"][0]["field"] == "seed"
    assert result[0]["changes"][0]["old"] == 42
    assert result[0]["changes"][0]["new"] == 99


def test_diff_added_and_removed():
    old = [{"sequence_number": 1, "seed": 1}]
    new = [{"sequence_number": 2, "seed": 2}]
    result = diff_snapshots(old, new)
    assert len(result) == 2
    statuses = {r["seq_num"]: r["status"] for r in result}
    assert statuses[1] == "removed"
    assert statuses[2] == "added"


def test_diff_empty():
    assert diff_snapshots([], []) == []
