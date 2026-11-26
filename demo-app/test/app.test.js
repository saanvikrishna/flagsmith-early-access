import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildIdentifier,
  findUserById,
  getUserTraits,
} from '../src/users.js';
import {
  createFlagsmithClient,
  evaluateOfflineFlags,
  formatTraitPayload,
  normalizeFlagsmithResponse,
} from '../src/flagsmithClient.js';
import { createApp } from '../src/server.js';

describe('Identity and trait mapping', () => {
  it('formats user_<id> identifiers consistently', () => {
    assert.equal(buildIdentifier(1), 'user_1');
    assert.equal(buildIdentifier('42'), 'user_42');
    assert.equal(buildIdentifier('user_3'), 'user_3');
  });

  it('maps Acme, Globex, and Initech users with org_id and plan traits', () => {
    const acmeUser = findUserById('1');
    assert.equal(acmeUser.identifier, 'user_1');
    assert.deepEqual(getUserTraits(acmeUser), { org_id: 'acme', plan: 'enterprise' });

    const globexUser = findUserById('user_3');
    assert.equal(globexUser.identifier, 'user_3');
    assert.deepEqual(getUserTraits(globexUser), { org_id: 'globex', plan: 'pro' });

    const initechUser = findUserById('42');
    assert.equal(initechUser.identifier, 'user_42');
    assert.deepEqual(getUserTraits(initechUser), { org_id: 'initech', plan: 'starter' });
  });

  it('formats traits into Flagsmith API trait objects', () => {
    assert.deepEqual(formatTraitPayload({ org_id: 'acme', plan: 'enterprise' }), [
      { trait_key: 'org_id', trait_value: 'acme' },
      { trait_key: 'plan', trait_value: 'enterprise' },
    ]);
  });
});

describe('Flagsmith client evaluation', () => {
  it('evaluates defaults, org overrides, and identity overrides in offline mode', () => {
    const state = {
      defaults: { new_dashboard: false, ai_summaries: false, bulk_export: false },
      orgOverrides: {
        acme: { new_dashboard: true },
        initech: { bulk_export: true },
      },
      identityOverrides: {
        user_3: { ai_summaries: true },
      },
    };

    const acmeFlags = evaluateOfflineFlags('user_1', { org_id: 'acme', plan: 'enterprise' }, state);
    assert.equal(acmeFlags.new_dashboard.enabled, true);
    assert.equal(acmeFlags.ai_summaries.enabled, false);
    assert.equal(acmeFlags.bulk_export.enabled, false);

    const globexFlags = evaluateOfflineFlags('user_3', { org_id: 'globex', plan: 'pro' }, state);
    assert.equal(globexFlags.new_dashboard.enabled, false);
    assert.equal(globexFlags.ai_summaries.enabled, true);

    const initechFlags = evaluateOfflineFlags('user_42', { org_id: 'initech', plan: 'starter' }, state);
    assert.equal(initechFlags.bulk_export.enabled, true);
    assert.equal(initechFlags.new_dashboard.enabled, false);
  });

  it('sends identifier and traits to Flagsmith API in live mode', async () => {
    let capturedRequest = null;
    const mockFetch = async (url, init) => {
      capturedRequest = { url, init };
      return {
        ok: true,
        async json() {
          return {
            flags: [
              { feature: { name: 'new_dashboard' }, enabled: true, feature_state_value: null },
              { feature: { name: 'ai_summaries' }, enabled: false, feature_state_value: null },
              { feature: { name: 'bulk_export' }, enabled: false, feature_state_value: null },
            ],
          };
        },
      };
    };

    const client = createFlagsmithClient({
      envKey: 'test-env-key',
      apiUrl: 'https://edge.api.flagsmith.com/api/v1/identities/',
      fetchImpl: mockFetch,
    });

    assert.equal(client.getMode(), 'live');
    const flags = await client.getIdentityFlags('1', { org_id: 'acme', plan: 'enterprise' });

    assert.equal(capturedRequest.url, 'https://edge.api.flagsmith.com/api/v1/identities/');
    assert.equal(capturedRequest.init.headers['X-Environment-Key'], 'test-env-key');
    const body = JSON.parse(capturedRequest.init.body);
    assert.equal(body.identifier, 'user_1');
    assert.deepEqual(body.traits, [
      { trait_key: 'org_id', trait_value: 'acme' },
      { trait_key: 'plan', trait_value: 'enterprise' },
    ]);

    assert.equal(flags.new_dashboard.enabled, true);
    assert.equal(flags.ai_summaries.enabled, false);
    assert.equal(flags.bulk_export.enabled, false);
  });

  it('normalizes missing flags to disabled defaults', () => {
    const normalized = normalizeFlagsmithResponse({ flags: [] });
    assert.deepEqual(normalized, {
      new_dashboard: { enabled: false, value: null },
      ai_summaries: { enabled: false, value: null },
      bulk_export: { enabled: false, value: null },
    });
  });
});

describe('HTTP endpoints', () => {
  let server;
  let baseUrl;

  before(async () => {
    const app = createApp({
      flagsmithOptions: {
        envKey: null,
        offlineState: {
          defaults: { new_dashboard: false, ai_summaries: false, bulk_export: false },
          orgOverrides: {
            acme: { new_dashboard: true },
            initech: { bulk_export: true },
          },
          identityOverrides: {},
        },
      },
    });

    await new Promise((resolve) => {
      server = app.listen(0, () => {
        const { port } = server.address();
        baseUrl = `http://127.0.0.1:${port}`;
        resolve();
      });
    });
  });

  after(async () => {
    if (server) {
      await new Promise((resolve) => server.close(resolve));
    }
  });

  it('GET /health returns status ok and tracked flags', async () => {
    const res = await fetch(`${baseUrl}/health`);
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.status, 'ok');
    assert.equal(data.mode, 'offline');
    assert.deepEqual(data.flags, ['new_dashboard', 'ai_summaries', 'bulk_export']);
  });

  it('GET /api/users returns all 6 demo users across 3 orgs', async () => {
    const res = await fetch(`${baseUrl}/api/users`);
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.users.length, 6);
  });

  it('GET /api/flags?user=1 returns Acme user flags', async () => {
    const res = await fetch(`${baseUrl}/api/flags?user=1`);
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.user.identifier, 'user_1');
    assert.equal(data.user.org_id, 'acme');
    assert.equal(data.flags.new_dashboard.enabled, true);
    assert.equal(data.flags.ai_summaries.enabled, false);
    assert.equal(data.flags.bulk_export.enabled, false);
  });

  it('GET /api/flags?user=3 returns Globex user flags', async () => {
    const res = await fetch(`${baseUrl}/api/flags?user=3`);
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.user.identifier, 'user_3');
    assert.equal(data.user.org_id, 'globex');
    assert.equal(data.flags.new_dashboard.enabled, false);
    assert.equal(data.flags.bulk_export.enabled, false);
  });

  it('GET /api/flags?user=42 returns Initech user flags', async () => {
    const res = await fetch(`${baseUrl}/api/flags?user=42`);
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.user.identifier, 'user_42');
    assert.equal(data.user.org_id, 'initech');
    assert.equal(data.flags.bulk_export.enabled, true);
  });

  it('GET /api/flags?user=999 returns 404 for unknown user', async () => {
    const res = await fetch(`${baseUrl}/api/flags?user=999`);
    assert.equal(res.status, 404);
  });
});
