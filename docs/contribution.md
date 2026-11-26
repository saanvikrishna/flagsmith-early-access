# Contributing `flagsmith-early-access` to the Official Flagsmith Skills Repository

This document provides the ready-to-open Pull Request description and verification checklist for contributing `skill/flagsmith-early-access/` to the official Flagsmith skills repository.

---

## Proposed PR Title

`feat(skills): add flagsmith-early-access for per-customer beta access lifecycle`

---

## PR Description

### Summary

Adds the self-contained **`flagsmith-early-access`** skill (`skill/flagsmith-early-access/`) for managing per-customer and per-user early access in Flagsmith across the full lifecycle:

**`grant` → `verify` → `record` → `expire` → `revoke` or `graduate`** (plus read-only **`audit`**)

While general Flagsmith skills operate at the environment level, `flagsmith-early-access` targets individual identities and scoped `ea-<flag>-<customer>` segments with strict blast-radius, human-approval, and rollback guardrails.

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

1. **`grant`** — Detects the app's identity/trait convention, presents a fixed 6-line approval plan, grants a single identity override or `ea-<flag>-<customer>` segment, verifies target ON and negative control OFF (rolling back via snapshot on failure), and records a GitHub issue trail + expiry follow-up.
2. **`revoke`** — Snapshots state, removes only the target early-access override/segment, verifies target OFF and negative control unchanged, and closes the follow-up issue.
3. **`graduate`** — Confirms the environment default is ON, cleans up all `ea-<flag>-*` segments and overrides, verifies default behavior, and closes related `early-access` issues.
4. **`audit`** — Read-only report of all active and overdue `ea-*` segments and `early-access` GitHub issues.

### Compatibility & Dependencies

- **License:** MIT (matching `LICENSE` at repository root).
- **Flagsmith CLI:** Tested against `flagsmith v2.0.0` (`--json` / `--jq` output filtering).
- **External Tools:** `jq` (JSON filtering), `gh` (optional, for GitHub issue trail & expiry tracking).

### Verification Summary

- **Safety & Script Tests:** `skill/flagsmith-early-access/scripts/test_scripts.py` covers snapshot/rollback, negative-control failure detection, and audit formatting.
- **Scenario Harness (`harness/run.py`):** **45/45 passed** in `mock` mode at skill SHA `86562ea` (3 runs each across 10 core scenarios `S1–S10` and 5 adversarial/safety scenarios `X1–X5`; see `results/scenarios.md`).
- **Token Efficiency (`results/tokens.md`, `mock` mode):**
  - `grant (org)`: 2,430 total tokens vs. 5,350 baseline
  - `grant (user)`: 2,260 total tokens vs. 4,500 baseline
  - `revoke`: 2,040 total tokens vs. 4,500 baseline
  - `graduate`: 1,970 total tokens vs. 4,500 baseline
  - `audit`: 1,360 total tokens vs. 4,500 baseline
- **Live Cloud Note:** End-to-end live Flagsmith Cloud + Anthropic API execution is documented in `docs/BLOCKERS.md` (pending human checkpoints H1–H3).

---

## Pre-Merge Checklist

- [x] Skill folder `skill/flagsmith-early-access/` is self-contained (no external repo dependencies).
- [x] License is MIT-compatible (`LICENSE` + `CONTRIBUTING-NOTE.md`).
- [x] Tested against Flagsmith CLI `v2.0.0`.
- [x] All 4 modes (`grant`, `revoke`, `graduate`, `audit`) documented with `--json --jq` examples.
- [x] Safety guardrails enforced: 6-line human approval gate, negative-control verification, automatic snapshot rollback, and prompt-injection resistance for issue bodies.
- [x] Helper script unit/safety tests (`scripts/test_scripts.py`) pass.
- [x] Scenario harness (`harness/run.py`) passes 45/45 in `mock` mode (`results/scenarios.md`).
- [ ] Live Flagsmith Cloud + Anthropic API run verified after human checkpoints H1–H3 (`docs/BLOCKERS.md`).
- [ ] Human review & PR submission to the official Flagsmith skills repository (once public/target branch is confirmed).
