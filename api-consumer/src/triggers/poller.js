'use strict';

const cron = require('node-cron');
const { child } = require('../logger');
const { config } = require('../config');

const log = child({ component: 'poller' });

/**
 * Scheduled polling job for discovering new matcha.tf matches.
 * @param {import('../ingest/IngestPipeline').IngestPipeline} pipeline
 * @param {object} [options]
 */
function startPoller(pipeline, options = {}) {
  const expression = options.cron || config.pollCron;
  if (!cron.validate(expression)) {
    throw new Error(`Invalid POLL_CRON expression: ${expression}`);
  }

  const task = cron.schedule(expression, async () => {
    try {
      await pipeline.pollAndIngest('cron');
    } catch (err) {
      if (err.code === 'POLL_IN_PROGRESS') {
        log.warn('cron poll skipped; another poll is in progress');
        return;
      }
      log.error({ err: err.message }, 'poll tick failed');
    }
  });

  log.info({ expression }, 'poller started');
  return {
    stop() {
      task.stop();
      log.info('poller stopped');
    },
  };
}

module.exports = { startPoller };
