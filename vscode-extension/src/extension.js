'use strict';

const vscode = require('vscode');
const { FlagsmithClient } = require('./flagsmithClient');
const { scanTextForFlags, formatCodeLensTitle } = require('./flagScanner');

const SUPPORTED_LANGUAGES = [
  'javascript',
  'typescript',
  'javascriptreact',
  'typescriptreact',
  'python'
];

class FlagsmithStateStore {
  constructor() {
    this.client = new FlagsmithClient();
    this.currentIdentity = 'user_1';
    this.state = {
      offline: true,
      identity: 'user_1',
      orgOrProject: null,
      flags: [],
      segments: [],
      error: null
    };
    this._onDidChange = new vscode.EventEmitter();
    this.onDidChange = this._onDidChange.event;
  }

  syncConfig() {
    const cfg = vscode.workspace.getConfiguration('flagsmithEarlyAccess');
    const apiUrl = cfg.get('apiUrl', 'http://localhost:8000');
    const environmentKey = cfg.get('environmentKey', '');
    const apiKey = cfg.get('apiKey', '');
    const defaultIdentity = cfg.get('defaultIdentity', 'user_1');

    this.client.configure({ apiUrl, environmentKey, apiKey, defaultIdentity });
    if (!this.currentIdentity) {
      this.currentIdentity = defaultIdentity || 'user_1';
    }
  }

  async refresh() {
    this.syncConfig();
    this.state = await this.client.fetchState(this.currentIdentity);
    this._onDidChange.fire();
    return this.state;
  }

  async setIdentity(identity) {
    this.currentIdentity = identity || 'user_1';
    return this.refresh();
  }

  async toggleOverride(flagName) {
    const existing = this.state.flags.find((f) => f.name === flagName);
    const currentEnabled = existing ? existing.enabled : false;
    this.client.toggleLocalOverride(flagName, currentEnabled);
    return this.refresh();
  }

  getFlagMap() {
    const map = new Map();
    for (const flag of this.state.flags || []) {
      map.set(flag.name, flag);
    }
    return map;
  }
}

class FlagsmithCodeLensProvider {
  /**
   * @param {FlagsmithStateStore} store
   */
  constructor(store) {
    this.store = store;
    this._onDidChangeCodeLenses = new vscode.EventEmitter();
    this.onDidChangeCodeLenses = this._onDidChangeCodeLenses.event;

    this.store.onDidChange(() => {
      this._onDidChangeCodeLenses.fire();
    });
  }

  /**
   * @param {vscode.TextDocument} document
   */
  provideCodeLenses(document) {
    const flagMap = this.store.getFlagMap();
    const knownFlags = Array.from(flagMap.keys());
    const matches = scanTextForFlags(document.getText(), knownFlags);

    return matches.map((m) => {
      const range = new vscode.Range(m.line, m.startCol, m.line, m.endCol);
      const flagState = flagMap.get(m.flagKey);
      const title = formatCodeLensTitle(m.flagKey, flagState, {
        identity: this.store.state.identity,
        orgOrProject: this.store.state.orgOrProject,
        offline: this.store.state.offline
      });

      return new vscode.CodeLens(range, {
        title,
        command: 'flagsmithEarlyAccess.toggleOverride',
        arguments: [m.flagKey],
        tooltip: 'Click to toggle local Flagsmith override for this flag'
      });
    });
  }
}

class FlagsmithTreeItem extends vscode.TreeItem {
  constructor(label, collapsibleState = vscode.TreeItemCollapsibleState.None, options = {}) {
    super(label, collapsibleState);
    if (options.description !== undefined) this.description = options.description;
    if (options.tooltip !== undefined) this.tooltip = options.tooltip;
    if (options.contextValue !== undefined) this.contextValue = options.contextValue;
    if (options.iconPath !== undefined) this.iconPath = options.iconPath;
    if (options.command !== undefined) this.command = options.command;
    if (options.children !== undefined) this.children = options.children;
    if (options.flagName !== undefined) this.flagName = options.flagName;
  }
}

class FlagsmithTreeDataProvider {
  /**
   * @param {FlagsmithStateStore} store
   */
  constructor(store) {
    this.store = store;
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;

    this.store.onDidChange(() => {
      this._onDidChangeTreeData.fire();
    });
  }

  getTreeItem(element) {
    return element;
  }

