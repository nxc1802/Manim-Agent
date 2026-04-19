from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("psycopg")
import psycopg  # noqa: E402


@pytest.fixture(scope="module")
def _rls_schema_applied() -> None:
    dsn = os.environ.get("POSTGRES_RLS_TEST_URL", "").strip()
    if not dsn:
        pytest.skip("POSTGRES_RLS_TEST_URL not set")
    sql_path = Path(__file__).resolve().parents[1] / "fixtures" / "postgres_rls_ci.sql"
    sql = sql_path.read_text(encoding="utf-8")
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql)


@pytest.mark.usefixtures("_rls_schema_applied")
@pytest.mark.integration
def test_rls_user_a_cannot_select_user_b_project() -> None:
    dsn = os.environ["POSTGRES_RLS_TEST_URL"].strip()
    user_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    project_b = UUID("22222222-2222-2222-2222-222222222222")
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('app.jwt_sub', %s, true)", (user_a,))
            n = conn.execute(
                "SELECT count(*) FROM public.projects WHERE id = %s",
                (str(project_b),),
            ).fetchone()
            assert n is not None
            assert int(n[0]) == 0


@pytest.mark.usefixtures("_rls_schema_applied")
@pytest.mark.integration
def test_rls_user_b_cannot_insert_project_for_user_a() -> None:
    dsn = os.environ["POSTGRES_RLS_TEST_URL"].strip()
    user_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    user_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('app.jwt_sub', %s, true)", (user_b,))
            with pytest.raises(psycopg.Error):
                conn.execute(
                    "INSERT INTO public.projects (user_id, title, status) VALUES (%s, %s, %s)",
                    (user_a, "evil", "draft"),
                )
