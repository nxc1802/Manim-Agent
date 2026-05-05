from __future__ import annotations

from ai_engine.rag.log_parser import parse_render_error


def test_parse_render_error_variants():
    # Empty
    res = parse_render_error("")
    assert res.error_type == "UnknownError"

    # AttributeError
    logs = "File \"scene.py\", line 10\nAttributeError: 'Scene' object has no attribute 'play_text'"
    res = parse_render_error(logs)
    assert res.error_type == "AttributeError"
    assert res.symbol == "play_text"
    assert res.line_number == 10

    # NameError
    logs = "NameError: name 'ShowCreation' is not defined"
    res = parse_render_error(logs)
    assert res.error_type == "NameError"
    assert res.symbol == "ShowCreation"

    # TypeError
    logs = "TypeError: play() got an unexpected keyword argument 'run_time_extra'"
    res = parse_render_error(logs)
    assert res.error_type == "TypeError"
    assert res.symbol == "play"
    assert res.invalid_arg == "run_time_extra"

    # ImportError
    logs = "ImportError: cannot import name 'X' from 'Y'"
    res = parse_render_error(logs)
    assert res.error_type == "ImportError"
    assert res.symbol == "X"

    # ModuleNotFoundError
    logs = "ModuleNotFoundError: No module named 'scipy'"
    res = parse_render_error(logs)
    assert res.error_type == "ImportError"
    assert res.symbol == "scipy"

    # SyntaxError
    logs = "SyntaxError: invalid syntax"
    res = parse_render_error(logs)
    assert res.error_type == "SyntaxError"

    # LatexError
    logs = "LaTeX compilation error: Missing $ inserted"
    res = parse_render_error(logs)
    assert res.error_type == "LatexError"
    assert res.symbol == "LaTeX"

    # Generic Error
    logs = "ValueError: something went wrong"
    res = parse_render_error(logs)
    assert res.error_type == "ValueError"
