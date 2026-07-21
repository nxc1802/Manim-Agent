from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("release_plan.py")
SPEC = importlib.util.spec_from_file_location("release_plan", MODULE_PATH)
assert SPEC and SPEC.loader
release_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_plan)


class ReleasePlanClassificationTests(unittest.TestCase):
    def classify(self, *paths: str):
        return release_plan.classify_files(paths)

    def test_frontend_runtime_deploys_only_vercel(self) -> None:
        plan = self.classify("frontend/src/App.tsx")
        self.assertEqual(
            plan["deploy"],
            {"supabase": False, "huggingface": False, "vercel": True},
        )
        self.assertTrue(plan["ci"]["frontend"])
        self.assertFalse(plan["ci"]["production_image"])

    def test_frontend_test_does_not_redeploy(self) -> None:
        plan = self.classify("frontend/src/lib/api.test.ts")
        self.assertFalse(any(plan["deploy"].values()))
        self.assertTrue(plan["ci"]["frontend"])

    def test_backend_runtime_deploys_only_huggingface(self) -> None:
        plan = self.classify("backend/app/main.py")
        self.assertEqual(
            plan["deploy"],
            {"supabase": False, "huggingface": True, "vercel": False},
        )
        self.assertTrue(plan["ci"]["backend"])
        self.assertTrue(plan["ci"]["production_image"])

    def test_dockerignore_is_a_huggingface_input(self) -> None:
        plan = self.classify(".dockerignore")
        self.assertTrue(plan["deploy"]["huggingface"])

    def test_shared_contract_deploys_huggingface_and_tests_python(self) -> None:
        plan = self.classify("shared/schemas/project.py")
        self.assertTrue(plan["deploy"]["huggingface"])
        self.assertTrue(plan["ci"]["backend"])
        self.assertTrue(plan["ci"]["ai_core"])

    def test_migration_is_database_only(self) -> None:
        plan = self.classify("backend/supabase/migrations/20260101000000_example.sql")
        self.assertEqual(
            plan["deploy"],
            {"supabase": True, "huggingface": False, "vercel": False},
        )
        self.assertTrue(plan["ci"]["migrations"])

    def test_docs_and_unit_tests_do_not_deploy(self) -> None:
        plan = self.classify("docs/CI_CD.md", "backend/tests/test_example.py")
        self.assertFalse(any(plan["deploy"].values()))
        self.assertTrue(plan["ci"]["backend"])

    def test_production_lock_is_hf_runtime_and_dependency_change(self) -> None:
        plan = self.classify("ai_core/requirements.lock")
        self.assertTrue(plan["deploy"]["huggingface"])
        self.assertTrue(plan["ci"]["dependency_audit"])
        self.assertTrue(plan["ci"]["python_dependency_audit"])
        self.assertFalse(plan["ci"]["frontend_dependency_audit"])

    def test_workflow_change_forces_ci_but_not_external_deployment(self) -> None:
        plan = self.classify(".github/workflows/ci.yml")
        self.assertFalse(any(plan["deploy"].values()))
        self.assertTrue(all(plan["ci"].values()))

    def test_mixed_change_targets_exact_services(self) -> None:
        plan = self.classify(
            "frontend/public/favicon.svg",
            "backend/app/api/v1/projects.py",
            "backend/supabase/postmigration_gate.sql",
        )
        self.assertTrue(all(plan["deploy"].values()))


