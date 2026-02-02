import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# Mock streamlit before importing utils
import sys
from unittest.mock import MagicMock
sys.modules.setdefault("streamlit", MagicMock())

from utils import load_json, save_json, get_file_mtime, ALLOWED_BASE_DIR, DEFAULTS


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
