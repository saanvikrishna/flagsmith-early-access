#!/usr/bin/env python3
"""Unit tests for demo-seed/seed_flagsmith.py and demo-seed/seed_issues.py."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

DEMO_SEED_DIR = Path(__file__).resolve().parent
if str(DEMO_SEED_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_SEED_DIR))

import seed_flagsmith  # noqa: E402
import seed_issues  # noqa: E402


class FakeFlagsmithBackend:
    """In-memory stateful fake for `flagsmith api` CLI calls."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.next_id = 100
        self.project_id = 1
        self.envs = {
            "Production": {"id": 10, "name": "Production", "api_key": "env_prod_key"},
            "Development": {"id": 11, "name": "Development", "api_key": "env_dev_key"},
        }
        self.features: dict[int, dict[str, Any]] = {
            1: {"id": 1, "name": "new_dashboard", "default_enabled": False},
            2: {"id": 2, "name": "ai_summaries", "default_enabled": False},
        }
        # Pre-seed an extra stale ea-* segment, an identity override, and a flipped default
        self.segments: dict[int, dict[str, Any]] = {
            50: {"id": 50, "name": "ea-old_flag-globex", "description": "stale"},
            51: {"id": 51, "name": "internal_staff", "description": "old internal"},
        }
        self.feature_segments: dict[int, dict[str, Any]] = {}
        self.feature_states: dict[str, list[dict[str, Any]]] = {
            "env_prod_key": [
                {"id": 201, "feature": 1, "enabled": True, "identity": None, "feature_segment": None},
                {"id": 202, "feature": 2, "enabled": False, "identity": None, "feature_segment": None},
                {"id": 203, "feature": 1, "enabled": True, "identity": 999, "feature_segment": None},
            ],
            "env_dev_key": [
                {"id": 301, "feature": 1, "enabled": False, "identity": None, "feature_segment": None},
                {"id": 302, "feature": 2, "enabled": True, "identity": None, "feature_segment": None},
            ],
        }
        self.identities: dict[str, dict[str, dict[str, str]]] = {
            "env_prod_key": {},
            "env_dev_key": {},
        }

    def _alloc_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def snapshot(self) -> dict[str, Any]:
        seg_name_by_id = {sid: s["name"] for sid, s in self.segments.items()}
        feat_name_by_id = {fid: f["name"] for fid, f in self.features.items()}
        return {
            "features": sorted(f["name"] for f in self.features.values()),
            "segments": sorted(
                (s["name"], s["description"], s["rules"])
                for s in self.segments.values()
            ),
            "feature_segments": sorted(
                (
                    feat_name_by_id.get(fs["feature"]),
                    seg_name_by_id.get(fs["segment"]),
                    fs["environment"],
                )
                for fs in self.feature_segments.values()
            ),
            "default_states": {
                env_key: sorted(
                    (feat_name_by_id.get(fs["feature"]), fs["enabled"])
                    for fs in states
                    if fs["identity"] is None and fs["feature_segment"] is None
                )
                for env_key, states in self.feature_states.items()
            },
            "segment_states": {
                env_key: sorted(
                    (feat_name_by_id.get(fs["feature"]), fs["enabled"], fs["feature_segment"] is not None)
                    for fs in states
                    if fs["feature_segment"] is not None
                )
                for env_key, states in self.feature_states.items()
            },
            "identity_overrides": {
                env_key: [fs for fs in states if fs["identity"] is not None]
                for env_key, states in self.feature_states.items()
            },
            "identities": self.identities,
        }

    def __call__(
        self,
        cmd: list[str],
        *,
        input: str | None = None,
        text: bool = True,
        capture_output: bool = True,
        check: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(cmd)
        if len(cmd) > 1 and cmd[1] == "evaluate":
            ek = (env or {}).get("FLAGSMITH_ENVIRONMENT", "env-prod-key")
            ident_id = cmd[cmd.index("--identity") + 1]
            traits: dict[str, str] = {}
            for idx, tok in enumerate(cmd):
                if tok == "--trait" and idx + 1 < len(cmd) and "=" in cmd[idx + 1]:
                    k, v = cmd[idx + 1].split("=", 1)
                    traits[k] = v
            self.identities[ek][ident_id] = traits
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"flags": {}}), stderr="")
        if len(cmd) > 2 and cmd[1] == "flag" and cmd[2] == "update":
            ek = (env or {}).get("FLAGSMITH_ENVIRONMENT", "env-prod-key")
            feat_name = cmd[3]
            enabled = "--enable" in cmd
            fid = next(f["id"] for f in self.features.values() if f["name"] == feat_name)
            if "--segment" in cmd:
                seg_name = cmd[cmd.index("--segment") + 1]
                sid = next(s["id"] for s in self.segments.values() if s["name"] == seg_name)
                eid = 1 if ek == "env-prod-key" else 2
                fs_id = self._alloc_id()
                self.feature_segments[fs_id] = {"id": fs_id, "feature": fid, "segment": sid, "environment": eid, "priority": 0}
                st = {"id": self._alloc_id(), "identity": None, "feature": fid, "enabled": enabled, "feature_segment": fs_id}
                self.feature_states[ek].append(st)
            else:
                for st in self.feature_states[ek]:
                    if st["feature"] == fid and st["identity"] is None and st["feature_segment"] is None:
                        st["enabled"] = enabled
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        sdk = "--sdk" in cmd
        method = "GET"
        if "-X" in cmd:
            method = cmd[cmd.index("-X") + 1]
        env_key = None
        if "-e" in cmd:
            env_key = cmd[cmd.index("-e") + 1]

        # Path is the first positional argument after `flagsmith api` (not a flag or flag value)
        path = ""
        skip_next = False
        for token in cmd[2:]:
            if skip_next:
                skip_next = False
                continue
            if token in ("-X", "-e", "--input"):
                skip_next = True
                continue
            if token.startswith("-"):
                continue
            path = token
            break

        body = json.loads(input) if input else {}
        resp: Any = None

        if sdk and path == "api/v1/identities/" and method == "POST":
            traits = {t["trait_key"]: t["trait_value"] for t in body["traits"]}
            self.identities[env_key][body["identifier"]] = traits
            resp = {"identifier": body["identifier"], "traits": body["traits"]}
        elif path == "api/v1/projects/" and method == "GET":
            resp = {"results": [{"id": self.project_id, "name": "early-access-demo"}]}
        elif path == f"api/v1/environments/?project={self.project_id}" and method == "GET":
            resp = {"results": list(self.envs.values())}
        elif path == f"api/v1/projects/{self.project_id}/features/" and method == "GET":
            resp = {"results": list(self.features.values())}
        elif path == f"api/v1/projects/{self.project_id}/features/" and method == "POST":
            fid = self._alloc_id()
            feat = {"id": fid, "name": body["name"], "default_enabled": body.get("default_enabled", False)}
            self.features[fid] = feat
            for ek in ("env_prod_key", "env_dev_key"):
                self.feature_states[ek].append(
                    {"id": self._alloc_id(), "feature": fid, "enabled": False, "identity": None, "feature_segment": None}
                )
            resp = feat
        elif path == f"api/v1/projects/{self.project_id}/segments/" and method == "GET":
            resp = {"results": list(self.segments.values())}
        elif path == f"api/v1/projects/{self.project_id}/segments/" and method == "POST":
            sid = self._alloc_id()
            seg = {"id": sid, **body}
            self.segments[sid] = seg
            resp = seg
        elif path.startswith(f"api/v1/projects/{self.project_id}/segments/") and method == "DELETE":
            sid = int(path.rstrip("/").split("/")[-1])
            self.segments.pop(sid, None)
            # Cascade delete feature_segments and their feature_states
            removed_fs = [fs_id for fs_id, fs in self.feature_segments.items() if fs["segment"] == sid]
            for fs_id in removed_fs:
                self.feature_segments.pop(fs_id, None)
                for ek in self.feature_states:
                    self.feature_states[ek] = [
                        st for st in self.feature_states[ek] if st.get("feature_segment") != fs_id
                    ]
            resp = {}
        elif "/featurestates/?feature=" in path and method == "GET":
            ek = path.split("/")[3]
            fid = int(path.split("feature=")[1])
            resp = {"results": [st for st in self.feature_states[ek] if st["feature"] == fid]}
        elif "/featurestates/" in path and method == "DELETE":
            parts = path.strip("/").split("/")
            ek, st_id = parts[3], int(parts[5])
            self.feature_states[ek] = [st for st in self.feature_states[ek] if st["id"] != st_id]
            resp = {}
        elif "/featurestates/" in path and method == "PATCH":
            parts = path.strip("/").split("/")
            ek, st_id = parts[3], int(parts[5])
            for st in self.feature_states[ek]:
                if st["id"] == st_id:
                    st["enabled"] = body["enabled"]
                    resp = st
                    break
        elif path.endswith("/featurestates/") and method == "POST":
            ek = path.strip("/").split("/")[3]
            st = {"id": self._alloc_id(), "identity": None, **body}
            self.feature_states[ek].append(st)
            resp = st
        elif path == "api/v1/features/feature-segments/" and method == "POST":
            fs_id = self._alloc_id()
            fs = {"id": fs_id, **body}
            self.feature_segments[fs_id] = fs
            resp = fs
        else:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=f"Unexpected {method} {path}")

        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(resp), stderr="")


