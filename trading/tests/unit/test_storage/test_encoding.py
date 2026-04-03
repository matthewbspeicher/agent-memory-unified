"""Tests for storage/encoding.py JSON encoding/decoding utilities."""

import pytest

from storage.encoding import decode_json_column, decode_json_columns


class TestJsonEncoding:
    def test_decode_json_column_string(self):
        assert decode_json_column('{"key": "value"}') == {"key": "value"}

    def test_decode_json_column_none(self):
        assert decode_json_column(None) is None

    def test_decode_json_column_already_parsed(self):
        d = {"key": "value"}
        assert decode_json_column(d) is d

    def test_decode_json_column_list(self):
        lst = [1, 2, 3]
        assert decode_json_column(lst) is lst

    def test_decode_json_columns_mutates_row(self):
        row = {"name": "test", "parameters": '{"a": 1}', "universe": '["SPY"]'}
        result = decode_json_columns(row, ["parameters", "universe"])
        assert result["parameters"] == {"a": 1}
        assert result["universe"] == ["SPY"]
        assert result["name"] == "test"

    def test_decode_json_columns_invalid_json_fallback(self):
        row = {"params": "not-json"}
        result = decode_json_columns(row, ["params"], fallback={})
        assert result["params"] == {}

    def test_decode_json_columns_independent_fallbacks(self):
        row = {"a": None, "b": None}
        result = decode_json_columns(row, ["a", "b"], fallback={})
        result["a"]["key"] = "value"
        assert result["b"] == {}  # b should NOT have "key"
