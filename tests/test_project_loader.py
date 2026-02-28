import json
from unittest.mock import patch, MagicMock
from io import BytesIO

import pytest

from project_loader import (
    ProjectLoaderDynamic,
    ProjectLoaderStandard,
    ProjectLoaderVACE,
    ProjectLoaderLoRA,
    _fetch_json,
    _fetch_data,
    _fetch_keys,
    MAX_DYNAMIC_OUTPUTS,
)


def _mock_urlopen(data: dict):
    """Create a mock context manager for urllib.request.urlopen."""
    response = MagicMock()
    response.read.return_value = json.dumps(data).encode()
    response.__enter__ = lambda s: s
    response.__exit__ = MagicMock(return_value=False)
    return response


class TestFetchHelpers:
    def test_fetch_json_success(self):
        data = {"key": "value"}
        with patch("project_loader.urllib.request.urlopen", return_value=_mock_urlopen(data)):
            result = _fetch_json("http://example.com/api")
        assert result == data

    def test_fetch_json_failure(self):
        import urllib.error
        with patch("project_loader.urllib.request.urlopen", side_effect=OSError("connection refused")):
            result = _fetch_json("http://example.com/api")
        assert result == {}

    def test_fetch_data_builds_url(self):
        data = {"prompt": "hello"}
        with patch("project_loader.urllib.request.urlopen", return_value=_mock_urlopen(data)) as mock:
            result = _fetch_data("http://localhost:8080", "proj1", "batch_i2v", 1)
        assert result == data
        called_url = mock.call_args[0][0]
        assert "/api/projects/proj1/files/batch_i2v/data?seq=1" in called_url

    def test_fetch_keys_builds_url(self):
        data = {"keys": ["prompt"], "types": ["STRING"]}
        with patch("project_loader.urllib.request.urlopen", return_value=_mock_urlopen(data)) as mock:
            result = _fetch_keys("http://localhost:8080", "proj1", "batch_i2v", 1)
        assert result == data
        called_url = mock.call_args[0][0]
        assert "/api/projects/proj1/files/batch_i2v/keys?seq=1" in called_url

    def test_fetch_data_strips_trailing_slash(self):
        data = {"prompt": "hello"}
        with patch("project_loader.urllib.request.urlopen", return_value=_mock_urlopen(data)) as mock:
            _fetch_data("http://localhost:8080/", "proj1", "file1", 1)
        called_url = mock.call_args[0][0]
        assert "//api" not in called_url

    def test_fetch_data_encodes_special_chars(self):
        """Project/file names with spaces or special chars should be percent-encoded."""
        data = {"prompt": "hello"}
        with patch("project_loader.urllib.request.urlopen", return_value=_mock_urlopen(data)) as mock:
            _fetch_data("http://localhost:8080", "my project", "batch file", 1)
        called_url = mock.call_args[0][0]
        assert "my%20project" in called_url
        assert "batch%20file" in called_url
        assert " " not in called_url.split("?")[0]  # no raw spaces in path


class TestProjectLoaderDynamic:
    def test_load_dynamic_with_keys(self):
        data = {"prompt": "hello", "seed": 42, "cfg": 1.5}
        node = ProjectLoaderDynamic()
        with patch("project_loader._fetch_data", return_value=data):
            result = node.load_dynamic(
                "http://localhost:8080", "proj1", "batch_i2v", 1,
                output_keys="prompt,seed,cfg"
            )
        assert result[0] == "hello"
        assert result[1] == 42
        assert result[2] == 1.5
        assert len(result) == MAX_DYNAMIC_OUTPUTS

    def test_load_dynamic_with_json_encoded_keys(self):
        """JSON-encoded output_keys should be parsed correctly."""
        import json as _json
        data = {"my,key": "comma_val", "normal": "ok"}
        node = ProjectLoaderDynamic()
        keys_json = _json.dumps(["my,key", "normal"])
        with patch("project_loader._fetch_data", return_value=data):
            result = node.load_dynamic(
                "http://localhost:8080", "proj1", "batch_i2v", 1,
                output_keys=keys_json
            )
        assert result[0] == "comma_val"
        assert result[1] == "ok"

    def test_load_dynamic_type_coercion(self):
        """output_types should coerce values to declared types."""
        import json as _json
        data = {"seed": "42", "cfg": "1.5", "prompt": "hello"}
        node = ProjectLoaderDynamic()
        keys_json = _json.dumps(["seed", "cfg", "prompt"])
        types_json = _json.dumps(["INT", "FLOAT", "STRING"])
        with patch("project_loader._fetch_data", return_value=data):
            result = node.load_dynamic(
                "http://localhost:8080", "proj1", "batch_i2v", 1,
                output_keys=keys_json, output_types=types_json
            )
        assert result[0] == 42       # string "42" coerced to int
        assert result[1] == 1.5      # string "1.5" coerced to float
        assert result[2] == "hello"  # string stays string

    def test_load_dynamic_empty_keys(self):
        node = ProjectLoaderDynamic()
        with patch("project_loader._fetch_data", return_value={"prompt": "hello"}):
            result = node.load_dynamic(
                "http://localhost:8080", "proj1", "batch_i2v", 1,
                output_keys=""
            )
        assert all(v == "" for v in result)

    def test_load_dynamic_missing_key(self):
        node = ProjectLoaderDynamic()
        with patch("project_loader._fetch_data", return_value={"prompt": "hello"}):
            result = node.load_dynamic(
                "http://localhost:8080", "proj1", "batch_i2v", 1,
                output_keys="nonexistent"
            )
        assert result[0] == ""

    def test_load_dynamic_bool_becomes_string(self):
        node = ProjectLoaderDynamic()
        with patch("project_loader._fetch_data", return_value={"flag": True}):
            result = node.load_dynamic(
                "http://localhost:8080", "proj1", "batch_i2v", 1,
                output_keys="flag"
            )
        assert result[0] == "true"

    def test_input_types_has_manager_url(self):
        inputs = ProjectLoaderDynamic.INPUT_TYPES()
        assert "manager_url" in inputs["required"]
        assert "project_name" in inputs["required"]
        assert "file_name" in inputs["required"]
        assert "sequence_number" in inputs["required"]

    def test_category(self):
        assert ProjectLoaderDynamic.CATEGORY == "utils/json/project"


