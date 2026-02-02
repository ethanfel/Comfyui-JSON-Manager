import pytest
from history_tree import HistoryTree


def test_commit_creates_node_with_correct_parent():
    tree = HistoryTree({})
    id1 = tree.commit({"a": 1}, note="first")
    id2 = tree.commit({"b": 2}, note="second")

    assert tree.nodes[id1]["parent"] is None
    assert tree.nodes[id2]["parent"] == id1


def test_checkout_returns_correct_data():
    tree = HistoryTree({})
    id1 = tree.commit({"val": 42}, note="snap")
    result = tree.checkout(id1)
    assert result == {"val": 42}


def test_checkout_nonexistent_returns_none():
    tree = HistoryTree({})
    assert tree.checkout("nonexistent") is None


def test_cycle_detection_raises():
    tree = HistoryTree({})
    id1 = tree.commit({"a": 1})
    # Manually introduce a cycle
    tree.nodes[id1]["parent"] = id1
    with pytest.raises(ValueError, match="Cycle detected"):
        tree.commit({"b": 2})


def test_branch_creation_on_detached_head():
    tree = HistoryTree({})
    id1 = tree.commit({"a": 1})
    id2 = tree.commit({"b": 2})
    # Detach head by checking out a non-tip node
    tree.checkout(id1)
    # head_id is now id1, which is no longer a branch tip (main points to id2)
    id3 = tree.commit({"c": 3})
    # A new branch should have been created
    assert len(tree.branches) == 2
    assert tree.nodes[id3]["parent"] == id1


def test_legacy_migration():
    legacy = {
        "prompt_history": [
            {"note": "Entry A", "seed": 1},
            {"note": "Entry B", "seed": 2},
        ]
    }
    tree = HistoryTree(legacy)
    assert len(tree.nodes) == 2
    assert tree.head_id is not None
    assert tree.branches["main"] == tree.head_id


def test_to_dict_roundtrip():
    tree = HistoryTree({})
    tree.commit({"x": 1}, note="test")
    d = tree.to_dict()
    tree2 = HistoryTree(d)
    assert tree2.head_id == tree.head_id
    assert tree2.nodes == tree.nodes
