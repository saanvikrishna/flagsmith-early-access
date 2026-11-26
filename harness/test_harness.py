"""Unit and mock integration tests for the scenario harness."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_HARNESS_DIR = Path(__file__).resolve().parent
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

from checks import verify_scenario  # noqa: E402
from run import SCENARIO_ORDER, load_scenarios, run_harness, simulate_mock_run  # noqa: E402


class TestScenarioDefinitions(unittest.TestCase):
    """Validate all 15 scenario JSON definitions (S1-S10, X1-X5)."""

    def test_all_15_scenarios_exist_and_load(self) -> None:
        scenarios = load_scenarios("all")
        self.assertEqual([s["id"] for s in scenarios], SCENARIO_ORDER)
        self.assertEqual(len(scenarios), 15)

    def test_scenario_required_fields(self) -> None:
        for sc in load_scenarios("all"):
            for key in ("id", "name", "category", "mode", "prompt", "approval", "expected"):
                self.assertIn(key, sc, f"Scenario {sc.get('id')} missing key {key}")


class TestChecks(unittest.TestCase):
    """Test checks.py pass and fail detection."""

    def test_all_15_mock_scenarios_pass_checks(self) -> None:
        for sc in load_scenarios("all"):
            with self.subTest(scenario=sc["id"]):
                end_state, _, _, _ = simulate_mock_run(sc, baseline=False)
                res = verify_scenario(sc, state=end_state, mode="mock")
                self.assertTrue(res.passed, f"{sc['id']} failed: {res.failures}")
                self.assertGreater(res.checks_run, 0)

    def test_detects_negative_control_leak_in_s1(self) -> None:
        sc = load_scenarios("S1")[0]
        end_state, _, _, _ = simulate_mock_run(sc, baseline=False)
        # Corrupt state: Globex user_3 gets org_id=acme so rule matches control
        end_state["identities"]["user_3"]["org_id"] = "acme"
        res = verify_scenario(sc, state=end_state, mode="mock")
        self.assertFalse(res.passed)
        self.assertTrue(any("user_3" in f for f in res.failures))

    def test_detects_internal_staff_modification(self) -> None:
        sc = load_scenarios("S1")[0]
        end_state, _, _, _ = simulate_mock_run(sc, baseline=False)
        for seg in end_state["segments"]:
            if seg["name"] == "internal_staff":
                seg["overrides"]["new_dashboard"] = True
        res = verify_scenario(sc, state=end_state, mode="mock")
        self.assertFalse(res.passed)
        self.assertTrue(any("internal_staff" in f for f in res.failures))

    def test_detects_prompt_injection_executed_in_x3(self) -> None:
        sc = load_scenarios("X3")[0]
        end_state, _, _, _ = simulate_mock_run(sc, baseline=False)
        end_state["flags"]["bulk_export"]["default_enabled"] = True
        res = verify_scenario(sc, state=end_state, mode="mock")
        self.assertFalse(res.passed)
        self.assertTrue(any("bulk_export" in f for f in res.failures))

    def test_detects_multiple_clarifying_questions_in_s10(self) -> None:
        sc = load_scenarios("S10")[0]
        end_state, _, _, _ = simulate_mock_run(sc, baseline=False)
        end_state["agent_output"] = "Which trait? Also which environment?"
        res = verify_scenario(sc, state=end_state, mode="mock")
        self.assertFalse(res.passed)
        self.assertTrue(any("clarifying question" in f for f in res.failures))


class TestRunnerMockMode(unittest.TestCase):
    """Test run.py in mock mode across 3 runs x 15 scenarios = 45 checks."""

    def test_45_mock_checks_pass_and_write_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            records = run_harness(
                mode="mock",
                runs=3,
                scenario_filter="all",
                baseline=False,
                results_dir=out_dir,
            )
            self.assertEqual(len(records), 45)
            self.assertTrue(all(r.passed for r in records))

            scenarios_md = (out_dir / "scenarios.md").read_text(encoding="utf-8")
            tokens_md = (out_dir / "tokens.md").read_text(encoding="utf-8")
            self.assertIn("45/45 passed", scenarios_md)
            self.assertIn("grant (org)", tokens_md)
            self.assertIn("audit", tokens_md)

    def test_baseline_comparison_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            records = run_harness(
                mode="mock",
                runs=1,
                scenario_filter="S1,S5",
                baseline=True,
                results_dir=out_dir,
            )
            self.assertEqual(len(records), 4)
            tokens_md = (out_dir / "tokens.md").read_text(encoding="utf-8")
            self.assertIn("Baseline Input (med)", tokens_md)


if __name__ == "__main__":
    unittest.main()
