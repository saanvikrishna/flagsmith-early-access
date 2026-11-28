#!/usr/bin/env bash
# shellcheck disable=SC2016  # backticks in printf formats are literal Markdown
# ea.sh - deterministic core of the flagsmith-early-access skill.
#   ea.sh detect   [--dir D]                                   which trait identifies a customer
#   ea.sh grant    <flag> org:<customer>|user:<id> --expires YYYY-MM-DD [--issue N] [--trait T] [--target ID] [--control ID] [--approved]
#   ea.sh revoke   <flag> org:<customer>|user:<id> [--issue N] [--control ID] [--approved]
#   ea.sh graduate <flag> [--control ID] [--approved]
#   ea.sh audit                                                read-only table (+ OVERDUE / STALE)
#   ea.sh expire   [--approved]                                revoke every overdue grant, close stale issues
# Without --approved every write command is a dry run that prints the 6-line PLAN.
# Exit 0 = ok, 3 = stopped / rolled back, 2 = usage. Never trusts CLI exit codes (the npm
# `flagsmith` wrapper always exits 0): parses stdout JSON + stderr, and re-reads state after writes.
set -euo pipefail

FS="${FLAGSMITH_BIN:-flagsmith}"
GH="${GH_BIN:-gh}"
MAX_SCAN="${EA_MAX_SCAN:-40}"
JOBS="${EA_JOBS:-8}"
TRIES="${EA_VERIFY_TRIES:-6}"; WAIT="${EA_VERIFY_WAIT:-2}"
SELF="$0"
W=$(mktemp -d "${TMPDIR:-/tmp}/ea-XXXXXX"); trap 'rm -rf "$W"' EXIT
ERRF="$W/err"

# jq.exe on Windows emits CRLF; strip CR so values compare cleanly on every OS
jq() { command jq "$@" | tr -d '\r'; }
die()  { echo "USAGE: $*" >&2; exit 2; }
stop() { echo "STOP $*"; exit 3; }
lower(){ printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
UP()   { printf '%s' "$1" | tr '[:lower:]' '[:upper:]'; }

# fsj <args...>: JSON on stdout, or the literal `null` (error text left in $ERRF)
fsj() {
  local out
  out=$("$FS" "$@" --no-input --json 2>"$ERRF") || true
  if [ -n "$out" ] && jq empty >/dev/null 2>&1 <<<"$out"; then printf '%s\n' "$out"; else printf 'null\n'; fi
}
# fsw <args...>: one write; true unless the CLI reported an error
fsw() { "$FS" "$@" --yes --no-input --json >/dev/null 2>"$ERRF" || true; ! grep -q '^Error' "$ERRF"; }
lasterr() { head -n1 "$ERRF" 2>/dev/null | cut -c1-160; }
ghc() { if [ -n "${GH_REPO:-}" ]; then "$GH" "$@" -R "$GH_REPO"; else "$GH" "$@"; fi; }
have_gh() { command -v "$GH" >/dev/null 2>&1; }
# parallel reads: bg <name> <fsj args...>; then `wait`; rd <name>
throttle() { while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 0.1; done; }
bg() { local n="$1"; shift; throttle; ( ERRF="$W/$n.err"; fsj "$@" >"$W/$n" ) & }
rd() { cat "$W/$1" 2>/dev/null || echo null; }
# ev <flag> <identity> -> on|off|err  (persisted traits only - never --trait, so real drift shows)
ev() { fsj evaluate "$1" --identity "$2" | jq -r 'if . == null then "err" elif .enabled then "on" else "off" end'; }
onoff() { jq -r 'if . == null then "err" elif .enabled then "on" else "off" end'; }

# --- arguments -------------------------------------------------------------------
CMD="${1:-}"; [ -n "$CMD" ] || die "ea.sh <detect|grant|revoke|graduate|audit|expire> ..."; shift
FLAG=""; WHO=""; TRAIT="${EA_TRAIT:-org_id}"; TARGET=""; CONTROL=""; EXPIRES=""; ISSUE=""; APPROVED=0; DIR="."
case "$CMD" in
  detect|audit|expire) ;;
  graduate) FLAG="${1:-}"; [ -n "$FLAG" ] || die "graduate <flag>"; shift ;;
  grant|revoke) FLAG="${1:-}"; WHO="${2:-}"; [ -n "$FLAG" ] && [ -n "$WHO" ] || die "$CMD <flag> <org:CUSTOMER|user:ID>"; shift 2 ;;
  *) die "unknown command $CMD" ;;
esac
while [ $# -gt 0 ]; do
  case "$1" in
    --trait) TRAIT="$2"; shift 2;; --target) TARGET="$2"; shift 2;; --control) CONTROL="$2"; shift 2;;
    --expires) EXPIRES="$2"; shift 2;; --issue) ISSUE="${2#\#}"; shift 2;; --dir) DIR="$2"; shift 2;;
    --approved) APPROVED=1; shift;; *) die "unknown option $1";;
  esac
