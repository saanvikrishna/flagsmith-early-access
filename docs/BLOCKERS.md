# Blockers & Human-Only Checkpoints

This file tracks every human-only checkpoint from `EARLY_ACCESS_SKILL_SPEC.md` (Section 5). Autonomous work proceeds on unblocked tasks and resumes blocked verification once credentials/actions are provided.

| ID | Checkpoint | Status | Needed For | Notes |
|---|---|---|---|---|
| **H1** | Create Flagsmith Cloud account, organisation, and project `early-access-demo` with `Development` and `Production` environments | **Blocked (Human)** | Phase 0 live verification, Phase 2 seed, Phase 6–9 | Required before live `--json` / `--jq` schema verification and demo seeding. |
| **H2** | Create Flagsmith CLI/Admin API key and environment client-side SDK keys (and confirm scope) | **Blocked (Human)** | Phase 0 live verification, Phase 2–9 | Store only in local `.env` / GitHub Actions secrets; never commit. |
| **H3** | Create an Anthropic API key (or chosen agent key) with a spending limit | **Blocked (Human)** | Phase 6–8 | Required for headless `claude -p --output-format json` scenario harness and token measurement. |
| **H4** | Create the public GitHub repo; add secrets; create `gh` token with issue read/write | **Completed** | Phase 1+ | Public GitHub repository is created and `gh` CLI (`2.96.0`) is available locally. |
| **H5** | Human approval of production writes during the recorded demo run | **Pending (Phase 9)** | Phase 9 | Intentional feature of the demo: human types `yes` at the 6-line approval gate. |
| **H6** | Record and upload the 2–3 minute demo video | **Pending (Phase 11)** | Phase 11, Phase 13 | Follows `docs/demo-script.md`. |
| **H7** | Register for hackathon, star Flagsmith on GitHub, submit WeMakeDevs form (Track 04) | **Pending (Phase 13)** | Phase 13 | Target: 29 Nov 2026, 3 PM IST (hard deadline 8 PM IST). |

---

## Impact on Current Phase

- **Unblocked now:** Local CLI `--help` verification (`flagsmith v2.0.0`, `gh 2.96.0`, `claude 2.1.318`), design & safety documentation (`docs/`), repository scaffold, `demo-app/`, `SKILL.md` draft, and unit-tested helper scripts.
- **Blocked until H1 + H2:** Live Flagsmith Cloud `--json` output shape confirmation, `demo-seed/` live execution, and end-to-end `S1–S10` / `X1–X5` harness runs.
- **Blocked until H3:** Headless `claude -p` harness runs and `results/tokens.md` measurement.
