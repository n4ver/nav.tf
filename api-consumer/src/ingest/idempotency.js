'use strict';

/**
 * In-memory idempotency store.
 * Same (sourceSite, sourceMatchId, logstfId) always maps to the same match_id
 * via uuid5; this store prevents duplicate RabbitMQ publishes within a process.
 *
 * Swap for Redis/Postgres in production multi-instance deployments.
 */
class IdempotencyStore {
  constructor() {
    /** @type {Map<string, { matchId: string, publishedAt: string }>} */
    this._seen = new Map();
  }

  /**
   * @param {string} key
   * @returns {{ matchId: string, publishedAt: string }|null}
   */
  get(key) {
    return this._seen.get(key) || null;
  }

  /**
   * @param {string} key
   * @param {string} matchId
   */
  mark(key, matchId) {
    this._seen.set(key, { matchId, publishedAt: new Date().toISOString() });
  }

  clear() {
    this._seen.clear();
  }

  get size() {
    return this._seen.size;
  }
}

module.exports = { IdempotencyStore };
