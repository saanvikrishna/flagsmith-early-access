# Design Document — `flagsmith-early-access`

This document describes the architecture and design decisions for the **Early Access** Agent Skill (`grant -> verify -> record -> expire -> revoke or graduate`, plus read-only `audit`). All CLI commands align with `flagsmith` CLI `v2.0.0` documented in [verified-facts.md](verified-facts.md).

---

## 1. Grant Mechanism: Identity Override vs. Org Segment

The skill always selects the **narrowest possible blast radius** for the requested customer:

| Request Scope | Mechanism | CLI Command Pattern |
|---|---|---|
| **Single user** (e.g., `user_42`) | Identity override on the feature in the target environment | `flagsmith flag update <flag> --enable --identifier <id> --no-input` |
| **Whole organisation / company** (e.g., `acme`) | Dedicated org segment `ea-<flag>-<org>` matching the org trait + segment override on the feature | 1. `flagsmith segment create ea-<flag>-<org> --rules '<rule_json>' --description "<marker>" --no-input`<br>2. `flagsmith flag update <flag> --enable --segment ea-<flag>-<org> --no-input` |

### Why two mechanisms?

- Flagsmith CLI `v2.0.0` natively supports both identity overrides (`flag update --identifier`, `flag delete --identifier`, `flag list --feature <f> --identities`) and segment overrides (`segment create`, `flag update --segment`, `flag delete --segment`).
- Using an identity override for a single user avoids creating an unnecessary segment.
- Using a dedicated `ea-<flag>-<org>` segment for a company ensures **all current and future users** with `org_id = <org>` receive access atomically while keeping the override isolated from pre-existing segments (such as `internal_staff`).
- **Environment-wide default changes (`flagsmith flag update <flag> --enable` without `--segment` or `--identifier`) are strictly forbidden** in `grant` mode.

---

## 2. Discovery Marker (Zero-Database Audit & Cleanup)

Early-access grants remain discoverable by `audit`, `revoke`, and `graduate` with zero external database state:

1. **Org segments:**
   - **Name prefix:** `ea-<flag>-<org>` (lowercase, sanitized).
   - **Description field:** structured key-value marker:
     `early-access; flag=<flag>; customer=<customer>; expires=<YYYY-MM-DD>; issue=<url>`
   - `audit` and `graduate` filter `flagsmith segment list --json` for names starting with `ea-` (and `ea-<flag>-` for `graduate`).

2. **Identity overrides & GitHub trail:**
   - Because identity overrides do not carry a description field in Flagsmith, every grant (org and single-user) opens a follow-up GitHub issue:
     - **Title:** `Revoke early access: <flag> for <customer> (due <YYYY-MM-DD>)`
     - **Label:** `early-access`
     - **Body:** structured metadata (`flag`, `customer`, `mechanism`, `identifier`/`segment`, `environment`, `expires`, and the exact revoke command).
   - `audit` combines `flagsmith segment list`, `flagsmith api` / `flagsmith flag list --feature <f> --identities`, and `gh issue list --label early-access` to produce a complete view of active and overdue grants.

---

## 3. Identity Detection Rules

