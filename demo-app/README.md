# Projects Dashboard (`demo-app`)

Lightweight Node.js + Express B2B "Projects Dashboard" used to demonstrate Flagsmith per-customer early access management.

## Identity & Flag Conventions

- **Identity pattern**: `user_<id>` (e.g. `user_1`, `user_3`, `user_42`)
- **Traits**: `org_id` (`acme`, `globex`, `initech`), `plan` (`enterprise`, `pro`, `starter`)
- **Flags**: `new_dashboard`, `ai_summaries`, `bulk_export`

## Quick Start

```bash
npm install
npm test
npm start
```

### Live Flagsmith Mode

Set `FLAGSMITH_ENV_KEY` (or `FLAGSMITH_ENV_KEY_PROD`) before starting:

```bash
FLAGSMITH_ENV_KEY=your_server_or_client_env_key npm start
```

When `FLAGSMITH_ENV_KEY` is unset (or `DEMO_OFFLINE=1`), the app uses `demo-state.json` as a deterministic local fallback.
