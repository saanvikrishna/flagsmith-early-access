#!/usr/bin/env python3
"""Unit tests for Flagsmith Early Access Terminal Dashboard (TUI)."""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from typing import Any

import ea_dashboard as tui


DEMO_STATE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "demo-app", "demo-state.json")
)


class TestAnsiAndTableRendering(unittest.TestCase):
    def test_ansi_table_alignment_and_escape_codes(self) -> None:
        ansi = tui.Ansi(enabled=True)
        table = tui.render_table(
            ["Flag", "Status"],
            [[ansi.style("bulk_export", tui.Ansi.BOLD), ansi.style("OVERDUE", tui.Ansi.RED)]],
            ansi=ansi,
            title="Test Table",
        )
        self.assertIn("\x1b[", table)
        lines = table.splitlines()
        # Title + top + header + sep + 1 row + bottom = 6 lines
        self.assertEqual(len(lines), 6)
        stripped_lengths = [tui.visible_len(line) for line in lines[1:]]
        self.assertEqual(len(set(stripped_lengths)), 1)

    def test_no_color_table_has_no_ansi_escapes(self) -> None:
        ansi = tui.Ansi(enabled=False)
        table = tui.render_table(
            ["Flag", "Status"],
            [["ai_summaries", "LIVE"]],
            ansi=ansi,
        )
        self.assertNotIn("\x1b[", table)
        self.assertIn("ai_summaries", table)
        self.assertIn("LIVE", table)


class TestOverdueDetection(unittest.TestCase):
    def test_overdue_dates(self) -> None:
        ref = dt.date(2026, 11, 27)
        self.assertTrue(tui.is_grant_overdue("2026-11-25", today=ref))
        self.assertFalse(tui.is_grant_overdue("2026-11-27", today=ref))
        self.assertFalse(tui.is_grant_overdue("2026-12-15", today=ref))
        self.assertFalse(tui.is_grant_overdue("unknown", today=ref))
        self.assertFalse(tui.is_grant_overdue("not-a-date", today=ref))

    def test_parse_ea_description(self) -> None:
        parsed = tui.parse_ea_description(
            "ea-bulk_export-initech",
            "early-access; flag=bulk_export; customer=initech; expires=2026-11-25; issue=seed",
        )
        self.assertEqual(parsed["flag"], "bulk_export")
        self.assertEqual(parsed["customer"], "initech")
        self.assertEqual(parsed["expires"], "2026-11-25")
        self.assertEqual(parsed["issue"], "seed")


