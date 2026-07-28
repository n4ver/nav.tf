'use strict';

const pino = require('pino');
const { config } = require('./config');

const logger = pino({
  level: config.logLevel,
  base: { service: 'tf2-api-consumer' },
  timestamp: pino.stdTimeFunctions.isoTime,
});

function child(bindings) {
  return logger.child(bindings);
}

module.exports = { logger, child };