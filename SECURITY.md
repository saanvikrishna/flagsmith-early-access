# Security Policy

**Early Access** (`flagsmith-early-access`) operates on live feature-flag environments and GitHub issue trackers. Blast-radius containment is built into the skill's script and into CI.

## 1. Credential hygiene

- **Never commit secrets.** `FLAGSMITH_API_KEY`, the environment SDK keys, `GH_TOKEN` and `ANTHROPIC_API_KEY` belong in environment variables or a gitignored `.env`. `.env.example` is an empty template.
- **CI scanning.** Every pull request and push to `main` runs `gitleaks/gitleaks-action@v2` over full history (`.github/workflows/ci.yml`).
- **No secrets in output.** `ea.sh` prints compact status lines only; the skill tells the agent never to echo credentials or full JSON into chat or issue comments.

## 2. Runtime guardrails

All Flagsmith writes go through `skill/flagsmith-early-access/scripts/ea.sh`.

| Control | Mechanism |
|---|---|
| Approval gate | Without `--approved`, write commands are read-only dry runs that print the 6-line `PLAN` and exit 3. The agent passes `--approved` only after an explicit yes |
| Narrowest blast radius | One identity override or one `ea-<flag>-<customer>` segment. Environment defaults, other flags and other segments are never touched |
| Negative control | A control identity outside the customer is evaluated after every write and must be unchanged |
| Snapshot and rollback | State is snapshotted before the write; any failure triggers rollback and re-verification |
| Exit codes not trusted | The npm CLI wrapper exits 0 on errors, so `ea.sh` parses stdout and stderr and re-reads state |
| Input validation | Refuses duplicate segment names, unknown identities, past or malformed expiry, and archived or missing features |
| Prompt-injection isolation | Issue bodies are untrusted: only customer, feature, expiry and environment are used; embedded instructions are ignored and reported |
| Least GitHub privilege | The trail never blocks a Flagsmith result; it works with a read-only or label-less `gh` account (reported, not fatal) |

Details and tests: [docs/safety.md](docs/safety.md).

## 3. Supported versions

| Component | Supported |
|---|---|
| `flagsmith-early-access` skill | `main`, with Flagsmith CLI `v2.0.0+` and `jq` (`gh` optional) |
| `demo-app` | Node.js `>= 20` |
| Python tooling (`demo-seed`, `harness`, `tui`, `self-hosted`) | Python `3.12+` |

## 4. Reporting a vulnerability

If you find a credential exposure or a safety-guardrail bypass:

1. Do not open a public issue with exploit details or tokens.
2. Rotate any exposed credentials in Flagsmith, GitHub or Anthropic.
3. Report privately through GitHub Security Advisories on this repository, with the affected component (`skill/`, `harness/`, `demo-app/`, `tui/`), reproduction steps or a failing test, and expected versus observed state.

Fixes affecting production flag safety or credential handling are prioritized.
