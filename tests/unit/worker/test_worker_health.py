from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from worker.worker_health import app, _celery_argv
from unittest.mock import MagicMock, patch

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_celery_argv_default():
    with patch.dict(os.environ, {"WORKER_HEALTH_MODE": "render", "CELERY_LOG_LEVEL": "DEBUG"}):
        argv = _celery_argv()
        assert "render" in argv
        assert "--loglevel=DEBUG" in argv

def test_celery_argv_tts():
    with patch.dict(os.environ, {"WORKER_HEALTH_MODE": "tts"}):
        argv = _celery_argv()
        assert "tts" in argv

def test_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "worker": "running"}

def test_health_endpoint_success(client):
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    app.state.proc = mock_proc
    
    with patch("backend.services.redis_client.get_redis") as mock_redis:
        mock_redis.return_value.ping.return_value = True
        res = client.get("/health")
        assert res.status_code == 200
        assert "redis\": true" in res.text

def test_health_endpoint_redis_error(client):
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    app.state.proc = mock_proc
    
    from redis.exceptions import RedisError
    with patch("backend.services.redis_client.get_redis") as mock_redis:
        mock_redis.return_value.ping.side_effect = RedisError("redis down")
        res = client.get("/health")
        assert res.status_code == 503
        assert "redis\": false" in res.text

def test_health_endpoint_worker_dead(client):
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 1
    app.state.proc = mock_proc
    
    res = client.get("/health")
    assert res.status_code == 503
    assert "worker\": \"dead\"" in res.text

@pytest.mark.anyio
async def test_lifespan():
    from worker.worker_health import lifespan
    mock_app = MagicMock()
    
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        async with lifespan(mock_app):
            assert mock_app.state.proc == mock_proc
        
        assert mock_proc.terminate.called
