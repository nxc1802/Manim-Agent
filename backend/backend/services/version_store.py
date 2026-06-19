from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from shared.schemas.artifact_version import ArtifactVersion

from backend.db.base import ContentStore

logger = logging.getLogger(__name__)


def compute_hash(content: Any) -> str:
    """Generate a stable SHA-256 hash of JSON-serializable content."""
    serialized = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class VersionStore:
    def __init__(self, store: ContentStore):
        self.store = store

    def list_versions(self, entity_type: str, entity_id: UUID) -> list[ArtifactVersion]:
        """List version history of an entity sorted by version number descending."""
        return self.store.list_artifact_versions(entity_type, entity_id)

    def get_version(self, entity_type: str, entity_id: UUID, version: int) -> ArtifactVersion | None:
        """Retrieve a specific version of an entity."""
        return self.store.get_artifact_version(entity_type, entity_id, version)

    def save_version(
        self,
        entity_type: str,
        entity_id: UUID,
        content: Any,
        created_by: str,
        parent_version: int | None = None,
    ) -> ArtifactVersion:
        """Create and persist a new auto-incremented version record for an entity."""
        existing = self.store.list_artifact_versions(entity_type, entity_id)
        next_version = 1
        if existing:
            next_version = max(v.version for v in existing) + 1

        content_hash = compute_hash(content)

        # Skip creating a duplicate version if the hash matches the most recent version
        if existing:
            latest = existing[0]  # ordered by version desc
            if latest.content_hash == content_hash:
                logger.info(
                    "Skipping duplicate version creation for %s:%s (already at version %d)",
                    entity_type,
                    entity_id,
                    latest.version,
                )
                return latest

        version_record = ArtifactVersion(
            id=uuid4(),
            entity_type=entity_type,
            entity_id=entity_id,
            version=next_version,
            content_hash=content_hash,
            content=content,
            parent_version=parent_version or (latest.version if existing else None),
            created_by=created_by,
        )

        self.store.save_artifact_version(version_record)
        logger.info(
            "Saved new version %d for %s:%s", next_version, entity_type, entity_id
        )
        return version_record

    def rollback(
        self,
        entity_type: str,
        entity_id: UUID,
        target_version: int,
        created_by: str,
    ) -> ArtifactVersion:
        """Roll back an entity to a target version, generating a new version record."""
        target = self.store.get_artifact_version(entity_type, entity_id, target_version)
        if not target:
            raise ValueError(
                f"Target version {target_version} not found for {entity_type}:{entity_id}"
            )

        # Create new version record carrying the target's content
        new_version = self.save_version(
            entity_type=entity_type,
            entity_id=entity_id,
            content=target.content,
            created_by=created_by,
            parent_version=target_version,
        )

        # Proactively update the active state in the scenes database table
        if entity_type == "storyboard":
            self.store.update_scene(entity_id, storyboard_text=target.content)
        elif entity_type == "plan":
            self.store.update_scene(entity_id, planner_output=target.content)
        elif entity_type == "dsl":
            self.store.update_scene(
                entity_id, scene_dsl=target.content, scene_dsl_version=new_version.version
            )
        elif entity_type == "code":
            self.store.update_scene(
                entity_id, manim_code=target.content, manim_code_version=new_version.version
            )
        else:
            raise ValueError(f"Unknown rollback entity type: {entity_type}")

        return new_version
