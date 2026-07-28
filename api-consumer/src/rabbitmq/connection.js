'use strict';

const amqp = require('amqplib');
const { config } = require('../config');
const { child } = require('../logger');

const log = child({ component: 'rabbitmq' });

/**
 * Robust amqplib connection with automatic channel recreation.
 */
class RabbitConnection {
  /**
   * @param {object} [options]
   * @param {string} [options.url]
   * @param {string} [options.exchangeName]
   * @param {string} [options.dlxName]
   */
  constructor(options = {}) {
    this.url = options.url || config.rabbitmqUrl;
    this.exchangeName = options.exchangeName || config.exchangeName;
    this.dlxName = options.dlxName || config.dlxName;
    this._connection = null;
    this._channel = null;
    this._connecting = null;
  }

  async connect() {
    if (this._channel) return this._channel;
    if (this._connecting) return this._connecting;

    this._connecting = (async () => {
      log.info({ url: this.url.replace(/:[^:@/]+@/, ':***@') }, 'connecting to RabbitMQ');
      this._connection = await amqp.connect(this.url);
      this._connection.on('error', (err) => {
        log.error({ err: err.message }, 'RabbitMQ connection error');
        this._reset();
      });
      this._connection.on('close', () => {
        log.warn('RabbitMQ connection closed');
        this._reset();
      });

      this._channel = await this._connection.createConfirmChannel();
      this._channel.on('error', (err) => {
        log.error({ err: err.message }, 'RabbitMQ channel error');
        this._channel = null;
      });
      this._channel.on('close', () => {
        this._channel = null;
      });

      await this._channel.assertExchange(this.dlxName, 'topic', { durable: true });
      await this._channel.assertExchange(this.exchangeName, 'topic', { durable: true });

      // Dead-letter queue for exhausted ingest failures.
      const dlq = await this._channel.assertQueue('tf2-api-consumer.dlq', {
        durable: true,
      });
      await this._channel.bindQueue(dlq.queue, this.dlxName, 'failed.#');

      log.info(
        { exchange: this.exchangeName, dlx: this.dlxName, dlq: dlq.queue },
        'RabbitMQ ready'
      );
      return this._channel;
    })();

    try {
      return await this._connecting;
    } finally {
      this._connecting = null;
    }
  }

  async getChannel() {
    return this.connect();
  }

  _reset() {
    this._connection = null;
    this._channel = null;
  }

  async close() {
    try {
      if (this._channel) await this._channel.close();
    } catch {
      /* ignore */
    }
    try {
      if (this._connection) await this._connection.close();
    } catch {
      /* ignore */
    }
    this._reset();
  }
}

module.exports = { RabbitConnection };
