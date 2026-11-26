# Audit Trail & GitHub Issue Templates

Use these exact templates so `audit`, `revoke`, and `graduate` can reliably parse metadata and close issues.

## 1. Grant — Comment on Source Issue

```markdown
Early access granted for **<customer>** on `<feature>` (`<environment>`).

- **Mechanism**: `<segment ea-<flag>-<customer> (trait <key>=<value>) | identity override <id>>`
- **Verification**: Target (`<target_id>`) = `ON`, Control (`<control_id>`) = `OFF` (unchanged)
- **Expires**: `<YYYY-MM-DD>`
- **Follow-up**: #<followup_number>
- **Revoke command**:
  ```bash
  <exact revoke command>
  ```
```

## 2. Grant — Follow-Up Revoke Issue

- **Title**: `Revoke early access: <feature> for <customer> (due <YYYY-MM-DD>)`
- **Label**: `early-access`
- **Body**:

```markdown
Scheduled cleanup for early-access grant.

- **Feature**: `<feature>`
- **Customer**: `<customer>`
- **Environment**: `<environment>`
- **Mechanism**: `<segment ea-<flag>-<customer> | identity <id>>`
- **Expires**: `<YYYY-MM-DD>`
- **Source issue**: #<source_number>

### Revoke instruction
Run the `flagsmith-early-access` skill in `revoke` mode on this issue, or execute:
```bash
<exact revoke command>
```
```

## 3. Revoke — Closing Comment on Follow-Up Issue

```markdown
Early access revoked for **<customer>** on `<feature>` (`<environment>`).

- **Removed**: `<segment ea-<flag>-<customer> and override | identity override <id>>`
- **Verification**: Target (`<target_id>`) = `OFF`, Control (`<control_id>`) = `OFF` (unchanged)
```

## 4. Graduate — Closing Comment on Related `early-access` Issues

```markdown
Feature `<feature>` has graduated (`<environment>` default is `ON` for everyone).

- **Cleaned up**: `<list of removed ea-<flag>-* segments and identity overrides>`
- **Verification**: Sample customer (`<target_id>`) = `ON` (via default), Control (`<control_id>`) = `ON` (matches default)
```