done
KIND="${WHO%%:*}"; CUST="${WHO#*:}"
if [ -n "$WHO" ]; then
  case "$KIND" in
    org) CUST=$(lower "$CUST" | tr -c 'a-z0-9_-' '-' | sed 's/-*$//') ;;
    user) ;;
    *) die "who must be org:<customer> or user:<identifier>" ;;
  esac
fi
SEG="ea-${FLAG}-${CUST}"

# --- detect (local, read-only) -----------------------------------------------------
if [ "$CMD" = detect ]; then
  ex="--exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=build --exclude-dir=vendor --exclude-dir=.venv --exclude-dir=.claude --exclude-dir=.agents"
  # shellcheck disable=SC2086
  hits=$(grep -rIowE $ex "(org_id|organisation_id|organization_id|company_id|tenant_id|account_id|customer_id|workspace_id)" "$DIR" 2>/dev/null \
    | awk -F: '{print $NF}' | sort | uniq -c | sort -rn | awk '{printf "%s(%s) ", $2, $1}' || true)
  # shellcheck disable=SC2086
  calls=$(grep -rIlE $ex "identify\(|getIdentityFlags|get_identity_flags|identity=|\.identify" "$DIR" 2>/dev/null | head -3 | tr '\n' ' ' || true)
  n=$(printf '%s' "$hits" | wc -w | tr -d ' ')
  [ "$n" -gt 0 ] || { echo "DETECT none sdk_calls=[${calls% }] -> ask which trait or identifier names a customer"; exit 3; }
  [ "$n" -eq 1 ] || { echo "DETECT ambiguous traits=[${hits% }] -> ask ONE question: which trait names the customer?"; exit 3; }
  echo "DETECT trait=${hits%%(*} sdk_calls=[${calls% }]"; exit 0
fi

# --- shared state (one parallel batch of reads) --------------------------------------
K="${FLAGSMITH_ENVIRONMENT:-}"
load_state() {
  bg cfg config
  if [ -n "$FLAG" ]; then
    bg feat feature get "$FLAG"; bg flag flag get "$FLAG"
    bg sovr flag list --feature "$FLAG"; bg iovr flag list --feature "$FLAG" --identities
  fi
  bg segs segment list
  [ -z "$K" ] || bg idl api "api/v1/environments/$K/edge-identities/?page_size=$MAX_SCAN"
  wait
  CFG=$(rd cfg)
  [ -n "$K" ] || K=$(jq -r '.environment.value // empty' <<<"$CFG")
  [ -n "$K" ] || stop "no Flagsmith environment configured (FLAGSMITH_ENVIRONMENT or -e) $(head -n1 "$W/cfg.err" 2>/dev/null)"
  ENVN=$(jq -r --arg k "$K" '.environment.name // $k' <<<"$CFG")
  SEGS=$(rd segs | jq -c '. // []')
}
load_idents() { # IDENTS = [{i:identifier, r:"edge:uuid"|"core:id"}]
  local j
  if [ -f "$W/idl" ]; then j=$(rd idl); else j=$(fsj api "api/v1/environments/$K/edge-identities/?page_size=$MAX_SCAN"); fi
  IDENTS=$(jq -c '[.results[]? | {i:.identifier, r:("edge:" + .identity_uuid)}]' <<<"$j")
  if [ "$IDENTS" = "[]" ]; then
    IDENTS=$(fsj api "api/v1/environments/$K/identities/?page_size=$MAX_SCAN" | jq -c '[.results[]? | {i:.identifier, r:("core:" + (.id|tostring))}]')
  fi
}
traits_path() { case "$1" in edge:*) echo "api/v1/environments/$K/edge-identities/${1#edge:}/list-traits/";; *) echo "api/v1/environments/$K/identities/${1#core:}/traits/";; esac; }
trait_val() { jq -r --arg t "$TRAIT" '(if type=="object" then .results else . end) | [.[]? | select(.trait_key==$t)][0].trait_value // empty | tostring' | tr '[:upper:]' '[:lower:]'; }
ident_ref() { # exact lookup for identities outside the scanned page
  local r
  r=$(jq -r --arg i "$1" '[.[] | select(.i==$i)][0].r // empty' <<<"$IDENTS"); [ -z "$r" ] || { echo "$r"; return; }
  r=$(fsj api "api/v1/environments/$K/edge-identities/?q=$1" | jq -r --arg i "$1" '[.results[]? | select(.identifier==$i)][0].identity_uuid // empty')
  [ -z "$r" ] || { echo "edge:$r"; return; }
  r=$(fsj api "api/v1/environments/$K/identities/?q=$1" | jq -r --arg i "$1" '[.results[]? | select(.identifier==$i)][0].id // empty')
  [ -z "$r" ] || echo "core:$r"
}
load_people() { # PEOPLE lines: identifier<TAB>trait<TAB>on|off   (parallel)
  local n=0 i r
  while IFS=$'\t' read -r i r; do
    n=$((n+1)); [ "$1" = traits ] && bg "t$n" api "$(traits_path "$r")"; bg "e$n" evaluate "$FLAG" --identity "$i"
  done < <(jq -r '.[] | [.i, .r] | @tsv' <<<"$IDENTS")
  wait; PEOPLE=""; n=0
  while IFS=$'\t' read -r i r; do
    n=$((n+1)); tv=""
    if [ "$1" = traits ]; then tv=$(rd "t$n" | trait_val); fi
    PEOPLE="$PEOPLE$i"$'\t'"$tv"$'\t'"$(rd "e$n" | onoff)"$'\n'
  done < <(jq -r '.[] | [.i, .r] | @tsv' <<<"$IDENTS")
}
col() { awk -F'\t' -v k="$1" -v c="$2" '$1==k {print $c; exit}' <<<"$PEOPLE"; }

