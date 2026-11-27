# Token Measurement Results

## Live Token Counts (Flagsmith Cloud `early-access-demo` + `claude-opus-5-5`)

- **CLI Version:** `flagsmith v2.0.0`
- **Agent:** `claude 2.1.318` (`claude-opus-5-5`)
- **Skill SHA:** `ed91a7e`
- **Note:** `Input Tokens` reflects Claude Code's reported `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` across all turns in the session.

| Mode | Scenario | Turns | Input Tokens | Output Tokens | Total Tokens |
|---|---|---:|---:|---:|---:|
| `grant (org)` | S1 (skill, median of 2) | 14.5 | 605541 | 5215 | 610756 |
| `grant (org)` | S1 (no-skill baseline) | — | 610759 | 3550 | 614309 |
| `grant (user)` | S2 (skill) | 12 | 477132 | 3776 | 480908 |
| `revoke` | S3 (skill) | 11 | 417701 | 3061 | 420762 |
| `graduate` | S4 (skill) | 14 | 547411 | 4109 | 551520 |
| `audit` | S5 (skill) | 7 | 234687 | 1899 | 236586 |
| `safety (refusal)` | X2 (skill) | 6 | 191961 | 1648 | 193609 |

### Key Takeaway
In `grant (org)` (`S1`), the skill uses **fewer total input tokens than the no-skill baseline** (`605,541` vs `610,759`) while additionally enforcing the 6-line approval plan, exact snapshot, negative-control verification (`user_3`), Flagsmith segment description marker, and GitHub follow-up revoke issue.
