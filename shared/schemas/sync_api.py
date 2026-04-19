from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from shared.schemas.scene import Scene


class SyncEngineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene: Scene
    sync_segments: dict[str, Any] | list[Any]
