# Blockers & Human-Only Checkpoints

This file tracks every human-only checkpoint from `EARLY_ACCESS_SKILL_SPEC.md` (Section 5). Autonomous work proceeds on unblocked tasks and resumes blocked verification once credentials/actions are provided.

| ID | Checkpoint | Status | Needed For | Notes |
|---|---|---|---|---|
| **H1** | Create Flagsmith Cloud account, organisation, and project `early-access-demo` with `Development` and `Production` environments | **Completed** | Phase 0 live verification, Phase 2 seed, Phase 6–9 | Live project `early-access-demo` seeded and verified. |
| **H2** | Create Flagsmith CLI/Admin API key and environment client-side SDK keys (and confirm scope) | **Completed** | Phase 0 live verification, Phase 2–9 | Configured in local `.env` (gitignored) and GitHub Actions secrets/variables. |
| **H3** | Agent CLI authentication for headless scenario runs | **Completed (Local)** | Phase 6–8 | `codex-cli 0.167.0` (ChatGPT login) and `claude 2.1.318` (`claude.ai` login) are both authenticated locally; `--agent codex` is default in `harness/run.py`. |
| **H4** | Create the public GitHub repo; add secrets; create `gh` token with issue read/write | **Completed** | Phase 1+ | Public GitHub repository is created and `gh` CLI (`2.96.0`) is available locally. |
| **H5** | Human approval of production writes during the recorded demo run | **Pending (Phase 9)** | Phase 9 | Intentional feature of the demo: human types `yes` at the 6-line approval gate. |
| **H6** | Record and upload the 2–3 minute demo video | **Pending (Phase 11)** | Phase 11, Phase 13 | Follows `docs/demo-script.md`. |
| **H7** | Register for hackathon, star Flagsmith on GitHub, submit WeMakeDevs form (Track 04) | **Pending (Phase 13)** | Phase 13 | Target: 29 Nov 2026, 3 PM IST (hard deadline 8 PM IST). |

---

## Impact on Current Phase

- **Completed:** Local & live Flagsmith Cloud verification (`flagsmith v2.0.0`, `gh 2.96.0`, `claude 2.1.318`), `demo-seed/` live idempotency, live scenario passes (`S1`, `S2`, `S3`, `S4`, `S5`, `X2`), live token measurements (`results/tokens.md`), `45/45` mock harness checks, and `55/55` unit/integration tests.
- **Remaining Human-Only:** Interactive demo video recording (`H5`, `H6`) and WeMakeDevs Track 04 submission (`H7`).
