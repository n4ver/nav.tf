'use strict';

const express = require('express');
const { child } = require('../logger');
const { config } = require('../config');

const log = child({ component: 'webhook' });

function requireWebhookAuth(req, res, next) {
  const expected = config.webhookApiKey;
  if (!expected) {
    log.error('WEBHOOK_API_KEY is not set; rejecting webhook/admin request');
    return res.status(503).json({
      error: 'Webhook authentication is not configured (set WEBHOOK_API_KEY)',
    });
  }

  const authHeader = String(req.headers.authorization || '');
  const bearer = authHeader.startsWith('Bearer ') ? authHeader.slice(7).trim() : '';
  const apiKey = String(req.headers['x-api-key'] || '').trim();
  const provided = bearer || apiKey;

  if (!provided || provided !== expected) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  return next();
}

/**
 * HTTP trigger surface for on-demand ingest (webhooks / admin).
 * @param {import('../ingest/IngestPipeline').IngestPipeline} pipeline
 */
function createWebhookApp(pipeline) {
  const app = express();
  app.use(express.json({ limit: '1mb' }));

  app.get('/health', (_req, res) => {
    res.json({ status: 'ok', service: 'tf2-api-consumer' });
  });

  /**
   * POST /webhooks/matcha/match
   * Body: { matchId: number|string, correlationId?: string }
   */
  app.post('/webhooks/matcha/match', requireWebhookAuth, async (req, res) => {
    const matchId = req.body?.matchId ?? req.body?.id;
    if (matchId == null) {
      return res.status(400).json({ error: 'matchId is required' });
    }

    try {
      const result = await pipeline.ingestMatch(matchId, {
        correlationId: req.body?.correlationId,
      });
      return res.status(202).json({
        status: 'accepted',
        sourceSite: 'matcha.tf',
        sourceMatchId: String(matchId),
        ...result,
      });
    } catch (err) {
      log.error({ matchId, err: err.message }, 'webhook ingest failed');
      return res.status(502).json({
        status: 'failed',
        error: err.message,
        sourceMatchId: String(matchId),
      });
    }
  });

  /**
   * POST /admin/poll
   * Manually kick a full league/division poll.
   */
  app.post('/admin/poll', requireWebhookAuth, async (req, res) => {
    if (req.query.reset === 'true') {
      const cleared = pipeline.clearIdempotency();
      log.info({ cleared }, 'idempotency store cleared');
    }

    try {
      const summary = await pipeline.pollAndIngest('admin');
      return res.status(202).json(summary);
    } catch (err) {
      if (err.code === 'POLL_IN_PROGRESS') {
        return res.status(409).json({ status: 'busy', error: err.message });
      }
      log.error({ err: err.message }, 'manual poll failed');
      return res.status(502).json({ status: 'failed', error: err.message });
    }
  });

  return app;
}

/**
 * @param {import('../ingest/IngestPipeline').IngestPipeline} pipeline
 * @param {object} [options]
 */
function startWebhookServer(pipeline, options = {}) {
  const app = createWebhookApp(pipeline);
  const port = options.port || config.port;
  const server = app.listen(port, () => {
    log.info({ port }, 'webhook server listening');
  });
  return { app, server };
}

module.exports = { createWebhookApp, startWebhookServer };
