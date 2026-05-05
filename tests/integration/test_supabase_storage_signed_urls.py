from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from backend.services.supabase_storage_rest import (
    sign_storage_object_read_url,
    upload_render_mp4_and_sign,
)


@pytest.fixture()
def mock_settings(monkeypatch):
    monkeypatch.setattr("backend.core.config.settings.supabase_url", "https://xyz.supabase.co")
    monkeypatch.setattr("backend.core.config.settings.supabase_service_role_key", "secret-key")
    monkeypatch.setattr("backend.core.config.settings.supabase_storage_bucket", "render-bucket")


def test_sign_storage_object_read_url(mock_settings) -> None:
    object_path = "project-1/job-2.mp4"

    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"signedURL": "https://signed-url.com/xyz"}
        mock_post.return_value = mock_response

        url = sign_storage_object_read_url(object_path=object_path)

        assert url == "https://signed-url.com/xyz"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert object_path in args[0]
        assert "Authorization" in kwargs["headers"]


def test_upload_render_mp4_and_sign(mock_settings, tmp_path: Path) -> None:
    video = tmp_path / "test.mp4"
    video.write_bytes(b"data")
    project_id = uuid4()
    job_id = uuid4()

    with patch("httpx.Client.post") as mock_post:
        # Mock 1: Upload (PostgREST/Storage usually returns empty or metadata)
        # Mock 2: Sign
        mock_upload = MagicMock(status_code=200)
        mock_sign = MagicMock(status_code=200)
        mock_sign.json.return_value = {"signedURL": "https://signed.com"}

        mock_post.side_effect = [mock_upload, mock_sign]

        url = upload_render_mp4_and_sign(video_path=video, project_id=project_id, job_id=job_id)

        assert url == "https://signed.com"
        assert mock_post.call_count == 2
