from __future__ import annotations

import pytest
from ai_engine.json_utils import strip_json_fence, parse_json_object

def test_strip_json_fence():
    assert strip_json_fence("```json\n{\"a\": 1}\n```") == "{\"a\": 1}"
    assert strip_json_fence("plain") == "plain"
    assert strip_json_fence("  ```\nfoo\n```  ") == "foo"

def test_parse_json_object_variants():
    # Simple dict
    assert parse_json_object('{"a": 1}') == {"a": 1}
    
    # Simple list
    assert parse_json_object('[1, 2]', list_key="items") == {"items": [1, 2]}
    
    # Embedded dict
    assert parse_json_object('Here is some text: {"foo": "bar"} and more') == {"foo": "bar"}
    
    # Embedded list
    assert parse_json_object('Look: [10, 20] end', list_key="vals") == {"vals": [10, 20]}
    
    # Trailing comma fix
    assert parse_json_object('{"a": 1,}') == {"a": 1}
    assert parse_json_object('[1, 2, ]', list_key="x") == {"x": [1, 2]}

def test_parse_json_object_fail():
    with pytest.raises(ValueError, match="Failed to parse resilient JSON"):
        parse_json_object("no json here")
