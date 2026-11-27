'use strict';

const DEFAULT_KNOWN_FLAGS = ['new_dashboard', 'ai_summaries', 'bulk_export'];

// Matches Flagsmith SDK method calls in JS/TS/Python
const CALL_PATTERN = /\b(hasFeature|has_feature|getValue|get_value|getFeatureValue|get_feature_value|isFeatureEnabled|is_feature_enabled)\s*\(\s*(['"`])([a-zA-Z0-9_.-]+)\2/g;

/**
 * Scan source code text for Flagsmith feature flag references.
 *
 * @param {string} text - Full document text
 * @param {Iterable<string>} [knownFlags] - Additional known flag keys to detect
 * @returns {Array<{flagKey: string, line: number, startCol: number, endCol: number, callType: string}>}
 */
function scanTextForFlags(text, knownFlags = DEFAULT_KNOWN_FLAGS) {
  if (!text || typeof text !== 'string') {
    return [];
  }

  const knownSet = new Set([...DEFAULT_KNOWN_FLAGS, ...(knownFlags || [])].filter(Boolean));
  const lines = text.split(/\r?\n/);
  const results = [];

  for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
    const lineText = lines[lineIdx];
    const trimmed = lineText.trim();

    // Skip comment-only lines
    if (trimmed.startsWith('//') || trimmed.startsWith('#') || trimmed.startsWith('/*') || trimmed.startsWith('*')) {
      continue;
    }

    const seenOnLine = new Set();

    // 1. Match explicit Flagsmith SDK calls
    CALL_PATTERN.lastIndex = 0;
    let match;
    while ((match = CALL_PATTERN.exec(lineText)) !== null) {
      const callType = match[1];
      const flagKey = match[3];
      const startCol = match.index;
      const endCol = match.index + match[0].length;

      if (!seenOnLine.has(flagKey)) {
        seenOnLine.add(flagKey);
        results.push({
          flagKey,
          line: lineIdx,
          startCol,
          endCol,
          callType
        });
      }
    }

    // 2. Match known flag keys referenced as quoted strings or standalone identifiers
    for (const flagKey of knownSet) {
      if (seenOnLine.has(flagKey)) {
        continue;
      }
      const escaped = flagKey.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const keyRegex = new RegExp(`(['"\`])${escaped}\\1|\\b${escaped}\\b`);
      const keyMatch = keyRegex.exec(lineText);
      if (keyMatch) {
        seenOnLine.add(flagKey);
        results.push({
          flagKey,
          line: lineIdx,
          startCol: keyMatch.index,
          endCol: keyMatch.index + keyMatch[0].length,
          callType: 'reference'
        });
      }
    }
  }

  return results;
}

/**
 * Format a concise inline CodeLens label for a flag reference.
 *
 * @param {string} flagKey
 * @param {Object|undefined} flagState
 * @param {{identity: string, orgOrProject?: string|null, offline?: boolean}} context
 * @returns {string}
 */
function formatCodeLensTitle(flagKey, flagState, context) {
  const identityLabel = context.orgOrProject
    ? `${context.identity} / ${context.orgOrProject}`
    : context.identity;

  if (!flagState) {
    return `Flagsmith [${identityLabel}]: ${flagKey} = UNKNOWN`;
  }

  const stateText = flagState.enabled ? 'ON' : 'OFF';
  const valuePart = flagState.value !== null && flagState.value !== undefined && flagState.value !== ''
    ? ` (${JSON.stringify(flagState.value)})`
    : '';
  const sourcePart = flagState.source ? ` (${flagState.source})` : '';
  const offlinePrefix = context.offline ? 'Offline · ' : '';

  return `${offlinePrefix}Flagsmith [${identityLabel}]: ${flagKey} = ${stateText}${valuePart}${sourcePart}`;
}

module.exports = {
  DEFAULT_KNOWN_FLAGS,
  scanTextForFlags,
  formatCodeLensTitle
};