Before modifying Flagsmith, the agent inspects the target repository (`demo-app/` or the user's codebase) to determine how customers are identified:

1. **Search order:** Scan for Flagsmith SDK calls (`identify(`, `getIdentityFlags`, `get_identity_flags`, `getFlags`, `setTrait`) and common customer/org trait keys (`org_id`, `organization_id`, `company_id`, `tenant_id`, `account_id`).
2. **Determine identifier vs. trait:**
   - If the request names a user ID matching the app's `identify(...)` pattern (e.g., `user_42`), use **identity override**.
   - If the request names a company/org and the codebase passes an org trait (e.g., `org_id`), use an **org segment** on that trait.
3. **Ambiguity rule (S10):** If two or more candidate org traits appear in the codebase (e.g., both `org_id` and `tenant_id` with equal weight) and the request does not specify which one, **stop and ask the user exactly one clarifying question** before applying any Flagsmith changes.

---

## 4. Negative Control Selection

Every `grant` and `revoke` verification step pairs the target check with a **negative control** — an identity belonging to a *different* customer/org that must remain unchanged:

1. **Automatic selection:** Inspect identities and traits in the codebase, seed data, or Flagsmith segment/override list to pick a known non-target org (e.g., when granting to `acme`, select `globex` / `user_3`).
2. **Fallback:** If no other org/identity can be resolved from the codebase or Flagsmith state, ask the user for a control identifier before executing any writes.
3. **Assertion:**
   - On `grant`: `flagsmith evaluate <flag> --identity <target>` -> enabled (`true`); `flagsmith evaluate <flag> --identity <control>` -> unchanged from pre-flight snapshot.
   - On `revoke`: `flagsmith evaluate <flag> --identity <target>` -> disabled (`false`, matching default); `flagsmith evaluate <flag> --identity <control>` -> unchanged.

---

## 5. Approval Plan Format (6-Line Gate)

Before any write in `grant`, `revoke`, or `graduate` (mandatory in Production; displayed in non-Production), the agent outputs **at most 6 lines** plus the confirmation prompt:

```text
PLAN (Production)
Change : add segment override ea-new_dashboard-acme -> new_dashboard ON
Who    : org_id = acme (2 identities)
Control: org_id = globex must stay OFF
Expires: 2027-01-15 (follow-up issue will be created)
Undo   : flagsmith flag delete new_dashboard --segment ea-new_dashboard-acme --yes --no-input && flagsmith segment delete ea-new_dashboard-acme --yes --no-input
Approve? (yes/no)
```

Zero writes execute until the human responds affirmatively (`yes`).

---

## 6. Exact Snapshot & Rollback

Before applying any write:

1. **Snapshot:** `scripts/snapshot.sh` captures the exact pre-change state of:
   - The target flag's environment default and existing overrides (`flagsmith flag get <flag> --json` and `flagsmith flag list --feature <flag> --json`).
   - Whether `ea-<flag>-<org>` already existed (`flagsmith segment get ea-<flag>-<org> --json`).
2. **Rollback trigger:** If post-apply verification fails (target did not reach expected state, or negative control changed) or a CLI write exits non-zero midway:
   - Immediately restore the pre-change state: delete any newly created segment override (`flagsmith flag delete ... --yes --no-input`), delete any newly created `ea-` segment (`flagsmith segment delete ... --yes --no-input`), or restore any prior override value from the snapshot.
   - Re-run `flagsmith evaluate` for both target and control to prove the environment returned to its exact start state.

---

## 7. Verification & Token Budget

The skill is validated across two complementary suites ([results/scenarios.md](../results/scenarios.md)):

- **Live Flagsmith Cloud Verification:** **6/6** end-to-end scenarios (`S1`, `S2`, `S3`, `S4`, `S5`, `X2`) verified against Flagsmith Cloud (`early-access-demo`) and `claude-opus-5-5`, consuming fewer input tokens than the no-skill baseline (`605,541` vs. `610,759` on `S1`).
- **Offline Regression Suite:** **45/45** deterministic checks (`S1–S10` and `X1–X5`, 3 runs each) via `make harness-offline` in CI.

Token efficiency practices enforced across `SKILL.md`:

- **Strict `--jq` filtering:** Every `flagsmith` and `gh` JSON call passes `--jq` (or `-q`) to extract only the fields needed for the next step.
- **Progressive disclosure:** `SKILL.md` stays concise (`< 2,000` words, enforced in CI), with command catalogs, detection patterns, and issue templates isolated in `skill/flagsmith-early-access/references/`.
- **Single-line helper summaries:** `scripts/snapshot.sh`, `scripts/verify.sh`, and `scripts/audit.sh` collapse multi-step operations into compact single-line outputs.
- **3-line final summary:** Every run concludes with action taken, verification result, and issue/trail link.