class TestSeedFlagsmith(unittest.TestCase):
    def test_dry_run_without_credentials_succeeds_and_does_not_run_cli(self) -> None:
        out = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch("subprocess.run") as mock_run:
            with redirect_stdout(out):
                rc = seed_flagsmith.main(["--dry-run"])
        self.assertEqual(rc, 0)
        mock_run.assert_not_called()
        output = out.getvalue()
        self.assertIn("early-access-demo", output)
        self.assertIn("ea-bulk_export-initech", output)
        self.assertIn("internal_staff", output)

    def test_live_mode_requires_credentials(self) -> None:
        err = io.StringIO()
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stderr(err):
                rc = seed_flagsmith.main(["--mode", "live"])
        self.assertEqual(rc, 1)
        self.assertIn("FLAGSMITH_API_KEY", err.getvalue())
        self.assertIn("FLAGSMITH_ENVIRONMENT", err.getvalue())

    def test_live_seed_creates_expected_state_and_is_idempotent(self) -> None:
        backend = FakeFlagsmithBackend()
        config = seed_flagsmith.SeedConfig(
            mode="live",
            project="early-access-demo",
            api_key="fs_test_key",
            environment="env_prod_key",
            organisation="org_1",
        )
        cli = seed_flagsmith.FlagsmithCLI(config, runner=backend)

        seed_flagsmith.seed_live(cli)
        state_after_first = backend.snapshot()

        # Verify expected features & default states (all False)
        self.assertEqual(state_after_first["features"], ["ai_summaries", "bulk_export", "new_dashboard"])
        for env_key in ("env_prod_key", "env_dev_key"):
            self.assertTrue(all(enabled is False for _, enabled in state_after_first["default_states"][env_key]))
            self.assertEqual(state_after_first["identity_overrides"][env_key], [])

        # Verify 6 identities with expected org_id and plan traits
        for env_key in ("env_prod_key", "env_dev_key"):
            idents = state_after_first["identities"][env_key]
            self.assertEqual(len(idents), 6)
            self.assertEqual(idents["user_1"], {"org_id": "acme", "plan": "enterprise"})
            self.assertEqual(idents["user_4"], {"org_id": "globex", "plan": "pro"})
            self.assertEqual(idents["user_42"], {"org_id": "initech", "plan": "starter"})

        # Verify stale ea-* segment removed, and both expected segments exist
        seg_names = [s[0] for s in state_after_first["segments"]]
        self.assertEqual(seg_names, ["ea-bulk_export-initech", "internal_staff"])

        ea_seg = next(s for s in state_after_first["segments"] if s[0] == "ea-bulk_export-initech")
        self.assertEqual(
            ea_seg[1],
            "early-access; flag=bulk_export; customer=initech; expires=2026-11-25; issue=seed",
        )
        self.assertEqual(
            ea_seg[2][0]["rules"][0]["conditions"][0],
            {"operator": "EQUAL", "property": "org_id", "value": "initech"},
        )

        # Verify exact CLI flags used (flagsmith api ... --json --no-input)
        self.assertTrue(any("evaluate" in cmd and "--persist" in cmd for cmd in backend.commands))
        self.assertTrue(all("--no-input" in cmd for cmd in backend.commands))

        # Run a second time and assert identical state
        seed_flagsmith.seed_live(cli)
        state_after_second = backend.snapshot()
        self.assertEqual(state_after_first, state_after_second)


