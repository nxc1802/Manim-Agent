from __future__ import annotations

import pytest
from uuid import uuid4
from pathlib import Path
from backend.db.content_store import get_content_store, RedisContentStore
from backend.core.config import settings
from shared.schemas.project import Project
from shared.schemas.scene import Scene
from unittest.mock import MagicMock

def test_get_content_store(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    store = get_content_store()
    assert isinstance(store, RedisContentStore)

def test_redis_content_store_project():
    mock_redis = MagicMock()
    store = RedisContentStore(mock_redis)
    pid = uuid4()
    uid = uuid4()
    
    # Create
    mock_redis.get.return_value = None
    proj = store.create_project(project_id=pid, user_id=uid, title="Test", description="desc", source_language="en")
    assert proj.id == pid
    assert mock_redis.set.called

def test_redis_content_store_scene():
    mock_redis = MagicMock()
    store = RedisContentStore(mock_redis)
    pid = uuid4()
    sid = uuid4()
    
    # Mock project exists for touch_project
    mock_redis.get.return_value = None
    
    # Create scene
    scene = store.create_scene(scene_id=sid, project_id=pid, scene_order=1)
    assert scene.id == sid
    assert mock_redis.rpush.called

def test_resolve_asset_local_path():
    mock_redis = MagicMock()
    store = RedisContentStore(mock_redis)
    assert store.resolve_asset_local_path(None) is None
    assert store.resolve_asset_local_path("http://remote.com/a.jpg") is None
    
    import tempfile
    with tempfile.NamedTemporaryFile() as tf:
        resolved = store.resolve_asset_local_path(f"file://{tf.name}")
        assert resolved == Path(tf.name)