preflight_common() {
  load_state
  FEAT=$(rd feat)
  if [ "$FEAT" = null ]; then
    if fsj feature list --include-archived | jq -e --arg f "$FLAG" 'any(.[]?; .name==$f)' >/dev/null; then
      stop "feature '$FLAG' is archived - unarchive it first; no changes made"; fi
    stop "feature '$FLAG' not found in this project; no changes made"
  fi
  DEF=$(rd flag | onoff); [ "$DEF" != err ] || stop "cannot read '$FLAG' default: $(head -n1 "$W/flag.err")"
  load_idents
}
snapshot() {
  local f; f="${TMPDIR:-/tmp}/ea-snapshot-$FLAG-$(date -u +%Y%m%dT%H%M%S).json"
  jq -n --arg flag "$FLAG" --arg who "$WHO" --arg env "$ENVN" --arg def "$DEF" \
    --argjson segs "$(jq -c --arg p "ea-$FLAG-" '[.[] | select(.name|startswith($p))]' <<<"$SEGS")" \
    --argjson so "$(rd sovr | jq -c '. // []')" --argjson io "$(rd iovr | jq -c '. // []')" \
    '{flag:$flag,who:$who,env:$env,default:$def,segments:$segs,segment_overrides:$so,identity_overrides:$io}' >"$f"
  echo "$f"
}
plan() { # <add|remove> <ON|OFF> <expires-line> <undo>
  local who mech
  if [ "$KIND" = org ]; then mech="segment override $SEG"; who="$TRAIT = $CUST ($TARGET + others in $CUST)"
  else mech="identity override $CUST"; who="identifier = $CUST"; fi
  printf 'PLAN (%s)\nChange : %s %s -> %s %s\nWho    : %s\nControl: %s%s must stay %s\nExpires: %s\nUndo   : %s\nApprove? (yes/no)\n' \
    "$ENVN" "$1" "$mech" "$FLAG" "$2" "$who" "$CONTROL" "${CONTROL_TRAIT:+ ($TRAIT=$CONTROL_TRAIT)}" "$(UP "$CTRL0")" "$3" "$4"
}

