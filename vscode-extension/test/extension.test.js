'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const { FlagsmithClient, DEFAULT_FALLBACK_FLAGS } = require('../src/flagsmithClient');
const { scanTextForFlags, formatCodeLensTitle } = require('../src/flagScanner');

describe('FlagsmithClient', () => {
  it('fetches identity flags and ea-* segments from mocked Flagsmith API', async () => {
    const calls = [];
    const mockFetch = async (url, init) => {
      calls.push({ url, headers: init.headers });
      if (url.includes('/api/v1/identities/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            flags: [
              { feature: { name: 'new_dashboard' }, enabled: false, feature_state_value: null },
              { feature: { name: 'ai_summaries' }, enabled: true, feature_state_value: 'v2' }
            ],
            traits: [{ trait_key: 'org', trait_value: 'acme' }]
          })
        };
      }
      if (url.endsWith('/api/v1/projects/')) {
        return {
          ok: true,
          status: 200,
          json: async () => [{ id: 42, name: 'Main Project' }]
        };
      }
      if (url.includes('/api/v1/projects/42/segments/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            results: [
              { id: 1, name: 'ea-beta', description: 'Beta cohort' },
              { id: 2, name: 'internal-staff', description: 'Should be filtered out' },
              { id: 3, name: 'ea-alpha', description: 'Alpha cohort' }
            ]
          })
        };
      }
      return { ok: false, status: 404, statusText: 'Not Found' };
    };

    const client = new FlagsmithClient({
      apiUrl: 'http://localhost:8000/',
      environmentKey: 'env-key-123',
      apiKey: 'admin-token-456',
      defaultIdentity: 'user_1',
      fetchFn: mockFetch
    });

    const state = await client.fetchState();

    assert.equal(state.offline, false);
    assert.equal(state.identity, 'user_1');
    assert.equal(state.orgOrProject, 'acme');
    assert.equal(state.error, null);
    assert.equal(state.flags.length, 2);
    assert.deepEqual(state.flags[0], {
      name: 'new_dashboard',
      enabled: false,
      value: null,
      source: 'default',
      segmentName: null,
      isOverride: false
    });
    assert.equal(state.flags[1].enabled, true);
    assert.equal(state.flags[1].value, 'v2');

    assert.equal(state.segments.length, 2);
    assert.deepEqual(
      state.segments.map((s) => s.name),
      ['ea-beta', 'ea-alpha']
    );

    assert.equal(calls[0].url, 'http://localhost:8000/api/v1/identities/?identifier=user_1');
    assert.equal(calls[0].headers['X-Environment-Key'], 'env-key-123');
    assert.equal(calls[1].headers.Authorization, 'Token admin-token-456');
  });

  it('falls back gracefully when environmentKey is missing', async () => {
    const client = new FlagsmithClient({
      apiUrl: 'http://localhost:8000',
      environmentKey: ''
    });

    const state = await client.fetchState('user_2');
    assert.equal(state.offline, true);
    assert.equal(state.identity, 'user_2');
    assert.equal(state.flags.length, DEFAULT_FALLBACK_FLAGS.length);
    assert.match(state.error, /environmentKey/);
  });

  it('falls back gracefully on network error (ECONNREFUSED) or HTTP 500', async () => {
    const failingFetch = async () => {
      throw new Error('connect ECONNREFUSED 127.0.0.1:8000');
    };

    const client = new FlagsmithClient({
      environmentKey: 'env-key-123',
      fetchFn: failingFetch
    });

    const netErrState = await client.fetchState('user_1');
    assert.equal(netErrState.offline, true);
    assert.match(netErrState.error, /ECONNREFUSED/);
    assert.equal(netErrState.flags.length, DEFAULT_FALLBACK_FLAGS.length);

    const serverErrClient = new FlagsmithClient({
      environmentKey: 'env-key-123',
      fetchFn: async () => ({ ok: false, status: 500, statusText: 'Internal Server Error' })
    });

    const httpErrState = await serverErrClient.fetchState('user_1');
    assert.equal(httpErrState.offline, true);
    assert.match(httpErrState.error, /500/);
  });

  it('applies local overrides on top of flag state', async () => {
    const client = new FlagsmithClient({ environmentKey: '' });
    client.toggleLocalOverride('new_dashboard', false);

    const state = await client.fetchState('user_1');
    const flag = state.flags.find((f) => f.name === 'new_dashboard');
    assert.equal(flag.enabled, true);
    assert.equal(flag.isOverride, true);
    assert.equal(flag.source, 'local-override');
  });
});

describe('flagScanner', () => {
  it('extracts Flagsmith flag calls from JS/TS and Python code', () => {
    const sampleCode = [
      '// hasFeature("ignored_in_comment")',
      'if (flagsmith.hasFeature("new_dashboard")) {',
      "  const model = flagsmith.getValue('ai_summaries');",
      '}',
      '# Python example',
      "if flags.is_feature_enabled('bulk_export'):",
      "    limit = flags.get_feature_value('export_limit')"
    ].join('\n');

    const matches = scanTextForFlags(sampleCode);
    assert.deepEqual(
      matches.map((m) => ({ flagKey: m.flagKey, line: m.line, callType: m.callType })),
      [
        { flagKey: 'new_dashboard', line: 1, callType: 'hasFeature' },
        { flagKey: 'ai_summaries', line: 2, callType: 'getValue' },
        { flagKey: 'bulk_export', line: 5, callType: 'is_feature_enabled' },
        { flagKey: 'export_limit', line: 6, callType: 'get_feature_value' }
      ]
    );
  });

  it('detects standalone known flag references without duplicating call matches', () => {
    const code = [
      'const FLAGS = ["new_dashboard", "ai_summaries"];',
      'if (flagsmith.hasFeature("new_dashboard")) return true;'
    ].join('\n');

    const matches = scanTextForFlags(code);
    assert.equal(matches.length, 3);
    assert.deepEqual(
      matches.map((m) => `${m.line}:${m.flagKey}:${m.callType}`),
      [
        '0:new_dashboard:reference',
        '0:ai_summaries:reference',
        '1:new_dashboard:hasFeature'
      ]
    );
  });

  it('formats CodeLens titles with identity, org, value, and source', () => {
    const titleOff = formatCodeLensTitle(
      'new_dashboard',
      { name: 'new_dashboard', enabled: false, value: null, source: 'default' },
      { identity: 'user_1', orgOrProject: 'acme', offline: false }
    );
    assert.equal(titleOff, 'Flagsmith [user_1 / acme]: new_dashboard = OFF (default)');

    const titleOn = formatCodeLensTitle(
      'ai_summaries',
      { name: 'ai_summaries', enabled: true, value: 'gpt-4o', source: 'ea-beta' },
      { identity: 'user_1', orgOrProject: null, offline: true }
    );
    assert.equal(titleOn, 'Offline · Flagsmith [user_1]: ai_summaries = ON ("gpt-4o") (ea-beta)');
  });
});
