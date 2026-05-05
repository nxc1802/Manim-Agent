import pytest
from ai_engine.rag.log_parser import parse_render_error
from ai_engine.rag.api_registry import ManimAPIRegistry
from ai_engine.rag.reviewer_context import build_reviewer_rag_context

def test_log_parser_attribute_error():
    logs = """
    File "scene.py", line 42, in construct
        self.play_text("Hello")
    AttributeError: 'GeneratedScene' object has no attribute 'play_text'
    """
    parsed = parse_render_error(logs)
    assert parsed.error_type == "AttributeError"
    assert parsed.symbol == "play_text"
    assert parsed.line_number == 42

def test_log_parser_name_error():
    logs = """
    File "scene.py", line 10, in construct
        circle = ShowCreation(Circle())
    NameError: name 'ShowCreation' is not defined
    """
    parsed = parse_render_error(logs)
    assert parsed.error_type == "NameError"
    assert parsed.symbol == "ShowCreation"

def test_api_registry_deprecated():
    registry = ManimAPIRegistry()
    dep = registry.lookup_deprecated("ShowCreation")
    assert dep is not None
    assert dep[0] == "Create"
    assert dep[1]["symbol"] == "Create"

def test_api_registry_exact():
    registry = ManimAPIRegistry()
    entry = registry.lookup_symbol("Text")
    assert entry is not None
    assert "text_mobject" in entry["module_path"]

def test_reviewer_context_building():
    logs = "NameError: name 'ShowCreation' is not defined"
    context = build_reviewer_rag_context(logs)
    assert context is not None
    assert "ShowCreation" in context
    assert "DEPRECATED" in context
    assert "Create" in context

if __name__ == "__main__":
    # Manual run if needed
    pass
