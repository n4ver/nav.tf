'use strict';

const { config } = require('./config');
const { logger } = require('./logger');
const { createAdapter } = require('./adapters');
const { RabbitConnection } = require('./rabbitmq/connection');
const { EventPublisher } = require('./rabbitmq/publisher');
const { IngestPipeline } = require('./ingest/IngestPipeline');
const { IdempotencyStore } = require('./ingest/idempotency');
const { startPoller } = require('./triggers/poller');
const { startWebhookServer } = require('./triggers/webhook');

async function main() {
  logger.info(
    {
      exchange: config.exchangeName,
      dlx: config.dlxName,
      leagueId: config.matchaLeagueId,
      divisionId: config.matchaDivisionId,
      pollEnabled: config.pollEnabled,
      webhookEnabled: config.webhookEnabled,
    },
    'starting tf2-api-consumer'
  );

  const rabbit = new RabbitConnection();
  await rabbit.connect();

  const adapter = createAdapter('matcha.tf');
  const publisher = new EventPublisher(rabbit);
  const pipeline = new IngestPipeline({
    adapter,
    publisher,
    idempotency: new IdempotencyStore(),
  });

  /** @type {{ stop: () => void }|null} */
  let poller = null;
  if (config.pollEnabled) {
    poller = startPoller(pipeline);
  }

  /** @type {{ server: import('http').Server }|null} */
  let webhook = null;
  if (config.webhookEnabled) {
    webhook = startWebhookServer(pipeline);
  }

  const shutdown = async (signal) => {
    logger.info({ signal }, 'shutting down');
    if (poller) poller.stop();
    if (webhook?.server) {
      await new Promise((resolve) => webhook.server.close(resolve));
    }
    await rabbit.close();
    process.exit(0);
  };

  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
}

main().catch((err) => {
  logger.error({ err: err.message, stack: err.stack }, 'fatal startup error');
  process.exit(1);
});
