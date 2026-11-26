#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <flag> <target>" >&2
  exit 2
fi

FLAG="$1"
TARGET="$2"
TMP_BASE="${TMPDIR:-/tmp}"
OUT_FILE=$(mktemp "${TMP_BASE%/}/ea-snapshot-XXXXXX.json")

FLAG_JSON=$(flagsmith flag get "$FLAG" --no-input --json --jq '{enabled,feature_state_value}' 2>/dev/null || echo 'null')

if [[ "$TARGET" == ea-* ]]; then
  KIND="segment"
  SEG_JSON=$(flagsmith segment get "$TARGET" --no-input --json --jq '{id,name,description,rules}' 2>/dev/null || echo 'null')
  OVR_JSON=$(flagsmith flag get "$FLAG" --segment "$TARGET" --no-input --json --jq '{enabled,feature_state_value,segment_priority}' 2>/dev/null || echo 'null')
else
  KIND="identity"
  SEG_JSON='null'
  OVR_JSON=$(flagsmith flag get "$FLAG" --identifier "$TARGET" --no-input --json --jq '{enabled,feature_state_value}' 2>/dev/null || echo 'null')
fi

jq -cn \
  --arg flag "$FLAG" \
  --arg target "$TARGET" \
  --arg kind "$KIND" \
  --argjson flag_default "$FLAG_JSON" \
  --argjson segment "$SEG_JSON" \
  --argjson override "$OVR_JSON" \
  '{flag:$flag,target:$target,kind:$kind,flag_default:$flag_default,segment:$segment,override:$override}' > "$OUT_FILE"

EXISTS="absent"
if [ "$OVR_JSON" != "null" ] || [ "$SEG_JSON" != "null" ]; then
  EXISTS="present"
fi

echo "${OUT_FILE} snapshot(${KIND}:${TARGET} on ${FLAG}, pre-state=${EXISTS})"
