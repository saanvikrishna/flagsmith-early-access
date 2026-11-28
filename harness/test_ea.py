"""Integration tests: run the real skill/scripts/ea.sh against a stateful fake Flagsmith CLI + gh.

The fake (harness/fake_cli/fake_cli.py) reproduces the CLI behaviour verified live, including the
quirks that broke the old helper scripts: errors exit 0, duplicate segment names are allowed, and
`flag update --identifier <unknown>` silently creates identities. Faults are injected with
FAKE_FAIL / FAKE_DRIFT to prove rollback paths.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EA = ROOT / "skill" / "flagsmith-early-access" / "scripts" / "ea.sh"
FAKE = ROOT / "harness" / "fake_cli"


def find_bash() -> str | None:
    for cand in (r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")):
        if cand and os.path.exists(cand):
            try:
                if subprocess.run([cand, "-c", "command -v jq >/dev/null && echo ok"], capture_output=True,
                                  text=True, timeout=10).stdout.strip() == "ok":
                    return cand
            except (OSError, subprocess.SubprocessError):
                continue
    return None


BASH = find_bash()

BASE = {
    "env_name": "Production",
    "env_key": "envkey123",
    "next_id": 100,
    "features": {
        "new_dashboard": {"id": 1, "enabled": False, "segment_overrides": [], "identity_overrides": {}},
        "ai_summaries": {"id": 2, "enabled": False, "segment_overrides": [], "identity_overrides": {}},
        "bulk_export": {"id": 3, "enabled": False, "segment_overrides": [{"segment": 11, "enabled": True}], "identity_overrides": {}},
        "legacy_billing": {"id": 4, "enabled": False, "archived": True, "segment_overrides": [], "identity_overrides": {}},
    },
    "identities": {
        "user_1": {"org_id": "acme", "plan": "enterprise"},
        "user_2": {"org_id": "acme", "plan": "enterprise"},
        "user_3": {"org_id": "globex", "plan": "starter"},
        "user_4": {"org_id": "globex", "plan": "starter"},
        "user_5": {"org_id": "initech", "plan": "pro"},
        "user_42": {"org_id": "initech", "plan": "starter"},
    },
    "segments": [
        {"id": 10, "name": "internal_staff", "description": "QA staff",
         "rules": {"type": "ALL", "rules": [{"type": "ANY", "conditions": [{"property": "email", "operator": "EQUAL", "value": "qa@co"}]}]}},
        {"id": 11, "name": "ea-bulk_export-initech",
         "description": "early-access; flag=bulk_export; customer=initech; expires=2026-01-01; issue=#3",
         "rules": {"type": "ALL", "rules": [{"type": "ANY", "conditions": [{"property": "org_id", "operator": "EQUAL", "value": "initech"}]}]}},
    ],
    "issues": [
        {"number": 1, "title": "Early access request: Acme -> new_dashboard until 2099-01-15",
         "body": "Customer: Acme\nFeature: new_dashboard\nEnd date: 2099-01-15", "state": "OPEN", "labels": ["early-access"], "comments": []},
        {"number": 3, "title": "Revoke early access: bulk_export for initech (due 2026-01-01)",
         "body": "", "state": "OPEN", "labels": ["early-access"], "comments": []},
    ],
}


@unittest.skipUnless(BASH, "bash + jq required")
class EaTestCase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ea-test-"))
        self.state_path = self.tmp / "state.json"
        self.write_state(copy.deepcopy(BASE))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers
    def write_state(self, st: dict) -> None:
        self.state_path.write_text(json.dumps(st), encoding="utf-8")

    def state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def calls(self) -> list[str]:
        log = Path(str(self.state_path) + ".log")
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def writes(self) -> list[str]:
        return [c for c in self.calls() if c.startswith("flagsmith ") and
                any(w in c for w in (" create ", " update ", " delete "))]

    def ea(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        e = os.environ.copy()
        for k in ("FLAGSMITH_ENVIRONMENT", "GH_REPO", "FAKE_FAIL", "FAKE_DRIFT", "FAKE_EXIT_CODES",
                  "FAKE_GH_READONLY", "FAKE_GH_NOLABEL"):
            e.pop(k, None)
        e.update({
            "FLAGSMITH_BIN": (FAKE / "flagsmith").as_posix(),
            "GH_BIN": (FAKE / "gh").as_posix(),
            "PYTHON": Path(sys.executable).as_posix(),
            "FAKE_STATE": str(self.state_path),
            "AUDIT_TODAY": "2026-11-28",
            "TMPDIR": self.tmp.as_posix(),
            "EA_VERIFY_WAIT": "0",
        })
        e.update(env)
        return subprocess.run([BASH, EA.as_posix(), *args], capture_output=True, text=True, env=e,
                              cwd=str(ROOT), timeout=300, encoding="utf-8")

    def ev(self, flag: str, ident: str) -> bool:
        st = self.state()
        f = st["features"][flag]
        if ident in f["identity_overrides"]:
            return f["identity_overrides"][ident]
        traits = st["identities"].get(ident, {})
        for o in f["segment_overrides"]:
            seg = next((s for s in st["segments"] if s["id"] == o["segment"]), None)
            if seg and any(c["property"] in traits and traits[c["property"]] == c["value"]
                           for r in seg["rules"]["rules"] for c in r["conditions"]):
                return o["enabled"]
        return f["enabled"]

    def seg_names(self) -> list[str]:
        return [s["name"] for s in self.state()["segments"]]

    def issue(self, n: int) -> dict:
        return next(i for i in self.state()["issues"] if i["number"] == n)


class TestDetect(EaTestCase):
    def test_single_trait(self) -> None:
        r = self.ea("detect", "--dir", "demo-app/src")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("DETECT trait=org_id", r.stdout)

    def test_ambiguous_traits_asks_one_question(self) -> None:
        d = self.tmp / "app"
        d.mkdir()
        (d / "client.js").write_text("flagsmith.identify(u.id, { org_id: u.org, tenant_id: u.tenant })\n")
        r = self.ea("detect", "--dir", d.as_posix())
        self.assertEqual(r.returncode, 3)
        self.assertIn("DETECT ambiguous", r.stdout)
        self.assertIn("org_id", r.stdout)
        self.assertIn("tenant_id", r.stdout)


class TestGrant(EaTestCase):
    def test_preview_is_read_only_and_prints_exact_plan(self) -> None:
        r = self.ea("grant", "new_dashboard", "org:Acme", "--expires", "2099-01-15", "--issue", "1")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        plan = r.stdout[r.stdout.index("PLAN (Production)"):].splitlines()
        self.assertEqual([l.split(":")[0].strip() for l in plan[1:6]], ["Change", "Who", "Control", "Expires", "Undo"])
        self.assertEqual(plan[6], "Approve? (yes/no)")
        self.assertIn("user_3 (org_id=globex) must stay OFF", r.stdout)
        self.assertEqual(self.writes(), [])
        self.assertEqual(len(self.state()["issues"]), 2)

    def test_org_grant_applies_verifies_and_leaves_trail(self) -> None:
        r = self.ea("grant", "new_dashboard", "org:Acme", "--expires", "2099-01-15", "--issue", "1", "--approved")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("VERIFY TARGET=user_1:on CONTROL=user_3:off", r.stdout)
        self.assertTrue(self.ev("new_dashboard", "user_1") and self.ev("new_dashboard", "user_2"))
        self.assertFalse(self.ev("new_dashboard", "user_3") or self.ev("new_dashboard", "user_5"))
        seg = next(s for s in self.state()["segments"] if s["name"] == "ea-new_dashboard-acme")
        for part in ("flag=new_dashboard", "customer=acme", "expires=2099-01-15", "issue=#1"):
            self.assertIn(part, seg["description"])
        follow = self.state()["issues"][-1]
        self.assertEqual(follow["title"], "Revoke early access: new_dashboard for acme (due 2099-01-15)")
        self.assertIn("early-access", follow["labels"])
        self.assertTrue(self.issue(1)["comments"])
        self.assertEqual(self.seg_names().count("internal_staff"), 1)
        self.assertEqual(len(r.stdout.strip().splitlines()), 3, "apply output must stay 3 lines")

    def test_target_with_own_identity_override_is_skipped(self) -> None:  # live X3 root cause
        st = copy.deepcopy(BASE)
        st["features"]["new_dashboard"]["identity_overrides"] = {"user_1": False}
        self.write_state(st)
        r = self.ea("grant", "new_dashboard", "org:acme", "--expires", "2099-01-15", "--approved")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("VERIFY TARGET=user_2:on", r.stdout)
        n = len(self.writes())
        r = self.ea("revoke", "new_dashboard", "org:acme", "--approved")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.ea("grant", "new_dashboard", "org:acme", "--expires", "2099-01-15", "--target", "user_1")
        self.assertEqual(r.returncode, 3)
        self.assertIn("has its own identity override", r.stdout)
        self.assertGreater(len(self.writes()), n)  # revoke wrote; the refused grant preview did not

    def test_second_grant_is_refused(self) -> None:
        self.ea("grant", "new_dashboard", "org:acme", "--expires", "2099-01-15", "--approved")
        n = len(self.writes())
        r = self.ea("grant", "new_dashboard", "org:acme", "--expires", "2099-01-15", "--approved")
        self.assertEqual(r.returncode, 3)
        self.assertIn("already has early access", r.stdout)
        self.assertEqual(len(self.writes()), n)
        self.assertEqual(self.seg_names().count("ea-new_dashboard-acme"), 1)

    def test_user_grant(self) -> None:
        r = self.ea("grant", "ai_summaries", "user:user_42", "--expires", "2099-02-01", "--approved")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.ev("ai_summaries", "user_42"))
        self.assertFalse(self.ev("ai_summaries", "user_1"))
        self.assertIn("Revoke early access: ai_summaries for user_42 (due 2099-02-01)", self.state()["issues"][-1]["title"])

    def test_stops_before_any_write(self) -> None:
        st = copy.deepcopy(BASE)
        st["features"]["ai_summaries"]["enabled"] = True
        self.write_state(st)
        cases = [
            (("grant", "new_dashboard", "org:umbrella", "--expires", "2099-01-01"), "customer not found"),
            (("grant", "legacy_billing", "org:acme", "--expires", "2099-01-01"), "archived"),
            (("grant", "nope_flag", "org:acme", "--expires", "2099-01-01"), "not found"),
            (("grant", "ai_summaries", "org:acme", "--expires", "2099-01-01"), "already ON for everyone"),
            (("grant", "new_dashboard", "org:acme"), "missing expiry"),
            (("grant", "new_dashboard", "org:acme", "--expires", "2020-01-01"), "in the past"),
            (("grant", "new_dashboard", "org:acme", "--expires", "15/01/2099"), "not YYYY-MM-DD"),
            (("grant", "new_dashboard", "user:user_4242", "--expires", "2099-01-01", "--approved"), "not found"),
            (("grant", "new_dashboard", "org:acme", "--expires", "2099-01-01", "--target", "user_3"), "not 'acme'"),
            (("grant", "new_dashboard", "org:acme", "--expires", "2099-01-01", "--control", "user_2"), "itself in acme"),
        ]
        for args, msg in cases:
            with self.subTest(args=args):
                r = self.ea(*args)
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
                self.assertIn("STOP", r.stdout)
                self.assertIn(msg, r.stdout)
        self.assertEqual(self.writes(), [])
        self.assertNotIn("user_4242", self.state()["identities"], "typo must not create an identity")
        self.assertEqual(len(self.state()["issues"]), 2)

    def test_duplicate_segment_names_are_refused(self) -> None:
        st = copy.deepcopy(BASE)
        for sid in (20, 21):
            st["segments"].append({"id": sid, "name": "ea-new_dashboard-acme", "description": "",
                                   "rules": {"type": "ALL", "rules": []}})
        self.write_state(st)
        r = self.ea("revoke", "new_dashboard", "org:acme", "--approved")
        self.assertEqual(r.returncode, 3)
        self.assertIn("duplicate segments", r.stdout)
        self.assertEqual(self.writes(), [])

    def test_midway_cli_fault_rolls_back(self) -> None:  # X4
        r = self.ea("grant", "new_dashboard", "org:acme", "--expires", "2099-01-15", "--approved",
                    FAKE_FAIL="flag update --segment")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("ROLLED BACK (override failed", r.stdout)
        self.assertNotIn("ea-new_dashboard-acme", self.seg_names())
        self.assertFalse(self.ev("new_dashboard", "user_1"))
        self.assertEqual(len(self.state()["issues"]), 2, "no trail on rollback")

    def test_segment_create_fault_stops_cleanly(self) -> None:
        r = self.ea("grant", "new_dashboard", "org:acme", "--expires", "2099-01-15", "--approved",
                    FAKE_FAIL="segment create")
        self.assertEqual(r.returncode, 3)
        self.assertIn("ROLLED BACK (segment create failed", r.stdout)
        self.assertNotIn("ea-new_dashboard-acme", self.seg_names())

    def test_control_drift_rolls_back(self) -> None:  # X1
        r = self.ea("grant", "new_dashboard", "org:acme", "--expires", "2099-01-15", "--approved",
                    FAKE_DRIFT="user_3:org_id=acme")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("ROLLED BACK (verification failed: target=user_1:on control=user_3:on)", r.stdout)
        self.assertNotIn("ea-new_dashboard-acme", self.seg_names())
        self.assertEqual(len(self.state()["issues"]), 2)

    def test_native_exit_codes_also_work(self) -> None:
        r = self.ea("grant", "new_dashboard", "org:acme", "--expires", "2099-01-15", "--approved", FAKE_EXIT_CODES="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.ea("grant", "nope", "org:acme", "--expires", "2099-01-15", FAKE_EXIT_CODES="1")
        self.assertIn("not found", r.stdout)

    def test_unlabelable_repo_still_gets_trail(self) -> None:
        r = self.ea("grant", "new_dashboard", "org:acme", "--expires", "2099-01-15", "--approved", FAKE_GH_NOLABEL="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("unlabeled", r.stdout)
        r = self.ea("audit")
        self.assertIn("| acme | new_dashboard | segment ea-new_dashboard-acme | 2099-01-15 | ok | #4 |", r.stdout)


class TestRevoke(EaTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ea("grant", "new_dashboard", "org:acme", "--expires", "2099-01-15", "--approved")
        self.follow = self.state()["issues"][-1]["number"]

    def test_revoke_removes_verifies_and_closes(self) -> None:
        r = self.ea("revoke", "new_dashboard", "org:acme", "--approved")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("VERIFY TARGET=user_1:off", r.stdout)
        self.assertNotIn("ea-new_dashboard-acme", self.seg_names())
        self.assertEqual(self.issue(self.follow)["state"], "CLOSED")
        r = self.ea("revoke", "new_dashboard", "org:acme", "--approved")
        self.assertEqual(r.returncode, 3)
        self.assertIn("nothing to revoke", r.stdout)

    def test_revoke_preview_offers_exact_undo(self) -> None:
        r = self.ea("revoke", "new_dashboard", "org:acme")
        self.assertIn("Undo   : ea.sh grant new_dashboard org:acme --expires 2099-01-15 --approved", r.stdout)

    def test_failed_segment_delete_restores_without_duplicates(self) -> None:
        r = self.ea("revoke", "new_dashboard", "org:acme", "--approved", FAKE_FAIL="segment delete")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("ROLLED BACK", r.stdout)
        self.assertEqual(self.seg_names().count("ea-new_dashboard-acme"), 1)
        self.assertTrue(self.ev("new_dashboard", "user_1"), "grant restored")

    def test_readonly_github_is_reported_not_hidden(self) -> None:
        r = self.ea("revoke", "new_dashboard", "org:acme", "--approved", FAKE_GH_READONLY="1")
        self.assertEqual(r.returncode, 0)
        self.assertIn("FAILED", r.stdout)

    def test_user_revoke(self) -> None:
        self.ea("grant", "ai_summaries", "user:user_42", "--expires", "2099-02-01", "--approved")
        r = self.ea("revoke", "ai_summaries", "user:user_42", "--approved")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.ev("ai_summaries", "user_42"))


class TestGraduateAuditExpire(EaTestCase):
    def test_graduate_refuses_when_default_off(self) -> None:
        r = self.ea("graduate", "bulk_export", "--approved")
        self.assertEqual(r.returncode, 3)
        self.assertIn("default is OFF", r.stdout)
        self.assertIn("ea-bulk_export-initech", self.seg_names())
        self.assertEqual(self.writes(), [])

    def test_graduate_cleans_everything(self) -> None:
        st = copy.deepcopy(BASE)
        st["features"]["bulk_export"]["enabled"] = True
        st["features"]["bulk_export"]["identity_overrides"] = {"user_3": True}
        self.write_state(st)
        r = self.ea("graduate", "bulk_export")
        self.assertEqual(r.returncode, 3)
        self.assertIn("remove 1 segment(s) [ea-bulk_export-initech] + 1 identity override(s) [user_3]", r.stdout)
        r = self.ea("graduate", "bulk_export", "--approved")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("ea-bulk_export-initech", self.seg_names())
        self.assertEqual(self.state()["features"]["bulk_export"]["identity_overrides"], {})
        self.assertTrue(self.state()["features"]["bulk_export"]["enabled"], "default untouched")
        self.assertEqual(self.issue(3)["state"], "CLOSED")
        self.assertIn("internal_staff", self.seg_names())

    def test_graduate_keeps_deliberate_off_overrides(self) -> None:  # T8
        st = copy.deepcopy(BASE)
        st["features"]["bulk_export"]["enabled"] = True
        st["features"]["bulk_export"]["identity_overrides"] = {"user_1": False, "user_3": True}
        self.write_state(st)
        r = self.ea("graduate", "bulk_export")
        self.assertIn("1 identity override(s) [user_3]", r.stdout)
        self.assertIn("OFF overrides kept: user_1", r.stdout)
        self.assertNotIn("Control: user_1", r.stdout)
        r = self.ea("graduate", "bulk_export", "--approved")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state()["features"]["bulk_export"]["identity_overrides"], {"user_1": False})
        r = self.ea("graduate", "bulk_export", "--control", "user_1")
        self.assertIn("nothing to clean", r.stdout)

    def test_audit_flags_overdue_stale_and_untracked(self) -> None:
        st = copy.deepcopy(BASE)
        st["features"]["ai_summaries"]["identity_overrides"] = {"user_4": True}
        st["issues"].append({"number": 9, "title": "Revoke early access: new_dashboard for acme (due 2099-01-15)",
                             "body": "", "state": "OPEN", "labels": [], "comments": []})
        self.write_state(st)
        r = self.ea("audit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("| initech | bulk_export | segment ea-bulk_export-initech | 2026-01-01 | OVERDUE | #3 |", r.stdout)
        self.assertIn("| user_4 | ai_summaries | identity override | - | NO-EXPIRY | UNTRACKED |", r.stdout)
        self.assertIn("| acme | new_dashboard | - | 2099-01-15 | STALE (no live override) | #9 |", r.stdout)
        self.assertIn("SUMMARY env=Production grants=2 overdue=1 stale_issues=1 untracked=1", r.stdout)
        self.assertEqual(self.writes(), [])

    def test_expire_revokes_overdue_and_closes_stale(self) -> None:
        st = copy.deepcopy(BASE)
        st["issues"].append({"number": 9, "title": "Revoke early access: new_dashboard for acme (due 2099-01-15)",
                             "body": "", "state": "OPEN", "labels": [], "comments": []})
        self.write_state(st)
        r = self.ea("expire")
        self.assertEqual(r.returncode, 3)
        self.assertIn("Revoke : bulk_export for org:initech", r.stdout)
        self.assertIn("Close  : #9", r.stdout)
        self.assertEqual(self.writes(), [])
        r = self.ea("expire", "--approved")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("ea-bulk_export-initech", self.seg_names())
        self.assertEqual(self.issue(3)["state"], "CLOSED")
        self.assertEqual(self.issue(9)["state"], "CLOSED")
        r = self.ea("expire")
        self.assertIn("nothing overdue", r.stdout)


if __name__ == "__main__":
    unittest.main()
