# Demo Video Script (about 2:45)

**Setup before recording**
- Seeded `early-access-demo` Flagsmith project (`python demo-seed/seed_flagsmith.py --mode live`), `demo-app/` running, GitHub issue #1 open ("Early access request: Acme -> new_dashboard until <date>").
- Terminal with `claude` and `flagsmith` v2; font 16-18 pt.
- For the drift scene, start the agent with `harness/fault` first on PATH and `EA_FAULT=x1` (as `harness/bench.py` does).
- Pre-stage one expired grant (a segment `ea-bulk_export-initech` with a past `expires=` and its follow-up issue) for the audit and expire scenes.
- `ea` below means `bash skill/flagsmith-early-access/scripts/ea.sh`.

| Time | On screen | Voiceover |
|---|---|---|
| 0:00-0:15 **Problem** | Issue #1; demo-app as an Acme user and a Globex user, neither sees the new dashboard | "A customer asks for the beta. Today someone edits production by hand, hopes they got the right users, and forgets the cleanup." |
| 0:15-0:50 **Preview** | Agent: "Handle issue #1." It runs `ea grant new_dashboard org:acme --expires 2027-01-15 --issue 1`. Show the `PREFLIGHT` line and the 6-line `PLAN`: segment `ea-new_dashboard-acme`, control `user_3` must stay OFF, expiry, undo. Point out that nothing has been written yet | "The skill's script resolves the customer's identities and a control from Flagsmith itself. Without approval it is a read-only dry run and prints exactly what it will change. This is the only thing the agent is allowed to run against Flagsmith." |
| 0:50-1:20 **Approve, verify, trail** | Type `yes`. Output: `APPLIED segment ...`, `VERIFY TARGET=user_1:on CONTROL=user_3:off (unchanged)`, `TRAIL follow-up=... commented=#1`. Refresh demo-app: Acme has it, Globex does not. Flip to GitHub: comment on #1 and the new "Revoke early access ... (due 2027-01-15)" issue | "On approval it snapshots state, applies the narrowest change, verifies the target and a control identity, and writes the GitHub trail with the expiry." |
| 1:20-1:50 **Drift rollback (live X1)** | Run the same grant for a second flag with the X1 fault on: right after the override lands, the control user is re-tagged into the customer org. Output: `ROLLED BACK (verification failed: target=...:on control=...:on)`. Show Flagsmith: no leftover segment | "Here the control identity really changed mid-flight. The script catches it, rolls back, re-verifies, and reports. The npm CLI exits 0 even on errors, so the script never trusts exit codes." |
| 1:50-2:15 **Audit** | `ea audit`: table with `OVERDUE` (initech), `STALE` (open issue, no override) and `UNTRACKED` (override with no issue), plus the `SUMMARY` line | "Audit finds what is overdue, what is stale, and what was granted behind our back, using only Flagsmith and GitHub, no database." |
| 2:15-2:35 **Expire** | `ea expire` shows one PLAN listing each revoke and each stale issue to close; `yes`; each revoke is verified and its issue closed | "One approval clears every overdue grant, each verified with a control, and closes the stale issues." |
| 2:35-2:45 **Results** | `results/tokens.md` and `results/scenarios.md` on screen; end on the repo card | "15 out of 15 live scenarios pass, with 40% fewer fresh tokens and half the cost of a no-skill baseline that wrote to production before approval in 4 of 4 safety runs. 24 deterministic fault-injection tests back it up." |

## Judging criteria map

| Criterion | Where it shows |
|---|---|
| Use of Flagsmith | Segments, segment and identity overrides, evaluate, edge-identities and traits, all on Flagsmith Cloud (0:15-1:20) |
| Impact | Per-customer beta access with scheduled, enforced cleanup; removes override debt (0:00, 1:50-2:35) |
| Creativity | Zero-database tracking: segment description markers plus GitHub issues; `STALE` and `UNTRACKED` detection (1:50) |
| Demo | Real Cloud, real GitHub, a live drift injection (1:20-1:50) |
| Token efficiency | ~800-word `SKILL.md`, logic in one script with compact output; numbers in `results/tokens.md` (2:35) |
| CLI creativity | Heavy use of `flagsmith` v2 plus `gh` and `jq` in one script; found and worked around CLI bugs (exit 0 on error, duplicate segment names, silent identity creation) (1:20) |
| Production safety | Dry-run PLAN, explicit approval, narrowest change, negative control, auto-rollback, live drift test, never trusting exit codes (0:15-1:50) |
