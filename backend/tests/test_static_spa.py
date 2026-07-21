from pathlib import Path

from app.core.static_spa import mount_static_spa
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _spa_client(static_dir: Path) -> TestClient:
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<main>manim-spa</main>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('manim')", encoding="utf-8")

    app = FastAPI()

    @app.get("/v1/known")
    def known_api_route() -> dict[str, bool]:
        return {"ok": True}

    assert mount_static_spa(app, static_dir)
    return TestClient(app)


def test_spa_serves_assets_and_falls_back_for_browser_routes(tmp_path: Path) -> None:
    client = _spa_client(tmp_path)

    root = client.get("/")
    nested_route = client.get("/projects/example")
    asset = client.get("/assets/app.js")

    assert root.status_code == 200
    assert nested_route.status_code == 200
    assert nested_route.text == "<main>manim-spa</main>"
    assert nested_route.headers["cache-control"] == "no-cache"
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert asset.headers["x-content-type-options"] == "nosniff"


def test_spa_does_not_mask_api_or_missing_asset_404s(tmp_path: Path) -> None:
    client = _spa_client(tmp_path)

    assert client.get("/v1/known").json() == {"ok": True}
    assert client.get("/v1/missing").status_code == 404
    assert client.get("/internal/missing").status_code == 404
    assert client.get("/assets/missing.js").status_code == 404


def test_missing_spa_directory_keeps_api_only_mode(tmp_path: Path) -> None:
    app = FastAPI()

    assert not mount_static_spa(app, tmp_path)
    assert TestClient(app).get("/projects/example").status_code == 404