class ReleaseBaselineTests(unittest.TestCase):
    HEAD = "2" * 40
    BASELINE = "1" * 40

    def test_missing_baseline_forces_first_deployment(self) -> None:
        needed, reason = release_plan.resolve_target(
            target="vercel", baseline=None, head_sha=self.HEAD
        )
        self.assertTrue(needed)
        self.assertIn("no successful", reason)

    @mock.patch.object(release_plan, "_git")
    @mock.patch.object(release_plan, "_is_ancestor")
    def test_newer_deployed_revision_prevents_rollback(self, is_ancestor, git) -> None:
        git.return_value = subprocess.CompletedProcess((), 0, "", "")
        is_ancestor.return_value = True
        needed, reason = release_plan.resolve_target(
            target="huggingface", baseline=self.BASELINE, head_sha=self.HEAD
        )
        self.assertFalse(needed)
        self.assertIn("already included", reason)

    @mock.patch.object(release_plan, "changed_files_between")
    @mock.patch.object(release_plan, "_git")
    @mock.patch.object(release_plan, "_is_ancestor")
    def test_docs_only_commit_carries_baseline_without_redeploy(
        self, is_ancestor, git, changed_files
    ) -> None:
        git.return_value = subprocess.CompletedProcess((), 0, "", "")
        is_ancestor.side_effect = [False, True]
        changed_files.return_value = ["docs/CI_CD.md"]
        needed, _ = release_plan.resolve_target(
            target="vercel", baseline=self.BASELINE, head_sha=self.HEAD
        )
        self.assertFalse(needed)

    @mock.patch.object(release_plan, "changed_files_between")
    @mock.patch.object(release_plan, "_git")
    @mock.patch.object(release_plan, "_is_ancestor")
    def test_undeployed_component_change_survives_later_docs_commit(
        self, is_ancestor, git, changed_files
    ) -> None:
        git.return_value = subprocess.CompletedProcess((), 0, "", "")
        is_ancestor.side_effect = [False, True]
        changed_files.return_value = ["frontend/src/App.tsx", "docs/CI_CD.md"]
        needed, _ = release_plan.resolve_target(
            target="vercel", baseline=self.BASELINE, head_sha=self.HEAD
        )
        self.assertTrue(needed)

    @mock.patch.object(release_plan, "_git")
    @mock.patch.object(release_plan, "_is_ancestor")
    def test_diverged_history_fails_safe_to_deploy(self, is_ancestor, git) -> None:
        git.return_value = subprocess.CompletedProcess((), 0, "", "")
        is_ancestor.side_effect = [False, False]
        needed, reason = release_plan.resolve_target(
            target="supabase", baseline=self.BASELINE, head_sha=self.HEAD
        )
        self.assertTrue(needed)
        self.assertIn("diverged", reason)

    def test_plan_head_mismatch_is_rejected(self) -> None:
        plan = {
            "schema_version": release_plan.PLAN_SCHEMA_VERSION,
            "head_sha": "3" * 40,
            "changed_files": [],
            "ci_target_coverage": {
                target: False for target in release_plan.TARGETS
            },
            "deploy": {target: False for target in release_plan.TARGETS},
            "ci": {
                "backend": False,
                "ai_core": False,
                "frontend": False,
                "migrations": False,
                "dependency_audit": False,
                "python_dependency_audit": False,
                "frontend_dependency_audit": False,
                "production_image": False,
                "workflow": False,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "plan.json")
            path.write_text(__import__("json").dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "head SHA"):
                release_plan.validate_plan(str(path), self.HEAD)

    @mock.patch.object(release_plan, "resolve_target")
    @mock.patch.object(release_plan.GitHubApi, "latest_successful_sha")
    def test_docs_push_covers_an_undeployed_frontend_change(
        self, latest_successful_sha, resolve_target
    ) -> None:
        latest_successful_sha.return_value = self.BASELINE
        resolve_target.side_effect = [
            (False, "database current"),
            (False, "runtime current"),
            (True, "frontend pending"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory, "plan.json")
            args = release_plan.build_parser().parse_args(
                [
                    "create",
                    "--base",
                    self.BASELINE,
                    "--head",
                    self.HEAD,
                    "--output",
                    str(plan_path),
                    "--file",
                    "docs/CI_CD.md",
                    "--cumulative-ci",
                    "--repository",
                    "owner/repository",
                ]
            )
            with mock.patch.dict(os.environ, {"GH_TOKEN": "test-token"}):
                self.assertEqual(args.handler(args), 0)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))

        self.assertFalse(plan["deploy"]["vercel"])
        self.assertTrue(plan["ci"]["frontend"])
        self.assertTrue(plan["ci"]["frontend_dependency_audit"])
        self.assertTrue(plan["ci_target_coverage"]["vercel"])

    def test_latest_successful_deployment_is_selected_by_id(self) -> None:
        older_sha = "a" * 40
        newer_sha = "b" * 40
        api = release_plan.GitHubApi(
            base_url="https://api.github.test",
            repository="owner/repository",
            token="test-token",
        )

        def request(_method: str, path: str, _body=None):
            if "/deployments?" in path:
                return [
                    {"id": 10, "sha": older_sha},
                    {"id": 20, "sha": newer_sha},
                ]
            if "/deployments/20/statuses" in path:
                return [{"id": 200, "state": "success"}]
            self.fail(f"unexpected API request: {path}")

        with mock.patch.object(api, "request", side_effect=request):
            self.assertEqual(api.latest_successful_sha("vercel"), newer_sha)

    @mock.patch.object(release_plan, "resolve_target", return_value=(True, "pending"))
    @mock.patch.object(
        release_plan.GitHubApi,
        "latest_successful_sha",
        return_value=BASELINE,
    )
    def test_resolver_rejects_a_target_without_ci_coverage(
        self, _latest_successful_sha, _resolve_target
    ) -> None:
        classified = release_plan.classify_files(["docs/CI_CD.md"])
        plan = {
            "schema_version": release_plan.PLAN_SCHEMA_VERSION,
            "base_sha": self.BASELINE,
            "head_sha": self.HEAD,
            "ci_target_coverage": {
                target: False for target in release_plan.TARGETS
            },
            **classified,
        }
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory, "plan.json")
            output_path = Path(directory, "github-output")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            args = release_plan.build_parser().parse_args(
                [
                    "resolve",
                    "--plan",
                    str(plan_path),
                    "--head",
                    self.HEAD,
                    "--repository",
                    "owner/repository",
                    "--github-output",
                    str(output_path),
                ]
            )
            with mock.patch.dict(os.environ, {"GH_TOKEN": "test-token"}):
                with self.assertRaisesRegex(RuntimeError, "does not cover"):
                    args.handler(args)


if __name__ == "__main__":
    unittest.main()
