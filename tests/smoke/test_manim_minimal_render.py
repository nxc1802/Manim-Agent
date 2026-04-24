from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.mark.skipif(not shutil.which("manim"), reason="manim CLI not found")
def test_manim_minimal_render_cli(tmp_path: Path) -> None:
    """Smoke test: ensure manim can render a simple scene."""
    code = """
from manim import *
class SmokeScene(Scene):
    def construct(self):
        self.add(Circle())
        self.wait(0.1)
"""
    scene_file = tmp_path / "scene.py"
    scene_file.write_text(code)
    
    media_dir = tmp_path / "media"
    
    cmd = [
        "manim",
        "render",
        "-ql",
        str(scene_file),
        "SmokeScene",
        "--media_dir",
        str(media_dir),
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, f"Manim failed: {res.stderr}"
    
    # Check if mp4 exists
    matches = list(media_dir.rglob("SmokeScene.mp4"))
    assert len(matches) > 0
    assert matches[0].stat().st_size > 0
