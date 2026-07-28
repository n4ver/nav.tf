'use strict';

const { v4: uuidv4 } = require('uuid');
const { config } = require('../config');
const { child } = require('../logger');
const {
  createMatchLogIngestedEvent,
  toMatchParsedPayload,
} = require('../models/normalized');

const log = child({ component: 'publisher' });

/**
 * Publishes normalized matches into the existing CQRS bus (`tf2-events`)
 * and a consumer-domain MatchLogIngested audit event.
 */
class EventPublisher {
  /**
   * @param {import('./connection').RabbitConnection} connection
   * @param {object} [options]
   */
  constructor(connection, options = {}) {
    this.connection = connection;
    this.routingPrefix = options.routingPrefix || config.routingPrefix;
    this.exchangeName = options.exchangeName || config.exchangeName;
    this.dlxName = options.dlxName || config.dlxName;
    this.actorId = options.actorId || config.actorId;
  }

  /**
   * Serialize normalized log data and publish to RabbitMQ.
   *
   * Wire envelope matches Python broker.py:
   *   { event_type, payload: EventEnvelope }
   *
   * @param {import('../models/normalized').NormalizedTF2Match} match
   * @param {{ correlationId?: string }} [meta]
   */
  async publishIngestedMatch(match, meta = {}) {
    const correlationId = meta.correlationId || match.source.correlationId || uuidv4();
    const ingestedEvent = createMatchLogIngestedEvent(match, {
      correlationId,
      actorId: this.actorId,
    });

    const matchParsedEnvelope = {
      event_id: uuidv4(),
      event_type: 'MatchParsed',
      occurred_at: new Date().toISOString(),
      actor_id: this.actorId,
      payload: toMatchParsedPayload(match),
    };

    // CQRS query pipeline consumes MatchParsed.
    await this._publish('MatchParsed', matchParsedEnvelope, {
      correlationId,
      sourceSite: match.source.sourceSite,
      sourceMatchId: match.source.sourceMatchId,
      headers: {
        'x-source-site': match.source.sourceSite,
        'x-source-match-id': String(match.source.sourceMatchId),
        'x-correlation-id': correlationId,
        'x-ingested-at': match.source.ingestedAt,
      },
    });

    // Consumer-domain audit event (same exchange, distinct routing key).
    await this._publish('MatchLogIngested', ingestedEvent, {
      correlationId,
      sourceSite: match.source.sourceSite,
      sourceMatchId: match.source.sourceMatchId,
      headers: {
        'x-source-site': match.source.sourceSite,
        'x-source-match-id': String(match.source.sourceMatchId),
        'x-correlation-id': correlationId,
        'x-ingested-at': match.source.ingestedAt,
      },
    });

    return {
      matchId: match.match_id,
      sourceLogId: match.source_log_id,
      correlationId,
      events: ['MatchParsed', 'MatchLogIngested'],
    };
  }

  /**
   * Publish a failure record to the DLX after retry exhaustion.
   * @param {object} failure
   */
  async publishDeadLetter(failure) {
    const envelope = {
      event_id: uuidv4(),
      event_type: 'IngestFailed',
      occurred_at: new Date().toISOString(),
      actor_id: this.actorId,
      payload: failure,
    };
    const channel = await this.connection.getChannel();
    const routingKey = `failed.${failure.sourceSite || 'unknown'}`;
    const body = Buffer.from(
      JSON.stringify({ event_type: 'IngestFailed', payload: envelope }),
      'utf8'
    );

    await new Promise((resolve, reject) => {
      channel.publish(
        this.dlxName,
        routingKey,
        body,
        {
          contentType: 'application/json',
          persistent: true,
          headers: {
            'x-correlation-id': failure.correlationId || '',
            'x-source-site': failure.sourceSite || '',
            'x-source-match-id': String(failure.sourceMatchId || ''),
          },
        },
        (err) => (err ? reject(err) : resolve())
      );
    });

    log.warn({ routingKey, failure }, 'published dead letter');
  }

  /**
   * @param {string} eventType
   * @param {object} envelope
   * @param {object} meta
   */
  async _publish(eventType, envelope, meta = {}) {
    const channel = await this.connection.getChannel();
    const routingKey = `${this.routingPrefix}.${eventType}`;
    const wire = { event_type: eventType, payload: envelope };
    const body = Buffer.from(JSON.stringify(wire), 'utf8');

    await new Promise((resolve, reject) => {
      channel.publish(
        this.exchangeName,
        routingKey,
        body,
        {
          contentType: 'application/json',
          persistent: true,
          messageId: envelope.event_id,
          correlationId: meta.correlationId,
          headers: meta.headers || {},
        },
        (err) => (err ? reject(err) : resolve())
      );
    });

    log.info(
      {
        eventType,
        routingKey,
        matchId: envelope.payload?.match_id || envelope.payload?.match?.match_id,
        correlationId: meta.correlationId,
        sourceSite: meta.sourceSite,
        sourceMatchId: meta.sourceMatchId,
        bytes: body.length,
      },
      'published event'
    );
  }
}

module.exports = { EventPublisher };
