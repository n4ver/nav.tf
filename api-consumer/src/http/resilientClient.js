'use strict';

const CircuitBreaker = require('opossum');
const { child } = require('../logger');
const { config } = require('../config');

const log = child({ component: 'http' });

class HttpError extends Error {
  /**
   * @param {string} message
   * @param {number} status
   * @param {string} url
   * @param {string} [body]
   */
  constructor(message, status, url, body) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
    this.url = url;
    this.body = body;
    this.retryable = status === 429 || status >= 500;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Shared HTTP client with rate pacing, exponential backoff, and circuit breaker.
 */
class ResilientHttpClient {
  /**
   * @param {object} [options]
   * @param {string} [options.name]
   * @param {number} [options.timeoutMs]
   * @param {number} [options.maxRetries]
   * @param {number} [options.minDelayMs]
   * @param {number} [options.errorThresholdPercentage]
   * @param {number} [options.resetTimeoutMs]
   * @param {typeof fetch} [options.fetchImpl]
   */
  constructor(options = {}) {
    this.name = options.name || 'http';
    this.timeoutMs = options.timeoutMs ?? config.httpTimeoutMs;
    this.maxRetries = options.maxRetries ?? config.httpMaxRetries;
    this.minDelayMs = options.minDelayMs ?? config.httpMinDelayMs;
    this.fetchImpl = options.fetchImpl || globalThis.fetch.bind(globalThis);
    this._lastRequestAt = 0;

    this._breaker = new CircuitBreaker(this._doFetch.bind(this), {
      timeout: this.timeoutMs + 1000,
      errorThresholdPercentage: options.errorThresholdPercentage ?? config.circuitErrorThreshold,
      resetTimeout: options.resetTimeoutMs ?? config.circuitResetMs,
      name: this.name,
    });

    this._breaker.on('open', () => log.warn({ client: this.name }, 'circuit opened'));
    this._breaker.on('halfOpen', () => log.info({ client: this.name }, 'circuit half-open'));
    this._breaker.on('close', () => log.info({ client: this.name }, 'circuit closed'));
  }

  /**
   * @param {string} url
   * @param {RequestInit & { headers?: Record<string, string> }} [init]
   */
  async getJson(url, init = {}) {
    const started = Date.now();
    let attempt = 0;
    let lastError;

    while (attempt <= this.maxRetries) {
      try {
        await this._pace();
        const result = await this._breaker.fire(url, {
          ...init,
          method: 'GET',
          headers: {
            Accept: 'application/json',
            ...(init.headers || {}),
          },
        });
        log.info(
          { client: this.name, url, status: result.status, latencyMs: Date.now() - started, attempt },
          'http ok'
        );
        return result.body;
      } catch (err) {
        lastError = err;
        const retryable =
          (err instanceof HttpError && err.retryable) ||
          err.code === 'ECONNRESET' ||
          err.name === 'AbortError' ||
          err.message?.includes('Breaker is open');

        log.warn(
          {
            client: this.name,
            url,
            attempt,
            err: err.message,
            status: err.status,
            latencyMs: Date.now() - started,
          },
          'http failed'
        );

        if (!retryable || attempt >= this.maxRetries) break;
        const backoff = this.minDelayMs * 2 ** attempt + Math.floor(Math.random() * 100);
        await sleep(backoff);
        attempt += 1;
      }
    }

    throw lastError;
  }

  async _pace() {
    const elapsed = Date.now() - this._lastRequestAt;
    if (elapsed < this.minDelayMs) {
      await sleep(this.minDelayMs - elapsed);
    }
    this._lastRequestAt = Date.now();
  }

  /**
   * @param {string} url
   * @param {RequestInit} init
   */
  async _doFetch(url, init) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(url, { ...init, signal: controller.signal });
      const text = await response.text();
      if (!response.ok) {
        throw new HttpError(
          `HTTP ${response.status} for ${url}`,
          response.status,
          url,
          text.slice(0, 500)
        );
      }
      let body = null;
      if (text) {
        try {
          body = JSON.parse(text);
        } catch {
          throw new HttpError(`Invalid JSON from ${url}`, response.status, url, text.slice(0, 200));
        }
      }
      return { status: response.status, body };
    } finally {
      clearTimeout(timer);
    }
  }
}

module.exports = { ResilientHttpClient, HttpError };
