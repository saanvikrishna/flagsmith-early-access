# Demo Video Script (2–3 Minutes)

- **Target Duration:** 2:45 (fits within 2–3 minutes)
- **Prerequisites:** Seeded `early-access-demo` Flagsmith project (`python demo-seed/seed_flagsmith.py --mode live`), `demo-app/` running locally (`http://localhost:3000`), terminal with `claude` + `flagsmith` CLI v2.0.0, and GitHub issue `#1` open.

---

## Scene-by-Scene Script

| Time | What's Shown on Screen | What's Said (Voiceover) |
|---|---|---|
| **0:00–0:15** | GitHub **Issue #1** from a customer (*"Early access request: Acme -> new_dashboard until 2027-01-15"*). Quick split-screen showing `demo-app/` logged in as an Acme user (`user_1`) and a Globex user (`user_3`) — neither sees the new dashboard yet. | *"A customer asks for the beta. Today a developer drops everything, edits production by hand, and forgets to clean up."* |
| **0:15–0:30** | Brief comparison card or README highlight showing environment-level skills vs `flagsmith-early-access`. | *"Every other skill works per environment. This one works per customer."* |
| **0:30–1:15** | Terminal: run the agent with `"Handle early access issue #1."` Show the agent:<br>1. Inspecting `demo-app/` to detect the identity convention (`user_<id>`) and `org_id` trait.<br>2. Presenting the **6-line approval plan** (`ea-new_dashboard-acme`, negative control `user_3`, expiry `2027-01-15`, exact undo command).<br>3. Human typing **`yes`**.<br>4. Creating the segment and segment override via `flagsmith` CLI v2.0.0. | *"The agent inspects the codebase to match the app's exact identity and trait conventions, then pauses with a six-line plan showing the narrowest possible change before touching production. Once approved, it creates a scoped segment and override for Acme alone."* |
| **1:15–1:40** | Terminal: verification output showing `user_1` **ON** and negative control `user_3` **OFF**. Switch to `demo-app/` and refresh both users: Acme sees `new_dashboard`; Globex still sees the standard dashboard. | *"Before finishing, it runs a mandatory negative-control check. Acme gets the new dashboard, and Globex proves nothing else changed—if the control ever flipped, it rolls back automatically."* |
| **1:40–2:00** | GitHub browser tab: show the comment posted on **Issue #1** (what changed, expiry date, revoke command) and the newly opened **expiry follow-up issue** with the `early-access` label. | *"Every grant leaves a full audit trail on the original issue and opens a follow-up issue with an expiry date—so cleanup is scheduled at the moment of the grant."* |
| **2:00–2:20** | Terminal: run `"Revoke Acme's early access to new_dashboard"`, showing Acme lose access while Globex stays untouched. Then run `"Graduate bulk_export"` to show `ea-bulk_export-*` segments and overrides cleaned up once the environment default is ON. | *"When the trial ends, revoking removes only that customer's override. When a feature ships to everyone, graduating cleans up all leftover early-access segments—eliminating hidden override debt."* |
| **2:20–2:45** | Terminal / `results/` tables: show `results/scenarios.md` (**14/14** live Flagsmith Cloud runs + **45/45** Offline Regression Suite + **55/55** CI tests) and `results/tokens.md` (live skill vs. baseline token counts across all 5 modes). End on the repo title card. | *"Across 14 live Flagsmith Cloud scenarios and 45 offline regression checks, Early Access passes every functional and safety test—with lower input tokens on org grants and guaranteed production safety trails."* |

---

## Recording Notes

1. **Font size:** Use 16–18 pt terminal font and 125% browser zoom so the 6-line approval plan, `--jq` outputs, and verification lines are readable at 1080p.
2. **Pre-flight:** Run `python demo-seed/seed_flagsmith.py --mode live` before recording so `user_1` and `user_3` both start with `new_dashboard` OFF, and Issue `#1` is open cleanly.
3. **Live Verification:** All live execution logs and token measurements are documented in `results/demo-run.md` and `results/tokens.md`.
