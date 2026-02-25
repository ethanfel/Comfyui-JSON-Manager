import json
from pathlib import Path

import pytest

from utils import load_json, save_json, get_file_mtime, ALLOWED_BASE_DIR, DEFAULTS, resolve_path_case_insensitive


def test_load_json_valid(tmp_path):
    p = tmp_path / "test.json"
    data = {"key": "value"}
    p.write_text(json.dumps(data))
    result, mtime = load_json(p)
    assert result == data
    assert mtime > 0


def test_load_json_missing(tmp_path):
    p = tmp_path / "nope.json"
    result, mtime = load_json(p)
    assert result == DEFAULTS.copy()
    assert mtime == 0


def test_load_json_invalid(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    result, mtime = load_json(p)
    assert result == DEFAULTS.copy()
    assert mtime == 0


def test_save_json_atomic(tmp_path):
    p = tmp_path / "out.json"
    data = {"hello": "world"}
    save_json(p, data)
    assert p.exists()
    assert not p.with_suffix(".json.tmp").exists()
    assert json.loads(p.read_text()) == data


def test_save_json_overwrites(tmp_path):
    p = tmp_path / "out.json"
    save_json(p, {"a": 1})
    save_json(p, {"b": 2})
    assert json.loads(p.read_text()) == {"b": 2}


def test_get_file_mtime_existing(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("x")
    assert get_file_mtime(p) > 0


def test_get_file_mtime_missing(tmp_path):
    assert get_file_mtime(tmp_path / "missing.txt") == 0


def test_allowed_base_dir_is_set():
    assert ALLOWED_BASE_DIR is not None
    assert isinstance(ALLOWED_BASE_DIR, Path)


class TestResolvePathCaseInsensitive:
    def test_exact_match(self, tmp_path):
        d = tmp_path / "MyFolder"
        d.mkdir()
        result = resolve_path_case_insensitive(str(d))
        assert result == d.resolve()

    def test_wrong_case_single_component(self, tmp_path):
        d = tmp_path / "MyFolder"
        d.mkdir()
        wrong = tmp_path / "myfolder"
        result = resolve_path_case_insensitive(str(wrong))
        assert result == d.resolve()

    def test_wrong_case_nested(self, tmp_path):
        d = tmp_path / "Parent" / "Child"
        d.mkdir(parents=True)
        wrong = tmp_path / "parent" / "CHILD"
        result = resolve_path_case_insensitive(str(wrong))
        assert result == d.resolve()

    def test_no_match_returns_none(self, tmp_path):
        result = resolve_path_case_insensitive(str(tmp_path / "nonexistent"))
        assert result is None

    def test_file_path(self, tmp_path):
        f = tmp_path / "Data.json"
        f.write_text("{}")
        wrong = tmp_path / "data.JSON"
        result = resolve_path_case_insensitive(str(wrong))
        assert result == f.resolve()