class TestProjectLoaderStandard:
    def test_load_standard(self):
        data = {
            "general_prompt": "hello",
            "general_negative": "bad",
            "current_prompt": "specific",
            "negative": "neg",
            "camera": "pan",
            "flf": 0.5,
            "seed": 42,
            "video file path": "/v.mp4",
            "reference image path": "/r.png",
            "flf image path": "/f.png",
        }
        node = ProjectLoaderStandard()
        with patch("project_loader._fetch_data", return_value=data):
            result = node.load_standard("http://localhost:8080", "proj1", "batch", 1)
        assert result == ("hello", "bad", "specific", "neg", "pan", 0.5, 42, "/v.mp4", "/r.png", "/f.png")

    def test_load_standard_defaults(self):
        node = ProjectLoaderStandard()
        with patch("project_loader._fetch_data", return_value={}):
            result = node.load_standard("http://localhost:8080", "proj1", "batch", 1)
        assert result[0] == ""  # general_prompt
        assert result[5] == 0.0  # flf
        assert result[6] == 0  # seed


class TestProjectLoaderVACE:
    def test_load_vace(self):
        data = {
            "general_prompt": "hello",
            "general_negative": "bad",
            "current_prompt": "specific",
            "negative": "neg",
            "camera": "pan",
            "flf": 0.5,
            "seed": 42,
            "frame_to_skip": 81,
            "input_a_frames": 16,
            "input_b_frames": 16,
            "reference path": "/ref",
            "reference switch": 1,
            "vace schedule": 2,
            "video file path": "/v.mp4",
            "reference image path": "/r.png",
        }
        node = ProjectLoaderVACE()
        with patch("project_loader._fetch_data", return_value=data):
            result = node.load_vace("http://localhost:8080", "proj1", "batch", 1)
        assert result[7] == 81  # frame_to_skip
        assert result[12] == 2  # vace_schedule


class TestProjectLoaderLoRA:
    def test_load_loras(self):
        data = {
            "lora 1 high": "<lora:model1:1.0>",
            "lora 1 low": "<lora:model1:0.5>",
            "lora 2 high": "",
            "lora 2 low": "",
            "lora 3 high": "",
            "lora 3 low": "",
        }
        node = ProjectLoaderLoRA()
        with patch("project_loader._fetch_data", return_value=data):
            result = node.load_loras("http://localhost:8080", "proj1", "batch", 1)
        assert result[0] == "<lora:model1:1.0>"
        assert result[1] == "<lora:model1:0.5>"

    def test_load_loras_empty(self):
        node = ProjectLoaderLoRA()
        with patch("project_loader._fetch_data", return_value={}):
            result = node.load_loras("http://localhost:8080", "proj1", "batch", 1)
        assert all(v == "" for v in result)


class TestNodeMappings:
    def test_mappings_exist(self):
        from project_loader import PROJECT_NODE_CLASS_MAPPINGS, PROJECT_NODE_DISPLAY_NAME_MAPPINGS
        assert "ProjectLoaderDynamic" in PROJECT_NODE_CLASS_MAPPINGS
        assert "ProjectLoaderStandard" in PROJECT_NODE_CLASS_MAPPINGS
        assert "ProjectLoaderVACE" in PROJECT_NODE_CLASS_MAPPINGS
        assert "ProjectLoaderLoRA" in PROJECT_NODE_CLASS_MAPPINGS
        assert len(PROJECT_NODE_DISPLAY_NAME_MAPPINGS) == 4
