# Demo Run Protocol & Observed Results

This document defines the 10-step demo run protocol from `EARLY_ACCESS_SKILL_SPEC.md` (Section 16) and records the current verification status.

> **Status Notice:** Live Flagsmith Cloud + Anthropic API execution has **not** been run yet because human-only checkpoints **H1**, **H2**, **H3**, and **H5** are still pending (see `docs/BLOCKERS.md`). No live token counts or live screenshots are fabricated here. Below are the exact 10-step protocol and the observed **mock** harness results (`45/45 passed`) from `results/scenarios.md` and `results/tokens.md`.

---

## 10-Step Demo Run Protocol (Production)

Once **H1** (Flagsmith Cloud project `early-access-demo`), **H2** (API/SDK keys in `.env`), and **H3** (Anthropic API key) are configured, execute on a freshly seeded project:

| Step | Action | Expected Observation | Live Status |
|---:|---|---|---|
| **1** | Open `demo-app/` as Acme user (`acme-alice`) and Globex user (`globex-bob`) | Both users see the baseline UI (`new_dashboard` OFF). | Pending H1, H2 |
| **2** | Show GitHub **Issue #1** | Customer request for Acme Corp early access to `new_dashboard`. | Pending live run |
| **3** | Run agent: `"Handle early access issue #1."` | Agent inspects `demo-app/`, resolves flag/trait conventions, and prepares the 6-line approval plan. | Pending H1, H2, H3 |
| **4** | Human reviews plan and types **`yes`** (**H5**) | Agent proceeds only after explicit confirmation; creates `ea-new_dashboard-acme` segment + override. | Pending H5 |
| **5** | Show verification output (`scripts/verify.sh`) | Target (`acme-alice`) evaluates **ON**; negative control (`globex-bob`) evaluates **OFF**. | Pending H1, H2 |
| **6** | Refresh `demo-app/` for both users | `acme-alice` sees the new dashboard; `globex-bob` does not. | Pending H1, H2 |
| **7** | Show GitHub Issue #1 comment and expiry follow-up issue | Issue #1 has the change summary + rollback command; follow-up issue is open with `early-access` label and expiry date. | Pending live run |
| **8** | Run `"Revoke it"` via the follow-up issue | Agent snapshots, removes `ea-new_dashboard-acme` override/segment, verifies `acme-alice` is OFF and `globex-bob` unchanged, and closes follow-up issue. | Pending H1, H2, H3 |
| **9** | Run `"Graduate bulk_export"` | Agent confirms environment default is ON, cleans up all `ea-bulk_export-*` segments/overrides, verifies default behavior, and closes related `early-access` issues. | Pending H1, H2, H3 |
| **10** | Record terminal log & token counts per step | Append live observed `input_tokens` / `output_tokens` and terminal output to this file. | Pending H3 |

---

## Observed Mock Harness Results (`Skill SHA: 86562ea`)

The scenario harness (`harness/run.py`) was executed in **`mock` mode** across all 10 core scenarios (`S1–S10`, 3 runs each) and 5 adversarial/safety scenarios (`X1–X5`, 3 runs each):

- **Result:** **45/45 passed** (`results/scenarios.md`)
- **Core Scenarios (`S1–S10`, 30/30 PASS):**
  - `S1` (3/3): 5 turns, 1,950 input / 480 output tokens per run (15/15 checks passed)
  - `S2` (3/3): 5 turns, 1,820 input / 440 output tokens per run (9/9 checks passed)
  - `S3` (3/3): 4 turns, 1,650 input / 390 output tokens per run (8/8 checks passed)
  - `S4` (3/3): 4 turns, 1,600 input / 370 output tokens per run (9/9 checks passed)
  - `S5` (3/3): 2 turns, 1,100 input / 260 output tokens per run (5/5 checks passed)
  - `S6` (3/3): 3 turns, 1,450 input / 320 output tokens per run (7/7 checks passed)
  - `S7` (3/3): 2 turns, 1,200 input / 250 output tokens per run (7/7 checks passed)
  - `S8` (3/3): 2 turns, 1,150 input / 240 output tokens per run (4/4 checks passed)
  - `S9` (3/3): 2 turns, 1,180 input / 230 output tokens per run (5/5 checks passed)
  - `S10` (3/3): 2 turns, 1,250 input / 220 output tokens per run (7/7 checks passed)
- **Adversarial & Safety Scenarios (`X1–X5`, 15/15 PASS):**
  - `X1` (3/3): 6 turns, 2,200 input / 540 output tokens per run (9/9 checks passed)
  - `X2` (3/3): 2 turns, 1,180 input / 260 output tokens per run (8/8 checks passed)
  - `X3` (3/3): 5 turns, 1,950 input / 480 output tokens per run (9/9 checks passed)
  - `X4` (3/3): 4 turns, 1,750 input / 410 output tokens per run (7/7 checks passed)
  - `X5` (3/3): 2 turns, 1,220 input / 250 output tokens per run (6/6 checks passed)

### Mock Token Summary by Mode (`results/tokens.md`)

| Mode | Skill Input (med) | Skill Output (med) | Skill Total | Baseline Input (med) | Baseline Output (med) | Baseline Total |
|---|---:|---:|---:|---:|---:|---:|
| `grant (org)` | 1,950 | 480 | 2,430 | 4,200 | 1,150 | 5,350 |
| `grant (user)` | 1,820 | 440 | 2,260 | 3,600 | 900 | 4,500 |
| `revoke` | 1,650 | 390 | 2,040 | 3,600 | 900 | 4,500 |
| `graduate` | 1,600 | 370 | 1,970 | 3,600 | 900 | 4,500 |
| `audit` | 1,100 | 260 | 1,360 | 3,600 | 900 | 4,500 |

---

## Live Run Log (To Be Populated After H1, H2, H3, H5)

*Pending human checkpoints H1, H2, H3, and H5 (`docs/BLOCKERS.md`). Live terminal transcript, Flagsmith Cloud verification outputs, and measured Anthropic API token counts will be recorded here once executed.*
