'use strict';

const logsTfPayload = require('../fixtures/logs-tf-4092518.json');

/** @param {import('express').Application} app */
async function request(app, method, path, { headers = {}, body } = {}) {
  const server = await new Promise((resolve) => {
    const s = app.listen(0, () => resolve(s));
  });
  const { port } = server.address();
  try {
    const response = await fetch(`http://127.0.0.1:${port}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const text = await response.text();
    return {
      status: response.status,
      body: text ? JSON.parse(text) : null,
    };
  } finally {
    await new Promise((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())));
  }
}

function loadWebhookApp(apiKey) {
  jest.resetModules();
  process.env.WEBHOOK_API_KEY = apiKey;
  const { createWebhookApp } = require('../../src/triggers/webhook');
  const pipeline = {
    ingestMatch: jest.fn().mockResolvedValue({ accepted: 1, skipped: 0, noLogs: false }),
    pollAndIngest: jest.fn().mockResolvedValue({ status: 'accepted', accepted: 2, skipped: 0 }),
    clearIdempotency: jest.fn().mockReturnValue(0),
  };
  const app = createWebhookApp(pipeline);
  return { app, pipeline };
}

describe('api-consumer webhook server', () => {
  afterEach(() => {
    delete process.env.WEBHOOK_API_KEY;
    jest.resetModules();
  });

  test('GET /health returns ok without auth', async () => {
    const { app } = loadWebhookApp('secret-key');
    const res = await request(app, 'GET', '/health');
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: 'ok', service: 'tf2-api-consumer' });
  });

  test('POST /webhooks/matcha/match rejects missing API key', async () => {
    const { app } = loadWebhookApp('secret-key');
    const res = await request(app, 'POST', '/webhooks/matcha/match', {
      body: { matchId: 201 },
    });
    expect(res.status).toBe(401);
    expect(res.body.error).toBe('Unauthorized');
  });

  test('POST /webhooks/matcha/match rejects wrong API key', async () => {
    const { app } = loadWebhookApp('secret-key');
    const res = await request(app, 'POST', '/webhooks/matcha/match', {
      headers: { Authorization: 'Bearer wrong-key' },
      body: { matchId: 201 },
    });
    expect(res.status).toBe(401);
  });

  test('POST /webhooks/matcha/match returns 503 when WEBHOOK_API_KEY unset', async () => {
    const { app } = loadWebhookApp('');
    const res = await request(app, 'POST', '/webhooks/matcha/match', {
      headers: { Authorization: 'Bearer anything' },
      body: { matchId: 201 },
    });
    expect(res.status).toBe(503);
    expect(res.body.error).toMatch(/WEBHOOK_API_KEY/);
  });

  test('POST /webhooks/matcha/match returns 400 when matchId missing', async () => {
    const { app } = loadWebhookApp('secret-key');
    const res = await request(app, 'POST', '/webhooks/matcha/match', {
      headers: { 'x-api-key': 'secret-key' },
      body: {},
    });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('matchId is required');
  });

  test('POST /webhooks/matcha/match happy path with Bearer token', async () => {
    const { app, pipeline } = loadWebhookApp('secret-key');
    const res = await request(app, 'POST', '/webhooks/matcha/match', {
      headers: { Authorization: 'Bearer secret-key' },
      body: { matchId: 201, correlationId: 'corr-webhook-1' },
    });
    expect(res.status).toBe(202);
    expect(res.body.status).toBe('accepted');
    expect(res.body.sourceMatchId).toBe('201');
    expect(res.body.accepted).toBe(1);
    expect(pipeline.ingestMatch).toHaveBeenCalledWith(201, { correlationId: 'corr-webhook-1' });
  });

  test('POST /webhooks/matcha/match returns 502 when pipeline throws', async () => {
    const { app, pipeline } = loadWebhookApp('secret-key');
    pipeline.ingestMatch.mockRejectedValue(new Error('matcha.tf down'));
    const res = await request(app, 'POST', '/webhooks/matcha/match', {
      headers: { 'x-api-key': 'secret-key' },
      body: { matchId: 99 },
    });
    expect(res.status).toBe(502);
    expect(res.body.status).toBe('failed');
    expect(res.body.error).toBe('matcha.tf down');
  });

  test('POST /admin/poll requires auth', async () => {
    const { app } = loadWebhookApp('secret-key');
    const res = await request(app, 'POST', '/admin/poll');
    expect(res.status).toBe(401);
  });

  test('POST /admin/poll happy path', async () => {
    const { app, pipeline } = loadWebhookApp('secret-key');
    const res = await request(app, 'POST', '/admin/poll', {
      headers: { 'x-api-key': 'secret-key' },
    });
    expect(res.status).toBe(202);
    expect(res.body.accepted).toBe(2);
    expect(pipeline.pollAndIngest).toHaveBeenCalledWith('admin');
  });

  test('POST /admin/poll returns 409 when poll already in progress', async () => {
    const { app, pipeline } = loadWebhookApp('secret-key');
    const busy = new Error('Poll already in progress');
    busy.code = 'POLL_IN_PROGRESS';
    pipeline.pollAndIngest.mockRejectedValue(busy);
    const res = await request(app, 'POST', '/admin/poll', {
      headers: { 'x-api-key': 'secret-key' },
    });
    expect(res.status).toBe(409);
    expect(res.body.status).toBe('busy');
  });
});

describe('parseLogsTf parsing', () => {
  const { parseLogsTf } = require('../../src/adapters/logsTf/parseLogsTf');

  test('maps fixture payload to canonical match shape', () => {
    const match = parseLogsTf(logsTfPayload, 4092518, {
      sourceSite: 'matcha.tf',
      sourceMatchId: '201',
      mapName: 'cp_process_f12',
    });

    expect(match.match_id).toBeTruthy();
    expect(match.map_name).toBe('cp_process_f12');
    expect(match.blu_score).toBe(0);
    expect(match.red_score).toBe(5);
    expect(match.duration_seconds).toBe(960);
    expect(match.source_log_id).toBe(4092518);
    expect(match.players.length).toBeGreaterThan(0);
  });

  test('handles empty payload without throwing', () => {
    const match = parseLogsTf({}, 1);
    expect(match.map_name).toBe('unknown_map');
    expect(match.players).toEqual([]);
    expect(match.blu_score).toBe(0);
    expect(match.red_score).toBe(0);
  });

  test('computes primary class from longest playtime', () => {
    const match = parseLogsTf(
      {
        info: { map: 'cp_test' },
        teams: { Blue: { score: 1 }, Red: { score: 0 } },
        length: 600,
        players: {
          'STEAM_1:1:1': {
            team: 'Blue',
            kills: 5,
            deaths: 2,
            class_stats: [
              { type: 'scout', kills: 3, deaths: 1, dmg: 1000, total_time: 200 },
              { type: 'soldier', kills: 2, deaths: 1, dmg: 2000, total_time: 400 },
            ],
          },
        },
      },
      42
    );
    const player = match.players[0];
    expect(player.primary_class).toBe('soldier');
    expect(player.classes_played).toEqual(['scout', 'soldier']);
  });
});
