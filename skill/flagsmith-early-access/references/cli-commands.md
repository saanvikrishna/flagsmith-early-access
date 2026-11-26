# Verified Flagsmith CLI v2.0.0 & `gh` Commands

All commands below were verified against `flagsmith version v2.0.0`. Always pass `--json --jq` to keep output minimal, and `--no-input` on non-interactive commands.

## Auth & Context

```bash
flagsmith auth status --json --jq '{authenticated, organisation}'
flagsmith config --json --jq '{project, environment, api_url}'
```

## Features & Flags (Pre-flight & State)

```bash
# Check feature exists and is not archived
flagsmith feature get <flag> --json --jq '{id, name, is_archived}'

# Check environment default state
flagsmith flag get <flag> --json --jq '{enabled, feature_state_value}'

# Check a segment override on a flag
flagsmith flag get <flag> --segment <segment_name_or_id> --json --jq '{enabled, feature_state_value, segment_priority}'

# Check an identity override on a flag
flagsmith flag get <flag> --identifier <identity_id> --json --jq '{enabled, feature_state_value}'
```

## Segments (Org-Level Early Access)

```bash
# List early-access segments
flagsmith segment list --json --jq '[.[] | select(.name | startswith("ea-")) | {id, name, description}]'

# Get a single segment and its rules (for snapshot)
flagsmith segment get <segment_name_or_id> --json --jq '{id, name, description, rules}'

# Create a segment matching an org trait
flagsmith segment create ea-<flag>-<customer> \
  --rules '[{"type":"ALL","rules":[{"type":"ANY","conditions":[{"operator":"EQUAL","property":"org_id","value":"<customer>"}]}]}]' \
  --description "early-access; flag=<flag>; customer=<customer>; expires=<YYYY-MM-DD>; issue=<url>" \
  --no-input --json --jq '{id, name}'

# Delete a segment
flagsmith segment delete ea-<flag>-<customer> --yes --no-input
```

## Overrides (Apply & Remove)

```bash
# Enable flag for a segment
flagsmith flag update <flag> --enable --segment ea-<flag>-<customer> --no-input --json --jq '{enabled}'

# Enable flag for a single identity
flagsmith flag update <flag> --enable --identifier <identity_id> --no-input --json --jq '{enabled}'

# Remove a segment override
flagsmith flag delete <flag> --segment ea-<flag>-<customer> --yes --no-input

# Remove an identity override
flagsmith flag delete <flag> --identifier <identity_id> --yes --no-input
```

## Evaluation (Verification & Negative Control)

```bash
# Evaluate a single flag for an existing identity
flagsmith evaluate <flag> --identity <identity_id> --json --jq '{enabled, value}'

# Evaluate with transient traits (when testing an org trait without persisting)
flagsmith evaluate <flag> --identity <identity_id> --trait org_id=<customer> --json --jq '{enabled, value}'
```

## Admin API Fallback (Listing Identity Overrides for `graduate` / `audit`)

```bash
# List identity-level feature overrides in an environment for a feature ID
flagsmith api "api/v1/environments/<env_id>/featurestates/?feature=<feature_id>" \
  --jq '[.results[] | select(.identity != null) | {id, identity, enabled}]'
```

## GitHub CLI (`gh`)

```bash
# Read an issue
gh issue view <number> --json number,title,body,author,url

# Comment on an issue
gh issue comment <number> --body "<comment>"

# Create a follow-up revoke issue
gh issue create --title "Revoke early access: <feature> for <customer> (due <YYYY-MM-DD>)" \
  --label "early-access" --body "<body>"

# List open early-access issues
gh issue list --label early-access --state open --json number,title,url,body

# Close an issue with a comment
gh issue close <number> --comment "<comment>"
```
