import json
from pathlib import Path

import pytest

from db import ProjectDB
from utils import KEY_BATCH_DATA, KEY_HISTORY_TREE


@pytest.fixture
def db(tmp_path):
    """Create a fresh ProjectDB in a temp directory."""
    db_path = tmp_path / "test.db"
    pdb = ProjectDB(db_path)
    yield pdb
    pdb.close()


# ------------------------------------------------------------------
# Projects CRUD
# ------------------------------------------------------------------

class TestProjects:
    def test_create_and_get(self, db):
        pid = db.create_project("proj1", "/some/path", "A test project")
        assert pid > 0
        proj = db.get_project("proj1")
        assert proj is not None
        assert proj["name"] == "proj1"
        assert proj["folder_path"] == "/some/path"
        assert proj["description"] == "A test project"

    def test_list_projects(self, db):
        db.create_project("beta", "/b")
        db.create_project("alpha", "/a")
        projects = db.list_projects()
        assert len(projects) == 2
        assert projects[0]["name"] == "alpha"
        assert projects[1]["name"] == "beta"

    def test_get_nonexistent(self, db):
        assert db.get_project("nope") is None

    def test_delete_project(self, db):
        db.create_project("to_delete", "/x")
        assert db.delete_project("to_delete") is True
        assert db.get_project("to_delete") is None

    def test_delete_nonexistent(self, db):
        assert db.delete_project("nope") is False

    def test_unique_name_constraint(self, db):
        db.create_project("dup", "/a")
        with pytest.raises(Exception):
            db.create_project("dup", "/b")


# ------------------------------------------------------------------
# Data files
# ------------------------------------------------------------------

