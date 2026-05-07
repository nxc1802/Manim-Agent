from __future__ import annotations

import primitives
from backend.main import app
from fastapi.testclient import TestClient
from primitives.constants import CATALOG_VERSION
from primitives.registry import build_primitives_catalog, catalog_primitive_names
from shared.schemas.primitives_catalog import PrimitivesCatalogResponse


def test_export_all_matches_registry() -> None:
    exported = {n for n in primitives.__all__ if n != "CATALOG_VERSION"}
    assert exported == catalog_primitive_names()


def test_build_primitives_catalog_validates() -> None:
    model = build_primitives_catalog()
    assert model.version == CATALOG_VERSION
    assert len(model.primitives) == len(catalog_primitive_names())


def test_primitives_catalog_http_contract() -> None:
    client = TestClient(app)
    response = client.get("/v1/primitives/catalog")
    assert response.status_code == 200
    PrimitivesCatalogResponse.model_validate(response.json())
