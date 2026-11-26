# Verified Facts — Phase 0 Spike

This document records the exact tool versions, commands, flags, and behaviors verified locally during Phase 0, and explicitly separates **locally observed** facts (from installed binaries and `--help` output) from **pending live verification** items that require Flagsmith Cloud project credentials ([BLOCKERS.md](file:///d:/early-access/docs/BLOCKERS.md) H1/H2).

---

## 1. Environment & Tool Versions

| Tool | Version / Status | Verification Method |
|---|---|---|
| `flagsmith` CLI | `v2.0.0` (`npm install -g @flagsmith/cli`) | Observed locally (`flagsmith --help` / `spike/cli-help-v2.txt`) |
| `gh` (GitHub CLI) | `2.96.0` (2026-07-02) | Observed locally (`gh --version`) |
| `claude` (Claude Code) | `2.1.318 (Claude Code)` | Observed locally (`claude --version`) |
| `jq` | `1.8.2` | Verified by project setup; note `flagsmith` CLI also has built-in `--jq` |

---

## 2. Flagsmith CLI v2.0.0 — Locally Observed Commands & Flags

### Global Flags (available on all `flagsmith` commands)

Observed from `flagsmith --help` (`spike/cli-help-v2.txt`):

| Flag | Env Var | Description |
|---|---|---|
| `--api-url string` | `FLAGSMITH_API_URL` | Flagsmith API base URL (default `"https://api.flagsmith.com"`) |
| `-c, --config-path string` | `FLAGSMITH_CONFIG_PATH` | Path to `flagsmith.json` |
| `-e, --environment string` | `FLAGSMITH_ENVIRONMENT` | Environment as its client-side SDK key |
| `--jq string` | — | Filter JSON output through a `jq` expression (implies `--json`) |
| `--json` | `FLAGSMITH_JSON_OUTPUT` | Output JSON instead of human-readable text |
| `--no-input` | `FLAGSMITH_NO_INPUT` | Never prompt or open a browser; fail if required input is missing |
| `--organisation string` | `FLAGSMITH_ORGANISATION` | Organisation ID or name |
| `-p, --project string` | `FLAGSMITH_PROJECT` | Project ID or name |
| `--sdk-api-url string` | `FLAGSMITH_SDK_API_URL` | SDK API base URL for flag evaluation |
| `--yes` | — | Answer confirmations affirmatively |

### Auth & Context

- `flagsmith auth status` — Show the current identity, organisation, and credential source.
- `flagsmith auth token` — Print the active Admin API credential.
- `flagsmith config` — Show the resolved context and where each value comes from.
- `flagsmith init` — Bind directory to a Flagsmith project (writes `flagsmith.json`).

### Features (`flagsmith feature`)

- `flagsmith feature get <feature>` — Show a feature and its variants. Supports `--json` / `--jq`.
- `flagsmith feature list [--include-archived]` — List features in the current project. Supports `--json` / `--jq`.

### Flags & Overrides (`flagsmith flag`)

- `flagsmith flag get <feature> [--segment <id|name>] [--identifier <id>]`
  - Shows a single flag's state in the current environment, or a specific segment/identity override.
  - Flags: `-i, --identifier string`, `--segment string`, plus global `--json` / `--jq`.
- `flagsmith flag list [--feature <id|name>] [--identities] [--segment <id|name>]`
  - Lists every flag in the current environment.
  - With `--feature <id|name>`: lists that feature's segment overrides in priority order.
  - With `--feature <id|name> --identities`: lists that feature's identity overrides instead.
  - With `--segment <id|name>`: lists overrides for that segment.
- `flagsmith flag update <feature> [--enable | --disable] [--segment <id|name>] [--identifier <id>] [--value <val>] [--type string|integer|boolean] [--priority <int>] [--weight <key|id>=<pct>]`
  - Toggles environment default if neither `--segment` nor `--identifier` is passed.
  - Targets a segment override with `--segment <id|name>`.
  - Targets an identity override with `--identifier <id>`.
- `flagsmith flag delete <feature> [--segment <id|name>] [--identifier <id>]`
  - Removes a segment or identity override in the current environment while leaving the flag itself untouched.

### Segments (`flagsmith segment`)

- `flagsmith segment create <name> --rules <json|@file|-> [--description "<text>"] [--feature <id|name>]`
  - Creates a segment. `--rules` accepts an inline JSON string, `@file`, or `-` for stdin.
  - `--description` attaches metadata used by `audit` discovery.
- `flagsmith segment list [--include-feature-specific]`
  - Lists segments in the current project. Supports `--json` / `--jq`.
- `flagsmith segment get <segment>`
  - Shows a segment and its rule tree. Supports `--json` / `--jq`.
- `flagsmith segment delete <segment> [--yes]`
  - Deletes a segment.

### Evaluation (`flagsmith evaluate`, alias `eval`)

- `flagsmith evaluate [feature] [--identity <id>] [--trait <key=value>] [--test] [--persist] [--js]`
  - Alias: `flagsmith eval`.
  - `--identity <id>` (`-i`): resolves flags for an identifier with segment overrides applied.
  - `--trait key=value` (repeatable): overlays traits transiently without persisting (unless `--persist` is set).
  - `--test`: with a named feature, exits non-zero when the flag is disabled.
  - `--jq .value` (observed in `--help` example): filters single-feature evaluation output.

### Generic Authenticated API (`flagsmith api`)

- `flagsmith api <path> [-X METHOD] [-F key=value] [-f key=value] [--input <file|->] [--sdk] [-H header] [-i]`
  - Fallback for any Admin API endpoint (default) or SDK API endpoint (`--sdk`) not covered by dedicated subcommands.

---

## 3. Pending Live Verification (Requires H1 / H2)

The following items **cannot** be marked observed until Flagsmith Cloud project `early-access-demo` (H1) and API/SDK credentials (H2) are provisioned:

1. **Exact `--json` response schemas and `--jq` field paths** for:
   - `flagsmith feature get <feature> --json` (exact keys for `id`, `name`, `is_archived`, `default_enabled`)
   - `flagsmith flag get <feature> --json` and `flagsmith flag list --feature <f> --identities --json` (exact keys for `enabled`, `feature_state_value`, `identity`, `segment`, `priority`)
   - `flagsmith segment list --json` and `flagsmith segment get <seg> --json` (exact keys for `id`, `name`, `description`, `rules`)
   - `flagsmith evaluate <feature> --identity <id> --trait org_id=<org> --json` (exact keys for `enabled`, `value`, and whether evaluation reason metadata is returned)
2. **Headless auth env var confirmation**: Confirm whether `FLAGSMITH_API_KEY` or `flagsmith auth` token/config is read in `--no-input` mode, and verify `--project` + `--environment` (client-side SDK key) selection end-to-end.
3. **Segment `--rules` JSON schema**: Verify the exact Flagsmith rule tree JSON accepted by `flagsmith segment create --rules` against live Flagsmith Cloud.

---

## 4. GitHub CLI (`gh` 2.96.0) — Locally Observed Commands

Observed from `gh issue <subcommand> --help`:

- **Read an issue as JSON:**
  `gh issue view <number|url> --json number,title,body,state,labels,url,author`
  (Available fields observed: `assignees, author, blockedBy, blocking, body, closed, closedAt, closedByPullRequestsReferences, comments, createdAt, id, isPinned, issueType, labels, milestone, number, parent, projectCards, projectItems, reactionGroups, state, stateReason, subIssues, subIssuesSummary, title, updatedAt, url`. Also supports `-q, --jq`.)
- **Comment on an issue:**
  `gh issue comment <number|url> --body "<text>"` (or `-F, --body-file <file>`).
- **Create a follow-up issue:**
  `gh issue create --title "<title>" --body "<body>" --label "early-access"`
  (Flags observed: `-t, --title`, `-b, --body`, `-F, --body-file`, `-l, --label`.)
- **List open/labelled issues:**
  `gh issue list --label "early-access" --json number,title,body,url,state`
- **Close an issue with comment:**
  `gh issue close <number|url> --comment "<text>"` (supports `-r, --reason completed`).

---

## 5. Agent Skills (`SKILL.md`) Conventions

Per the Agent Skills specification used by Claude Code / Antigravity:

- **Location:** `skill/flagsmith-early-access/SKILL.md` (with optional `references/` and `scripts/` subdirectories).
- **Required YAML Frontmatter:**
  ```yaml
  ---
  name: flagsmith-early-access
  description: <concise trigger-oriented description of what the skill does and when to use it>
  ---
  ```
- **Progressive Disclosure:** Keep `SKILL.md` concise (target < 2,000 words) with core workflows and safety gates; move detailed CLI command tables, identity detection heuristics, and GitHub comment/issue templates into `references/`.

---

## 6. Claude Code (`2.1.318`) Headless Execution Notes

Observed from `claude --help`:

- **Non-interactive execution:** `-p, --print` prints response and exits (no interactive TUI).
- **Structured JSON output:** `--output-format json` (works with `--print`) emits a single JSON payload containing the final result and token/usage metadata for Phase 8 measurement.
- **Turn / permission controls:** `--input-format text` (default) or `stream-json`; `--max-turns` / permission prompt flags should be verified in Phase 6 harness setup when `ANTHROPIC_API_KEY` (H3) is available.
