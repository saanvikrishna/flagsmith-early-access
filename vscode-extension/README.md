# Flagsmith Early Access (Self-Hosted) — VS Code Extension

Live inline Flagsmith feature flag values (via CodeLens) and Early Access (`ea-*`) segment visibility in VS Code for self-hosted open-source Flagsmith.

## Features

- **Inline CodeLens**: Detects Flagsmith flag references in JS, TS, JSX, TSX, and Python files (`hasFeature(...)`, `getValue(...)`, `is_feature_enabled(...)`, and known flag keys) and renders live flag values above the line (e.g. `Flagsmith [user_1 / acme]: new_dashboard = OFF (default)`).
- **Explorer Sidebar View (`Flagsmith Early Access`)**: Displays the active identity, connection status (with graceful offline fallback), live feature flags, and `ea-*` Early Access segments.
- **Commands**:
  - `Flagsmith: Refresh Flags` (`flagsmithEarlyAccess.refreshFlags`)
  - `Flagsmith: Switch Identity` (`flagsmithEarlyAccess.switchIdentity`)
  - `Flagsmith: Toggle Early Access Override` (`flagsmithEarlyAccess.toggleOverride`)

## Configuration

Open VS Code Settings and configure:

- `flagsmithEarlyAccess.apiUrl` (default: `http://localhost:8000`)
- `flagsmithEarlyAccess.environmentKey` — Client/Server Environment Key (`X-Environment-Key`)
- `flagsmithEarlyAccess.apiKey` — Optional Admin API Token to load `ea-*` segments
- `flagsmithEarlyAccess.defaultIdentity` (default: `user_1`)

## Running in VS Code (Extension Development Host)

1. Open `d:\early-access\vscode-extension` in VS Code.
2. Press `F5` to launch an **Extension Development Host** window.
3. Open any JS, TS, or Python file referencing Flagsmith flags to see live CodeLens annotations, and check the **Flagsmith Early Access** panel in the Explorer sidebar.

## Running Tests

Zero npm dependencies are required. Run the built-in Node test runner:

```bash
node --test test/extension.test.js
```

## Packaging with `vsce`

To package as a `.vsix` file for distribution or local installation:

```bash
npm install -g @vscode/vsce
vsce package
```

Then install the generated `.vsix` via `code --install-extension flagsmith-early-access-vscode-0.1.0.vsix`.
