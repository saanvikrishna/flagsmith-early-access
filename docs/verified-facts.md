# Verified Facts: Flagsmith CLI `v2.0.0`, `gh`, Agent Skills

Tool versions, flags, JSON shapes and quirks verified locally and live against Flagsmith Cloud (`early-access-demo`) and GitHub. The command-by-command reference used for debugging is `skill/flagsmith-early-access/references/cli-commands.md`; this page is the summary.

## 1. Environment

| Tool | Version | Verified by |
|---|---|---|
| `flagsmith` CLI | `v2.0.0` (`npm install -g @flagsmith/cli`) | `flagsmith --help` and live Cloud runs |
| `gh` | `2.96.0` | live issue lifecycle runs |
| `claude` (Claude Code) | `2.1.318` | live headless harness runs |
| `jq` | `1.8.2` | used by `ea.sh` |

## 2. Flagsmith CLI v2.0.0

### Global flags

| Flag | Env var | Description |
|---|---|---|
| `--api-url` | `FLAGSMITH_API_URL` | API base URL (default `https://api.flagsmith.com`) |
| `-c, --config-path` | `FLAGSMITH_CONFIG_PATH` | Path to `flagsmith.json` |
| `-e, --environment` | `FLAGSMITH_ENVIRONMENT` | Environment as its client-side SDK key |
| `--jq` | - | Filter JSON output (implies `--json`) |
| `--json` | `FLAGSMITH_JSON_OUTPUT` | JSON output |
| `--no-input` | `FLAGSMITH_NO_INPUT` | Never prompt; fail fast |
| `--organisation` | `FLAGSMITH_ORGANISATION` | Organisation ID or name |
| `-p, --project` | `FLAGSMITH_PROJECT` | Project ID or name |
| `--sdk-api-url` | `FLAGSMITH_SDK_API_URL` | SDK API base URL |
| `--yes` | - | Answer confirmations affirmatively |

### Commands used

- `feature get|list [--include-archived]`
- `flag get|list|update|delete` with `--segment <id>` or `--identifier <id>`; `flag list --feature <f> [--identities]`
- `segment create|get|list|delete`
- `evaluate <flag> --identity <id>` (alias `eval`; `--trait k=v` overlays transient traits, `--persist` stores them)
- `api <path> [-X METHOD]` for Admin API reads (edge-identities and traits)
- `config`, `auth status`

### Verified JSON shapes

Fields that do not exist and must not be used: `is_archived`, `feature_state_value`, `segment_priority`.

| Command | Shape |
|---|---|
| `config --json` | `{environment:{name,value}, project:{value}}` (`environment.value` is the SDK key) |
| `feature get <f> --json` | `{id,name,type,default_value,enabled}`; an archived feature returns "not found" |
| `flag get <f> --json` | `{feature,enabled,value,segment_overrides:N,identity_overrides:N}` |
| `flag get <f> --segment <id> --json` | `{segment:{id,name},priority,enabled,value}` |
| `flag list --feature <f> --json` | Segment overrides in priority order |
| `flag list --feature <f> --identities --json` | `[{identifier,enabled,value}]` |
| `segment list --json` | `[{id,name,description,rules}]` |
| `evaluate <f> --identity <id> --json` | `{name,enabled,value,reason}` where reason is `TARGETING_MATCH; segment=...` or `DEFAULT` |
| `api "api/v1/environments/<key>/edge-identities/?q=<id>"` | `{results:[{identity_uuid,identifier}]}` |
| `api ".../edge-identities/<uuid>/list-traits/"` | `[{trait_key,trait_value}]` |

Self-hosted (non-Edge) Flagsmith uses `.../identities/?q=<id>` and `.../identities/<id>/traits/`.

Segment `--rules` payload:

```json
{"type":"ALL","rules":[{"type":"ANY","conditions":[{"property":"org_id","operator":"EQUAL","value":"<customer>"}]}]}
```

## 3. CLI quirks found by live testing

| Quirk | Consequence | How `ea.sh` handles it |
|---|---|---|
| The npm `@flagsmith/cli` wrapper always exits 0, even on `Error:` (the native binary exits 1) | Exit codes cannot gate anything | Parses stdout JSON, reads `Error` from stderr, re-reads state after every write |
| `segment create` allows duplicate names; name-based commands then fail as ambiguous | A retried grant would break revoke | Refuses duplicates; writes use segment ids |
| `flag update --identifier <unknown>` silently creates the identity | A typo grants a feature to a ghost identity | Refuses user grants to identities that do not exist |
| `evaluate --trait k=v` overlays transient traits | Hides real drift | Verification uses persisted traits only |
| Status lines go to stderr, JSON to stdout | | Captured separately |
| Windows `jq.exe` emits CRLF | Values carry `\r` | `ea.sh` strips CR |
| Edge evaluation can lag a write by a few seconds | An immediate check reads stale state and triggers a false rollback (seen live in benchmark X3) | `verify` polls up to `EA_VERIFY_TRIES` x `EA_VERIFY_WAIT`s (default 6 x 2s) before deciding |
| An identity override beats every segment override | A target with its own `off` override never turns on, so verification fails | Auto-selected targets skip identities with overrides; an explicit `--target` with one is refused at preview |
| The previous helper scripts used the wrong field names above, and `snapshot.sh` crashed (`jq --argjson` on empty input) before every new grant | | Replaced by `ea.sh` with the verified shapes |

## 4. GitHub CLI (`gh` 2.96.0)

- `gh issue view <n> --json number,title,body,author,url`
- `gh issue create --title ... --body ... [--label early-access]` (the label needs triage rights; `ea.sh` retries without it)
- `gh issue comment <n> --body ...`
- `gh issue list --state open --json number,title` (`ea.sh` matches follow-up issues by title)
- `gh issue close <n> --comment ...`

## 5. Agent Skills conventions

- Location: `skill/flagsmith-early-access/SKILL.md` with `references/` and `scripts/`.
- Frontmatter: `name: flagsmith-early-access` and a trigger-oriented `description`.
- Progressive disclosure: `SKILL.md` is ~800 words (CI budget 2,000); command shapes live in `references/cli-commands.md` and mechanics in `scripts/ea.sh`.

## 6. Claude Code headless execution

Used by `harness/bench.py`: `-p/--print` for non-interactive runs, `--output-format json` for turn counts and token usage (`input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`), recorded in [results/tokens.md](../results/tokens.md).
