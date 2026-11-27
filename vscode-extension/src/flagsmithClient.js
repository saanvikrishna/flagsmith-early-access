'use strict';

const DEFAULT_FALLBACK_FLAGS = [
  { name: 'new_dashboard', enabled: false, value: null, source: 'default (offline)', segmentName: null, isOverride: false },
  { name: 'ai_summaries', enabled: false, value: null, source: 'default (offline)', segmentName: null, isOverride: false },
  { name: 'bulk_export', enabled: false, value: null, source: 'default (offline)', segmentName: null, isOverride: false }
];

/**
 * Pure Node.js client for self-hosted Flagsmith (Client API + optional Admin API).
 */
class FlagsmithClient {
  /**
   * @param {Object} options
   * @param {string} [options.apiUrl='http://localhost:8000']
   * @param {string} [options.environmentKey='']
   * @param {string} [options.apiKey='']
   * @param {string} [options.defaultIdentity='user_1']
   * @param {typeof globalThis.fetch} [options.fetchFn]
   */
  constructor(options = {}) {
    this.apiUrl = (options.apiUrl || 'http://localhost:8000').replace(/\/+$/, '');
    this.environmentKey = options.environmentKey || '';
    this.apiKey = options.apiKey || '';
    this.defaultIdentity = options.defaultIdentity || 'user_1';
    this.fetchFn = options.fetchFn || globalThis.fetch;

    /** @type {Map<string, boolean>} */
    this.localOverrides = new Map();
    /** @type {Object|null} */
    this.lastResult = null;
  }

  /**
   * Update client configuration at runtime.
   * @param {Object} config
   */
  configure(config = {}) {
    if (config.apiUrl !== undefined) {
      this.apiUrl = String(config.apiUrl || 'http://localhost:8000').replace(/\/+$/, '');
    }
    if (config.environmentKey !== undefined) {
      this.environmentKey = String(config.environmentKey || '');
    }
    if (config.apiKey !== undefined) {
      this.apiKey = String(config.apiKey || '');
    }
    if (config.defaultIdentity !== undefined) {
      this.defaultIdentity = String(config.defaultIdentity || 'user_1');
    }
  }

  /**
   * Fetch identity flags and optional ea-* segments from self-hosted Flagsmith.
   * Falls back gracefully when offline or misconfigured.
   *
   * @param {string} [identity]
   * @returns {Promise<{
   *   offline: boolean,
   *   identity: string,
   *   orgOrProject: string|null,
   *   flags: Array<{name: string, enabled: boolean, value: any, source: string, segmentName: string|null, isOverride: boolean}>,
   *   segments: Array<{id: number|string, name: string, description: string}>,
   *   error: string|null
   * }>}
   */
  async fetchState(identity = this.defaultIdentity) {
    const activeIdentity = identity || this.defaultIdentity || 'user_1';

    if (!this.environmentKey) {
      return this._offlineResult(
        activeIdentity,
        'Missing flagsmithEarlyAccess.environmentKey; using offline defaults.'
      );
    }

    if (typeof this.fetchFn !== 'function') {
      return this._offlineResult(activeIdentity, 'Global fetch is unavailable.');
    }

    try {
      const url = `${this.apiUrl}/api/v1/identities/?identifier=${encodeURIComponent(activeIdentity)}`;
      const res = await this.fetchFn(url, {
        method: 'GET',
        headers: {
          'X-Environment-Key': this.environmentKey,
          'Accept': 'application/json'
        }
      });

      if (!res.ok) {
        return this._offlineResult(
          activeIdentity,
          `Flagsmith API returned HTTP ${res.status} ${res.statusText || ''}`.trim()
        );
      }

      const data = await res.json();
      const flags = this._normalizeIdentityFlags(data);
      const segments = await this._fetchEarlyAccessSegments();
      const orgOrProject = this._extractOrgOrProject(data);

      const result = {
        offline: false,
        identity: activeIdentity,
        orgOrProject,
        flags: this._applyLocalOverrides(flags),
        segments,
        error: null
      };

      this.lastResult = result;
      return result;
    } catch (err) {
      return this._offlineResult(
        activeIdentity,
        err && err.message ? err.message : 'Network error connecting to Flagsmith'
      );
    }
  }

