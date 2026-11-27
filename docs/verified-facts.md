# Verified Facts — Flagsmith CLI `v2.0.0`, `gh`, & Agent Skills

This reference records all tool versions, CLI flags, JSON schemas, and behaviors verified locally and live against **Flagsmith Cloud** (`early-access-demo`) and **GitHub** (`saanvikrishna/flagsmith-early-access`).

---

## 1. Environment & Tool Versions

| Tool | Version | Verification Method |
|---|---|---|
| `flagsmith` CLI | `v2.0.0` (`npm install -g @flagsmith/cli`) | Local CLI (`flagsmith --help`, `spike/cli-help-v2.txt`) + Live Cloud runs |
| `gh` (GitHub CLI) | `2.96.0` (2026-07-02) | Local CLI (`gh --version`) + Live GitHub issue lifecycle runs |
| `claude` (Claude Code) | `2.1.318` (`claude-opus-5-5`) | Local CLI (`claude --version`) + Live headless harness runs |
| `jq` | `1.8.2` | Verified JSON filtering alongside `flagsmith --jq` |

---

## 2. Flagsmith CLI `v2.0.0` — Verified Commands & Flags

### Global Flags (Available on All Subcommands)

| Flag | Env Var | Description |
|---|---|---|
| `--api-url string` | `FLAGSMITH_API_URL` | Flagsmith API base URL (default `"https://api.flagsmith.com"`) |
| `-c, --config-path string` | `FLAGSMITH_CONFIG_PATH` | Path to `flagsmith.json` |
| `-e, --environment string` | `FLAGSMITH_ENVIRONMENT` | Environment as its client-side SDK key |
| `--jq string` | — | Filter JSON output through a `jq` expression (implies `--json`) |
| `--json` | `FLAGSMITH_JSON_OUTPUT` | Output JSON instead of human-readable text |
| `--no-input` | `FLAGSMITH_NO_INPUT` | Never prompt or open a browser; fail fast if required input is missing |
| `--organisation string` | `FLAGSMITH_ORGANISATION` | Organisation ID or name |
| `-p, --project string` | `FLAGSMITH_PROJECT` | Project ID or name |
| `--sdk-api-url string` | `FLAGSMITH_SDK_API_URL` | SDK API base URL for flag evaluation |
| `--yes` | — | Answer confirmations affirmatively |

### Auth & Context

- `flagsmith auth status --json --jq '{authenticated, organisation}'` — Verify active identity, organisation, and credential source.
- `flagsmith auth token` — Print active Admin API credential.
- `flagsmith config --json --jq '{project, environment, api_url}'` — Inspect resolved context and precedence.
- `flagsmith init` — Bind a directory to a Flagsmith project (`flagsmith.json`).

### Features (`flagsmith feature`)

- `flagsmith feature get <feature> --json --jq '{id, name, is_archived}'` — Retrieve feature metadata and archive state.
- `flagsmith feature list [--include-archived]` — List features in the current project.

### Flags & Overrides (`flagsmith flag`)

- `flagsmith flag get <feature> [--segment <id|name>] [--identifier <id>]` — Read environment default (`{enabled, feature_state_value}`) or a specific segment/identity override.
- `flagsmith flag list [--feature <id|name>] [--identities] [--segment <id|name>]` — List environment flags or feature overrides in priority order.
- `flagsmith flag update <feature> [--enable | --disable] [--segment <id|name>] [--identifier <id>] [--value <val>] [--type string|integer|boolean] [--priority <int>] [--weight <key|id>=<pct>]` — Apply an override (`--segment` or `--identifier`) or environment default.
- `flagsmith flag delete <feature> [--segment <id|name>] [--identifier <id>] [--yes] [--no-input]` — Remove a segment or identity override while leaving the flag untouched.

### Segments (`flagsmith segment`)

- `flagsmith segment create <name> --rules <json|@file|-> [--description "<text>"] [--feature <id|name>] [--no-input]` — Create an early-access segment (`--rules` accepts inline JSON, `@file`, or `-`).
- `flagsmith segment list [--include-feature-specific]` — List project segments (filtered with `--jq` for `ea-` prefixes).
- `flagsmith segment get <segment>` — Inspect `{id, name, description, rules}` for snapshot capture.
- `flagsmith segment delete <segment> --yes --no-input` — Delete an early-access segment during `revoke` or `graduate`.

