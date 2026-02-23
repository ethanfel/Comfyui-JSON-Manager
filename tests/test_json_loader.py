import json
import os

import pytest

from json_loader import (
    to_float, to_int, get_batch_item, read_json_data,
    JSONLoaderDynamic, MAX_DYNAMIC_OUTPUTS,
)


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
    def test_lookup_by_sequence_number_field(self):
        data = {"batch_data": [
            {"sequence_number": 1, "a": "first"},
            {"sequence_number": 5, "a": "fifth"},
            {"sequence_number": 3, "a": "third"},
        ]}
        assert get_batch_item(data, 5) == {"sequence_number": 5, "a": "fifth"}
        assert get_batch_item(data, 3) == {"sequence_number": 3, "a": "third"}

    def test_fallback_to_index(self):
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


class TestJSONLoaderDynamic:
    def _make_json(self, tmp_path, data):
        p = tmp_path / "test.json"
        p.write_text(json.dumps(data))
        return str(p)

    def test_known_keys(self, tmp_path):
        path = self._make_json(tmp_path, {"name": "alice", "age": 30, "score": 9.5})
        loader = JSONLoaderDynamic()
        result = loader.load_dynamic(path, 1, output_keys="name,age,score")
        assert result[0] == "alice"
        assert result[1] == 30
        assert result[2] == 9.5

    def test_empty_output_keys(self, tmp_path):
        path = self._make_json(tmp_path, {"name": "alice"})
        loader = JSONLoaderDynamic()
        result = loader.load_dynamic(path, 1, output_keys="")
        assert len(result) == MAX_DYNAMIC_OUTPUTS
        assert all(v == "" for v in result)

    def test_pads_to_max(self, tmp_path):
        path = self._make_json(tmp_path, {"a": "1", "b": "2"})
        loader = JSONLoaderDynamic()
        result = loader.load_dynamic(path, 1, output_keys="a,b")
        assert len(result) == MAX_DYNAMIC_OUTPUTS
        assert result[0] == "1"
        assert result[1] == "2"
        assert all(v == "" for v in result[2:])

    def test_type_preservation_int(self, tmp_path):
        path = self._make_json(tmp_path, {"count": 42})
        loader = JSONLoaderDynamic()
        result = loader.load_dynamic(path, 1, output_keys="count")
        assert result[0] == 42
        assert isinstance(result[0], int)

    def test_type_preservation_float(self, tmp_path):
        path = self._make_json(tmp_path, {"rate": 3.14})
        loader = JSONLoaderDynamic()
        result = loader.load_dynamic(path, 1, output_keys="rate")
        assert result[0] == 3.14
        assert isinstance(result[0], float)

    def test_type_preservation_str(self, tmp_path):
        path = self._make_json(tmp_path, {"label": "hello"})
        loader = JSONLoaderDynamic()
        result = loader.load_dynamic(path, 1, output_keys="label")
        assert result[0] == "hello"
        assert isinstance(result[0], str)

    def test_bool_becomes_string(self, tmp_path):
        path = self._make_json(tmp_path, {"flag": True, "off": False})
        loader = JSONLoaderDynamic()
        result = loader.load_dynamic(path, 1, output_keys="flag,off")
        assert result[0] == "true"
        assert result[1] == "false"
        assert isinstance(result[0], str)

    def test_missing_key_returns_empty_string(self, tmp_path):
        path = self._make_json(tmp_path, {"a": "1"})
        loader = JSONLoaderDynamic()
        result = loader.load_dynamic(path, 1, output_keys="a,nonexistent")
        assert result[0] == "1"
        assert result[1] == ""

    def test_missing_file_returns_all_empty(self, tmp_path):
        loader = JSONLoaderDynamic()
        result = loader.load_dynamic(str(tmp_path / "nope.json"), 1, output_keys="a,b")
        assert len(result) == MAX_DYNAMIC_OUTPUTS
        assert result[0] == ""
        assert result[1] == ""

    def test_batch_data(self, tmp_path):
        path = self._make_json(tmp_path, {
            "batch_data": [
                {"sequence_number": 1, "x": "first"},
                {"sequence_number": 2, "x": "second"},
            ]
        })
        loader = JSONLoaderDynamic()
        result = loader.load_dynamic(path, 2, output_keys="x")
        assert result[0] == "second"
