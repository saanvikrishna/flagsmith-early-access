"""Unit tests for flagsmith-early-access helper scripts and SKILL.md."""

import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import unittest

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"


def find_working_bash() -> str | None:
    """Return a working bash executable path, or None if unavailable."""
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        shutil.which("bash"),
    ]
    for cand in candidates:
        if not cand or not os.path.exists(cand):
            continue
        try:
            res = subprocess.run(
                [cand, "-c", "echo ok"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip() == "ok":
                return cand
        except (OSError, subprocess.SubprocessError):
            continue
    return None


BASH_BIN = find_working_bash()


class TestSkillAndScriptsStructure(unittest.TestCase):
    """Verify SKILL.md and shell script constraints."""

    def test_skill_md_frontmatter_and_word_count(self) -> None:
        skill_md = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill_md.startswith("---\n"))
        self.assertIn("name: flagsmith-early-access\n", skill_md)
        self.assertIn("description:", skill_md)
        words = len(skill_md.split())
        self.assertLessEqual(words, 2000, f"SKILL.md has {words} words (>2000)")

    def test_scripts_under_80_lines_and_strict_mode(self) -> None:
        for name in ("snapshot.sh", "verify.sh", "audit.sh"):
            path = SCRIPTS_DIR / name
            self.assertTrue(path.is_file(), f"Missing {name}")
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertLess(len(lines), 80, f"{name} has {len(lines)} lines (>=80)")
            self.assertEqual(lines[0], "#!/usr/bin/env bash")
            self.assertEqual(lines[1], "set -euo pipefail")

    @unittest.skipUnless(BASH_BIN, "No working bash available on this host")
    def test_bash_syntax_check(self) -> None:
        for name in ("snapshot.sh", "verify.sh", "audit.sh"):
            path = SCRIPTS_DIR / name
            res = subprocess.run(
                [BASH_BIN, "-n", str(path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Syntax error in {name}: {res.stderr}")


@unittest.skipUnless(BASH_BIN, "No working bash available on this host")
class TestScriptsWithMockedCLI(unittest.TestCase):
    """Run snapshot.sh, verify.sh, and audit.sh against mocked flagsmith, jq, and gh."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = pathlib.Path(self.tmp.name)
        self.bin_dir = self.tmp_path / "bin"
        self.bin_dir.mkdir()

        self._write_mock(
            "flagsmith",
            """#!/usr/bin/env bash
case "$1 $2" in
  "flag get")
    if [[ "$*" == *"--segment"* ]]; then
      echo '{"enabled":false,"feature_state_value":null,"segment_priority":0}'
    elif [[ "$*" == *"--identifier"* ]]; then
      echo '{"enabled":false,"feature_state_value":null}'
    else
      echo '{"enabled":false,"feature_state_value":null}'
    fi
    ;;
  "segment get")
    echo '{"id":10,"name":"ea-new_dashboard-acme","description":"early-access; flag=new_dashboard; customer=acme; expires=2027-01-15; issue=#1","rules":[]}'
    ;;
  "segment list")
    echo '[{"name":"ea-bulk_export-initech","description":"early-access; flag=bulk_export; customer=initech; expires=2025-01-01; issue=#2"}]'
    ;;
  "eval new_dashboard")
    if [[ "$*" == *"user_acme"* ]]; then
      echo "true"
    else
      echo "false"
    fi
    ;;
  *)
    echo "{}"
    ;;
esac
""",
        )

        self._write_mock(
            "gh",
            """#!/usr/bin/env bash
echo '[{"number":5,"title":"Revoke early access: ai_summaries for user_42 (due 2027-02-01)","url":"https://github.com/org/repo/issues/5","body":"- **Feature**: `ai_summaries`\\n- **Customer**: `user_42`\\n- **Mechanism**: `identity user_42`"}]'
""",
        )

        # Minimal Python-backed jq mock if real jq is not installed
        if not shutil.which("jq"):
            py_exe = pathlib.Path(shutil.which("python") or shutil.which("python3") or "python").as_posix()
            jq_py = self.tmp_path / "jq_mock.py"
            jq_py.write_text(
                """import json, sys
args = sys.argv[1:]
if "-cn" in args:
    obj = {}
    i = 0
    while i < len(args):
        if args[i] == "--arg":
            obj[args[i + 1]] = args[i + 2]
            i += 3
        elif args[i] == "--argjson":
            obj[args[i + 1]] = json.loads(args[i + 2])
            i += 3
        else:
            i += 1
    print(json.dumps(obj, separators=(",", ":")))
else:
    segs = json.loads(sys.stdin.read() or "[]")
    for s in segs:
        print(f"| initech | bulk_export | segment:{s['name']} | 2025-01-01 | yes | #2 |")
    print("| user_42 | ai_summaries | identity user_42 | 2027-02-01 | no | #5 |")
""",
                encoding="utf-8",
            )
            self._write_mock(
                "jq",
                f"""#!/usr/bin/env bash
exec "{py_exe}" "{jq_py.as_posix()}" "$@"
""",
            )

        self.env = os.environ.copy()
        self.env["PATH"] = f"{self.bin_dir}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["TMPDIR"] = str(self.tmp_path)
        self.env["AUDIT_TODAY"] = "2026-11-26"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_mock(self, name: str, content: str) -> None:
        path = self.bin_dir / name
        path.write_text(content, encoding="utf-8", newline="\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def _run_script(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH_BIN, str(SCRIPTS_DIR / name), *args],
            capture_output=True,
            text=True,
            env=self.env,
            timeout=15,
        )

    def test_snapshot_sh(self) -> None:
        res = self._run_script("snapshot.sh", "new_dashboard", "ea-new_dashboard-acme")
        self.assertEqual(res.returncode, 0, res.stderr)
        parts = res.stdout.strip().split(" ", 1)
        self.assertEqual(len(parts), 2)
        snap_path, summary = parts
        if os.name == "nt" and snap_path.startswith("/"):
            snap_path = subprocess.check_output(
                [BASH_BIN, "-c", f'cygpath -w "{snap_path}"'],
                text=True,
            ).strip()
        self.assertTrue(os.path.exists(snap_path), f"Missing snapshot file: {snap_path}")
        self.assertIn("segment:ea-new_dashboard-acme", summary)
        data = json.loads(pathlib.Path(snap_path).read_text(encoding="utf-8"))
        self.assertEqual(data["flag"], "new_dashboard")
        self.assertEqual(data["kind"], "segment")

    def test_verify_sh(self) -> None:
        res = self._run_script("verify.sh", "new_dashboard", "user_acme", "user_globex")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "TARGET=true CONTROL=false")

    def test_audit_sh(self) -> None:
        res = self._run_script("audit.sh")
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.strip().splitlines()
        self.assertGreaterEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("| Customer | Feature |"))
        self.assertIn("initech", res.stdout)
        self.assertIn("yes", res.stdout)