class TestDataFiles:
    def test_create_and_list(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch_i2v", "i2v", {"extra": "meta"})
        assert df_id > 0
        files = db.list_data_files(pid)
        assert len(files) == 1
        assert files[0]["name"] == "batch_i2v"
        assert files[0]["data_type"] == "i2v"

    def test_get_data_file(self, db):
        pid = db.create_project("p1", "/p1")
        db.create_data_file(pid, "batch_i2v", "i2v", {"key": "value"})
        df = db.get_data_file(pid, "batch_i2v")
        assert df is not None
        assert df["top_level"] == {"key": "value"}

    def test_get_data_file_by_names(self, db):
        pid = db.create_project("p1", "/p1")
        db.create_data_file(pid, "batch_i2v", "i2v")
        df = db.get_data_file_by_names("p1", "batch_i2v")
        assert df is not None
        assert df["name"] == "batch_i2v"

    def test_get_nonexistent_data_file(self, db):
        pid = db.create_project("p1", "/p1")
        assert db.get_data_file(pid, "nope") is None

    def test_unique_constraint(self, db):
        pid = db.create_project("p1", "/p1")
        db.create_data_file(pid, "batch_i2v", "i2v")
        with pytest.raises(Exception):
            db.create_data_file(pid, "batch_i2v", "vace")

    def test_cascade_delete(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch_i2v", "i2v")
        db.upsert_sequence(df_id, 1, {"prompt": "hello"})
        db.save_history_tree(df_id, {"nodes": {}})
        db.delete_project("p1")
        assert db.get_data_file(pid, "batch_i2v") is None


# ------------------------------------------------------------------
# Sequences
# ------------------------------------------------------------------

class TestSequences:
    def test_upsert_and_get(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        db.upsert_sequence(df_id, 1, {"prompt": "hello", "seed": 42})
        data = db.get_sequence(df_id, 1)
        assert data == {"prompt": "hello", "seed": 42}

    def test_upsert_updates_existing(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        db.upsert_sequence(df_id, 1, {"prompt": "v1"})
        db.upsert_sequence(df_id, 1, {"prompt": "v2"})
        data = db.get_sequence(df_id, 1)
        assert data["prompt"] == "v2"

    def test_list_sequences(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        db.upsert_sequence(df_id, 3, {"a": 1})
        db.upsert_sequence(df_id, 1, {"b": 2})
        db.upsert_sequence(df_id, 2, {"c": 3})
        seqs = db.list_sequences(df_id)
        assert seqs == [1, 2, 3]

    def test_get_nonexistent_sequence(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        assert db.get_sequence(df_id, 99) is None

    def test_get_sequence_keys(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        db.upsert_sequence(df_id, 1, {
            "prompt": "hello",
            "seed": 42,
            "cfg": 1.5,
            "flag": True,
        })
        keys, types = db.get_sequence_keys(df_id, 1)
        assert "prompt" in keys
        assert "seed" in keys
        idx_prompt = keys.index("prompt")
        idx_seed = keys.index("seed")
        idx_cfg = keys.index("cfg")
        idx_flag = keys.index("flag")
        assert types[idx_prompt] == "STRING"
        assert types[idx_seed] == "INT"
        assert types[idx_cfg] == "FLOAT"
        assert types[idx_flag] == "STRING"  # bools -> STRING

    def test_get_sequence_keys_nonexistent(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        keys, types = db.get_sequence_keys(df_id, 99)
        assert keys == []
        assert types == []

    def test_delete_sequences_for_file(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        db.upsert_sequence(df_id, 1, {"a": 1})
        db.upsert_sequence(df_id, 2, {"b": 2})
        db.delete_sequences_for_file(df_id)
        assert db.list_sequences(df_id) == []


# ------------------------------------------------------------------
# History trees
# ------------------------------------------------------------------

class TestHistoryTrees:
    def test_save_and_get(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        tree = {"nodes": {"abc": {"id": "abc"}}, "head_id": "abc"}
        db.save_history_tree(df_id, tree)
        result = db.get_history_tree(df_id)
        assert result == tree

    def test_upsert_updates(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        db.save_history_tree(df_id, {"v": 1})
        db.save_history_tree(df_id, {"v": 2})
        result = db.get_history_tree(df_id)
        assert result == {"v": 2}

    def test_get_nonexistent(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        assert db.get_history_tree(df_id) is None


# ------------------------------------------------------------------
# Import
# ------------------------------------------------------------------

class TestImport:
    def test_import_json_file(self, db, tmp_path):
        pid = db.create_project("p1", "/p1")
        json_path = tmp_path / "batch_prompt_i2v.json"
        data = {
            KEY_BATCH_DATA: [
                {"sequence_number": 1, "prompt": "hello", "seed": 42},
                {"sequence_number": 2, "prompt": "world", "seed": 99},
            ],
            KEY_HISTORY_TREE: {"nodes": {}, "head_id": None},
        }
        json_path.write_text(json.dumps(data))

        df_id = db.import_json_file(pid, json_path, "i2v")
        assert df_id > 0

        seqs = db.list_sequences(df_id)
        assert seqs == [1, 2]

        s1 = db.get_sequence(df_id, 1)
        assert s1["prompt"] == "hello"
        assert s1["seed"] == 42

        tree = db.get_history_tree(df_id)
        assert tree == {"nodes": {}, "head_id": None}

    def test_import_file_name_from_stem(self, db, tmp_path):
        pid = db.create_project("p1", "/p1")
        json_path = tmp_path / "my_batch.json"
        json_path.write_text(json.dumps({KEY_BATCH_DATA: [{"sequence_number": 1}]}))
        db.import_json_file(pid, json_path)
        df = db.get_data_file(pid, "my_batch")
        assert df is not None

    def test_import_no_batch_data(self, db, tmp_path):
        pid = db.create_project("p1", "/p1")
        json_path = tmp_path / "simple.json"
        json_path.write_text(json.dumps({"prompt": "flat file"}))
        df_id = db.import_json_file(pid, json_path)
        seqs = db.list_sequences(df_id)
        assert seqs == []

    def test_reimport_updates_existing(self, db, tmp_path):
        """Re-importing the same file should update data, not crash."""
        pid = db.create_project("p1", "/p1")
        json_path = tmp_path / "batch.json"

        # First import
        data_v1 = {KEY_BATCH_DATA: [{"sequence_number": 1, "prompt": "v1"}]}
        json_path.write_text(json.dumps(data_v1))
        df_id_1 = db.import_json_file(pid, json_path, "i2v")

        # Second import (same file, updated data)
        data_v2 = {KEY_BATCH_DATA: [{"sequence_number": 1, "prompt": "v2"}, {"sequence_number": 2, "prompt": "new"}]}
        json_path.write_text(json.dumps(data_v2))
        df_id_2 = db.import_json_file(pid, json_path, "vace")

        # Should reuse the same data_file row
        assert df_id_1 == df_id_2
        # Data type should be updated
        df = db.get_data_file(pid, "batch")
        assert df["data_type"] == "vace"
        # Sequences should reflect v2
        seqs = db.list_sequences(df_id_2)
        assert seqs == [1, 2]
        s1 = db.get_sequence(df_id_2, 1)
        assert s1["prompt"] == "v2"


# ------------------------------------------------------------------
# Query helpers
# ------------------------------------------------------------------

class TestQueryHelpers:
    def test_query_sequence_data(self, db):
        pid = db.create_project("myproject", "/mp")
        df_id = db.create_data_file(pid, "batch_i2v", "i2v")
        db.upsert_sequence(df_id, 1, {"prompt": "test", "seed": 7})
        result = db.query_sequence_data("myproject", "batch_i2v", 1)
        assert result == {"prompt": "test", "seed": 7}

    def test_query_sequence_data_not_found(self, db):
        assert db.query_sequence_data("nope", "nope", 1) is None

    def test_query_sequence_keys(self, db):
        pid = db.create_project("myproject", "/mp")
        df_id = db.create_data_file(pid, "batch_i2v", "i2v")
        db.upsert_sequence(df_id, 1, {"prompt": "test", "seed": 7})
        keys, types = db.query_sequence_keys("myproject", "batch_i2v", 1)
        assert "prompt" in keys
        assert "seed" in keys

    def test_list_project_files(self, db):
        pid = db.create_project("p1", "/p1")
        db.create_data_file(pid, "file_a", "i2v")
        db.create_data_file(pid, "file_b", "vace")
        files = db.list_project_files("p1")
        assert len(files) == 2

    def test_list_project_sequences(self, db):
        pid = db.create_project("p1", "/p1")
        df_id = db.create_data_file(pid, "batch", "generic")
        db.upsert_sequence(df_id, 1, {})
        db.upsert_sequence(df_id, 2, {})
        seqs = db.list_project_sequences("p1", "batch")
        assert seqs == [1, 2]