  getChildren(element) {
    if (element && Array.isArray(element.children)) {
      return element.children;
    }
    if (element) {
      return [];
    }

    const { offline, identity, orgOrProject, flags, segments, error } = this.store.state;
    const statusDesc = offline ? 'Offline fallback' : 'Connected';
    const identityLabel = orgOrProject ? `${identity} (${orgOrProject})` : identity;

    const statusItem = new FlagsmithTreeItem(
      `Identity: ${identityLabel}`,
      vscode.TreeItemCollapsibleState.None,
      {
        description: statusDesc,
        tooltip: error || `Connected to ${this.store.client.apiUrl}`,
        iconPath: new vscode.ThemeIcon(offline ? 'warning' : 'account'),
        command: {
          command: 'flagsmithEarlyAccess.switchIdentity',
          title: 'Switch Identity'
        }
      }
    );

    const flagItems = (flags || []).map((flag) => {
      const stateText = flag.enabled ? 'ON' : 'OFF';
      const valText = flag.value !== null && flag.value !== undefined && flag.value !== ''
        ? ` · ${JSON.stringify(flag.value)}`
        : '';
      return new FlagsmithTreeItem(
        flag.name,
        vscode.TreeItemCollapsibleState.None,
        {
          description: `${stateText}${valText} (${flag.source})`,
          tooltip: `Flag: ${flag.name}\nState: ${stateText}\nSource: ${flag.source}`,
          contextValue: 'flagItem',
          flagName: flag.name,
          iconPath: new vscode.ThemeIcon(flag.enabled ? 'pass-filled' : 'circle-large-outline')
        }
      );
    });

    const flagsGroup = new FlagsmithTreeItem(
      'Feature Flags',
      vscode.TreeItemCollapsibleState.Expanded,
      {
        description: `${flagItems.length}`,
        children: flagItems,
        iconPath: new vscode.ThemeIcon('symbol-boolean')
      }
    );

    const segmentItems = (segments || []).map((seg) =>
      new FlagsmithTreeItem(seg.name, vscode.TreeItemCollapsibleState.None, {
        description: seg.description || 'Early Access segment',
        iconPath: new vscode.ThemeIcon('tag')
      })
    );

    const segmentsGroup = new FlagsmithTreeItem(
      'Early Access Segments (ea-*)',
      vscode.TreeItemCollapsibleState.Expanded,
      {
        description: segmentItems.length > 0 ? `${segmentItems.length}` : 'None',
        children: segmentItems.length > 0
          ? segmentItems
          : [new FlagsmithTreeItem('No ea-* segments loaded', vscode.TreeItemCollapsibleState.None, {
              description: 'Set apiKey to load Admin segments'
            })],
        iconPath: new vscode.ThemeIcon('organization')
      }
    );

    return [statusItem, flagsGroup, segmentsGroup];
  }
}

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  const store = new FlagsmithStateStore();
  store.syncConfig();

  const codeLensProvider = new FlagsmithCodeLensProvider(store);
  const treeProvider = new FlagsmithTreeDataProvider(store);

  context.subscriptions.push(
    vscode.languages.registerCodeLensProvider(
      SUPPORTED_LANGUAGES.map((language) => ({ language })),
      codeLensProvider
    ),
    vscode.window.registerTreeDataProvider('flagsmithEarlyAccessView', treeProvider),
    vscode.commands.registerCommand('flagsmithEarlyAccess.refreshFlags', async () => {
      const state = await store.refresh();
      const mode = state.offline ? 'offline fallback' : 'live';
      vscode.window.setStatusBarMessage(`Flagsmith: refreshed ${state.flags.length} flags (${mode})`, 3000);
    }),
    vscode.commands.registerCommand('flagsmithEarlyAccess.switchIdentity', async () => {
      const next = await vscode.window.showInputBox({
        prompt: 'Enter Flagsmith identity identifier (e.g. user_1)',
        value: store.currentIdentity
      });
      if (next !== undefined && next.trim()) {
        await store.setIdentity(next.trim());
      }
    }),
    vscode.commands.registerCommand('flagsmithEarlyAccess.toggleOverride', async (arg) => {
      const flagName = typeof arg === 'string' ? arg : (arg && arg.flagName);
      if (!flagName) return;
      await store.toggleOverride(flagName);
    }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('flagsmithEarlyAccess')) {
        const cfg = vscode.workspace.getConfiguration('flagsmithEarlyAccess');
        store.currentIdentity = cfg.get('defaultIdentity', 'user_1');
        store.refresh();
      }
    })
  );

  // Initial background fetch
  store.refresh();
}

function deactivate() {}

module.exports = {
  activate,
  deactivate,
  FlagsmithStateStore,
  FlagsmithCodeLensProvider,
  FlagsmithTreeDataProvider
};
