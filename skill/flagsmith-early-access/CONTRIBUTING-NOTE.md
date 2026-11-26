# Contributing Note: `flagsmith-early-access`

- **License**: MIT (compatible with the official Flagsmith skills repository).
- **CLI Version Tested**: `flagsmith v2.0.0` (verified against `flagsmith` Go/npm CLI v2.0.0).
- **Dependencies**: `flagsmith` CLI v2.0.0+, `jq`, `gh` (GitHub CLI, optional for issue trail).

## What It Does

`flagsmith-early-access` automates the full per-customer early-access lifecycle in Flagsmith:

**grant -> verify -> record -> expire -> revoke or graduate** (+ read-only **audit**)

### Supported Modes

| Mode | Purpose |
|---|---|
| `grant` | Grants a single user (identity override) or company (`ea-<flag>-<customer>` segment) early access, verifies with a negative control, and opens an expiry follow-up issue. |
| `revoke` | Snapshots, removes the early-access override/segment, verifies target is off and control is unchanged, and closes the follow-up issue. |
| `graduate` | Confirms the environment default is ON, cleans up all `ea-<flag>-*` segments and identity overrides, verifies default behavior, and closes related `early-access` issues. |
| `audit` | Read-only table of all active/expired `ea-*` segments and `early-access` issues, flagging overdue grants. |

## Safety & Verification

- Enforces smallest blast radius (1 identity or 1 `ea-<flag>-<customer>` segment; never touches environment defaults or unrelated segments like `internal_staff`).
- Requires human approval via a fixed 6-line plan before production writes.
- Mandatory negative-control verification with automatic snapshot rollback on failure.
- Prompt-injection resistant when reading GitHub issue bodies.

## Token Efficiency

- `SKILL.md` is kept concise (< 2,000 words) with command catalogs, identity detection patterns, and issue templates separated into `references/`.
- Every CLI call uses `--json --jq` to return only the fields needed for the next step.
- Helper scripts (`scripts/snapshot.sh`, `scripts/verify.sh`, `scripts/audit.sh`) collapse multi-step operations into single-line summaries.
