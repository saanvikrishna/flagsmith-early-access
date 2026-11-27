# Security Policy

**Early Access** (`flagsmith-early-access`) operates directly against live feature-flag environments and GitHub issue trackers. Security and blast-radius containment are built into both the skill runtime and CI pipeline.

---

## 1. Credential Hygiene & Secret Scanning

- **Never commit secrets:** API keys, SDK keys, and personal access tokens (`FLAGSMITH_API_KEY`, `FLAGSMITH_ENV_KEY_PROD`, `FLAGSMITH_ENV_KEY_DEV`, `GH_TOKEN`, `ANTHROPIC_API_KEY`) must stay in environment variables or a local `.env` file (excluded via `.gitignore`). Use `.env.example` strictly as an empty template.
- **Automated CI scanning:** Every pull request and push to `main` runs `gitleaks/gitleaks-action@v2` across full git history (`fetch-depth: 0`) in `.github/workflows/ci.yml`.
- **Zero-secret agent output:** The skill instructs coding agents never to echo credentials, tokens, or full environment dumps into chat summaries or GitHub issue comments.

---

## 2. Runtime Guardrails

Every mutating workflow in `skill/flagsmith-early-access/` enforces five defense-in-depth controls:

| Control | Mechanism | Guarantee |
|---|---|---|
| **Human Approval Gate** | Fixed 6-line `PLAN` (`Change`, `Who`, `Control`, `Expires`, `Undo`, `Approve? (yes/no)`) | Zero Production mutations occur without explicit `yes` confirmation from a human operator. |
| **Narrowest Blast Radius** | `--identifier <id>` or dedicated `ea-<flag>-<customer>` segment | Environment defaults, unrelated flags, and pre-existing segments (e.g., `internal_staff`) are untouched. Environment-wide `grant` requests are refused. |
| **Negative-Control Verification** | Dual `flagsmith evaluate` check (target identity + unrelated control identity) | Confirms the target matches the intended state and the control identity remains unchanged. |
| **Exact Snapshot Rollback** | Pre-write state capture via `scripts/snapshot.sh` | Any verification mismatch or partial failure triggers immediate restoration of the pre-change state and re-verification. |
| **Prompt-Injection Isolation** | Strict structured-field parsing on GitHub issue bodies | External text is treated as untrusted data; only `customer`, `feature`, `environment`, `expires`, and `requester` are extracted, while embedded override instructions are ignored and surfaced in the summary. |

---

## 3. Supported Versions

| Component | Supported Version |
|---|---|
| `flagsmith-early-access` skill | `main` (Flagsmith CLI `v2.0.0+`) |
| `demo-app` | Node.js `>= 20.0.0` |
| Python tooling (`demo-seed`, `harness`, `tui`, `self-hosted`) | Python `3.12+` |

---

## 4. Reporting a Vulnerability

If you discover a security issue, credential exposure, or safety-guardrail bypass:

1. **Do not open a public GitHub issue** with exploit details or sensitive tokens.
2. **Rotate any exposed credentials immediately** in Flagsmith, GitHub, or Anthropic consoles.
3. **Report privately** via GitHub Security Advisories on this repository with:
   - Affected component (`skill/`, `scripts/`, `demo-app/`, `harness/`, or `tui/`).
   - Reproduction steps or failing adversarial test case.
   - Expected vs. observed state.

We acknowledge security reports promptly and prioritize fixes affecting Production flag safety or credential handling.
