from __future__ import annotations

import pytest
import yaml
from pathlib import Path
from ai_engine.rag.api_registry import ManimAPIRegistry

@pytest.fixture
def registry_file(tmp_path):
    p = tmp_path / "registry.yaml"
    data = {
        "entries": [
            {
                "symbol": "Create",
                "module_path": "manim.animation.creation",
                "common_errors": [{"pattern": "ShowCreation", "fix": "Use Create"}]
            },
            {
                "symbol": "Scene.play",
                "module_path": "manim.scene.scene"
            }
        ],
        "deprecated_aliases": {
            "ShowCreation": "Create"
        }
    }
    p.write_text(yaml.dump(data))
    return p

def test_api_registry_load_fail():
    reg = ManimAPIRegistry(Path("non_existent.yaml"))
    assert reg._data == {"entries": [], "deprecated_aliases": {}}

def test_api_registry_lookup_method(registry_file):
    reg = ManimAPIRegistry(registry_file)
    # Match by full symbol
    assert reg.lookup_symbol("Scene.play")["symbol"] == "Scene.play"
    # Match by suffix
    assert reg.lookup_symbol("play")["symbol"] == "Scene.play"

def test_api_registry_find_similar(registry_file):
    reg = ManimAPIRegistry(registry_file)
    # entry_sym "create" in "CreateNew"
    sim = reg.find_similar("CreateNew")
    assert any(e["symbol"] == "Create" for e in sim)
    
    # Error pattern match
    sim2 = reg.find_similar("ShowCreation")
    assert any(e["symbol"] == "Create" for e in sim2)

def test_api_registry_resolve_error(registry_file):
    reg = ManimAPIRegistry(registry_file)
    assert reg.resolve_error("NameError", None) == []
    
    # Deprecated
    res = reg.resolve_error("NameError", "ShowCreation")
    assert res[0]["symbol"] == "Create"
    
    # Exact
    res2 = reg.resolve_error("NameError", "Create")
    assert res2[0]["symbol"] == "Create"
    
    # Fuzzy
    res3 = reg.resolve_error("AttributeError", "play")
    assert res3[0]["symbol"] == "Scene.play"
