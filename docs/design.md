# Design Document — `flagsmith-early-access`

This document records the architecture and design decisions for the **Early Access** Agent Skill (`grant → verify → record → expire → revoke or graduate`, plus `audit`). All CLI commands referenced here align with `flagsmith` CLI `v2.0.0` recorded in [verified-facts.md](file:///d:/early-access/docs/verified-facts.md).

---

## 1. Grant Mechanism: Identity Override vs. Org Segment

The skill always chooses the **narrowest possible blast radius** for the requested customer:

| Request Scope | Mechanism | CLI Command Pattern |
|---|---|---|
| **Single user** (e.g., `user_42`) | Identity override on the feature in the target environment | `flagsmith flag update <flag> --enable --identifier <id>` |
| **Whole organisation / company** (e.g., `acme`) | Dedicated org segment `ea-<flag>-<org>` matching the org trait + segment override on the feature | 1. `flagsmith segment create ea-<flag>-<org> --rules '<rule_json>' --description "<marker>"`<br>2. `flagsmith flag update <flag> --enable --segment ea-<flag>-<org>` |

### Why two mechanisms?
- Flagsmith CLI v2.0.0 natively supports both identity overrides (`flag update --identifier`, `flag delete --identifier`, `flag list --feature <f> --identities`) and segment overrides (`segment create`, `flag update --segment`, `flag delete --segment`).
- Using an identity override for a single user avoids creating an unnecessary segment.
- Using a dedicated `ea-<flag>-<org>` segment for a company ensures **all current and future users** with `org_id = <org>` receive access atomically, while keeping the override isolated from any pre-existing segments (such as `internal_staff`).
- **Environment-wide default changes (`flagsmith flag update <flag> --enable` without `--segment` or `--identifier`) are strictly forbidden** in `grant` mode.

---

## 2. Discovery Marker (Zero-Database Audit & Cleanup)

Early-access grants must be discoverable later by `audit`, `revoke`, and `graduate` without an external database:

1. **Org segments:**
   - **Name prefix:** `ea-<flag>-<org>` (lowercase, sanitized).
   - **Description field:** structured key-value string:
     `early-access; flag=<flag>; customer=<customer>; expires=<YYYY-MM-DD>; issue=<url>`
   - `audit` and `graduate` filter `flagsmith segment list --json` for names starting with `ea-` (and `ea-<flag>-` for `graduate`).

2. **Identity overrides & GitHub trail:**
   - Identity overrides do not carry a description field in Flagsmith, so every grant (both org and single-user) creates a follow-up GitHub issue:
     - **Title:** `Revoke early access: <flag> for <customer> (due <YYYY-MM-DD>)`
     - **Label:** `early-access`
     - **Body:** structured metadata (`flag`, `customer`, `mechanism`, `identifier`/`segment`, `environment`, `expires`, and the exact revoke instruction).
   - `audit` combines `flagsmith segment list`, `flagsmith flag list --feature <f> --identities` (for active flags), and `gh issue list --label early-access` to produce a complete view of active and overdue grants.

---

## 3. Identity Detection Rules

Before touching Flagsmith, the agent inspects the target repository (`demo-app/` or user codebase) to determine how customers are identified:

1. **Search order:** Grep for Flagsmith SDK calls (`identify(`, `getIdentityFlags`, `get_identity_flags`, `getFlags`, `setTrait`) and common customer/org trait keys (`org_id`, `organization_id`, `company_id`, `tenant_id`, `account_id`).
2. **Determine identifier vs. trait:**
   - If the request names a user ID matching the app's `identify(...)` pattern (e.g., `user_42`), use **identity override**.
   - If the request names a company/org and the codebase passes an org trait (e.g., `org_id`), use **org segment** on that trait.
3. **Ambiguity rule (S10):** If two or more candidate org traits exist in the codebase (e.g., both `org_id` and `tenant_id` are used with no clear primary) and the request does not specify which one, **stop and ask the user exactly one clarifying question** before making any Flagsmith changes.

---

## 4. Negative Control Selection

Every `grant` and `revoke` verification step requires a **negative control** — an identity belonging to a *different* customer/org that must remain unchanged:

1. **Automatic selection:** Inspect existing identities/traits in the codebase, seed data, or Flagsmith segment/override list to pick a known non-target org (e.g., when granting to `acme`, pick `globex`).
2. **Fallback:** If no other org/identity can be identified with confidence, ask the user to provide a control identifier before applying the change.
3. **Assertion:**
   - On `grant`: `flagsmith eval <flag> --identity <target>` → enabled; `flagsmith eval <flag> --identity <control>` → unchanged from pre-flight snapshot.
   - On `revoke`: `flagsmith eval <flag> --identity <target>` → disabled (or matches default); `flagsmith eval <flag> --identity <control>` → unchanged.

---

## 5. Approval Plan Format (6-Line Gate)

Before any write in `grant`, `revoke`, or `graduate` (mandatory in Production; shown in non-Production), the agent outputs **at most 6 lines** plus the prompt:

```text
PLAN (Production)
Change : add segment override ea-new_dashboard-acme -> new_dashboard ON
Who    : org_id = acme (2 identities)
Control: org_id = globex must stay OFF
Expires: 2027-01-15 (follow-up issue will be created)
Undo   : flagsmith flag delete new_dashboard --segment ea-new_dashboard-acme && flagsmith segment delete ea-new_dashboard-acme --yes
Approve? (yes/no)
```

No writes occur until the human responds affirmatively (`yes`).

---

## 6. Exact Snapshot & Rollback

Before applying any write:

1. **Snapshot:** Record the exact pre-change state of:
   - The target flag's environment default and existing overrides (`flagsmith flag get <flag> --json` and `flagsmith flag list --feature <flag> --json` / `--identities --json`).
   - Whether `ea-<flag>-<org>` already existed (`flagsmith segment get ea-<flag>-<org>`).
2. **Rollback trigger:** If post-apply verification fails (target did not change as expected, OR negative control changed) or a CLI write fails midway:
   - Immediately restore the pre-change state: delete any newly created segment override (`flagsmith flag delete ...`), delete any newly created `ea-` segment (`flagsmith segment delete ... --yes`), or re-apply any prior override value from the snapshot.
   - Re-run `flagsmith eval` for both target and control to prove the environment returned to its exact start state.

---

## 7. Token Output Budget

Token efficiency is a judged Track 04 criterion:

- **Strict `--jq` filtering:** Every `flagsmith` and `gh` JSON call must pass `--jq` (or `-q`) to extract only the fields required by the next step. Never dump full environment or feature lists into agent context.
- **Concise `SKILL.md`:** Keep `SKILL.md` under 2,000 words; place detailed command catalogs, detection patterns, and issue templates in `skill/flagsmith-early-access/references/` so they are loaded on demand.
- **Minimalist scripts (optional):** Where multi-step snapshot/verify/audit calls would otherwise emit verbose intermediate output, small POSIX/Python helpers in `scripts/` return 1-line summaries.
- **Final summary:** End every run with at most a 3-line summary (action taken, verification result, issue/trail link).
