#!/usr/bin/env python3
"""Create and resolve deterministic monorepo CI/CD release plans.

The unprivileged CI workflow creates a per-push plan from the exact Git diff.
The privileged deployment workflow validates that artifact, then resolves each
target against its latest successful GitHub Deployment.  The second step is
what prevents an older, slower CI run from rolling a newer release back and
what carries an undeployed component change across later docs-only commits.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable


PLAN_SCHEMA_VERSION = 2
ZERO_SHA = "0" * 40
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TARGETS = ("supabase", "huggingface", "vercel")

# A production target is covered only when the CI run for the exact release
# revision plans every check below.  The deployment workflow consumes this
# evidence only after the stable CI Gate has succeeded.
TARGET_CI_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "supabase": ("migrations",),
    "huggingface": (
        "backend",
        "ai_core",
        "dependency_audit",
        "python_dependency_audit",
        "production_image",
    ),
    "vercel": (
        "frontend",
        "dependency_audit",
        "frontend_dependency_audit",
    ),
}

# Deployment paths describe production artifacts, not broad source folders.
# Tests, documentation, development locks, migrations and local tooling must
# not rebuild an unrelated external target.
DEPLOY_PATTERNS: dict[str, tuple[str, ...]] = {
    "supabase": (
        "backend/supabase/config.toml",
        "backend/supabase/migrations/**",
        "backend/supabase/postmigration_gate.sql",
    ),
    "huggingface": (
        ".dockerignore",
        "Dockerfile",
        "backend/app/**",
        "backend/requirements.lock",
        "ai_core/app/**",
        "ai_core/config/**",
        "ai_core/requirements.lock",
        "shared/**",
        "deploy/huggingface/**",
    ),
    "vercel": (
        "frontend/index.html",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/public/**",
        "frontend/src/**",
        "frontend/tsconfig.json",
        "frontend/tsconfig.app.json",
        "frontend/tsconfig.node.json",
        "frontend/vercel.json",
        "frontend/vite.config.ts",
        "deploy/vercel/**",
    ),
}

CI_CONTROL_PATTERNS = (
    ".github/workflows/ci.yml",
    "scripts/ci/**",
)


def _git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *arguments),
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def validate_sha(value: str, *, name: str) -> str:
    normalized = value.strip().lower()
    if not SHA_RE.fullmatch(normalized):
        raise ValueError(f"{name} must be a full lowercase 40-character Git SHA")
    return normalized


def path_matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def is_frontend_runtime_path(path: str) -> bool:
    if not path_matches(path, DEPLOY_PATTERNS["vercel"]):
        return False
    return not path.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))


def deployment_scope(path: str, target: str) -> bool:
    if target not in TARGETS:
        raise ValueError(f"unknown deployment target: {target}")
    if target == "vercel":
        return is_frontend_runtime_path(path)
    return path_matches(path, DEPLOY_PATTERNS[target])


def classify_files(changed_files: Iterable[str], *, force_all_ci: bool = False) -> dict[str, Any]:
    files = sorted(
        {
            normalized[2:] if normalized.startswith("./") else normalized
            for item in changed_files
            if (normalized := item.strip())
        }
    )
    control_changed = any(path_matches(path, CI_CONTROL_PATTERNS) for path in files)
    all_ci = force_all_ci or control_changed

    deploy = {
        target: any(deployment_scope(path, target) for path in files)
        for target in TARGETS
    }
    dependency_patterns = (
        "backend/requirements*.lock",
        "ai_core/requirements*.lock",
        "frontend/package.json",
        "frontend/package-lock.json",
    )
    python_dependency_patterns = (
        "backend/requirements*.lock",
        "ai_core/requirements*.lock",
    )
    frontend_dependency_patterns = (
        "frontend/package.json",
        "frontend/package-lock.json",
    )
    ci = {
        "backend": all_ci
        or any(path_matches(path, ("backend/**", "shared/**")) for path in files),
        "ai_core": all_ci
        or any(path_matches(path, ("ai_core/**", "shared/**")) for path in files),
        "frontend": all_ci or any(path_matches(path, ("frontend/**",)) for path in files),
        "migrations": all_ci
        or any(path_matches(path, ("backend/supabase/**",)) for path in files),
        "dependency_audit": all_ci
        or any(path_matches(path, dependency_patterns) for path in files),
        "python_dependency_audit": all_ci
        or any(path_matches(path, python_dependency_patterns) for path in files),
        "frontend_dependency_audit": all_ci
        or any(path_matches(path, frontend_dependency_patterns) for path in files),
        "production_image": all_ci or deploy["huggingface"],
        "workflow": all_ci
        or any(path_matches(path, (".github/workflows/**",)) for path in files),
    }
    return {"changed_files": files, "ci": ci, "deploy": deploy}


def changed_files_between(base_sha: str, head_sha: str) -> list[str]:
    head = validate_sha(head_sha, name="head SHA")
    _git("cat-file", "-e", f"{head}^{{commit}}")
    if base_sha == ZERO_SHA:
        output = _git("ls-tree", "-r", "--name-only", head).stdout
    else:
        base = validate_sha(base_sha, name="base SHA")
        _git("cat-file", "-e", f"{base}^{{commit}}")
        # Treat renames as a delete plus an add so both component paths remain
        # visible to the classifier.
        output = _git(
            "diff",
            "--no-renames",
            "--name-only",
            "--diff-filter=ACDMRTUXB",
            base,
            head,
        ).stdout
    return [line for line in output.splitlines() if line]


def write_github_outputs(path: str | None, values: dict[str, str | bool]) -> None:
    if not path:
        return
    output_path = Path(path)
    with output_path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            if "\n" in rendered or "\r" in rendered:
                raise ValueError(f"multiline GitHub output is not allowed: {key}")
            handle.write(f"{key}={rendered}\n")


def create_plan(args: argparse.Namespace) -> int:
    head_sha = validate_sha(args.head, name="head SHA")
    base_sha = args.base.strip().lower()
    if base_sha != ZERO_SHA:
        validate_sha(base_sha, name="base SHA")
    files = list(args.file or ()) or changed_files_between(base_sha, head_sha)
    result = classify_files(files, force_all_ci=args.force_all_ci)
    if args.cumulative_ci:
        api = GitHubApi(
            base_url=args.api_url,
            repository=args.repository,
            token=os.environ.get("GH_TOKEN", ""),
        )
        for target in TARGETS:
            baseline = api.latest_successful_sha(target)
            needed, reason = resolve_target(
                target=target,
                baseline=baseline,
                head_sha=head_sha,
            )
            print(f"CI coverage {target}: {'required' if needed else 'not required'} ({reason})")
            if needed:
                for check_name in TARGET_CI_REQUIREMENTS[target]:
                    result["ci"][check_name] = True

    target_coverage = {
        target: all(result["ci"][check_name] for check_name in TARGET_CI_REQUIREMENTS[target])
        for target in TARGETS
    }
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "ci_target_coverage": target_coverage,
        **result,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_github_outputs(args.github_output, {**plan["ci"], **plan["deploy"]})
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def validate_plan(path: str, expected_head: str) -> dict[str, Any]:
    try:
        plan = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"release plan is unreadable: {exc}") from exc
    if not isinstance(plan, dict) or plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError("release plan has an unsupported schema version")
    if plan.get("head_sha") != expected_head:
        raise ValueError("release plan head SHA does not match the CI-tested revision")
    if not isinstance(plan.get("changed_files"), list) or not all(
        isinstance(item, str) for item in plan["changed_files"]
    ):
        raise ValueError("release plan changed_files must be an array of strings")
    coverage = plan.get("ci_target_coverage")
    if not isinstance(coverage, dict) or set(coverage) != set(TARGETS):
        raise ValueError("release plan ci_target_coverage keys are invalid")
    if not all(isinstance(value, bool) for value in coverage.values()):
        raise ValueError("release plan ci_target_coverage values must be booleans")
    for group_name, expected_keys in (
        ("deploy", TARGETS),
        (
            "ci",
            (
                "backend",
                "ai_core",
                "frontend",
                "migrations",
                "dependency_audit",
                "python_dependency_audit",
                "frontend_dependency_audit",
                "production_image",
                "workflow",
            ),
        ),
    ):
        group = plan.get(group_name)
        if not isinstance(group, dict) or set(group) != set(expected_keys):
            raise ValueError(f"release plan {group_name} keys are invalid")
        if not all(isinstance(value, bool) for value in group.values()):
            raise ValueError(f"release plan {group_name} values must be booleans")
    expected_coverage = {
        target: all(plan["ci"][check_name] for check_name in TARGET_CI_REQUIREMENTS[target])
        for target in TARGETS
    }
    if coverage != expected_coverage:
        raise ValueError("release plan ci_target_coverage is inconsistent with its CI scopes")
    return plan


class GitHubApi:
    def __init__(self, *, base_url: str, repository: str, token: str) -> None:
        if not REPOSITORY_RE.fullmatch(repository):
            raise ValueError("repository must use owner/name format")
        if not token:
            raise ValueError("GH_TOKEN is required")
        self.base_url = base_url.rstrip("/")
        self.repository = repository
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "manim-agent-release-plan",
        }

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={**self.headers, **({"Content-Type": "application/json"} if data else {})},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2_000]
            raise RuntimeError(f"GitHub API {method} {path} failed: {exc.code} {detail}") from exc

    def latest_successful_sha(self, target: str) -> str | None:
        deployments: list[dict[str, Any]] = []
        for page in range(1, 101):
            query = urllib.parse.urlencode(
                {
                    "environment": "production",
                    "task": f"deploy:{target}",
                    "per_page": "100",
                    "page": str(page),
                }
            )
            response = self.request(
                "GET", f"/repos/{self.repository}/deployments?{query}"
            )
            if not isinstance(response, list):
                raise RuntimeError("GitHub deployments response is not an array")
            deployments.extend(item for item in response if isinstance(item, dict))
            if len(response) < 100:
                break
        else:
            raise RuntimeError("GitHub deployment history exceeds the safe pagination limit")

        # Do not rely on an undocumented response order. Deployment ids are
        # monotonically increasing within a repository.
        deployments.sort(
            key=lambda item: item.get("id") if isinstance(item.get("id"), int) else -1,
            reverse=True,
        )
        for deployment in deployments:
            deployment_id = deployment.get("id") if isinstance(deployment, dict) else None
            sha = deployment.get("sha") if isinstance(deployment, dict) else None
            if not isinstance(deployment_id, int) or not isinstance(sha, str):
                continue
            statuses = self.request(
                "GET",
                f"/repos/{self.repository}/deployments/{deployment_id}/statuses?per_page=100",
            )
            if not isinstance(statuses, list):
                raise RuntimeError("GitHub deployment statuses response is not an array")
            ordered_statuses = sorted(
                (item for item in statuses if isinstance(item, dict)),
                key=lambda item: item.get("id") if isinstance(item.get("id"), int) else -1,
                reverse=True,
            )
            if ordered_statuses and ordered_statuses[0].get("state") == "success":
                normalized_sha = sha.lower()
                if SHA_RE.fullmatch(normalized_sha):
                    return normalized_sha
        return None

    def record_success(self, *, target: str, sha: str, environment_url: str | None) -> int:
        deployment = self.request(
            "POST",
            f"/repos/{self.repository}/deployments",
            {
                "ref": sha,
                "task": f"deploy:{target}",
                "environment": "production",
                "description": f"Manim Agent {target} production release",
                "auto_merge": False,
                "required_contexts": [],
                "transient_environment": False,
                "production_environment": True,
                "payload": {"source": "github-actions"},
            },
        )
        deployment_id = deployment.get("id") if isinstance(deployment, dict) else None
        if not isinstance(deployment_id, int):
            raise RuntimeError("GitHub did not return a deployment id")
        run_url = (
            f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
            f"{self.repository}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
        )
        status: dict[str, Any] = {
            "state": "success",
            "description": f"{target} deployment completed",
            "environment": "production",
            "log_url": run_url,
            "auto_inactive": False,
        }
        if environment_url:
            if not re.fullmatch(r"https://[^\s]+", environment_url):
                raise ValueError("environment URL must be an absolute HTTPS URL")
            status["environment_url"] = environment_url
        self.request(
            "POST",
            f"/repos/{self.repository}/deployments/{deployment_id}/statuses",
            status,
        )
        return deployment_id


def _is_ancestor(older: str, newer: str) -> bool:
    result = _git("merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "git merge-base failed")
    return result.returncode == 0


def resolve_target(*, target: str, baseline: str | None, head_sha: str) -> tuple[bool, str]:
    if baseline is None:
        return True, "no successful component deployment baseline"
    if _git("cat-file", "-e", f"{baseline}^{{commit}}", check=False).returncode != 0:
        return True, "deployment baseline is unavailable locally"
    if _is_ancestor(head_sha, baseline):
        return False, f"already included by deployed revision {baseline[:12]}"
    if not _is_ancestor(baseline, head_sha):
        return True, "deployment baseline and tested revision have diverged"
    files = changed_files_between(baseline, head_sha)
    needed = any(deployment_scope(path, target) for path in files)
    return needed, (
        f"matching changes since {baseline[:12]}" if needed else f"no matching changes since {baseline[:12]}"
    )


def resolve_plan(args: argparse.Namespace) -> int:
    head_sha = validate_sha(args.head, name="head SHA")
    plan = validate_plan(args.plan, head_sha)
    api = GitHubApi(
        base_url=args.api_url,
        repository=args.repository,
        token=os.environ.get("GH_TOKEN", ""),
    )
    resolved: dict[str, bool] = {}
    baselines: dict[str, str] = {}
    for target in TARGETS:
        baseline = api.latest_successful_sha(target)
        needed, reason = resolve_target(target=target, baseline=baseline, head_sha=head_sha)
        if needed and plan["ci_target_coverage"][target] is not True:
            raise RuntimeError(
                f"{target} requires deployment but the successful CI plan does not cover its required checks"
            )
        resolved[target] = needed
        baselines[target] = baseline or "none"
        print(f"{target}: {'deploy' if needed else 'skip'} ({reason})")
    write_github_outputs(
        args.github_output,
        {
            **resolved,
            **{f"{target}_baseline": value for target, value in baselines.items()},
        },
    )
    return 0


def record_success(args: argparse.Namespace) -> int:
    target = args.target
    if target not in TARGETS:
        raise ValueError(f"unknown deployment target: {target}")
    sha = validate_sha(args.head, name="head SHA")
    api = GitHubApi(
        base_url=args.api_url,
        repository=args.repository,
        token=os.environ.get("GH_TOKEN", ""),
    )
    deployment_id = api.record_success(
        target=target,
        sha=sha,
        environment_url=args.environment_url,
    )
    print(f"Recorded successful {target} deployment id={deployment_id} sha={sha}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create a release plan from a Git diff")
    create.add_argument("--base", required=True)
    create.add_argument("--head", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--github-output")
    create.add_argument("--file", action="append", help="inject a changed file for tests")
    create.add_argument("--force-all-ci", action="store_true")
    create.add_argument(
        "--cumulative-ci",
        action="store_true",
        help="cover changes since every target's last successful deployment",
    )
    create.add_argument("--repository")
    create.add_argument("--api-url", default="https://api.github.com")
    create.set_defaults(handler=create_plan)

    resolve = subparsers.add_parser("resolve", help="resolve targets against deployed baselines")
    resolve.add_argument("--plan", required=True)
    resolve.add_argument("--head", required=True)
    resolve.add_argument("--repository", required=True)
    resolve.add_argument("--api-url", default="https://api.github.com")
    resolve.add_argument("--github-output", required=True)
    resolve.set_defaults(handler=resolve_plan)

    record = subparsers.add_parser("record-success", help="record a successful component release")
    record.add_argument("--target", required=True, choices=TARGETS)
    record.add_argument("--head", required=True)
    record.add_argument("--repository", required=True)
    record.add_argument("--api-url", default="https://api.github.com")
    record.add_argument("--environment-url")
    record.set_defaults(handler=record_success)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"release-plan error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
