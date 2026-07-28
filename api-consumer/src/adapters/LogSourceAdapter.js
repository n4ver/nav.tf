'use strict';

/**
 * Base adapter contract for TF2 log sources (matcha.tf, TF2Center, logs.tf, …).
 *
 * Implementations must:
 * 1. Discover candidate match IDs (list / poll)
 * 2. Fetch raw site-specific JSON for a match
 * 3. Map into NormalizedTF2Match[] (one entry per playable log / map segment)
 *
 * Adding a new source = new subclass + register in adapters/index.js.
 */
class LogSourceAdapter {
  /** @returns {string} Stable site key, e.g. "matcha.tf" */
  get sourceSite() {
    throw new Error(`${this.constructor.name} must implement sourceSite`);
  }

  /**
   * List ingestible match identifiers for the configured league/division/window.
   * @returns {Promise<Array<string|number>>}
   */
  async listMatchIds() {
    throw new Error(`${this.constructor.name} must implement listMatchIds`);
  }

  /**
   * Fetch and normalize a single source match into zero or more canonical matches.
   * Empty array is valid (e.g. forfeit with no logs yet).
   *
   * @param {string|number} sourceMatchId
   * @param {{ correlationId?: string }} [options]
   * @returns {Promise<import('../models/normalized').NormalizedTF2Match[]>}
   */
  async fetchNormalizedMatch(sourceMatchId, options = {}) {
    throw new Error(`${this.constructor.name} must implement fetchNormalizedMatch`);
  }
}

module.exports = { LogSourceAdapter };
