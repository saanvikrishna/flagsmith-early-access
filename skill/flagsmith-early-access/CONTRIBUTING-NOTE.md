# Contributing Note: `flagsmith-early-access`

Note for merging this skill into the official Flagsmith skills repository.

## What it does

Manages per-customer and per-user early access to a Flagsmith feature: `grant -> verify -> track expiry -> revoke | expire | graduate`, plus read-only `audit`. It targets one identity override or one segment `ea-<flag>-<customer>`; it never changes environment defaults.

All Flagsmith and GitHub work is done by one deterministic script, `scripts/ea.sh`. `SKILL.md` (~740 words) handles intake, the approval gate and reporting.

## Dependencies

- `flagsmith` CLI v2 (tested with v2.0.0) and `jq`.
- `gh` is optional; without it the GitHub trail is skipped and reported.
- License: MIT.

## Modes

| Mode | Purpose |
|---|---|
| `grant` | Identity override or segment `ea-<flag>-<customer>`; verifies target and a negative-control identity; creates a "Revoke early access: <flag> for <customer> (due YYYY-MM-DD)" follow-up issue and comments on the source issue |
| `revoke` | Removes that grant, verifies, closes the issue |
| `graduate` | Default must be ON; removes all `ea-<flag>-*` segments and identity overrides; closes issues |
| `audit` | Read-only table; flags `OVERDUE`, `STALE` (open issue, no live override) and `UNTRACKED` (override, no issue) |
| `expire` | Revokes every overdue grant after one approval; closes stale follow-up issues |

`ea.sh` also has `detect` (which trait identifies a customer).

## Safety model

- Without `--approved`, every write command is a read-only dry run that prints a `PREFLIGHT` line and the exact 6-line `PLAN`, then exits 3. The agent passes `--approved` only after an explicit yes.
- With `--approved`: snapshot, narrowest change (by segment id), verify target and a negative-control identity, auto-rollback and re-verify on any failure.
- Never trusts CLI exit codes: the npm `@flagsmith/cli` wrapper always exits 0, even on errors. It parses stdout and stderr and re-reads state after writes.
- Refuses duplicate segment names and user grants to unknown identities (the CLI would silently create one).
- Issue bodies are treated as untrusted data.
- Details: `docs/safety.md`; CLI shapes and quirks: `references/cli-commands.md`.

## How it was tested

- `harness/test_ea.py`: 24 tests running the real `ea.sh` against a stateful fake Flagsmith CLI and `gh`, with fault injection (midway CLI error, control drift, exit-code modes, read-only and no-label `gh`).
- Live runs against Flagsmith Cloud via `harness/bench.py` (two-turn approval, "wrote before approval" check, live X1 control drift and X4 midway 502 faults), compared against a no-skill baseline. Results: `results/tokens.md`, `results/scenarios.md`.
- `shellcheck` is clean on `scripts/ea.sh`.

## Token efficiency

`SKILL.md` is ~740 words; the script prints a few compact lines per step so the agent never reads raw CLI JSON; reads run in parallel inside the script. See `results/tokens.md` for measured numbers.
