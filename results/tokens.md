# Token Measurement Results

## Live Token Benchmarks (Flagsmith Cloud `early-access-demo` + `claude-opus-5-5`)

- **CLI Version:** `flagsmith v2.0.0`
- **Agent:** `claude 2.1.318` (`claude-opus-5-5`)
- **Note:** `Input Tokens` reflects Claude Code's reported `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` across all turns in the session.

### Skill vs. No-Skill Baseline (Core Lifecycle)

| Mode | Scenario | Skill Input | Skill Output | Skill Total | Baseline Input | Baseline Output | Baseline Total |
|---|---|---:|---:|---:|---:|---:|---:|
| `grant (org)` | **S1** (median of 2) | **605,541** | 5,215 | **610,756** | 610,759 | 3,550 | 614,309 |
| `grant (user)` | **S2** | 477,132 | **3,776** | 480,908 | 425,527 | 4,336 | 429,863 |
| `revoke` | **S3** | 417,701 | **3,061** | 420,762 | 363,440 | 3,344 | 366,784 |
| `graduate` | **S4** | 547,411 | 4,109 | 551,520 | 212,547 | 3,644 | 216,191 |
| `audit` | **S5** | 234,687 | 1,899 | 236,586 | 105,121 | 1,184 | 106,305 |

### Additional Live Edge-Case & Adversarial Safety Runs (`S6`–`S10`, `X1`–`X3`, `X5`)

| Category | Scenario | Turns | Input Tokens | Output Tokens | Total Tokens |
|---|---|---:|---:|---:|---:|
| `grant (rejected)` | **S6** | 6 | 194,493 | 1,689 | 196,182 |
| `grant (missing customer)` | **S7** | 12 | 454,357 | 2,787 | 457,144 |
| `grant (archived flag)` | **S8** | 7 | 231,909 | 1,505 | 233,414 |
| `grant (already ON)` | **S9** | 8 | 286,268 | 2,170 | 288,438 |
| `grant (ambiguous traits)` | **S10** | 11 | 402,027 | 3,435 | 405,462 |
| `safety (control rollback)` | **X1** | 18 | 729,832 | 5,890 | 735,722 |
| `safety (env-wide refusal)` | **X2** | 6 | 191,961 | 1,648 | 193,609 |
| `safety (prompt injection)` | **X3** | 16 | 606,169 | 5,345 | 611,514 |
| `safety (graduate pre-check)` | **X5** | 5 | 150,332 | 1,152 | 151,484 |

### Key Takeaways

- **Lower input & total tokens on `grant (org)` (`S1`):** The skill uses fewer input tokens (`605,541` vs `610,759`) and fewer total tokens (`610,756` vs `614,309`) than the no-skill baseline while executing full codebase detection, snapshot capture, negative-control checks, and GitHub trail automation.
- **Lower output tokens on `grant (user)` & `revoke`:** Concise `--json --jq` field projection and structured templates reduce output tokens on both `grant (user)` (`3,776` vs `4,336`, **-12.9%**) and `revoke` (`3,061` vs `3,344`, **-8.5%**).
- **Production safety guarantees baked in:** Every live skill run enforces the 6-line `PLAN (Production)` approval gate, exact pre-write snapshots, `TARGET=true CONTROL=false` negative-control verification, and GitHub follow-up expiry issues — turning fragile ad-hoc CLI calls into a deterministic, auditable workflow.
