from __future__ import annotations

from pathlib import Path

from app.api.v1 import internal as internal_api
from app.api.v1 import ws as ws_api
from app.main import app
from starlette.routing import WebSocketRoute


def test_public_openapi_surface_is_intentional() -> None:
    """Prevent public routes from drifting away from the Frontend contract."""
    expected = {
        ("GET", "/health"),
        ("GET", "/ready"),
        ("GET", "/v1/jobs/{job_id}"),
        ("GET", "/v1/jobs/{job_id}/signed-video-url"),
        ("GET", "/v1/jobs/{job_id}/video"),
        ("GET", "/v1/projects"),
        ("POST", "/v1/projects"),
        ("GET", "/v1/projects/stats"),
        ("DELETE", "/v1/projects/{project_id}"),
        ("GET", "/v1/projects/{project_id}"),
        ("GET", "/v1/projects/{project_id}/ai-runs"),
        ("POST", "/v1/projects/{project_id}/ai-runs"),
        ("POST", "/v1/projects/{project_id}/ai-runs/{run_id}/rollback"),
        ("GET", "/v1/projects/{project_id}/ai-runs/{run_id}/steps"),
        ("PATCH", "/v1/projects/{project_id}/ai-runs/{run_id}/steps/{step_id}"),
        ("POST", "/v1/projects/{project_id}/ai-runs/{run_id}/steps/{step_id}/approve"),
        ("POST", "/v1/projects/{project_id}/ai-runs/{run_id}/steps/{step_id}/reject"),
        ("POST", "/v1/projects/{project_id}/generate-scenes"),
        ("POST", "/v1/projects/{project_id}/render"),
        ("GET", "/v1/projects/{project_id}/render-jobs"),
        ("GET", "/v1/projects/{project_id}/rendered-video"),
        ("GET", "/v1/projects/{project_id}/rendered-video-url"),
        ("GET", "/v1/projects/{project_id}/scenes"),
        ("GET", "/v1/users/me/settings"),
        ("PATCH", "/v1/users/me/settings"),
    }
    methods = {"get", "post", "patch", "put", "delete"}
    actual = {
        (method.upper(), path)
        for path, definition in app.openapi()["paths"].items()
        for method in definition
        if method in methods
    }

    assert actual == expected


def test_internal_worker_and_websocket_surfaces_are_exact() -> None:
    expected_internal = {
        ("POST", "/internal/hitl-steps/{step_id}/claim"),
        ("POST", "/internal/hitl-steps/{step_id}/stream"),
        ("POST", "/internal/hitl-steps/{step_id}/complete"),
        ("POST", "/internal/hitl-steps/{step_id}/fail"),
        ("POST", "/internal/render-jobs/{job_id}/claim"),
        ("POST", "/internal/render-jobs/{job_id}/complete"),
        ("POST", "/internal/render-jobs/{job_id}/fail"),
    }
    actual_internal = {
        (method, f"/internal{route.path}")
        for route in internal_api.router.routes
        for method in (getattr(route, "methods", None) or set())
    }
    websocket_paths = {
        f"/v1{route.path}"
        for route in ws_api.router.routes
        if isinstance(route, WebSocketRoute)
    }

    assert actual_internal == expected_internal
    assert websocket_paths == {"/v1/ws/projects/{project_id}"}


def test_unused_dashboard_security_definer_rpc_is_removed() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    for schema in (
        backend_root / "supabase" / "init_schema.sql",
        backend_root / "supabase" / "migrations" / "20260219000000_init_schema.sql",
    ):
        assert "FUNCTION public.get_dashboard_stats" not in schema.read_text(encoding="utf-8")

    removal = (
        backend_root
        / "supabase"
        / "migrations"
        / "20260718000001_drop_legacy_dashboard_rpc.sql"
    ).read_text(encoding="utf-8")
    assert "DROP FUNCTION IF EXISTS public.get_dashboard_stats(UUID)" in removal
