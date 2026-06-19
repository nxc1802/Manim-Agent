from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from backend.main import app
from fastapi.testclient import TestClient


def test_websocket_ping_pong() -> None:
    client = TestClient(app)
    scene_id = str(uuid4())

    with patch("backend.core.websocket_manager.redis.from_url") as mock_from_url:
        mock_redis = AsyncMock()
        mock_from_url.return_value = mock_redis

        with client.websocket_connect(f"/v1/ws/{scene_id}") as websocket:
            websocket.send_text("ping")
            data = websocket.receive_text()
            assert data == "pong"
