#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "Usage: $0 <flag> <target_identity> <control_identity>" >&2
  exit 2
fi

FLAG="$1"
TARGET_ID="$2"
CONTROL_ID="$3"

eval_flag() {
  local id="$1"
  local trait="${2:-}"
  if [ -n "$trait" ]; then
    flagsmith eval "$FLAG" --identity "$id" --trait "$trait" --no-input --json --jq '.enabled'
  else
    flagsmith eval "$FLAG" --identity "$id" --no-input --json --jq '.enabled'
  fi
}

TARGET_VAL=$(eval_flag "$TARGET_ID" "${TARGET_TRAIT:-}")
CONTROL_VAL=$(eval_flag "$CONTROL_ID" "${CONTROL_TRAIT:-}")

echo "TARGET=${TARGET_VAL} CONTROL=${CONTROL_VAL}"