# --- grant / revoke ------------------------------------------------------------------
if [ "$CMD" = grant ] || [ "$CMD" = revoke ]; then
  preflight_common
  CONTROL_TRAIT=""
  if [ "$KIND" = org ]; then
    load_people traits
    if [ -n "$TARGET" ]; then
      v=$(col "$TARGET" 2); [ -n "$(col "$TARGET" 1)" ] || v=$(fsj api "$(traits_path "$(ident_ref "$TARGET")")" | trait_val)
      [ "$v" = "$CUST" ] || stop "target '$TARGET' has $TRAIT='${v:-<none>}', not '$CUST'"
    else
      OV=" $(rd iovr | jq -r '[.[]?.identifier] | join(" ")') "  # prefer a member without its own override
      TARGET=$(awk -F'\t' -v c="$CUST" -v o="$OV" '$2==c && index(o, " "$1" ")==0 {print $1; exit}' <<<"$PEOPLE")
      [ -n "$TARGET" ] || TARGET=$(awk -F'\t' -v c="$CUST" '$2==c {print $1; exit}' <<<"$PEOPLE")
    fi
    [ -n "$TARGET" ] || stop "customer not found: no identity with $TRAIT=$CUST in the first $MAX_SCAN identities - check the name, or pass --target <identifier>"
    if [ -z "$CONTROL" ]; then
      CONTROL=$(awk -F'\t' -v c="$CUST" -v s="$DEF" '$2!="" && $2!=c && $3==s {print $1; exit}' <<<"$PEOPLE")
    fi
    [ -n "$CONTROL" ] || stop "no control identity outside $CUST - pass --control <identifier>"
    CONTROL_TRAIT=$(col "$CONTROL" 2)
    [ -n "$(col "$CONTROL" 1)" ] || CONTROL_TRAIT=$(fsj api "$(traits_path "$(ident_ref "$CONTROL")")" | trait_val)
    [ "$CONTROL_TRAIT" != "$CUST" ] || stop "control '$CONTROL' is itself in $CUST ($TRAIT=$CUST) - pick an identity outside the customer"
  else
    TARGET="$CUST"; load_people evals
    [ -n "$(ident_ref "$TARGET")" ] || stop "identity '$TARGET' not found in $ENVN - check the identifier (a typo would silently create a new identity)"
    [ -n "$CONTROL" ] || CONTROL=$(awk -F'\t' -v t="$TARGET" -v s="$DEF" '$1!=t && $3==s {print $1; exit}' <<<"$PEOPLE")
    [ -n "$CONTROL" ] || stop "no control identity found - pass --control <identifier>"
  fi
  [ "$CONTROL" != "$TARGET" ] || stop "control must differ from target"
  if [ "$KIND" = org ] && rd iovr | jq -e --arg i "$TARGET" 'any(.[]?; .identifier==$i)' >/dev/null; then
    stop "target $TARGET has its own identity override on '$FLAG', which beats segment overrides - pass --target <another $CUST identity>"
  fi
  T0=$(col "$TARGET" 3); [ -n "$T0" ] || T0=$(ev "$FLAG" "$TARGET")
  CTRL0=$(col "$CONTROL" 3); [ -n "$CTRL0" ] || CTRL0=$(ev "$FLAG" "$CONTROL")
  IDS=$(jq -r --arg n "$SEG" '[.[] | select(.name==$n) | .id | tostring] | join(",")' <<<"$SEGS")
  [ "${IDS//[0-9]/}" = "" ] || stop "duplicate segments named $SEG (ids $IDS): name-based commands are ambiguous - delete the extra one by id"
  if [ "$KIND" = user ]; then HAS=$(rd iovr | jq -r --arg i "$CUST" 'if any(.[]?; .identifier==$i) then "yes" else "no" end')
  else HAS=$([ -n "$IDS" ] && echo yes || echo no); fi

  if [ "$CMD" = grant ]; then
    [ "$DEF" = off ] || stop "'$FLAG' is already ON for everyone in $ENVN - nothing to grant"
    [ "$HAS" = no ] || stop "$WHO already has early access to '$FLAG' ($([ -n "$IDS" ] && echo "segment id $IDS" || echo "identity override")) - nothing to grant"
    [ "$T0" = off ] || stop "target $TARGET already sees '$FLAG' ON through another rule - nothing to grant"
    [ -n "$EXPIRES" ] || stop "missing expiry - ask for an end date (--expires YYYY-MM-DD); every grant must expire"
    [[ "$EXPIRES" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || stop "expiry '$EXPIRES' is not YYYY-MM-DD"
    [[ ! "$EXPIRES" < "$(date -u +%Y-%m-%d)" ]] || stop "expiry $EXPIRES is in the past"
    [ "$CTRL0" = off ] || stop "control $CONTROL already sees '$FLAG' ON - pick a control without access (--control)"
  else
    [ "$HAS" = yes ] || stop "no early-access grant for $WHO on '$FLAG' in $ENVN - nothing to revoke (run audit)"
  fi
  S=$(snapshot)
  UNDO_G="ea.sh revoke $FLAG $KIND:$CUST --approved"
  if [ "$APPROVED" -ne 1 ]; then
    echo "PREFLIGHT ok env=$ENVN default=$DEF target=$TARGET:$T0 control=$CONTROL:$CTRL0 snapshot=$S"
    if [ "$CMD" = grant ]; then plan add ON "$EXPIRES (follow-up issue will be created)" "$UNDO_G"
    else
      OEXP=$(jq -r --arg n "$SEG" '[.[] | select(.name==$n)][0].description // "" | (capture("expires=(?<v>[0-9-]+)").v // "")' <<<"$SEGS")
      plan remove OFF "N/A (revoking)" "ea.sh grant $FLAG $KIND:$CUST --expires ${OEXP:-<date>} --approved (snapshot $S)"
    fi
    stop "awaiting approval - show this PLAN verbatim, wait for an explicit 'yes', then re-run with --approved"
  fi

  # Edge evaluation can lag a write by a few seconds: poll before declaring failure
  verify() { local i=0; while :; do T1=$(ev "$FLAG" "$TARGET"); C1=$(ev "$FLAG" "$CONTROL")
    { [ "$T1" = "$1" ] && [ "$C1" = "$CTRL0" ]; } && return 0
    i=$((i+1)); [ "$i" -lt "$TRIES" ] || return 1; sleep "$WAIT"; done; }
  if [ "$CMD" = grant ]; then
    SID=""
    rollback() {
      if [ "$KIND" = org ]; then
        [ -n "$SID" ] || SID=$(fsj segment list | jq -r --arg n "$SEG" '[.[]? | select(.name==$n) | .id][0] // empty')
        if [ -n "$SID" ]; then fsw flag delete "$FLAG" --segment "$SID" || true; fsw segment delete "$SID" || true; fi
      else fsw flag delete "$FLAG" --identifier "$CUST" || true; fi
      if verify "$T0"; then echo "ROLLED BACK ($1) - verified target=$TARGET:$T1 control=$CONTROL:$C1; no trail created; snapshot=$S"
      else echo "ROLLBACK INCOMPLETE ($1) - target=$TARGET:$T1 control=$CONTROL:$C1; restore manually from $S"; fi
      exit 3
    }
    if [ "$KIND" = org ]; then
      RULES=$(jq -cn --arg t "$TRAIT" --arg v "$CUST" '{type:"ALL",rules:[{type:"ANY",conditions:[{property:$t,operator:"EQUAL",value:$v}]}]}')
      DESC="early-access; flag=$FLAG; customer=$CUST; expires=$EXPIRES; issue=${ISSUE:+#$ISSUE}"
      SID=$(fsj segment create "$SEG" --rules "$RULES" --description "$DESC" | jq -r '.id // empty')
      [ -n "$SID" ] || rollback "segment create failed: $(lasterr)"
      fsw flag update "$FLAG" --enable --segment "$SID" || rollback "override failed: $(lasterr)"
      MECH="segment $SEG (id $SID, $TRAIT=$CUST)"
    else
      fsw flag update "$FLAG" --enable --identifier "$CUST" || rollback "override failed: $(lasterr)"
      MECH="identity override $CUST"
    fi
    verify on || rollback "verification failed: target=$TARGET:$T1 control=$CONTROL:$C1"
    echo "APPLIED $MECH -> $FLAG ON in $ENVN"
    echo "VERIFY TARGET=$TARGET:on CONTROL=$CONTROL:$C1 (unchanged)"
  else
    if [ "$KIND" = org ]; then
      SEGJ=$(fsj segment get "$IDS"); OVR=$(fsj flag get "$FLAG" --segment "$IDS")
      restore() { # reuse the segment if it still exists (never create a duplicate), else recreate it
        local nid
        nid=$(fsj segment list | jq -r --arg i "$IDS" '[.[]? | select((.id|tostring)==$i) | .id][0] // empty')
        [ -n "$nid" ] || nid=$(fsj segment create "$SEG" --rules "$(jq -c '.rules | del(.["$schema"])' <<<"$SEGJ")" \
          --description "$(jq -r '.description // ""' <<<"$SEGJ")" | jq -r '.id // empty')
        [ -z "$nid" ] || [ "$(jq -r '.enabled' <<<"$OVR")" != true ] || fsw flag update "$FLAG" --enable --segment "$nid" || true
        if verify "$T0"; then echo "ROLLED BACK ($1) - grant restored (segment id $nid); target=$TARGET:$T1 control=$CONTROL:$C1"
        else echo "ROLLBACK INCOMPLETE ($1) - restore manually from $S"; fi
        exit 3
      }
      [ "$OVR" = null ] || fsw flag delete "$FLAG" --segment "$IDS" || restore "override delete failed: $(lasterr)"
      fsw segment delete "$IDS" || restore "segment delete failed: $(lasterr)"
      MECH="segment $SEG (id $IDS) and its override"
    else
      fsw flag delete "$FLAG" --identifier "$CUST" || stop "delete failed: $(lasterr); nothing changed"
      MECH="identity override $CUST"
    fi
    if ! verify "$DEF"; then
      [ "$KIND" != org ] || restore "verification failed: target=$TARGET:$T1 control=$CONTROL:$C1"
      fsw flag update "$FLAG" --enable --identifier "$CUST" || true
      echo "ROLLED BACK (verification failed: target=$TARGET:$T1 control=$CONTROL:$C1) - override restored"; exit 3
    fi
    echo "REMOVED $MECH in $ENVN"
    echo "VERIFY TARGET=$TARGET:$T1 (back to default) CONTROL=$CONTROL:$C1 (unchanged)"
  fi

  # trail - never blocks or undoes the Flagsmith result
  if ! have_gh; then echo "TRAIL skipped: gh not installed - record the expiry manually"; exit 0; fi
  if [ "$CMD" = grant ]; then
    TITLE="Revoke early access: $FLAG for $CUST (due $EXPIRES)"
    BODY=$(printf 'Scheduled cleanup for an early-access grant.\n\n- **Feature**: `%s`\n- **Customer**: `%s`\n- **Environment**: `%s`\n- **Mechanism**: %s\n- **Expires**: `%s`\n- **Verified**: target `%s`=ON, control `%s`=OFF\n- **Source**: %s\n\nOn or after the due date, ask your agent to revoke it (or run `ea.sh expire`):\n```bash\n%s\n```\n' \
      "$FLAG" "$CUST" "$ENVN" "$MECH" "$EXPIRES" "$TARGET" "$CONTROL" "$( [ -n "$ISSUE" ] && echo "#$ISSUE" || echo "chat request")" "$UNDO_G")
    LBL=""; URL=$(ghc issue create --title "$TITLE" --label early-access --body "$BODY" 2>/dev/null) \
      || { URL=$(ghc issue create --title "$TITLE" --body "$BODY" 2>/dev/null || true); }
    [ -z "$URL" ] || ghc issue view "$URL" --json labels 2>/dev/null | jq -e 'any(.labels[]?; .name=="early-access")' >/dev/null       || LBL=" (unlabeled - gh account lacks triage rights; audit still tracks it by title)"
    if [ -n "$ISSUE" ]; then
      ghc issue comment "$ISSUE" --body "$(printf 'Early access granted: **%s** -> `%s` in %s via %s.\nVerified target `%s`=ON, control `%s`=OFF (unchanged). Expires **%s**; cleanup tracked in %s.' \
        "$CUST" "$FLAG" "$ENVN" "$MECH" "$TARGET" "$CONTROL" "$EXPIRES" "${URL:-(follow-up issue failed)}")" >/dev/null 2>&1 || true
    fi
    echo "TRAIL follow-up=${URL:-FAILED - create manually: \"$TITLE\"}${URL:+$LBL}${ISSUE:+ commented=#$ISSUE}"
  else
    [ -n "$ISSUE" ] || ISSUE=$(ghc issue list --state open --limit 300 --json number,title 2>/dev/null \
      | jq -r --arg p "Revoke early access: $FLAG for $CUST " '[.[]? | select(.title|startswith($p)) | .number][0] // empty' || true)
    if [ -n "$ISSUE" ]; then
      if ghc issue close "$ISSUE" --comment "$(printf 'Early access revoked: **%s** on `%s` (%s). Removed %s. Verified target `%s`=%s, control `%s`=%s.' \
        "$CUST" "$FLAG" "$ENVN" "$MECH" "$TARGET" "$T1" "$CONTROL" "$C1")" >/dev/null 2>&1; then echo "TRAIL closed=#$ISSUE"
      else echo "TRAIL close #$ISSUE FAILED - close it manually"; fi
    else echo "TRAIL no open follow-up issue found"; fi
  fi
  exit 0
fi

# --- graduate ------------------------------------------------------------------------
if [ "$CMD" = graduate ]; then
  preflight_common
  [ "$DEF" = on ] || stop "'$FLAG' default is OFF in $ENVN - turn it on for everyone first (this skill never changes defaults); nothing removed"
  GSEGS=$(jq -c --arg p "ea-$FLAG-" '[.[] | select(.name|startswith($p)) | {id,name}]' <<<"$SEGS")
  IDO=$(rd iovr | jq -c '[.[]? | select(.enabled) | .identifier]')    # grants only
  KEEP=$(rd iovr | jq -c '[.[]? | select(.enabled|not) | .identifier]') # deliberate OFF overrides are not grants: never touched
  NS=$(jq length <<<"$GSEGS"); NI=$(jq length <<<"$IDO")
  ISS='[]'; ! have_gh || ISS=$(ghc issue list --state open --limit 300 --json number,title 2>/dev/null \
    | jq -c --arg p "Revoke early access: $FLAG for " '[.[]? | select(.title|startswith($p)) | .number]' 2>/dev/null || echo '[]')
  [ -n "$ISS" ] || ISS='[]'
  if [ "$NS" -eq 0 ] && [ "$NI" -eq 0 ]; then
    echo "GRADUATE nothing to clean: '$FLAG' default ON, no ea-* segments or identity overrides"; exit 0; fi
  SAMPLE=$(jq -r '.[0] // empty' <<<"$IDO")
  if [ -z "$SAMPLE" ] && [ "$NS" -gt 0 ]; then  # a member of a graduating customer segment
    gc=$(jq -r --arg n "$(jq -r '.[0].name' <<<"$GSEGS")" '[.[] | select(.name==$n)][0].description // "" | (capture("customer=(?<v>[^; ]+)").v // "")' <<<"$SEGS")
    gt=$(jq -r --arg n "$(jq -r '.[0].name' <<<"$GSEGS")" '[.[] | select(.name==$n)][0].rules.rules[0].conditions[0].property // empty' <<<"$SEGS")
    if [ -n "$gc" ]; then TRAIT="${gt:-$TRAIT}"; load_people traits; SAMPLE=$(awk -F'	' -v c="$gc" '$2==c {print $1; exit}' <<<"$PEOPLE"); fi
  fi
  [ -n "$SAMPLE" ] || SAMPLE=$(jq -r '.[0].i // empty' <<<"$IDENTS")
  [ -n "$CONTROL" ] || CONTROL=$(jq -r --arg s "$SAMPLE" --argjson o "$(rd iovr | jq -c '[.[]?.identifier]')" '[.[] | select(.i != $s and ((.i | IN($o[])) | not))][0].i // empty' <<<"$IDENTS")
  CTRL0=on; [ -z "$CONTROL" ] || CTRL0=$(ev "$FLAG" "$CONTROL")
  [ "$CTRL0" != err ] || stop "cannot evaluate control $CONTROL - pass --control <identifier>"
  S=$(snapshot)
  if [ "$APPROVED" -ne 1 ]; then
    printf 'PLAN (%s)\nChange : remove %s segment(s) [%s] + %s identity override(s) [%s] on %s\nWho    : everyone keeps %s via default ON\nControl: %s must stay %s%s\nExpires: N/A (graduating; closes issues %s)\nUndo   : restore from %s\nApprove? (yes/no)\n' \
      "$ENVN" "$NS" "$(jq -r '[.[].name]|join(",")' <<<"$GSEGS")" "$NI" "$(jq -r 'join(",")' <<<"$IDO")" "$FLAG" "$FLAG" \
      "${CONTROL:-<none>}" "$(UP "$CTRL0")" "$([ "$(jq length <<<"$KEEP")" -eq 0 ] || echo "; OFF overrides kept: $(jq -r 'join(",")' <<<"$KEEP")")" "$(jq -r 'map("#\(.)")|join(",")' <<<"$ISS")" "$S"
    stop "awaiting approval - show this PLAN verbatim, wait for an explicit 'yes', then re-run with --approved"
  fi
  FAIL=""
  for id in $(jq -r '.[].id' <<<"$GSEGS"); do
    fsw flag delete "$FLAG" --segment "$id" || true
    fsw segment delete "$id" || FAIL="$FAIL seg:$id"
  done
  for u in $(jq -r '.[]' <<<"$IDO"); do fsw flag delete "$FLAG" --identifier "$u" || FAIL="$FAIL id:$u"; done
  i=0; while :; do T1=$(ev "$FLAG" "${SAMPLE:-none}"); C1=$(ev "$FLAG" "${CONTROL:-none}")
    { [ "$T1" = on ] && [ "$C1" = "$CTRL0" ]; } && break
    i=$((i+1)); [ "$i" -lt "$TRIES" ] || { FAIL="$FAIL verify(sample=$T1,control=$C1)"; break; }; sleep "$WAIT"; done
  echo "REMOVED $NS segment(s), $NI identity override(s) from $FLAG in $ENVN${FAIL:+ - FAILED:$FAIL (snapshot $S)}"
  echo "VERIFY default=on sample=${SAMPLE:-none}:$T1 control=${CONTROL:-none}:$C1"
  if [ -z "$FAIL" ]; then
    ok=""; bad=""
    for n in $(jq -r '.[]' <<<"$ISS"); do
      if ghc issue close "$n" --comment "Feature \`$FLAG\` graduated: default is ON for everyone in $ENVN; early-access overrides removed and verified." >/dev/null 2>&1
      then ok="$ok #$n"; else bad="$bad #$n"; fi
    done
    echo "TRAIL closed=[${ok# }]${bad:+ close FAILED=[${bad# }] - close manually}"; exit 0
  fi
  exit 3
fi

# --- audit / expire (read-only scan; expire then revokes with approval) -----------------
load_state
TODAY="${AUDIT_TODAY:-$(date -u +%Y-%m-%d)}"
bg feats feature list; wait
n=0; for f in $(rd feats | jq -r '.[]?.name' | head -n "$MAX_SCAN"); do n=$((n+1)); bg "io$n" flag list --feature "$f" --identities; done
ISS='[]'; if have_gh; then ISS=$(ghc issue list --state open --limit 300 --json number,title 2>/dev/null || echo '[]'); fi
wait
IDOV='[]'; for i in $(seq 1 "$n"); do IDOV=$(jq -c --argjson a "$(rd "io$i" | jq -c '[.[]? | select(.enabled) | {f:.feature, c:.identifier}]')" '. + $a' <<<"$IDOV"); done
# rows: kind<TAB>customer<TAB>feature<TAB>expires<TAB>status<TAB>issue   (kind: org|user|stale)
ROWS=$(jq -r --arg today "$TODAY" --argjson iss "${ISS:-[]}" --argjson idov "$IDOV" '
  def kv($k): ((capture($k + "=(?<v>[^;\\s]+)") // {v:"-"}).v);
  def st($e): if $e == "-" then "NO-EXPIRY" elif $e < $today then "OVERDUE" else "ok" end;
  def parse: (.title | capture("^Revoke early access: (?<f>\\S+) for (?<c>\\S+) \\(due (?<d>[0-9-]+)\\)")?) // null;
  ([$iss[] | (parse) as $p | select($p != null) | $p + {n: .number}]) as $tr
  | ([.[] | select(.name|startswith("ea-")) | (.description // "") as $d
      | {k:"org", c:($d|kv("customer")), f:($d|kv("flag")), e:($d|kv("expires"))}
      | . as $g | . + {i:([$tr[] | select(.f==$g.f and .c==$g.c) | "#\(.n)"] | join(",") | if .=="" then "-" else . end)}]) as $s
  | ([$idov[] | . as $o | ([$tr[] | select(.f==$o.f and .c==$o.c)][0]) as $t
      | {k:"user", c:.c, f:.f, e:($t.d // "-"), i:(if $t then "#\($t.n)" else "UNTRACKED" end)}]) as $u
  | ([$tr[] | . as $t | select(([$s[], $u[]] | map(select(.f==$t.f and .c==$t.c)) | length) == 0)
      | {k:"stale", c:.c, f:.f, e:.d, i:"#\(.n)"}]) as $x
  | ($s + $u + $x)[] | [.k, .c, .f, .e, (if .k=="stale" then "STALE (no live override)" else st(.e) end), .i] | @tsv' <<<"$SEGS")

if [ "$CMD" = audit ]; then
  echo "| Customer | Feature | Mechanism | Expires | Status | Issue |"; echo "|---|---|---|---|---|---|"
  [ -z "$ROWS" ] || while IFS=$'\t' read -r k c f e s i; do
    case "$k" in org) m="segment ea-$f-$c";; user) m="identity override";; *) m="-";; esac
    echo "| $c | $f | $m | $e | $s | $i |"
  done <<<"$ROWS"
  printf '%s\n' "$ROWS" | awk -F'\t' -v e="$ENVN" 'NF>1 {g+=($1!="stale"); o+=($5=="OVERDUE"); s+=($1=="stale"); u+=($6=="UNTRACKED")}
    END {printf "SUMMARY env=%s grants=%d overdue=%d stale_issues=%d untracked=%d\n", e, g, o, s, u}'
  exit 0
fi

# expire
DUE=$(awk -F'\t' '$5=="OVERDUE"' <<<"$ROWS"); STALE=$(awk -F'\t' '$1=="stale"' <<<"$ROWS")
if [ -z "$DUE" ] && [ -z "$STALE" ]; then echo "EXPIRE nothing overdue in $ENVN (today $TODAY)"; exit 0; fi
if [ "$APPROVED" -ne 1 ]; then
  echo "PLAN ($ENVN) - expire overdue early access (today $TODAY)"
  [ -z "$DUE" ] || while IFS=$'\t' read -r k c f e s i; do echo "Revoke : $f for $([ "$k" = org ] && echo "org:$c" || echo "user:$c") (expired $e, $i) - each verified with a control, auto-rollback"; done <<<"$DUE"
  [ -z "$STALE" ] || while IFS=$'\t' read -r k c f e s i; do echo "Close  : $i (no live override for $c on $f)"; done <<<"$STALE"
  echo "Approve? (yes/no)"
  stop "awaiting approval - show this PLAN verbatim, wait for an explicit 'yes', then re-run with --approved"
fi
RC=0
[ -z "$DUE" ] || while IFS=$'\t' read -r k c f e s i; do
  kk=$([ "$k" = org ] && echo org || echo user); ii="${i%%,*}"; ii="${ii#\#}"
  out=$(bash "$SELF" revoke "$f" "$kk:$c" --approved ${ii:+--issue "$ii"} 2>&1) || RC=3
  echo "[$f $kk:$c] $(tr '\n' ' ' <<<"$out" | cut -c1-300)"
done <<<"$DUE"
[ -z "$STALE" ] || while IFS=$'\t' read -r k c f e s i; do
  ghc issue close "${i#\#}" --comment "Closed by early-access expire: no live override for \`$c\` on \`$f\` in $ENVN." >/dev/null 2>&1 \
    && echo "TRAIL closed stale $i" || echo "TRAIL close $i FAILED"
done <<<"$STALE"
exit "$RC"
