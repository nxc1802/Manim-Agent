from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.core.config import settings
from backend.main import app
from fastapi.testclient import TestClient


def test_websocket_ping_pong() -> None:
    client = TestClient(app)
    scene_id = str(uuid4())

    store = MagicMock()
    store.get_scene.return_value = MagicMock(project_id=uuid4())
    store.get_project.return_value = MagicMock(user_id=settings.dev_default_user_id)

    with (
        patch("backend.core.websocket_manager.redis.from_url") as mock_from_url,
        patch("backend.api.v1.ws.get_content_store", return_value=store),
    ):
        mock_redis = AsyncMock()
        mock_from_url.return_value = mock_redis

        with client.websocket_connect(f"/v1/ws/{scene_id}") as websocket:
            websocket.send_text("ping")
            data = websocket.receive_text()
            assert data == "pong"
