# Identity & Trait Detection Rules

When granting or revoking early access, inspect the repository first to discover how the application identifies users and organisations in Flagsmith.

## Ordered Grep Patterns

Run a search across the codebase in this priority order:

1. **SDK identity calls** (highest signal — shows exact identifier format and traits object):
   - `identify(` (JS/TS, Python, Go, Ruby, Java)
   - `getIdentityFlags` (JS/TS, Node, React)
   - `get_identity_flags` (Python, Ruby)
2. **Organisation / customer trait keys**:
   - `org_id`
   - `company_id`
   - `tenant_id`
   - `account_id` / `customer_id` / `workspace_id`
3. **Environment / SDK configuration**:
   - `FLAGSMITH_` or `environmentID` / `environment_key`

Example search command:

```bash
rg -n "identify\(|getIdentityFlags|get_identity_flags|org_id|company_id|tenant_id"
```

## Choosing the Mechanism

- **Single user requested** (e.g., `user_42`, an email, or a specific user ID matching the `identify(...)` pattern):
  - Use an **identity override** (`--identifier <id>`).
- **Company / org requested** (e.g., `Acme`, `initech`):
  - Map the customer name to the trait value used in code (usually lowercased slug like `acme`, or check seed/fixtures/tests).
  - Use a dedicated **org segment** `ea-<flag>-<customer>` with a rule matching `<org_trait> == <customer_value>`.

## Ambiguity Handling

If the codebase search finds:
- **Two or more competing org traits** (e.g., both `org_id` and `tenant_id` are passed to `identify()` and it is unclear which represents the customer), OR
- **Two different identifier formats** (e.g., `user_<id>` vs `org_<id>`), OR
- **No Flagsmith identity calls** in the repo and the user did not specify an identifier/trait:

**Stop and ask exactly ONE clarifying question** before running any write or creating any plan. For example:
> "I found both `org_id` and `tenant_id` in the codebase. Which trait should I match for Acme's early-access segment?"

Make zero changes in Flagsmith or GitHub until the user answers.