### Evaluation (`flagsmith evaluate`, alias `eval`)

- `flagsmith evaluate [feature] [--identity <id>] [--trait <key=value>] [--test] [--persist] [--js]` — Resolve flags for an identity with segment overrides applied.
- `--trait key=value` overlays transient traits without persistence unless `--persist` is set.
- `--test` exits non-zero when a named flag evaluates to disabled.

### Generic Authenticated API (`flagsmith api`)

- `flagsmith api <path> [-X METHOD] [-F key=value] [-f key=value] [--input <file|->] [--sdk] [-H header] [-i]` — Authenticated fallback for Admin API endpoints (such as listing identity feature states via `api/v1/environments/<env_id>/featurestates/?feature=<feature_id>`) or SDK API endpoints (`--sdk`).

---

## 3. Live Flagsmith Cloud Verification (`early-access-demo`)

All CLI patterns, JSON fields, and rule payloads were verified end-to-end against Flagsmith Cloud project `early-access-demo` (`results/demo-run.md`):

1. **Verified `--json --jq` field paths:**
   - `flagsmith feature get <flag> --json` -> `{id, name, is_archived}`
   - `flagsmith flag get <flag> --json` -> `{enabled, feature_state_value}` (and `segment_priority` for segment overrides)
   - `flagsmith segment list --json` / `flagsmith segment get <seg> --json` -> `{id, name, description, rules}`
   - `flagsmith evaluate <flag> --identity <id> --json` -> `{enabled, value}` (with evaluation reason metadata such as `TARGETING_MATCH; segment=ea-bulk_export-initech` or `DEFAULT`)
   - `flagsmith api "api/v1/environments/<env_id>/featurestates/?feature=<feature_id>"` -> `.results[] | select(.identity != null) | {id, identity, enabled}`
2. **Verified headless authentication & context selection:**
   - `FLAGSMITH_API_KEY`, `FLAGSMITH_ORGANISATION`, `FLAGSMITH_PROJECT`, and `FLAGSMITH_ENVIRONMENT` operate cleanly under `--no-input` across both `demo-seed/seed_flagsmith.py --mode live` and `harness/run.py --mode live`.
3. **Verified segment `--rules` JSON schema:**
   ```json
   [{"type":"ALL","rules":[{"type":"ANY","conditions":[{"operator":"EQUAL","property":"org_id","value":"<customer>"}]}]}]
   ```

---

## 4. GitHub CLI (`gh` `2.96.0`) — Verified Commands

- **Read an issue as JSON:** `gh issue view <number|url> --json number,title,body,author,url`
- **Comment on an issue:** `gh issue comment <number|url> --body "<text>"` (or `-F, --body-file <file>`)
- **Create a follow-up issue:** `gh issue create --title "<title>" --body "<body>" --label "early-access"`
- **List open/labelled issues:** `gh issue list --label "early-access" --state open --json number,title,url,body`
- **Close an issue with comment:** `gh issue close <number|url> --comment "<text>"` (supports `-r, --reason completed`)

---

## 5. Agent Skills (`SKILL.md`) Conventions

Per the Agent Skills specification used by Claude Code and Antigravity:

- **Location:** `skill/flagsmith-early-access/SKILL.md` (with `references/` and `scripts/` subdirectories).
- **YAML Frontmatter:**
  ```yaml
  ---
  name: flagsmith-early-access
  description: <concise trigger-oriented description of what the skill does and when to use it>
  ---
  ```
- **Progressive Disclosure:** `SKILL.md` remains concise (`< 2,000` words, validated in CI), while detailed CLI tables, identity-detection heuristics, and GitHub issue templates live in `references/`.

---

## 6. Claude Code (`2.1.318`) Headless Execution

Verified live in `harness/run.py --mode live`:

- **Non-interactive execution:** `-p, --print` prints the final response and exits cleanly.
- **Structured JSON telemetry:** `--output-format json` emits the final result along with exact turn counts and token usage (`input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`) recorded in `results/tokens.md`.
