# Design: `flagsmith-early-access`

Per-customer early access for Flagsmith: `grant -> verify -> track expiry -> revoke | expire | graduate`, plus read-only `audit`.
CLI shapes and quirks are in [verified-facts.md](verified-facts.md) and `skill/flagsmith-early-access/references/cli-commands.md`.

## 1. Division of labour

The agent talks to the human; one script touches Flagsmith.

| Layer | Owns |
|---|---|
| `SKILL.md` (~800 words) | Intake (issue or chat), the approval gate, relaying output, untrusted-issue handling, the 3-line report |
| `scripts/ea.sh` | Every Flagsmith and GitHub operation: identity resolution, preflight, snapshot, write, verify, rollback, trail |

Why: the judgment calls (who is the customer, did the human say yes) need a model; the multi-step, failure-prone mechanics do not. Moving them into a deterministic script makes them testable (section 8) and keeps the agent's context small. The agent is told never to run Flagsmith writes itself.

## 2. Subcommands

| Command | Effect |
|---|---|
| `detect [--dir D]` | Local grep: which trait (`org_id`, `tenant_id`, ...) names a customer. Prints `trait=`, `ambiguous` or `none` |
| `grant <flag> org:<c>\|user:<id> --expires YYYY-MM-DD [--issue N] [--trait T] [--target ID] [--control ID]` | Add early access |
| `revoke <flag> org:<c>\|user:<id> [--issue N]` | Remove it and close the follow-up issue |
| `graduate <flag>` | After the default is ON: remove every `ea-<flag>-*` segment and identity override, close issues |
| `audit` | Read-only table with `OVERDUE`, `STALE`, `UNTRACKED` |
| `expire` | Revoke every overdue grant after one approval; close stale follow-up issues |

Exit codes: 0 ok, 3 stopped or rolled back, 2 usage. Every `STOP <reason>` line is a clean, no-change exit.

## 3. Grant mechanism: narrowest blast radius

| Scope | Mechanism |
|---|---|
| One user (`user:<id>`) | Identity override on the feature. Refused if the identity does not already exist (a typo would silently create one) |
| A customer (`org:<c>`) | Segment `ea-<flag>-<customer>` (rule: `<trait> EQUAL <customer>`) plus a segment override. All current and future members get access; pre-existing segments such as `internal_staff` are untouched |

The environment default is never changed, and `grant` stops if the default is already ON. All writes address segments by **id**, because the CLI allows duplicate segment names and name-based commands then fail as ambiguous. `ea.sh` refuses to create a duplicate and stops if one exists.

## 4. Discovery without a database

- **Org grants** are found by segment name `ea-<flag>-<customer>` and a description marker:
  `early-access; flag=<flag>; customer=<customer>; expires=<YYYY-MM-DD>; issue=#<n>`.
- **User grants** (identity overrides carry no description) are found via `flag list --feature <f> --identities` and matched to a GitHub follow-up issue.
- **The follow-up issue** is titled `Revoke early access: <flag> for <customer> (due YYYY-MM-DD)`. `ea.sh` tracks issues **by title**, so it works even when the `gh` account cannot apply the `early-access` label (the label is attempted; if that fails the issue is created unlabeled and the output says so).

`audit` joins the two sources and flags:

| Flag | Meaning |
|---|---|
| `OVERDUE` | Expiry date has passed |
| `STALE` | An open follow-up issue exists but no live override does |
| `UNTRACKED` | An identity override exists with no follow-up issue |

## 5. Identity and control resolution

`ea.sh` resolves identities from Flagsmith itself (edge-identities API plus traits, falling back to the core identities API on self-hosted), scanning up to `EA_MAX_SCAN` (default 40) identities with reads run in parallel (`EA_JOBS`, default 8).

- **Target** for an org grant: the first identity whose trait equals the customer (or `--target`, validated against the trait).
- **Negative control:** an identity whose trait is a *different* customer and whose current state equals the default (or `--control`). It must not be in the customer.
- Verification evaluates persisted traits only (never `--trait`), so real drift shows up.

## 6. Approval gate

Without `--approved`, every write command is a read-only dry run: a `PREFLIGHT` line, the exact 6-line `PLAN`, then exit 3.

```text
PLAN (<environment>)
Change : add segment override ea-<flag>-<customer> -> <flag> ON
Who    : <trait> = <customer> (<target> + others in <customer>)
Control: <control> (<trait>=<other>) must stay OFF
Expires: <YYYY-MM-DD> (follow-up issue will be created)
Undo   : ea.sh revoke <flag> org:<customer> --approved
Approve? (yes/no)
```

The agent shows it verbatim, waits for an explicit yes, and re-runs the identical command with `--approved`. `expire` prints one plan listing every revoke and every stale issue to close.

## 7. Snapshot, verify, rollback, trail

With `--approved`:

1. **Snapshot** the flag's default, segment overrides, identity overrides and `ea-<flag>-*` segments to a JSON file (path printed).
2. **Apply** the single narrowest change.
3. **Verify** target and control by evaluating both. Grant: target ON, control unchanged. Revoke: target back to default, control unchanged.
4. **Roll back** on any failure (write error, wrong target, control drift): remove what was added, or restore what was removed (reusing the segment id rather than creating a duplicate), then **re-verify**. Output is `ROLLED BACK ... verified` or `ROLLBACK INCOMPLETE ... restore manually from <snapshot>`.
5. **Trail** (never blocks or undoes the Flagsmith result): create the follow-up issue and comment on the source issue; on revoke, graduate and expire, close the issues. Without `gh`, it prints `TRAIL skipped`.

### Never trust exit codes

The npm `@flagsmith/cli` wrapper always exits 0, even on errors; the native binary exits 1. `ea.sh` therefore parses stdout JSON, treats a line starting with `Error` on stderr as failure, and re-reads state after writes.

## 8. Testing and benchmarking

- `harness/test_ea.py` runs the real `ea.sh` against a stateful fake Flagsmith CLI and `gh` (`harness/fake_cli/`) with fault injection (`FAKE_FAIL` midway CLI error, `FAKE_DRIFT` control drift, exit-code modes, read-only `gh`, no-label `gh`): 24 tests.
- `harness/bench.py` is the live benchmark against Flagsmith Cloud: a two-turn approval (the agent must stop and show the PLAN; the harness then resumes with yes or no) that records whether anything was written before approval. `harness/fault/flagsmith` injects live faults for skill and baseline alike (X1 real mid-flight control drift, X4 midway 502).
- Results: [results/tokens.md](../results/tokens.md), [results/scenarios.md](../results/scenarios.md).

## 9. Token efficiency

- `SKILL.md` is ~800 words; the mechanics live in `ea.sh`, not in the prompt.
- `ea.sh` emits a few compact lines (`PREFLIGHT`, `PLAN`, `APPLIED`, `VERIFY`, `TRAIL`), so the agent never reads raw CLI JSON.
- Reads run in parallel inside the script, not as agent turns.
- `references/cli-commands.md` is read only when `ea.sh` reports something unexpected.
