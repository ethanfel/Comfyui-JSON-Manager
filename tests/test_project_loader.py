import json
from unittest.mock import patch, MagicMock
from io import BytesIO

import pytest

from project_loader import (
    ProjectLoaderDynamic,
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

    def test_fetch_json_network_error(self):
        with patch("project_loader.urllib.request.urlopen", side_effect=OSError("connection refused")):
            result = _fetch_json("http://example.com/api")
        assert result["error"] == "network_error"
        assert "connection refused" in result["message"]

    def test_fetch_json_http_error(self):
        import urllib.error
        err = urllib.error.HTTPError(
            "http://example.com/api", 404, "Not Found", {},
            BytesIO(json.dumps({"detail": "Project 'x' not found"}).encode())
        )
        with patch("project_loader.urllib.request.urlopen", side_effect=err):
            result = _fetch_json("http://example.com/api")
        assert result["error"] == "http_error"
        assert result["status"] == 404
        assert "not found" in result["message"].lower()

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
    def _keys_meta(self, total=5):
        return {"keys": [], "types": [], "total_sequences": total}

    def test_load_dynamic_with_keys(self):
        data = {"prompt": "hello", "seed": 42, "cfg": 1.5}
        node = ProjectLoaderDynamic()
        with patch("project_loader._fetch_keys", return_value=self._keys_meta()):
            with patch("project_loader._fetch_data", return_value=data):
                result = node.load_dynamic(
                    "http://localhost:8080", "proj1", "batch_i2v", 1,
                    output_keys="prompt,seed,cfg"
                )
        assert result[0] == 5  # total_sequences
        assert result[1] == "hello"
        assert result[2] == 42
        assert result[3] == 1.5
        assert len(result) == MAX_DYNAMIC_OUTPUTS + 1

    def test_load_dynamic_with_json_encoded_keys(self):
        """JSON-encoded output_keys should be parsed correctly."""
        import json as _json
        data = {"my,key": "comma_val", "normal": "ok"}
        node = ProjectLoaderDynamic()
        keys_json = _json.dumps(["my,key", "normal"])
        with patch("project_loader._fetch_keys", return_value=self._keys_meta()):
            with patch("project_loader._fetch_data", return_value=data):
                result = node.load_dynamic(
                    "http://localhost:8080", "proj1", "batch_i2v", 1,
                    output_keys=keys_json
                )
        assert result[1] == "comma_val"
        assert result[2] == "ok"

    def test_load_dynamic_type_coercion(self):
        """output_types should coerce values to declared types."""
        import json as _json
        data = {"seed": "42", "cfg": "1.5", "prompt": "hello"}
        node = ProjectLoaderDynamic()
        keys_json = _json.dumps(["seed", "cfg", "prompt"])
        types_json = _json.dumps(["INT", "FLOAT", "STRING"])
        with patch("project_loader._fetch_keys", return_value=self._keys_meta()):
            with patch("project_loader._fetch_data", return_value=data):
                result = node.load_dynamic(
                    "http://localhost:8080", "proj1", "batch_i2v", 1,
                    output_keys=keys_json, output_types=types_json
                )
        assert result[1] == 42       # string "42" coerced to int
        assert result[2] == 1.5      # string "1.5" coerced to float
        assert result[3] == "hello"  # string stays string

    def test_load_dynamic_empty_keys(self):
        node = ProjectLoaderDynamic()
        with patch("project_loader._fetch_keys", return_value=self._keys_meta()):
            with patch("project_loader._fetch_data", return_value={"prompt": "hello"}):
                result = node.load_dynamic(
                    "http://localhost:8080", "proj1", "batch_i2v", 1,
                    output_keys=""
                )
        # Slot 0 is total_sequences (INT), rest are empty strings
        assert result[0] == 5
        assert all(v == "" for v in result[1:])

    def test_load_dynamic_missing_key(self):
        node = ProjectLoaderDynamic()
        with patch("project_loader._fetch_keys", return_value=self._keys_meta()):
            with patch("project_loader._fetch_data", return_value={"prompt": "hello"}):
                result = node.load_dynamic(
                    "http://localhost:8080", "proj1", "batch_i2v", 1,
                    output_keys="nonexistent"
                )
        assert result[1] == ""

    def test_load_dynamic_bool_becomes_string(self):
        node = ProjectLoaderDynamic()
        with patch("project_loader._fetch_keys", return_value=self._keys_meta()):
            with patch("project_loader._fetch_data", return_value={"flag": True}):
                result = node.load_dynamic(
                    "http://localhost:8080", "proj1", "batch_i2v", 1,
                    output_keys="flag"
                )
        assert result[1] == "true"

    def test_load_dynamic_returns_total_sequences(self):
        """total_sequences should be the first output from keys metadata."""
        node = ProjectLoaderDynamic()
        with patch("project_loader._fetch_keys", return_value={"keys": [], "types": [], "total_sequences": 42}):
            with patch("project_loader._fetch_data", return_value={}):
                result = node.load_dynamic(
                    "http://localhost:8080", "proj1", "batch_i2v", 1,
                    output_keys=""
                )
        assert result[0] == 42

    def test_load_dynamic_raises_on_network_error(self):
        """Network errors from _fetch_keys should raise RuntimeError."""
        node = ProjectLoaderDynamic()
        error_resp = {"error": "network_error", "message": "Connection refused"}
        with patch("project_loader._fetch_keys", return_value=error_resp):
            with pytest.raises(RuntimeError, match="Failed to fetch project keys"):
                node.load_dynamic("http://localhost:8080", "proj1", "batch", 1)

    def test_load_dynamic_raises_on_data_fetch_error(self):
        """Network errors from _fetch_data should raise RuntimeError."""
        node = ProjectLoaderDynamic()
        error_resp = {"error": "http_error", "status": 404, "message": "Sequence not found"}
        with patch("project_loader._fetch_keys", return_value=self._keys_meta()):
            with patch("project_loader._fetch_data", return_value=error_resp):
                with pytest.raises(RuntimeError, match="Failed to fetch sequence data"):
                    node.load_dynamic("http://localhost:8080", "proj1", "batch", 1)

    def test_input_types_has_manager_url(self):
        inputs = ProjectLoaderDynamic.INPUT_TYPES()
        assert "manager_url" in inputs["required"]
        assert "project_name" in inputs["required"]
        assert "file_name" in inputs["required"]
        assert "sequence_number" in inputs["required"]

    def test_category(self):
        assert ProjectLoaderDynamic.CATEGORY == "JSON Manager/project"


class TestProjectSource:
    def test_input_types(self):
        from project_loader import ProjectSource
        inputs = ProjectSource.INPUT_TYPES()
        assert "manager_url" in inputs["required"]
        assert "project_name" in inputs["required"]
        assert "file_name" in inputs["required"]
        assert "sequence_number" in inputs["required"]
        assert "label" in inputs["required"]

    def test_outputs_sequence_number(self):
        from project_loader import ProjectSource
        assert ProjectSource.RETURN_TYPES == ("INT", "STRING",)
        assert ProjectSource.RETURN_NAMES == ("sequence_number", "file_name",)

    def test_hold_config_returns_sequence_number(self):
        from project_loader import ProjectSource
        node = ProjectSource()
        result = node.hold_config(
            manager_url="http://localhost:8080",
            project_name="proj1",
            file_name="batch_i2v",
            sequence_number=42,
            label="my_source"
        )
        assert result == (42, "batch_i2v")

    def test_category(self):
        from project_loader import ProjectSource
        assert ProjectSource.CATEGORY == "JSON Manager/project"


class TestProjectKey:
    def test_input_types(self):
        from project_loader import ProjectKey
        inputs = ProjectKey.INPUT_TYPES()
        assert "source_label" in inputs["required"]
        assert "key_name" in inputs["required"]
        assert "key_type" in inputs["required"]

    def test_single_output(self):
        from project_loader import ProjectKey
        assert len(ProjectKey.RETURN_TYPES) == 1
        assert len(ProjectKey.RETURN_NAMES) == 1

    def test_fetch_key_string(self):
        from project_loader import ProjectKey
        node = ProjectKey()
        data = {"prompt": "hello", "seed": 42}
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_key(
                source_label="my_source",
                key_name="prompt",
                key_type="STRING",
                manager_url="http://localhost:8080",
                project_name="proj1",
                file_name="batch_i2v",
                sequence_number=1,
            )
        assert result == ("hello",)

    def test_fetch_key_int_coercion(self):
        from project_loader import ProjectKey
        node = ProjectKey()
        data = {"seed": "42"}
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_key(
                source_label="my_source",
                key_name="seed",
                key_type="INT",
                manager_url="http://localhost:8080",
                project_name="proj1",
                file_name="batch_i2v",
                sequence_number=1,
            )
        assert result == (42,)

    def test_fetch_key_float_coercion(self):
        from project_loader import ProjectKey
        node = ProjectKey()
        data = {"cfg": "1.5"}
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_key(
                source_label="my_source",
                key_name="cfg",
                key_type="FLOAT",
                manager_url="http://localhost:8080",
                project_name="proj1",
                file_name="batch_i2v",
                sequence_number=1,
            )
        assert result == (1.5,)

    def test_fetch_key_missing_key(self):
        from project_loader import ProjectKey
        node = ProjectKey()
        with patch("project_loader._fetch_data", return_value={}):
            result = node.fetch_key(
                source_label="my_source",
                key_name="nonexistent",
                key_type="STRING",
                manager_url="http://localhost:8080",
                project_name="proj1",
                file_name="batch_i2v",
                sequence_number=1,
            )
        assert result == ("",)

    def test_fetch_key_network_error_returns_default(self):
        from project_loader import ProjectKey
        node = ProjectKey()
        error_resp = {"error": "network_error", "message": "Connection refused"}
        with patch("project_loader._fetch_data", return_value=error_resp):
            result = node.fetch_key(
                source_label="my_source",
                key_name="prompt",
                key_type="STRING",
                manager_url="http://localhost:8080",
                project_name="proj1",
                file_name="batch_i2v",
                sequence_number=1,
            )
        assert result == ("",)

    def test_fetch_key_error_returns_int_default(self):
        from project_loader import ProjectKey
        node = ProjectKey()
        error_resp = {"error": "http_error", "status": 404, "message": "Not found"}
        with patch("project_loader._fetch_data", return_value=error_resp):
            result = node.fetch_key(
                source_label="s", key_name="seed", key_type="INT",
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (0,)

    def test_category(self):
        from project_loader import ProjectKey
        assert ProjectKey.CATEGORY == "JSON Manager/project"


class TestProjectResolution:
    def test_input_types(self):
        from project_loader import ProjectResolution
        inputs = ProjectResolution.INPUT_TYPES()
        assert "source_label" in inputs["required"]
        assert "key_name" in inputs["required"]
        assert "index" in inputs["required"]
        assert inputs["required"]["index"][0] == "INT"

    def test_three_outputs(self):
        from project_loader import ProjectResolution
        assert ProjectResolution.RETURN_TYPES == ("INT", "INT", "INT")
        assert ProjectResolution.RETURN_NAMES == ("width", "height", "seed")

    def test_fetch_resolution_basic(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        data = {"resolutions": [[512, 512, 0], [768, 1344, 12345], [1344, 768, 99]]}
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_resolution(
                source_label="src", key_name="resolutions", index=1,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (768, 1344, 12345)

    def test_fetch_resolution_index_zero(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        data = {"resolutions": [[512, 512, 42], [1024, 1024, 0]]}
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_resolution(
                source_label="src", key_name="resolutions", index=0,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (512, 512, 42)

    def test_fetch_resolution_clamps_on_out_of_bounds(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        data = {"resolutions": [[512, 512, 0], [1024, 1024, 7]]}
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_resolution(
                source_label="src", key_name="resolutions", index=99,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (1024, 1024, 7)  # last entry

    def test_fetch_resolution_old_format_no_seed(self):
        """Old [w, h] entries without seed should return seed=0."""
        from project_loader import ProjectResolution
        node = ProjectResolution()
        data = {"resolutions": [[576, 384], [960, 640]]}
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_resolution(
                source_label="src", key_name="resolutions", index=0,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (576, 384, 0)

    def test_fetch_resolution_missing_key_returns_defaults(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        with patch("project_loader._fetch_data", return_value={}):
            result = node.fetch_resolution(
                source_label="src", key_name="nonexistent", index=0,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (512, 512, 0)

    def test_fetch_resolution_network_error_returns_defaults(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        error_resp = {"error": "network_error", "message": "Connection refused"}
        with patch("project_loader._fetch_data", return_value=error_resp):
            result = node.fetch_resolution(
                source_label="src", key_name="resolutions", index=0,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (512, 512, 0)

    def test_fetch_resolution_malformed_entry_returns_defaults(self):
        from project_loader import ProjectResolution
        node = ProjectResolution()
        data = {"resolutions": [[512]]}  # single-element, not a valid pair
        with patch("project_loader._fetch_data", return_value=data):
            result = node.fetch_resolution(
                source_label="src", key_name="resolutions", index=0,
                manager_url="http://localhost:8080", project_name="p",
                file_name="f", sequence_number=1,
            )
        assert result == (512, 512, 0)

    def test_category(self):
        from project_loader import ProjectResolution
        assert ProjectResolution.CATEGORY == "JSON Manager/project"


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


class TestNodeMappings:
    def test_mappings_exist(self):
        from project_loader import PROJECT_NODE_CLASS_MAPPINGS, PROJECT_NODE_DISPLAY_NAME_MAPPINGS
        assert "ProjectLoaderDynamic" in PROJECT_NODE_CLASS_MAPPINGS
        assert "ProjectSource" in PROJECT_NODE_CLASS_MAPPINGS
        assert "ProjectKey" in PROJECT_NODE_CLASS_MAPPINGS
        assert "ProjectResolution" in PROJECT_NODE_CLASS_MAPPINGS
        assert "BinaryIndexDecoder" in PROJECT_NODE_CLASS_MAPPINGS
        assert len(PROJECT_NODE_CLASS_MAPPINGS) == 5
        assert len(PROJECT_NODE_DISPLAY_NAME_MAPPINGS) == 5
