"""Load Piper CLI parameters from YAML (no env-based tuning)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]


@dataclass(frozen=True)
class PiperRuntimeConfig:
    binary: str
    voice_model_path: str
    noise_scale: float
    length_scale: float
    sentence_silence: float


def _config_dir() -> Path:
    return Path(__file__).resolve().parent / "config"


def default_piper_config_path() -> Path:
    """Bundled defaults when no ``piper.local.yaml`` exists."""
    return _config_dir() / "piper.example.yaml"


def resolve_piper_config_path() -> Path:
    """Use ``piper.local.yaml`` in ``ai_engine/config/`` when present (Docker / dev)."""
    d = _config_dir()
    local = d / "piper.local.yaml"
    if local.is_file():
        return local
    return default_piper_config_path()


def load_piper_runtime_config(path: Path | None = None) -> PiperRuntimeConfig:
    p = path or resolve_piper_config_path()
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"Invalid Piper YAML (expected mapping): {p}"
        raise ValueError(msg)
    data = cast(dict[str, Any], raw)
    return PiperRuntimeConfig(
        binary=str(data.get("binary") or "piper"),
        voice_model_path=str(data.get("voice_model_path") or ""),
        noise_scale=float(data.get("noise_scale", 0.667)),
        length_scale=float(data.get("length_scale", 1.0)),
        sentence_silence=float(data.get("sentence_silence", 0.25)),
    )
