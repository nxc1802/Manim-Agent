from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from ai_engine.piper_config import load_piper_runtime_config


def test_piper_synthesis_smoke(tmp_path: Path) -> None:
    """Smoke test: ensure piper can synthesize audio."""
    try:
        cfg = load_piper_runtime_config()
    except Exception as e:
        pytest.skip(f"Piper config could not be loaded: {e}")
        
    if not shutil.which(cfg.binary):
        pytest.skip(f"Piper binary {cfg.binary} not found")
    
    if not cfg.voice_model_path or not Path(cfg.voice_model_path).is_file():
        pytest.skip(f"Piper voice model {cfg.voice_model_path} not found")
        
    out_wav = tmp_path / "output.wav"
    text = "Hello world"
    
    cmd = [
        cfg.binary,
        "--model",
        cfg.voice_model_path,
        "--output_file",
        str(out_wav),
        "--noise_scale",
        str(cfg.noise_scale),
        "--length_scale",
        str(cfg.length_scale),
        "--sentence_silence",
        str(cfg.sentence_silence),
    ]
    
    # Piper reads from stdin
    try:
        res = subprocess.run(
            cmd,
            input=text,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8"
        )
    except subprocess.TimeoutExpired:
        pytest.fail("Piper synthesis timed out")
        
    assert res.returncode == 0, f"Piper failed: {res.stderr}"
    assert out_wav.exists()
    assert out_wav.stat().st_size > 0
