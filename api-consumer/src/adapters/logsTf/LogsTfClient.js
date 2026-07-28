'use strict';

const { config } = require('../../config');
const { ResilientHttpClient } = require('../../http/resilientClient');
const { parseLogsTf } = require('./parseLogsTf');

class LogsTfClient {
  /**
   * @param {object} [options]
   * @param {ResilientHttpClient} [options.http]
   * @param {string} [options.baseUrl]
   */
  constructor(options = {}) {
    this.baseUrl = (options.baseUrl || config.logsTfBaseUrl).replace(/\/$/, '');
    this.http =
      options.http ||
      new ResilientHttpClient({
        name: 'logs.tf',
        minDelayMs: Math.max(config.httpMinDelayMs, 300),
      });
  }

  /**
   * @param {number|string} logId
   * @returns {Promise<object>}
   */
  async fetchLog(logId) {
    const url = `${this.baseUrl}/${logId}`;
    return this.http.getJson(url);
  }

  /**
   * @param {number|string} logId
   * @param {object} [context]
   */
  async fetchNormalized(logId, context = {}) {
    const data = await this.fetchLog(logId);
    return parseLogsTf(data, Number(logId), context);
  }
}

module.exports = { LogsTfClient };
