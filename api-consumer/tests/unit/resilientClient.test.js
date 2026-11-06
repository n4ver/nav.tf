'use strict';

const { ResilientHttpClient, HttpError } = require('../../src/http/resilientClient');

function jsonResponse(status, body, text) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text ?? JSON.stringify(body),
  };
}

describe('ResilientHttpClient', () => {
  test('getJson returns parsed body on success', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    const client = new ResilientHttpClient({
      name: 'test',
      minDelayMs: 0,
      maxRetries: 0,
      fetchImpl,
    });

    const body = await client.getJson('https://example.com/data');
    expect(body).toEqual({ ok: true });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  test('getJson retries on 503 then succeeds', async () => {
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce(jsonResponse(503, null, 'unavailable'))
      .mockResolvedValueOnce(jsonResponse(200, { recovered: true }));
    const client = new ResilientHttpClient({
      name: 'test-retry',
      minDelayMs: 0,
      maxRetries: 2,
      errorThresholdPercentage: 100,
      fetchImpl,
    });

    const body = await client.getJson('https://example.com/data');
    expect(body).toEqual({ recovered: true });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  test('getJson does not retry on 404', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse(404, null, 'missing'));
    const client = new ResilientHttpClient({
      name: 'test',
      minDelayMs: 0,
      maxRetries: 3,
      fetchImpl,
    });

    await expect(client.getJson('https://example.com/missing')).rejects.toMatchObject({
      status: 404,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  test('getJson rejects invalid JSON', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse(200, null, 'not-json'));
    const client = new ResilientHttpClient({
      name: 'test',
      minDelayMs: 0,
      maxRetries: 0,
      fetchImpl,
    });

    await expect(client.getJson('https://example.com/bad')).rejects.toMatchObject({
      message: expect.stringContaining('Invalid JSON'),
    });
  });

  test('HttpError marks retryable statuses', () => {
    expect(new HttpError('rate limited', 429, 'https://x').retryable).toBe(true);
    expect(new HttpError('server error', 500, 'https://x').retryable).toBe(true);
    expect(new HttpError('not found', 404, 'https://x').retryable).toBe(false);
  });
});
