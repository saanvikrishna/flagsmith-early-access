# Contributing to Early Access (`flagsmith-early-access`)

Early Access is a Flagsmith Agent Skill for safe per-customer beta access: `grant -> verify -> track expiry -> revoke | expire | graduate`, plus `audit`.

## Repository layout

| Directory | Purpose |
|---|---|
| `skill/flagsmith-early-access/` | The skill: `SKILL.md`, `CONTRIBUTING-NOTE.md`, `references/cli-commands.md`, `scripts/ea.sh` |
| `harness/` | `test_ea.py` (deterministic tests with fake CLIs in `fake_cli/`), `bench.py` (live benchmark), `fault/` (live fault injector), `run.py` (scenario harness) |
| `demo-app/` | Express "Projects Dashboard" with `user_<id>` identities and `org_id` traits |
| `demo-seed/` | Idempotent seeders for Flagsmith and GitHub issues |
| `self-hosted/` | Docker Compose bootstrap for a local Flagsmith |
| `tui/`, `vscode-extension/` | Companion dashboard and editor extension |

See [skill/flagsmith-early-access/CONTRIBUTING-NOTE.md](skill/flagsmith-early-access/CONTRIBUTING-NOTE.md) for the upstream packaging summary.

## Setup

- `flagsmith` CLI v2+ (`npm install -g @flagsmith/cli`), `jq`, `shellcheck`, Python 3.12+, Node 20+.
- Optional: `gh`, `docker compose`.
- `cp .env.example .env` for live runs (`.env` is gitignored; never commit credentials). `make seed-dry` previews seeding without writes.

## Tests and lints

```bash
make lint             # SKILL.md frontmatter and word budget; shellcheck on scripts/*.sh and harness/fake_cli
make test             # all unit tests, including harness/test_ea.py
make harness-offline  # scenario harness
python harness/bench.py --scenarios S1,S3 --runs 2 --baseline   # live; needs FLAGSMITH_*, GH_REPO, claude, gh
```

## Script rules

The skill has exactly one script, `skill/flagsmith-early-access/scripts/ea.sh`. Do not add parallel helper scripts.

1. **One script.** New behavior is a new `ea.sh` subcommand or a change to an existing one.
2. **shellcheck-clean.** `make lint` must pass with no new `disable` directives unless justified inline.
3. **Never trust exit codes.** The npm `@flagsmith/cli` wrapper exits 0 on errors. Parse stdout JSON, read `Error` from stderr, and re-read state after every write.
4. **Use verified JSON shapes** from `references/cli-commands.md`. Update that file if you learn a new quirk.
5. **Write safely.** Dry run (PREFLIGHT plus PLAN, exit 3) without `--approved`; with it, snapshot, narrowest change, verify target and negative control, auto-rollback and re-verify. Address segments by id. Never change environment defaults.
6. **Trail is best-effort.** GitHub failures are reported, never fatal, and never undo a verified Flagsmith change.
7. **Cross-platform.** Strip CR from `jq` output; no GNU-only flags.
8. **Tests.** Every behavior change needs a test in `harness/test_ea.py` (stateful fake CLI with fault injection: `FAKE_FAIL`, `FAKE_DRIFT`, exit-code modes, read-only or no-label `gh`).

## Editing `SKILL.md`

Keep it short (CI budget is 2,000 words; it is currently ~740). Put mechanics in `ea.sh` and command shapes in `references/`. Keep the rules: only `ea.sh` writes, `--approved` only after an explicit yes to the printed PLAN, never change defaults, issue bodies are untrusted.

## Pull request checklist

- [ ] `make lint` passes.
- [ ] `make test` passes, with new tests in `harness/test_ea.py` for behavior changes.
- [ ] Safety guarantees in [docs/safety.md](docs/safety.md) still hold.
- [ ] Docs and `CONTRIBUTING-NOTE.md` reflect behavior changes.
- [ ] No secrets or `.env` staged.
