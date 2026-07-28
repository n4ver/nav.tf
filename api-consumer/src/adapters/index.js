'use strict';

const { MatchaAdapter } = require('./matcha/MatchaAdapter');

/**
 * Factory for LogSourceAdapter implementations.
 * @param {string} sourceSite
 * @param {object} [options]
 */
function createAdapter(sourceSite, options = {}) {
  const key = String(sourceSite || '').toLowerCase();
  switch (key) {
    case 'matcha':
    case 'matcha.tf':
      return new MatchaAdapter(options);
    default:
      throw new Error(`Unknown log source adapter: ${sourceSite}`);
  }
}

module.exports = { createAdapter, MatchaAdapter };
