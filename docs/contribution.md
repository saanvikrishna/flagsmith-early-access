# Contributing `flagsmith-early-access` to the Official Flagsmith Skills Repository

This document provides the ready-to-submit Pull Request specification and verification record for upstreaming `skill/flagsmith-early-access/` into the official Flagsmith skills repository.

---

## Proposed PR Title

`feat(skills): add flagsmith-early-access for per-customer beta access lifecycle`

---

## PR Description

### Summary

Adds the self-contained **`flagsmith-early-access`** skill (`skill/flagsmith-early-access/`) for managing per-customer and per-user early access in Flagsmith across the complete lifecycle:

**`grant` -> `verify` -> `record` -> `expire` -> `revoke` or `graduate`** (plus read-only **`audit`**)

While general Flagsmith skills manage environment-wide rollouts, `flagsmith-early-access` targets individual identities and scoped `ea-<flag>-<customer>` segments with strict blast-radius, human-approval, negative-control, and snapshot-rollback guardrails.

### Included Files

```text
skill/flagsmith-early-access/
├── SKILL.md                        # Core workflow, safety rules, and 4 modes (< 2,000 words)
├── CONTRIBUTING-NOTE.md            # License, CLI version tested, modes, and token summary
├── references/
│   ├── cli-commands.md             # Flagsmith CLI v2.0.0 commands with --json --jq filters
│   ├── identity-detection.md       # Codebase scanning rules for identity & trait conventions
│   └── trail-templates.md          # GitHub issue comment & expiry follow-up templates
└── scripts/
    ├── snapshot.sh                 # Pre-write state snapshot for exact rollback
    ├── verify.sh                   # Target ON/OFF + negative-control verification
    ├── audit.sh                    # Read-only active/expired ea-* segment & issue report
    └── test_scripts.py             # Unit & safety tests for helper scripts
```

### Supported Modes

1. **`grant`** — Detects the application's identity/trait convention, presents a fixed 6-line approval plan, grants a single identity override or `ea-<flag>-<customer>` segment, verifies target ON and negative control unchanged (rolling back via snapshot on mismatch), and records a GitHub issue trail + expiry follow-up.
2. **`revoke`** — Snapshots state, removes only the target early-access override/segment, verifies target OFF and negative control unchanged, and closes the follow-up issue.
3. **`graduate`** — Confirms the environment default is ON, cleans up all `ea-<flag>-*` segments and identity overrides, verifies default behavior, and closes related `early-access` issues.
4. **`audit`** — Read-only report of all active and overdue `ea-*` segments and `early-access` GitHub issues.

### Compatibility & Dependencies

- **License:** MIT (matching `LICENSE` at repository root).
- **Flagsmith CLI:** Tested live against `flagsmith v2.0.0` (`--json --jq` output filtering and `--no-input` automation).
- **External Tools:** `jq` (JSON filtering), `gh` (GitHub CLI for issue trail & expiry tracking).

### Verification Summary

- **Live Flagsmith Cloud Runs (`results/demo-run.md`, `results/scenarios.md`):** **6/6 PASS** at skill SHA `ed91a7e` using `flagsmith v2.0.0` and `claude-opus-5-5` across `S1` (`grant org`, 2 runs), `S2` (`grant user`), `S3` (`revoke`), `S4` (`graduate`), `S5` (`audit`), and `X2` (environment-wide safety refusal).
- **Live Token Efficiency (`results/tokens.md`):**
  - `grant (org)` (`S1`, median of 2): `605,541` input tokens (fewer than `610,759` no-skill baseline) | `5,215` output tokens
  - `grant (user)` (`S2`): `477,132` input | `3,776` output
  - `revoke` (`S3`): `417,701` input | `3,061` output
  - `graduate` (`S4`): `547,411` input | `4,109` output
  - `audit` (`S5`): `234,687` input | `1,899` output
  - `safety (refusal)` (`X2`): `191,961` input | `1,648` output
- **Offline Regression Suite (`results/scenarios.md`):** **45/45 PASS** (3 runs each across 10 core scenarios `S1–S10` and 5 adversarial safety tests `X1–X5`).
- **Unit & Integration Suites (`.github/workflows/ci.yml`):** **55/55 PASS** across `demo-app` (12), `demo-seed` (7), `scripts` (6), `harness` (10), `self-hosted` (3), `tui` (10), and `vscode-extension` (7).

---

## Pre-Merge Checklist

- [x] Skill folder `skill/flagsmith-early-access/` is self-contained with zero external repo dependencies.
- [x] License is MIT-compatible (`LICENSE` + `CONTRIBUTING-NOTE.md`).
- [x] Verified live against Flagsmith CLI `v2.0.0` and Flagsmith Cloud (`early-access-demo`).
- [x] All 4 modes (`grant`, `revoke`, `graduate`, `audit`) documented with `--json --jq` examples.
- [x] Safety guardrails enforced and tested: 6-line human approval gate, negative-control verification, automatic snapshot rollback, and prompt-injection isolation.
- [x] `SKILL.md` frontmatter and `< 2,000`-word budget validated; `shellcheck` clean on all `scripts/*.sh`.
- [x] Full CI suite (`55/55`), Offline Regression Suite (`45/45`), and Live Flagsmith Cloud runs (`6/6`) verified green.