class TestSeedIssues(unittest.TestCase):
    def test_dry_run_validates_repo_and_prints_commands(self) -> None:
        out = io.StringIO()
        with patch("subprocess.run") as mock_run:
            with redirect_stdout(out):
                rc = seed_issues.main(["--repo", "acme-org/demo-repo", "--dry-run"])
        self.assertEqual(rc, 0)
        mock_run.assert_not_called()
        text = out.getvalue()
        self.assertIn("gh label create early-access --repo acme-org/demo-repo", text)
        self.assertIn("Early access request: Acme -> new_dashboard until 2027-01-15", text)

    def test_invalid_repo_returns_error(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            rc = seed_issues.main(["--repo", "not-a-valid-repo", "--dry-run"])
        self.assertEqual(rc, 1)
        self.assertIn("Invalid --repo", err.getvalue())

    def test_seed_issues_live_is_idempotent(self) -> None:
        calls: list[list[str]] = []
        created = False

        def fake_gh(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            nonlocal created
            calls.append(cmd)
            if cmd[:3] == ["gh", "label", "create"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gh", "issue", "list"]:
                issues = (
                    [{"number": 1, "title": seed_issues.ISSUE_TITLE, "state": "OPEN"}]
                    if created
                    else []
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(issues), stderr="")
            if cmd[:3] == ["gh", "issue", "create"]:
                created = True
                return subprocess.CompletedProcess(cmd, 0, stdout="https://github.com/acme/demo/issues/1\n", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unexpected command")

        cfg = seed_issues.IssueSeedConfig(repo="acme/demo", dry_run=False)
        seed_issues.seed_issues_live(cfg, runner=fake_gh)
        seed_issues.seed_issues_live(cfg, runner=fake_gh)

        create_calls = [c for c in calls if c[:3] == ["gh", "issue", "create"]]
        self.assertEqual(len(create_calls), 1)
        self.assertIn("--body", create_calls[0])
        body = create_calls[0][create_calls[0].index("--body") + 1]
        self.assertIn("acme", body)
        self.assertIn("new_dashboard", body)
        self.assertIn("Production", body)
        self.assertIn("2027-01-15", body)
        self.assertIn("sales-team", body)

    def test_seed_issues_live_reopens_closed_issue(self) -> None:
        calls: list[list[str]] = []

        def fake_gh(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if cmd[:3] == ["gh", "label", "create"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:3] == ["gh", "issue", "list"]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout=json.dumps([{"number": 7, "title": seed_issues.ISSUE_TITLE, "state": "CLOSED"}]),
                    stderr="",
                )
            if cmd[:3] == ["gh", "issue", "reopen"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unexpected command")

        cfg = seed_issues.IssueSeedConfig(repo="acme/demo", dry_run=False)
        seed_issues.seed_issues_live(cfg, runner=fake_gh)

        self.assertTrue(any(c[:4] == ["gh", "issue", "reopen", "7"] for c in calls))
        self.assertFalse(any(c[:3] == ["gh", "issue", "create"] for c in calls))


if __name__ == "__main__":
    unittest.main()
