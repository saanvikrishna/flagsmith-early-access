# Contributing to Early Access (`flagsmith-early-access`)

Thank you for contributing to **Early Access** — the per-customer Flagsmith Agent Skill for safe beta access management (`grant -> verify -> record -> expire -> revoke or graduate`, plus `audit`).

---

## Repository Layout

| Directory | Purpose |
|---|---|
| `skill/flagsmith-early-access/` | Self-contained Agent Skill (`SKILL.md`, `CONTRIBUTING-NOTE.md`, `references/`, `scripts/`) |
| `demo-app/` | Express B2B "Projects Dashboard" demonstrating `user_<id>` identities and `org_id` traits |
| `demo-seed/` | Idempotent Python standard-library seeders for Flagsmith (`seed_flagsmith.py`) and GitHub issues (`seed_issues.py`) |
| `harness/` | Scenario verification suite (`S1–S10`, `X1–X5`) supporting offline regression and live cloud runs |
| `self-hosted/` | Docker Compose bootstrap and local open-source Flagsmith stack |
| `tui/` | Zero-dependency terminal dashboard (`ea_dashboard.py`) for inspecting early-access segments and overrides |
| `vscode-extension/` | VS Code companion extension for managing early-access flags from the editor |

See [skill/flagsmith-early-access/CONTRIBUTING-NOTE.md](skill/flagsmith-early-access/CONTRIBUTING-NOTE.md) for the upstream skill packaging summary.

---

## Development Setup

### Prerequisites

- **Flagsmith CLI**: `flagsmith` `v2.0.0+` (`npm install -g @flagsmith/cli`)
- **Utilities**: `jq`, `shellcheck`, `python3` (`3.12+`), `node` (`>= 20`)
- **Optional (issue trail & live runs)**: `gh` (GitHub CLI), `docker compose`

### Environment Configuration

Copy `.env.example` to `.env` for local live testing (`.env` is gitignored — never commit credentials):

```bash
cp .env.example .env
```

Preview seed state without making external writes:

```bash
make seed-dry
```

---

## Running Tests & Lints

Run the full unit, integration, and lint suites with `make`:

```bash
make lint             # Validate SKILL.md frontmatter/word count and shellcheck scripts/*.sh
make test             # Run all Python, demo-app, and VS Code extension tests
make harness-offline  # Run the Offline Regression Suite (S1–S10 & X1–X5, 3 runs each)
```

For live verification against Flagsmith Cloud and GitHub:

```bash
make harness-live
```

---

## Extending the Skill

All skill changes live inside `skill/flagsmith-early-access/` and follow the Flagsmith CLI `v2.0.0` and Agent Skills conventions:

1. **Keep `SKILL.md` focused (< 2,000 words):** Place core workflows, safety invariants, and the 6-line approval gate in `skill/flagsmith-early-access/SKILL.md`. Move detailed command catalogs, detection patterns, and comment templates into `skill/flagsmith-early-access/references/`.
2. **Follow Flagsmith CLI `v2.0.0` standards:**
   - Pass `--json --jq '<expr>'` on every `flagsmith` command to keep agent context minimal.
   - Pass `--no-input` (and `--yes` on confirmed deletes) so non-interactive execution stays deterministic.
   - Target only `--identifier <id>` or a scoped `ea-<flag>-<customer>` segment; never modify environment defaults in `grant` mode.
3. **Keep helper scripts POSIX-clean & concise:** Scripts in `skill/flagsmith-early-access/scripts/` must pass `shellcheck`, emit single-line summaries where appropriate, and include unit coverage in `skill/flagsmith-early-access/scripts/test_scripts.py`.
4. **Preserve safety guarantees:** Any new mode or sub-workflow must uphold the 6-line Production approval plan, negative-control verification, exact snapshot rollback, and prompt-injection isolation documented in [docs/safety.md](docs/safety.md).

---

## Pull Request Checklist

- [ ] `make lint` passes (`SKILL.md` frontmatter valid, `<= 2,000` words, `shellcheck` clean).
- [ ] `make test` passes across `demo-seed`, `skill/flagsmith-early-access/scripts`, `harness`, `self-hosted`, `tui`, `demo-app`, and `vscode-extension`.
- [ ] `make harness-offline` passes `45/45` across `S1–S10` and `X1–X5`.
- [ ] No secrets, tokens, or `.env` files are staged (`gitleaks` passes in CI).
- [ ] Documentation and `skill/flagsmith-early-access/CONTRIBUTING-NOTE.md` reflect any behavior changes.
