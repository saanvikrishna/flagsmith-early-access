#!/usr/bin/env bash
set -euo pipefail

TODAY="${AUDIT_TODAY:-$(date -u +%Y-%m-%d)}"

SEGS_JSON=$(flagsmith segment list --no-input --json --jq '[.[] | select(.name | startswith("ea-")) | {name,description}]' 2>/dev/null || echo '[]')

ISSUES_JSON='[]'
if command -v gh >/dev/null 2>&1; then
  ISSUES_JSON=$(gh issue list --label early-access --state open --json number,title,url,body 2>/dev/null || echo '[]')
fi

echo "| Customer | Feature | Mechanism | Expires | Overdue | Issue |"
echo "|---|---|---|---|---|---|"

jq -r --arg today "$TODAY" --argjson issues "$ISSUES_JSON" '
  def kv(key):
    (if test(key + "=[^;\\s]+") then capture(key + "=(?<v>[^;\\s]+)").v else "-" end);
  def overdue(exp):
    if exp == "-" then "no" elif exp < $today then "yes" else "no" end;
  [
    (.[] |
      (.description // "") as $d |
      ($d | kv("customer")) as $cust |
      ($d | kv("flag")) as $feat |
      ($d | kv("expires")) as $exp |
      ($d | kv("issue")) as $iss |
      {
        customer: (if $cust != "-" then $cust else (.name | split("-")[2:] | join("-")) end),
        feature: (if $feat != "-" then $feat else (.name | split("-")[1] // "-") end),
        mechanism: ("segment:" + .name),
        expires: $exp,
        overdue: overdue($exp),
        issue: $iss
      }
    ),
    ($issues[] |
      (.title // "") as $t |
      (.body // "") as $b |
      select(($b | test("Mechanism:\\s*`?identity")) or ($t | startswith("Revoke early access:"))) |
      {
        customer: (if ($b | test("Customer\\*\\*:\\s*`?[^`\\n]+")) then ($b | capture("Customer\\*\\*:\\s*`?(?<v>[^`\\n]+)").v) else "-" end),
        feature: (if ($b | test("Feature\\*\\*:\\s*`?[^`\\n]+")) then ($b | capture("Feature\\*\\*:\\s*`?(?<v>[^`\\n]+)").v) else "-" end),
        mechanism: (if ($b | test("Mechanism\\*\\*:\\s*`?[^`\\n]+")) then ($b | capture("Mechanism\\*\\*:\\s*`?(?<v>[^`\\n]+)").v) else "issue" end),
        expires: (if ($t | test("\\(due \\d{4}-\\d{2}-\\d{2}\\)")) then ($t | capture("\\(due (?<v>\\d{4}-\\d{2}-\\d{2})\\)").v) else "-" end),
        overdue: overdue((if ($t | test("\\(due \\d{4}-\\d{2}-\\d{2}\\)")) then ($t | capture("\\(due (?<v>\\d{4}-\\d{2}-\\d{2})\\)").v) else "-" end)),
        issue: ("#" + (.number | tostring))
      }
    )
  ] | unique_by([.customer, .feature]) |
  .[] | "| \(.customer) | \(.feature) | \(.mechanism) | \(.expires) | \(.overdue) | \(.issue) |"
' <<< "$SEGS_JSON"
