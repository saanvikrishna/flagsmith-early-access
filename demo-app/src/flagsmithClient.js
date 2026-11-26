import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildIdentifier } from './users.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_STATE_PATH = path.resolve(__dirname, '..', 'demo-state.json');

export const FEATURE_FLAGS = ['new_dashboard', 'ai_summaries', 'bulk_export'];
export const DEFAULT_SDK_API_URL = 'https://edge.api.flagsmith.com/api/v1/identities/';

function getEnvKey() {
  if (process.env.DEMO_OFFLINE === '1') {
    return null;
  }
  return process.env.FLAGSMITH_ENV_KEY || process.env.FLAGSMITH_ENV_KEY_PROD || null;
}

function loadOfflineState(statePath = DEFAULT_STATE_PATH) {
  try {
    const raw = fs.readFileSync(statePath, 'utf8');
    return JSON.parse(raw);
  } catch {
    return {
      defaults: {
        new_dashboard: false,
        ai_summaries: false,
        bulk_export: false,
      },
      orgOverrides: {},
      identityOverrides: {},
    };
  }
}

export function formatTraitPayload(traits = {}) {
  return Object.entries(traits)
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([trait_key, trait_value]) => ({
      trait_key,
      trait_value,
    }));
}

export function evaluateOfflineFlags(identifier, traits = {}, state) {
  const resolvedState = state ?? loadOfflineState();
  const defaults = resolvedState.defaults ?? {};
  const orgOverrides = resolvedState.orgOverrides?.[traits.org_id] ?? {};
  const identityOverrides = resolvedState.identityOverrides?.[identifier] ?? {};

  const result = {};
  for (const flagName of FEATURE_FLAGS) {
    const enabled = Boolean(
      identityOverrides[flagName] ??
        orgOverrides[flagName] ??
        defaults[flagName] ??
        false
    );
    result[flagName] = {
      enabled,
      value: null,
    };
  }
  return result;
}

export function normalizeFlagsmithResponse(payload) {
  const byName = new Map();
  for (const entry of payload?.flags ?? []) {
    const name = entry?.feature?.name;
    if (name) {
      byName.set(name, {
        enabled: Boolean(entry.enabled),
        value: entry.feature_state_value ?? null,
      });
    }
  }

  const result = {};
  for (const flagName of FEATURE_FLAGS) {
    result[flagName] = byName.get(flagName) ?? { enabled: false, value: null };
  }
  return result;
}

export function createFlagsmithClient(options = {}) {
  const envKey = options.envKey !== undefined ? options.envKey : getEnvKey();
  const apiUrl = options.apiUrl || process.env.FLAGSMITH_SDK_API_URL || DEFAULT_SDK_API_URL;
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const offlineState = options.offlineState;
  const statePath = options.statePath || DEFAULT_STATE_PATH;

  function getMode() {
    return envKey ? 'live' : 'offline';
  }

  /**
   * Identify a user in Flagsmith using `user_<id>` and traits `{ org_id, plan }`.
   */
  async function identify(userId, traits = {}) {
    const identifier = buildIdentifier(userId);
    const traitPayload = formatTraitPayload({
      org_id: traits.org_id,
      plan: traits.plan,
    });

    if (!envKey) {
      const state = offlineState ?? loadOfflineState(statePath);
      return {
        mode: 'offline',
        identifier,
        traits: { org_id: traits.org_id, plan: traits.plan },
        flags: evaluateOfflineFlags(identifier, traits, state),
      };
    }

    const response = await fetchImpl(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Environment-Key': envKey,
      },
      body: JSON.stringify({
        identifier,
        traits: traitPayload,
      }),
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => '');
      throw new Error(`Flagsmith API error (${response.status}): ${detail || response.statusText}`);
    }

    const data = await response.json();
    return {
      mode: 'live',
      identifier,
      traits: { org_id: traits.org_id, plan: traits.plan },
      flags: normalizeFlagsmithResponse(data),
    };
  }

  async function getIdentityFlags(userId, traits = {}) {
    const result = await identify(userId, traits);
    return result.flags;
  }

  return {
    getMode,
    identify,
    getIdentityFlags,
  };
}
