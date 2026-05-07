from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter
from primitives.registry import build_primitives_catalog
from shared.schemas.primitives_catalog import PrimitivesCatalogResponse

router = APIRouter(tags=["primitives"])


@lru_cache(maxsize=1)
def _get_cached_catalog() -> PrimitivesCatalogResponse:
    return build_primitives_catalog()


@router.get("/catalog", response_model=PrimitivesCatalogResponse, summary="Primitives catalog")
def get_primitives_catalog() -> PrimitivesCatalogResponse:
    """Read-only catalog for Builder prompts and tooling."""
    return _get_cached_catalog()
