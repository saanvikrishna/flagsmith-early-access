"""Unit tests for self-hosted/bootstrap.py."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: E402


class FakeFlagsmithServer:
    """In-memory mock of the Flagsmith REST API for bootstrap tests."""

    def __init__(self, *, health_failures: int = 0) -> None:
        self.health_failures = health_failures
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.orgs: list[dict[str, Any]] = []
        self.projects: list[dict[str, Any]] = []
        self.features: list[dict[str, Any]] = []
        self.segments: list[dict[str, Any]] = []
        self.featurestates: dict[str, list[dict[str, Any]]] = {
            "prod-key-123": [],
            "dev-key-456": [],
        }
        self.identities: dict[str, list[dict[str, Any]]] = {
            "prod-key-123": [],
            "dev-key-456": [],
        }
        self._next_id = 1

    def _alloc_id(self) -> int:
        val = self._next_id
        self._next_id += 1
        return val

    def handle(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bootstrap.HttpResponse:
        self.calls.append((method, url, payload))
        path = url.split("http://localhost:8000", 1)[-1]

        if path == "/health":
            if self.health_failures > 0:
                self.health_failures -= 1
                return bootstrap.HttpResponse(503, {"status": "starting"})
            return bootstrap.HttpResponse(200, {"status": "ok"})

        if path == "/api/v1/auth/users/" and method == "POST":
            return bootstrap.HttpResponse(201, {"email": payload["email"]})

        if path == "/api/v1/auth/login/" and method == "POST":
            return bootstrap.HttpResponse(200, {"key": "user-token-abc"})

        if path == "/api/v1/organisations/":
            if method == "GET":
                return bootstrap.HttpResponse(200, {"results": self.orgs})
            if method == "POST":
                org = {"id": self._alloc_id(), "name": payload["name"]}
                self.orgs.append(org)
                return bootstrap.HttpResponse(201, org)

        if path.startswith("/api/v1/projects/?organisation="):
            return bootstrap.HttpResponse(200, {"results": self.projects})

        if path == "/api/v1/projects/" and method == "POST":
            proj = {
                "id": self._alloc_id(),
                "name": payload["name"],
                "organisation": payload["organisation"],
            }
            self.projects.append(proj)
            return bootstrap.HttpResponse(201, proj)

        if path.startswith("/api/v1/environments/?project="):
            return bootstrap.HttpResponse(
                200,
                {
                    "results": [
                        {"id": 10, "name": "Development", "api_key": "dev-key-456"},
                        {"id": 11, "name": "Production", "api_key": "prod-key-123"},
                    ]
                },
            )

        if path.endswith("/master-api-keys/") and method == "POST":
            return bootstrap.HttpResponse(
                201, {"id": 99, "name": payload["name"], "key": "master-key-xyz"}
            )

        if path.endswith("/features/"):
            if method == "GET":
                return bootstrap.HttpResponse(200, {"results": self.features})
            if method == "POST":
                feat = {"id": self._alloc_id(), "name": payload["name"]}
                self.features.append(feat)
                return bootstrap.HttpResponse(201, feat)

        if path.endswith("/segments/"):
            if method == "GET":
                return bootstrap.HttpResponse(200, {"results": self.segments})
            if method == "POST":
                seg = {"id": self._alloc_id(), "name": payload["name"]}
                self.segments.append(seg)
                return bootstrap.HttpResponse(201, seg)

        if "/featurestates/" in path:
            env_key = path.split("/api/v1/environments/")[1].split("/")[0]
            if method == "GET":
                return bootstrap.HttpResponse(
                    200, {"results": self.featurestates[env_key]}
                )
            if method == "POST":
                fs = {
                    "id": self._alloc_id(),
                    "feature": payload["feature"],
                    "feature_segment": payload["feature_segment"],
                    "enabled": payload["enabled"],
                }
                self.featurestates[env_key].append(fs)
                return bootstrap.HttpResponse(201, fs)

        if path == "/api/v1/identities/" and method == "POST":
            env_key = (headers or {}).get("X-Environment-Key", "")
            self.identities[env_key].append(payload)
            return bootstrap.HttpResponse(200, {"identifier": payload["identifier"]})

        raise AssertionError(f"Unhandled mock request: {method} {url}")


class TestBootstrap(unittest.TestCase):
    def test_dry_run_makes_no_http_calls_or_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = bootstrap.main(
                    ["--dry-run", "--url", "http://localhost:8000", "--env-file", str(env_path)]
                )
            self.assertEqual(rc, 0)
            self.assertFalse(env_path.exists())
            output = stdout.getvalue()
            self.assertIn("[dry-run] 1. Wait for GET http://localhost:8000/health", output)
            self.assertIn("ea-bulk_export-initech", output)

    def test_write_env_file_formats_expected_variables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            bootstrap.write_env_file(
                env_path,
                api_url="http://localhost:8000/",
                api_key="admin-token",
                prod_env_key="prod-key",
                dev_env_key="dev-key",
            )
            content = env_path.read_text(encoding="utf-8")
            self.assertEqual(
                content.splitlines(),
                [
                    "FLAGSMITH_API_URL=http://localhost:8000",
                    "FLAGSMITH_SDK_API_URL=http://localhost:8000/api/v1/identities/",
                    "FLAGSMITH_API_KEY=admin-token",
                    "FLAGSMITH_ENVIRONMENT=prod-key",
                    "FLAGSMITH_ENV_KEY_PROD=prod-key",
                    "FLAGSMITH_ENV_KEY_DEV=dev-key",
                ],
            )

    def test_mocked_bootstrap_flow_creates_resources_and_env(self) -> None:
        server = FakeFlagsmithServer(health_failures=1)
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            result = bootstrap.bootstrap(
                base_url="http://localhost:8000",
                env_path=env_path,
                request_fn=server.handle,
                sleep_fn=lambda _s: None,
            )

            self.assertFalse(result["dry_run"])
            self.assertEqual(result["prod_env_key"], "prod-key-123")
            self.assertEqual(result["dev_env_key"], "dev-key-456")

            self.assertEqual([o["name"] for o in server.orgs], ["Early Access Demo"])
            self.assertEqual([p["name"] for p in server.projects], ["early-access-demo"])
            self.assertEqual(
                [f["name"] for f in server.features],
                ["new_dashboard", "ai_summaries", "bulk_export"],
            )
            self.assertEqual(
                [s["name"] for s in server.segments],
                ["ea-bulk_export-initech", "internal_staff"],
            )
            self.assertEqual(len(server.featurestates["prod-key-123"]), 2)
            self.assertEqual(len(server.featurestates["dev-key-456"]), 2)
            self.assertEqual(len(server.identities["prod-key-123"]), 6)
            self.assertEqual(len(server.identities["dev-key-456"]), 6)

            env_text = env_path.read_text(encoding="utf-8")
            self.assertIn("FLAGSMITH_API_KEY=master-key-xyz", env_text)
            self.assertIn("FLAGSMITH_ENVIRONMENT=prod-key-123", env_text)
            self.assertIn("FLAGSMITH_ENV_KEY_DEV=dev-key-456", env_text)

            # Second run should be idempotent (no duplicate features, segments, or overrides)
            bootstrap.bootstrap(
                base_url="http://localhost:8000",
                env_path=env_path,
                request_fn=server.handle,
                sleep_fn=lambda _s: None,
            )
            self.assertEqual(len(server.features), 3)
            self.assertEqual(len(server.segments), 2)
            self.assertEqual(len(server.featurestates["prod-key-123"]), 2)
            self.assertEqual(len(server.featurestates["dev-key-456"]), 2)


if __name__ == "__main__":
    unittest.main()
