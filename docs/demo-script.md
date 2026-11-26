# Demo Video Script (2–3 Minutes)

- **Target Duration:** 2:45 (fits within 2–3 minutes)
- **Human Checkpoint:** **H6** (Record and upload video) & **H5** (Type `yes` at the production approval gate during the recorded run)
- **Source Spec:** `EARLY_ACCESS_SKILL_SPEC.md` Section 18
- **Prerequisites:** Seeded `early-access-demo` project (H1 + H2), `demo-app/` running locally, terminal with `claude` + `flagsmith` CLI v2.0.0, and GitHub issue #1 open.

---

## Scene-by-Scene Script

| Time | What's Shown on Screen | What's Said (Voiceover) |
|---|---|---|
| **0:00–0:15** | GitHub **Issue #1** from a customer (*"Can Acme Corp get early access to `new_dashboard`?"*). Quick split-screen showing `demo-app/` logged in as an Acme user (`acme-alice`) and a Globex user (`globex-bob`) — neither sees the new dashboard yet. | *"A customer asks for the beta. Today a developer drops everything, edits production by hand, and forgets to clean up."* |
| **0:15–0:30** | Brief comparison card or terminal/README highlight showing existing Flagsmith skills vs `flagsmith-early-access`. | *"Every other skill works per environment. This one works per customer."* |
| **0:30–1:15** | Terminal: run the agent with `"Handle early access issue #1."` Show the agent:<br>1. Reading `demo-app/` to detect the flag key (`new_dashboard`), identity format, and `org_id` trait.<br>2. Presenting the **6-line approval plan** (Target: `ea-new_dashboard-acme`, Control: `globex-bob`, Blast radius: 1 segment, Expiry: 14 days).<br>3. Human typing **`yes`** (checkpoint **H5**).<br>4. Applying the segment and segment override via `flagsmith` CLI v2.0.0. | *"The agent inspects the codebase to match the app's exact identity and trait conventions, then pauses with a six-line plan showing the narrowest possible change before touching production. Once approved, it creates a scoped segment and override for Acme alone."* |
| **1:15–1:40** | Terminal: `scripts/verify.sh` output showing target **ON** (`acme-alice`) and negative control **OFF** (`globex-bob`). Switch to `demo-app/` and refresh both users: Acme sees `new_dashboard`; Globex still sees the old dashboard. | *"Before finishing, it runs a mandatory negative-control check. Acme gets the new dashboard, and Globex proves nothing else changed—if the control ever flipped, it rolls back automatically."* |
| **1:40–2:00** | GitHub browser tab: show the comment posted on **Issue #1** (what changed, expiry date, rollback command) and the newly opened **expiry follow-up issue** with the `early-access` label. | *"Every grant leaves a full audit trail on the original issue and opens a follow-up issue with an expiry date—so cleanup is scheduled at the moment of the grant."* |
| **2:00–2:20** | Terminal: run `"Revoke it"` via the follow-up issue, showing Acme lose access while Globex stays untouched. Then run `"Graduate bulk_export"` to show `ea-bulk_export-*` segments and overrides cleaned up once the environment default is ON. | *"When the trial ends, revoking removes only that customer's override. When a feature ships to everyone, graduating cleans up all leftover early-access segments—eliminating hidden override debt."* |
| **2:20–2:45** | Terminal / `results/` tables: show `results/scenarios.md` (**45/45** mock runs passed: 30/30 core `S1–S10` + 15/15 safety/adversarial `X1–X5`), `scripts/test_scripts.py`, and `results/tokens.md` (skill vs. baseline token counts per mode). End on the repo title card. | *"Across 30 core scenario runs and 15 adversarial safety checks in the mock harness, the skill passes 45 out of 45—cutting token usage roughly in half compared to an unguided baseline while keeping production safe."* |

---

## Recording Notes

1. **Font size:** Use 16–18 pt terminal font and 125% browser zoom so the 6-line approval plan, `--jq` outputs, and verification lines are readable at 1080p.
2. **Pre-flight:** Run `demo-seed/` reset before recording so `acme-alice` and `globex-bob` both start with `new_dashboard` OFF, and Issue #1 is open with no prior comments.
3. **Live vs. Mock:** When H1–H3 are configured, record the live Flagsmith Cloud + `claude` run and update `results/demo-run.md` with the observed live token counts before final upload.
