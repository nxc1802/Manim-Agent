from __future__ import annotations

from ai_engine.json_utils import parse_json_object, strip_json_fence


def test_strip_json_fence() -> None:
    raw = strip_json_fence('```json\n{"a": 1}\n```')
    assert raw == '{"a": 1}'


def test_parse_json_object() -> None:
    d = parse_json_object('{"x": true}')
    assert d["x"] is True
