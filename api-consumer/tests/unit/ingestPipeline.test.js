'use strict';

const { IngestPipeline } = require('../../src/ingest/IngestPipeline');
const { IdempotencyStore } = require('../../src/ingest/idempotency');
const { idempotencyKey } = require('../../src/models/normalized');
const logsTfPayload = require('../fixtures/logs-tf-4092518.json');
const { parseLogsTf } = require('../../src/adapters/logsTf/parseLogsTf');

function makeNormalizedMatch(logId = 4092518) {
  return parseLogsTf(logsTfPayload, logId, {
    sourceSite: 'matcha.tf',
    sourceMatchId: '201',
    correlationId: 'corr-pipeline',
    ingestedAt: '2026-07-28T08:00:00.000Z',
    actorId: 'api-consumer',
    mapName: 'cp_process_f12',
    tournament: { name: 'Test Cup', slug: 'test-cup' },
  });
}

function createPipeline(overrides = {}) {
  const idempotency = new IdempotencyStore();
  const adapter = {
    sourceSite: 'matcha.tf',
    listMatchIds: jest.fn().mockResolvedValue([201, 202]),
    fetchNormalizedMatch: jest.fn().mockResolvedValue([makeNormalizedMatch()]),
    ...overrides.adapter,
  };
  const publisher = {
    publishIngestedMatch: jest.fn().mockResolvedValue({ routingKey: 'events.MatchLogIngested' }),
    publishDeadLetter: jest.fn().mockResolvedValue(undefined),
    ...overrides.publisher,
  };
  const pipeline = new IngestPipeline({ adapter, publisher, idempotency });
  return { pipeline, adapter, publisher, idempotency };
}

describe('IngestPipeline', () => {
  test('ingestMatch publishes and marks idempotency on happy path', async () => {
    const { pipeline, publisher, idempotency } = createPipeline();
    const result = await pipeline.ingestMatch(201, { correlationId: 'corr-1' });

    expect(result.accepted).toBe(1);
    expect(result.skipped).toBe(0);
    expect(result.noLogs).toBe(false);
    expect(publisher.publishIngestedMatch).toHaveBeenCalledTimes(1);

    const match = makeNormalizedMatch();
    const key = idempotencyKey('matcha.tf', '201', match.source_log_id);
    expect(idempotency.get(key)).toBeTruthy();
    expect(idempotency.get(key).matchId).toBe(match.match_id);
  });

  test('ingestMatch skips duplicate logs via idempotency', async () => {
    const { pipeline, publisher } = createPipeline();
    await pipeline.ingestMatch(201);
    await pipeline.ingestMatch(201);

    expect(publisher.publishIngestedMatch).toHaveBeenCalledTimes(1);
  });

  test('ingestMatch reports noLogs when adapter returns empty array', async () => {
    const { pipeline, publisher } = createPipeline({
      adapter: { fetchNormalizedMatch: jest.fn().mockResolvedValue([]) },
    });
    const result = await pipeline.ingestMatch(201);

    expect(result.noLogs).toBe(true);
    expect(result.accepted).toBe(0);
    expect(publisher.publishIngestedMatch).not.toHaveBeenCalled();
  });

  test('ingestMatch publishes dead letter when fetch fails', async () => {
    const err = new Error('upstream timeout');
    err.status = 504;
    const { pipeline, publisher } = createPipeline({
      adapter: {
        fetchNormalizedMatch: jest.fn().mockRejectedValue(err),
      },
    });

    await expect(pipeline.ingestMatch(201)).rejects.toThrow('upstream timeout');
    expect(publisher.publishDeadLetter).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceSite: 'matcha.tf',
        sourceMatchId: '201',
        stage: 'fetchNormalizedMatch',
        error: 'upstream timeout',
      })
    );
  });

  test('ingestMatch continues when one publish fails but others succeed', async () => {
    const second = makeNormalizedMatch(4092532);
    const { pipeline, publisher } = createPipeline({
      adapter: {
        fetchNormalizedMatch: jest.fn().mockResolvedValue([makeNormalizedMatch(), second]),
      },
      publisher: {
        publishIngestedMatch: jest
          .fn()
          .mockRejectedValueOnce(new Error('broker down'))
          .mockResolvedValueOnce({ routingKey: 'events.MatchLogIngested' }),
      },
    });

    const result = await pipeline.ingestMatch(201);
    expect(result.accepted).toBe(1);
    expect(result.errors).toHaveLength(1);
    expect(publisher.publishDeadLetter).toHaveBeenCalled();
  });

  test('ingestMatch throws when all publishes fail', async () => {
    const { pipeline } = createPipeline({
      publisher: {
        publishIngestedMatch: jest.fn().mockRejectedValue(new Error('broker down')),
        publishDeadLetter: jest.fn().mockResolvedValue(undefined),
      },
    });

    await expect(pipeline.ingestMatch(201)).rejects.toThrow(/All 1 log\(s\) failed to publish/);
  });

  test('pollAndIngest aggregates accepted/skipped across matches', async () => {
    const { pipeline, adapter } = createPipeline();
    const summary = await pipeline.pollAndIngest('cron');

    expect(adapter.listMatchIds).toHaveBeenCalled();
    expect(summary.status).toBe('accepted');
    expect(summary.matchIds).toBe(2);
    expect(summary.accepted).toBeGreaterThan(0);
  });

  test('pollAndIngest rejects concurrent polls with POLL_IN_PROGRESS', async () => {
    const { pipeline, adapter } = createPipeline({
      adapter: {
        listMatchIds: jest.fn().mockImplementation(
          () => new Promise((resolve) => setTimeout(() => resolve([201]), 50))
        ),
      },
    });

    const first = pipeline.pollAndIngest('cron');
    await expect(pipeline.pollAndIngest('cron')).rejects.toMatchObject({
      code: 'POLL_IN_PROGRESS',
    });
    await first;
  });

  test('clearIdempotency resets the store', async () => {
    const { pipeline, idempotency } = createPipeline();
    await pipeline.ingestMatch(201);
    expect(idempotency.size).toBe(1);

    const cleared = pipeline.clearIdempotency();
    expect(cleared).toBe(1);
    expect(idempotency.size).toBe(0);
  });
});

describe('IdempotencyStore', () => {
  test('get returns null for unknown keys', () => {
    const store = new IdempotencyStore();
    expect(store.get('missing')).toBeNull();
  });

  test('mark and get round-trip', () => {
    const store = new IdempotencyStore();
    store.mark('key-1', 'match-uuid');
    expect(store.get('key-1')).toEqual(
      expect.objectContaining({ matchId: 'match-uuid', publishedAt: expect.any(String) })
    );
  });
});
