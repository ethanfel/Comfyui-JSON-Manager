import json
import os

import pytest

from json_loader import to_float, to_int, get_batch_item, read_json_data


class TestToFloat:
    def test_valid(self):
        assert to_float("3.14") == 3.14
        assert to_float(5) == 5.0

    def test_invalid(self):
        assert to_float("abc") == 0.0

    def test_none(self):
        assert to_float(None) == 0.0


class TestToInt:
    def test_valid(self):
        assert to_int("7") == 7
        assert to_int(3.9) == 3

    def test_invalid(self):
        assert to_int("xyz") == 0

    def test_none(self):
        assert to_int(None) == 0


class TestGetBatchItem:
    def test_valid_index(self):
        data = {"batch_data": [{"a": 1}, {"a": 2}, {"a": 3}]}
        assert get_batch_item(data, 2) == {"a": 2}

    def test_clamp_high(self):
        data = {"batch_data": [{"a": 1}, {"a": 2}]}
        assert get_batch_item(data, 99) == {"a": 2}

    def test_clamp_low(self):
        data = {"batch_data": [{"a": 1}, {"a": 2}]}
        assert get_batch_item(data, 0) == {"a": 1}

    def test_no_batch_data(self):
        data = {"key": "val"}
        assert get_batch_item(data, 1) == data


class TestReadJsonData:
    def test_missing_file(self, tmp_path):
        assert read_json_data(str(tmp_path / "nope.json")) == {}

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{broken")
        assert read_json_data(str(p)) == {}

    def test_non_dict_json(self, tmp_path):
        p = tmp_path / "list.json"
        p.write_text(json.dumps([1, 2, 3]))
        assert read_json_data(str(p)) == {}

    def test_valid(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text(json.dumps({"key": "val"}))
        assert read_json_data(str(p)) == {"key": "val"}