  /**
   * Query Admin API for ea-* segments when apiKey is configured.
   * @returns {Promise<Array<{id: number|string, name: string, description: string}>>}
   */
  async _fetchEarlyAccessSegments() {
    if (!this.apiKey) {
      return [];
    }

    try {
      const projectsRes = await this.fetchFn(`${this.apiUrl}/api/v1/projects/`, {
        method: 'GET',
        headers: {
          'Authorization': `Token ${this.apiKey}`,
          'Accept': 'application/json'
        }
      });

      if (!projectsRes.ok) {
        return [];
      }

      const projectsPayload = await projectsRes.json();
      const projects = Array.isArray(projectsPayload)
        ? projectsPayload
        : (projectsPayload && Array.isArray(projectsPayload.results) ? projectsPayload.results : []);

      const eaSegments = [];
      for (const project of projects) {
        if (!project || project.id === undefined) continue;
        const segRes = await this.fetchFn(`${this.apiUrl}/api/v1/projects/${project.id}/segments/`, {
          method: 'GET',
          headers: {
            'Authorization': `Token ${this.apiKey}`,
            'Accept': 'application/json'
          }
        });
        if (!segRes.ok) continue;

        const segPayload = await segRes.json();
        const segList = Array.isArray(segPayload)
          ? segPayload
          : (segPayload && Array.isArray(segPayload.results) ? segPayload.results : []);

        for (const seg of segList) {
          if (seg && typeof seg.name === 'string' && seg.name.startsWith('ea-')) {
            eaSegments.push({
              id: seg.id,
              name: seg.name,
              description: seg.description || ''
            });
          }
        }
      }
      return eaSegments;
    } catch {
      return [];
    }
  }

  /**
   * Toggle a local override for a flag key.
   * @param {string} flagName
   * @param {boolean} [currentEnabled=false]
   * @returns {boolean} New overridden state
   */
  toggleLocalOverride(flagName, currentEnabled = false) {
    const next = this.localOverrides.has(flagName)
      ? !this.localOverrides.get(flagName)
      : !currentEnabled;
    this.localOverrides.set(flagName, next);
    return next;
  }

  /**
   * Clear a local override for a flag key.
   * @param {string} flagName
   */
  clearLocalOverride(flagName) {
    this.localOverrides.delete(flagName);
  }

  /**
   * Normalize Flagsmith /api/v1/identities/ payload.
   * @param {any} data
   */
  _normalizeIdentityFlags(data) {
    const rawFlags = data && Array.isArray(data.flags) ? data.flags : [];
    const traits = data && Array.isArray(data.traits) ? data.traits : [];
    const eaTrait = traits.find(
      (t) => t && t.trait_key === 'early_access_cohort' && t.trait_value
    );

    return rawFlags
      .filter((entry) => entry && entry.feature && entry.feature.name)
      .map((entry) => {
        const name = entry.feature.name;
        const enabled = Boolean(entry.enabled);
        const value = entry.feature_state_value !== undefined ? entry.feature_state_value : null;
        const segmentName = entry.segment_name || (eaTrait ? String(eaTrait.trait_value) : null);
        const isOverride = Boolean(segmentName && String(segmentName).startsWith('ea-'));
        const source = isOverride ? segmentName : 'default';

        return {
          name,
          enabled,
          value,
          source,
          segmentName: segmentName || null,
          isOverride
        };
      });
  }

  /**
   * Extract optional org/tenant trait from identity payload for display.
   * @param {any} data
   * @returns {string|null}
   */
  _extractOrgOrProject(data) {
    const traits = data && Array.isArray(data.traits) ? data.traits : [];
    const orgTrait = traits.find(
      (t) => t && ['org', 'organization', 'tenant', 'company'].includes(t.trait_key) && t.trait_value
    );
    return orgTrait ? String(orgTrait.trait_value) : null;
  }

  /**
   * Apply in-memory local overrides on top of fetched or fallback flags.
   * @param {Array} flags
   */
  _applyLocalOverrides(flags) {
    const byName = new Map(flags.map((f) => [f.name, { ...f }]));
    for (const [name, overriddenEnabled] of this.localOverrides.entries()) {
      const existing = byName.get(name);
      if (existing) {
        existing.enabled = overriddenEnabled;
        existing.isOverride = true;
        existing.source = 'local-override';
      } else {
        byName.set(name, {
          name,
          enabled: overriddenEnabled,
          value: null,
          source: 'local-override',
          segmentName: null,
          isOverride: true
        });
      }
    }
    return Array.from(byName.values());
  }

  /**
   * Build a graceful offline fallback response.
   * @param {string} identity
   * @param {string} error
   */
  _offlineResult(identity, error) {
    const baseFlags = this.lastResult && this.lastResult.flags && this.lastResult.flags.length > 0
      ? this.lastResult.flags.map((f) => ({ ...f, source: f.isOverride ? f.source : `${f.source} (cached)` }))
      : DEFAULT_FALLBACK_FLAGS.map((f) => ({ ...f }));

    const baseSegments = this.lastResult && Array.isArray(this.lastResult.segments)
      ? this.lastResult.segments
      : [];

    return {
      offline: true,
      identity,
      orgOrProject: this.lastResult ? this.lastResult.orgOrProject : null,
      flags: this._applyLocalOverrides(baseFlags),
      segments: baseSegments,
      error
    };
  }
}

module.exports = {
  FlagsmithClient,
  DEFAULT_FALLBACK_FLAGS
};
