# Contributing `flagsmith-early-access` to the Official Flagsmith Skills Repository

Ready-to-submit PR text for upstreaming `skill/flagsmith-early-access/`. See also `skill/flagsmith-early-access/CONTRIBUTING-NOTE.md`.

## Proposed PR title

`feat(skills): add flagsmith-early-access for per-customer beta access lifecycle`

## PR description

### Summary

Adds **`flagsmith-early-access`**, a skill for per-customer and per-user early access in Flagsmith:
`grant -> verify -> track expiry -> revoke | expire | graduate`, plus read-only `audit`.

General skills manage environment-wide rollouts; this one targets one identity or one `ea-<flag>-<customer>` segment, behind an approval gate, with negative-control verification and automatic rollback.

All Flagsmith work is done by one deterministic script, `scripts/ea.sh`. `SKILL.md` (~800 words) covers intake, the approval gate and reporting.

### Included files

```text
skill/flagsmith-early-access/
  SKILL.md                  workflow, rules, modes
  CONTRIBUTING-NOTE.md      summary for the upstream maintainers
  references/
    cli-commands.md         verified CLI shapes and quirks (debugging aid)
  scripts/
    ea.sh                   detect | grant | revoke | graduate | audit | expire
```

### Modes

| Mode | Behavior |
|---|---|
| `grant` | Identity override or segment `ea-<flag>-<customer>`; verifies target ON and a control unchanged; opens a "Revoke early access" follow-up issue and comments on the source issue |
| `revoke` | Removes only that grant, verifies, closes the issue |
| `graduate` | Requires default ON; removes all `ea-<flag>-*` segments and identity overrides; closes issues |
| `audit` | Read-only; flags `OVERDUE`, `STALE`, `UNTRACKED` |
| `expire` | Revokes every overdue grant after one approval; closes stale issues |

Without `--approved`, every write is a dry run that prints the exact 6-line PLAN.

### Dependencies

- MIT licensed (repository `LICENSE`).
- `flagsmith` CLI v2 (tested with v2.0.0) and `jq`; `gh` optional (the GitHub trail is skipped without it).

### Verification

- `harness/test_ea.py`: 24 tests running the real `ea.sh` against a stateful fake Flagsmith CLI and `gh`, with fault injection.
- Live runs against Flagsmith Cloud with a two-turn approval check and live fault injection (X1 control drift, X4 midway 502): [results/scenarios.md](../results/scenarios.md), [results/tokens.md](../results/tokens.md).
- Live testing surfaced CLI quirks (the npm wrapper always exits 0, duplicate segment names are allowed, `--identifier` silently creates identities). `ea.sh` handles each; see `references/cli-commands.md`.

## Pre-merge checklist

- [ ] `skill/flagsmith-early-access/` is self-contained.
- [ ] `make lint` passes (frontmatter, word budget, `shellcheck`).
- [ ] `make test` passes, including `harness/test_ea.py`.
- [ ] Verified against `flagsmith` v2.0.0 on Flagsmith Cloud.
- [ ] Safety model documented in [safety.md](safety.md) and covered by tests.
