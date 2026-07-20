from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from shared.schemas.scene import Scene


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def scene_render_source(scene: Scene) -> dict[str, Any]:
    """Describe the approved code revision a scene render is allowed to publish."""
    code = scene.manim_code or ""
    payload = {
        "kind": "scene",
        "scene_id": str(scene.id),
        "generation_status": scene.generation_status,
        "manim_code_version": scene.manim_code_version,
        "manim_code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
    }
    return {"source_fingerprint": _fingerprint(payload), "source_snapshot": payload}


def project_render_source(scenes: Iterable[Scene]) -> dict[str, Any]:
    """Describe the exact ordered scene sources used by a final project render."""
    ordered_scenes = sorted(scenes, key=lambda scene: (scene.scene_order, str(scene.id)))
    payload = {
        "kind": "full_project",
        "scenes": [
            {
                "scene_id": str(scene.id),
                "scene_order": scene.scene_order,
                "generation_status": scene.generation_status,
                "manim_code_version": scene.manim_code_version,
                "manim_code_sha256": hashlib.sha256(
                    (scene.manim_code or "").encode("utf-8")
                ).hexdigest(),
                "voice_script_sha256": hashlib.sha256(
                    (scene.voice_script or "").encode("utf-8")
                ).hexdigest(),
            }
            for scene in ordered_scenes
        ],
    }
    return {"source_fingerprint": _fingerprint(payload), "source_snapshot": payload}


def job_source_fingerprint(metadata: dict[str, Any] | None) -> str:
    value = (metadata or {}).get("source_fingerprint")
    return value if isinstance(value, str) and value else "legacy"
