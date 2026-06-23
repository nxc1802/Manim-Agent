from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

from backend.core.config import settings
from backend.db.content_store import RedisContentStore, get_content_store
from backend.services.redis_client import get_redis
from shared.schemas.artifact_version import ArtifactVersion


def test_get_content_store(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "supabase_url", "")
    store = get_content_store()
    assert isinstance(store, RedisContentStore)


def test_redis_content_store_project() -> None:
    mock_redis = MagicMock()
    store = RedisContentStore(mock_redis)
    pid = uuid4()
    uid = uuid4()

    # Create
    mock_redis.get.return_value = None
    proj = store.create_project(
        project_id=pid, user_id=uid, title="Test", description="desc", source_language="en"
    )
    assert proj.id == pid
    assert mock_redis.set.called


def test_redis_content_store_scene() -> None:
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


def test_resolve_asset_local_path() -> None:
    mock_redis = MagicMock()
    store = RedisContentStore(mock_redis)
    assert store.resolve_asset_local_path(None) is None
    assert store.resolve_asset_local_path("http://remote.com/a.jpg") is None

    import tempfile

    with tempfile.NamedTemporaryFile() as tf:
        resolved = store.resolve_asset_local_path(f"file://{tf.name}")
        assert resolved == Path(tf.name)


def test_redis_content_store_artifact_versions() -> None:
    store = RedisContentStore(get_redis())
    entity_id = uuid4()
    first = ArtifactVersion(
        entity_type="dsl",
        entity_id=entity_id,
        version=1,
        content_hash="hash-1",
        content={"title": "one"},
        created_by="test",
    )
    second = first.model_copy(update={"id": uuid4(), "version": 2, "content_hash": "hash-2"})

    store.save_artifact_version(first)
    store.save_artifact_version(second)

    assert store.get_artifact_version("dsl", entity_id, 1) == first
    assert [item.version for item in store.list_artifact_versions("dsl", entity_id)] == [2, 1]