class TestOfflineCLI(unittest.TestCase):
    def test_snapshot_offline(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tui.main(
                [
                    "--offline",
                    "--state-file",
                    DEMO_STATE_PATH,
                    "--snapshot",
                    "--today",
                    "2026-11-27",
                ]
            )
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("Flags Across Environments", out)
        self.assertIn("Development", out)
        self.assertIn("Production", out)
        self.assertIn("bulk_export", out)
        self.assertIn("ea-bulk_export-initech", out)
        self.assertIn("OVERDUE", out)

    def test_audit_offline_live_and_overdue(self) -> None:
        state = {
            "defaults": {"bulk_export": False, "ai_summaries": False},
            "orgOverrides": {
                "initech": {"bulk_export": True},
                "acme": {"ai_summaries": True},
            },
            "identityOverrides": {},
            "segments": [
                {
                    "name": "ea-bulk_export-initech",
                    "description": "early-access; flag=bulk_export; customer=initech; expires=2026-11-25; issue=#1",
                },
                {
                    "name": "ea-ai_summaries-acme",
                    "description": "early-access; flag=ai_summaries; customer=acme; expires=2026-12-20; issue=#2",
                },
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(state, fh)
            tmp_path = fh.name
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = tui.main(
                    [
                        "--offline",
                        "--state-file",
                        tmp_path,
                        "--audit",
                        "--today",
                        "2026-11-27",
                        "--no-color",
                    ]
                )
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("OVERDUE", out)
            self.assertIn("LIVE", out)
            self.assertIn("2 total | 1 LIVE | 1 OVERDUE", out)
        finally:
            os.remove(tmp_path)

    def test_eval_offline(self) -> None:
        buf_enabled = io.StringIO()
        with redirect_stdout(buf_enabled):
            rc1 = tui.main(
                ["--offline", "--state-file", DEMO_STATE_PATH, "--eval", "bulk_export", "user_42", "--no-color"]
            )
        self.assertEqual(rc1, 0)
        self.assertIn("ENABLED (true)", buf_enabled.getvalue())
        self.assertIn("initech", buf_enabled.getvalue())

        buf_disabled = io.StringIO()
        with redirect_stdout(buf_disabled):
            rc2 = tui.main(
                ["--offline", "--state-file", DEMO_STATE_PATH, "--eval", "bulk_export", "user_1", "--no-color"]
            )
        self.assertEqual(rc2, 0)
        self.assertIn("DISABLED (false)", buf_disabled.getvalue())
        self.assertIn("acme", buf_disabled.getvalue())

    def test_interactive_grant_revoke_eval_quit(self) -> None:
        backend = tui.OfflineBackend(DEMO_STATE_PATH)
        ansi = tui.Ansi(enabled=False)
        inputs = iter(["1", "ai_summaries", "acme", "2026-12-30", "4", "ai_summaries", "user_1", "2", "ai_summaries", "acme", "q"])
        outputs: list[str] = []
        rc = tui.run_interactive(
            backend,
            ansi=ansi,
            input_fn=lambda _prompt: next(inputs),
            output_fn=outputs.append,
        )
        self.assertEqual(rc, 0)
        joined = "\n".join(outputs)
        self.assertIn("Granted 'ai_summaries' to 'acme'", joined)
        self.assertIn("CONTROL(user_3)=False", joined)
        self.assertIn("ENABLED (true)", joined)
        self.assertIn("Revoked 'ai_summaries' for 'acme'", joined)


class TestMockedFlagsmithAPI(unittest.TestCase):
    def _build_mock_backend(self) -> tuple[tui.LiveFlagsmithBackend, list[tuple[str, str, Any]]]:
        calls: list[tuple[str, str, Any]] = []
        segments: list[dict[str, Any]] = [
            {
                "id": 10,
                "name": "ea-bulk_export-initech",
                "description": "early-access; flag=bulk_export; customer=initech; expires=2026-11-25; issue=seed",
            },
            {
                "id": 11,
                "name": "internal_staff",
                "description": "Internal dogfooding",
            },
        ]
        # Track whether acme has ai_summaries enabled via segment
        state = {"acme_ai": False, "prod_ai_default": False}

        def mock_request(
            url: str,
            *,
            method: str = "GET",
            headers: dict[str, str] | None = None,
            body: bytes | None = None,
        ) -> Any:
            payload = json.loads(body.decode("utf-8")) if body else None
            calls.append((method, url, payload))

            if url.endswith("/api/v1/projects/"):
                return {"results": [{"id": 1, "name": "early-access-demo"}]}
            if "/api/v1/environments/?project=1" in url:
                return {
                    "results": [
                        {"id": 101, "name": "Development", "api_key": "dev_key"},
                        {"id": 102, "name": "Production", "api_key": "prod_key"},
                    ]
                }
            if url.endswith("/api/v1/projects/1/features/"):
                return {
                    "results": [
                        {"id": 201, "name": "ai_summaries"},
                        {"id": 202, "name": "bulk_export"},
                    ]
                }
            if "/api/v1/environments/dev_key/featurestates/?feature=201" in url:
                return {"results": [{"id": 301, "enabled": False, "feature_segment": None, "identity": None}]}
            if "/api/v1/environments/dev_key/featurestates/?feature=202" in url:
                return {"results": [{"id": 302, "enabled": False, "feature_segment": None, "identity": None}]}
            if "/api/v1/environments/prod_key/featurestates/?feature=201" in url:
                return {
                    "results": [
                        {"id": 401, "enabled": state["prod_ai_default"], "feature_segment": None, "identity": None}
                    ]
                }
            if "/api/v1/environments/prod_key/featurestates/?feature=202" in url:
                return {
                    "results": [
                        {"id": 402, "enabled": False, "feature_segment": None, "identity": None},
                        {"id": 403, "enabled": True, "feature_segment": 501, "identity": None},
                    ]
                }
            if url.endswith("/api/v1/projects/1/segments/") and method == "GET":
                return {"results": list(segments)}
            if url.endswith("/api/v1/projects/1/segments/") and method == "POST":
                new_seg = {"id": 99, "name": payload["name"], "description": payload["description"]}
                segments.append(new_seg)
                state["acme_ai"] = True
                return new_seg
            if "/api/v1/projects/1/segments/" in url and method == "DELETE":
                seg_id = int(url.rstrip("/").split("/")[-1])
                segments[:] = [s for s in segments if s["id"] != seg_id]
                state["acme_ai"] = False
                return None
            if url.endswith("/api/v1/features/feature-segments/") and method == "POST":
                return {"id": 599}
            if "/api/v1/environments/prod_key/featurestates/" in url and method == "POST":
                return {"id": 699}
            if url.endswith("/api/v1/identities/") and method == "POST":
                ident = payload["identifier"]
                org = next(
                    (t["trait_value"] for t in payload.get("traits", []) if t["trait_key"] == "org_id"),
                    "",
                )
                return {
                    "flags": [
                        {"feature": {"name": "ai_summaries"}, "enabled": org == "acme" and state["acme_ai"]},
                        {"feature": {"name": "bulk_export"}, "enabled": org == "initech"},
                    ]
                }
            raise AssertionError(f"Unexpected mock request: {method} {url}")

        backend = tui.LiveFlagsmithBackend(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            environment_key="prod_key",
            request_fn=mock_request,
        )
        return backend, calls

    def test_mocked_summary_grants_eval_and_grant_flow(self) -> None:
        backend, _ = self._build_mock_backend()
        summaries = backend.get_flags_summary()
        self.assertEqual([s.name for s in summaries], ["ai_summaries", "bulk_export"])
        self.assertEqual(summaries[1].prod_overrides, 1)

        grants = backend.get_ea_grants(today=dt.date(2026, 11, 27))
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0].segment_name, "ea-bulk_export-initech")
        self.assertTrue(grants[0].overdue)

        ev = backend.evaluate_identity("bulk_export", "user_42")
        self.assertTrue(ev.enabled)

        grant_res = backend.grant_early_access(
            flag="ai_summaries",
            customer="acme",
            expires="2026-12-20",
            mechanism="segment",
        )
        self.assertTrue(grant_res["target_enabled"])
        self.assertFalse(grant_res["control_enabled"])

        revoke_res = backend.revoke_grant(flag="ai_summaries", customer="acme")
        self.assertTrue(revoke_res["revoked"])

    def test_fallback_to_offline_when_unreachable(self) -> None:
        backend, notice = tui.create_backend(
            offline=False,
            state_path=DEMO_STATE_PATH,
            api_url="http://127.0.0.1:1",
            api_key="dummy",
            environment_key="dummy_env",
        )
        self.assertIsInstance(backend, tui.OfflineBackend)
        self.assertIsNotNone(notice)
        self.assertIn("falling back to offline mode", notice)


if __name__ == "__main__":
    unittest.main()
