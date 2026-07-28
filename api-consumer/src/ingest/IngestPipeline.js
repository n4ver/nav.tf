'use strict';

const { v4: uuidv4 } = require('uuid');
const { idempotencyKey } = require('../models/normalized');
const { IdempotencyStore } = require('./idempotency');
const { child } = require('../logger');

const log = child({ component: 'ingest-pipeline' });

/**
 * Orchestrates: discover → normalize → publish, with idempotency + DLX.
 */
class IngestPipeline {
  /**
   * @param {object} deps
   * @param {import('../adapters/LogSourceAdapter').LogSourceAdapter} deps.adapter
   * @param {import('../rabbitmq/publisher').EventPublisher} deps.publisher
   * @param {IdempotencyStore} [deps.idempotency]
   */
  constructor({ adapter, publisher, idempotency }) {
    this.adapter = adapter;
    this.publisher = publisher;
    this.idempotency = idempotency || new IdempotencyStore();
    this._pollInFlight = null;
  }

  /**
   * @param {string} trigger
   */
  async pollAndIngest(trigger = 'manual') {
    if (this._pollInFlight) {
      const err = new Error('Poll already in progress');
      err.code = 'POLL_IN_PROGRESS';
      throw err;
    }

    this._pollInFlight = this._runPoll(trigger).finally(() => {
      this._pollInFlight = null;
    });
    return this._pollInFlight;
  }

  /**
   * @param {string} trigger
   */
  async _runPoll(trigger) {
    const correlationId = uuidv4();
    const started = Date.now();
    log.info(
      {
        sourceSite: this.adapter.sourceSite,
        correlationId,
        trigger,
        idempotencySize: this.idempotency.size,
      },
      'poll started'
    );

    let matchIds;
    try {
      matchIds = await this.adapter.listMatchIds();
    } catch (err) {
      await this._safeDeadLetter({
        sourceSite: this.adapter.sourceSite,
        sourceMatchId: null,
        correlationId,
        stage: 'listMatchIds',
        error: err.message,
        status: err.status ?? null,
      });
      throw err;
    }

    const summary = {
      status: 'accepted',
      trigger,
      correlationId,
      accepted: 0,
      skipped: 0,
      failed: 0,
      noLogs: 0,
      matchIds: matchIds.length,
      failedMatchIds: [],
      noLogMatchIds: [],
      idempotencySizeAtStart: this.idempotency.size,
    };

    for (const matchId of matchIds) {
      try {
        const result = await this.ingestMatch(matchId, { correlationId, trigger });
        summary.accepted += result.accepted;
        summary.skipped += result.skipped;
        if (result.noLogs) {
          summary.noLogs += 1;
          summary.noLogMatchIds.push(String(matchId));
        }
        if (result.errors?.length && result.accepted === 0 && result.skipped === 0) {
          summary.failed += 1;
          summary.failedMatchIds.push(String(matchId));
        }
      } catch (err) {
        summary.failed += 1;
        summary.failedMatchIds.push(String(matchId));
        log.error(
          { sourceMatchId: matchId, err: err.message, correlationId, trigger },
          'ingest match failed'
        );
      }
    }

    summary.idempotencySizeAtEnd = this.idempotency.size;
    summary.latencyMs = Date.now() - started;

    log.info({ ...summary }, 'poll completed');
    return summary;
  }

  /**
   * Ingest a single source match ID (webhook or manual trigger).
   * @param {string|number} sourceMatchId
   * @param {{ correlationId?: string, trigger?: string }} [options]
   */
  async ingestMatch(sourceMatchId, options = {}) {
    const correlationId = options.correlationId || uuidv4();
    const trigger = options.trigger || 'manual';
    const started = Date.now();

    let matches;
    try {
      matches = await this.adapter.fetchNormalizedMatch(sourceMatchId, { correlationId });
    } catch (err) {
      await this._safeDeadLetter({
        sourceSite: this.adapter.sourceSite,
        sourceMatchId: String(sourceMatchId),
        correlationId,
        stage: 'fetchNormalizedMatch',
        error: err.message,
        status: err.status ?? null,
      });
      throw err;
    }

    const result = { accepted: 0, skipped: 0, noLogs: false, published: [], errors: [] };

    if (!matches.length) {
      result.noLogs = true;
      log.info(
        { sourceMatchId, correlationId, trigger, latencyMs: Date.now() - started },
        'match has no logs to ingest'
      );
      return result;
    }

    for (const match of matches) {
      const key = idempotencyKey(
        match.source.sourceSite,
        match.source.sourceMatchId,
        match.source_log_id
      );
      const existing = this.idempotency.get(key);
      if (existing) {
        result.skipped += 1;
        log.info(
          {
            key,
            matchId: existing.matchId,
            sourceMatchId,
            sourceLogId: match.source_log_id,
            correlationId,
            trigger,
          },
          'skipped duplicate ingest'
        );
        continue;
      }

      try {
        const published = await this.publisher.publishIngestedMatch(match, { correlationId });
        this.idempotency.mark(key, match.match_id);
        result.accepted += 1;
        result.published.push(published);
      } catch (err) {
        result.errors.push({
          sourceLogId: match.source_log_id,
          matchId: match.match_id,
          error: err.message,
        });
        await this._safeDeadLetter({
          sourceSite: match.source.sourceSite,
          sourceMatchId: match.source.sourceMatchId,
          sourceLogId: match.source_log_id,
          correlationId,
          stage: 'publish',
          error: err.message,
          matchId: match.match_id,
        });
        log.error(
          {
            sourceMatchId,
            sourceLogId: match.source_log_id,
            correlationId,
            trigger,
            err: err.message,
          },
          'publish failed for map log; continuing with remaining logs'
        );
      }
    }

    if (result.errors.length && result.accepted === 0 && result.skipped === 0) {
      const err = new Error(
        `All ${result.errors.length} log(s) failed to publish for match ${sourceMatchId}`
      );
      err.details = result.errors;
      throw err;
    }

    log.info(
      {
        sourceMatchId,
        correlationId,
        trigger,
        accepted: result.accepted,
        skipped: result.skipped,
        errors: result.errors.length,
        latencyMs: Date.now() - started,
      },
      'ingest match done'
    );
    return result;
  }

  clearIdempotency() {
    const cleared = this.idempotency.size;
    this.idempotency.clear();
    return cleared;
  }

  async _safeDeadLetter(failure) {
    try {
      await this.publisher.publishDeadLetter(failure);
    } catch (err) {
      log.error({ err: err.message, failure }, 'failed to publish dead letter');
    }
  }
}

module.exports = { IngestPipeline };
