# Flagsmith CLI v2 - verified shapes & quirks (for debugging `ea.sh`)

You normally never need these: `ea.sh` wraps them. Read this only when `ea.sh` reports something unexpected.
Everything here was verified live against Flagsmith Cloud with `flagsmith v2.0.0`.

## Quirks that shape `ea.sh`

| Quirk | Consequence | How `ea.sh` handles it |
|---|---|---|
| The npm wrapper (`@flagsmith/cli`) **always exits 0**, even on `Error:` (the native binary exits 1) | You can't gate on `$?` | Parses stdout JSON and reads `Error` from stderr. Re-reads state after every write |
| `segment create` **allows duplicate names**. Name lookups then fail with `is ambiguous (2 matches)` | A retried grant would break revoke | Refuses grants when the segment exists. Uses segment **ids** for every write. Stops on duplicates |
| `flag update --identifier <unknown>` **silently creates the identity** | A typo grants a feature to a ghost identity | Refuses user grants unless the identity already exists |
| `evaluate --trait k=v` overlays transient traits | Hides real drift | Verification uses persisted traits only |
| Status lines (`✓ Created ...`) go to stderr; JSON goes to stdout | | Captured separately |
| Windows `jq.exe` emits CRLF | Values carry `\r` | `ea.sh` strips CR |
| Edge evaluation can lag a write by a few seconds | An immediate check reads stale state and triggers a false rollback (seen live in benchmark X3) | `verify` polls up to `EA_VERIFY_TRIES` x `EA_VERIFY_WAIT`s (default 6 x 2s) before deciding |
| An identity override beats every segment override | A target with its own `off` override never turns on, so verification fails | Auto-selected targets skip identities with overrides; an explicit `--target` with one is refused at preview |

## Read commands (JSON shapes)

```bash
flagsmith config --json                       # {environment:{name,value(sdk key)}, project:{value}}
flagsmith feature get <f> --json              # {id,name,type,default_value,enabled}   (archived => "not found")
flagsmith feature list --include-archived --json
flagsmith flag get <f> --json                 # {feature,enabled,value,segment_overrides:N,identity_overrides:N}
flagsmith flag get <f> --segment <id> --json  # {segment:{id,name},priority,enabled,value}
flagsmith flag list --feature <f> --json      # segment overrides, in priority order
flagsmith flag list --feature <f> --identities --json   # [{identifier,enabled,value}]
flagsmith segment list --json                 # [{id,name,description,rules}]
flagsmith evaluate <f> --identity <id> --json # {name,enabled,value,reason: "TARGETING_MATCH; segment=..."|"DEFAULT"}
flagsmith api "api/v1/environments/<key>/edge-identities/?q=<id>"          # {results:[{identity_uuid,identifier}]}
flagsmith api "api/v1/environments/<key>/edge-identities/<uuid>/list-traits/"  # [{trait_key,trait_value}]
```

Self-hosted (non-Edge) Flagsmith uses `api/v1/environments/<key>/identities/?q=<id>` and `.../identities/<id>/traits/`.

## Manual equivalents of a grant (for an emergency, by hand)

```bash
flagsmith segment create ea-<flag>-<customer> --description "early-access; flag=<flag>; customer=<customer>; expires=<date>; issue=#<n>" \
  --rules '{"type":"ALL","rules":[{"type":"ANY","conditions":[{"property":"org_id","operator":"EQUAL","value":"<customer>"}]}]}' --json   # -> {id}
flagsmith flag update <flag> --enable --segment <id> --yes
flagsmith flag delete <flag> --segment <id> --yes && flagsmith segment delete <id> --yes   # undo
flagsmith flag update <flag> --enable --identifier <id> --yes                               # user grant
flagsmith flag delete <flag> --identifier <id> --yes                                        # undo
```
