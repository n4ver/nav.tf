'use strict';

const logsTfPayload = require('../fixtures/logs-tf-4092518.json');
const { parseLogsTf } = require('../../src/adapters/logsTf/parseLogsTf');
const { EventPublisher } = require('../../src/rabbitmq/publisher');

function createMockChannel() {
  return {
    publish: jest.fn((_exchange, _key, _body, _opts, cb) => cb(null)),
    assertExchange: jest.fn().mockResolvedValue(undefined),
    assertQueue: jest.fn().mockResolvedValue({ queue: 'tf2-api-consumer.dlq' }),
    bindQueue: jest.fn().mockResolvedValue(undefined),
    on: jest.fn(),
    close: jest.fn().mockResolvedValue(undefined),
  };
}

function createMockConnection(channel = createMockChannel()) {
  return {
    getChannel: jest.fn().mockResolvedValue(channel),
  };
}

function sampleMatch() {
  return parseLogsTf(logsTfPayload, 4092518, {
    sourceSite: 'matcha.tf',
    sourceMatchId: '201',
    correlationId: 'corr-publisher',
    ingestedAt: '2026-07-28T08:00:00.000Z',
    actorId: 'api-consumer',
    mapName: 'cp_process_f12',
    tournament: { name: 'Test Cup', slug: 'test-cup' },
  });
}

describe('EventPublisher', () => {
  test('publishIngestedMatch emits MatchParsed and MatchLogIngested', async () => {
    const channel = createMockChannel();
    const connection = createMockConnection(channel);
    const publisher = new EventPublisher(connection, {
      routingPrefix: 'events',
      exchangeName: 'tf2-events',
      dlxName: 'tf2-events.dlx',
      actorId: 'test-actor',
    });

    const match = sampleMatch();
    const result = await publisher.publishIngestedMatch(match, { correlationId: 'corr-publisher' });

    expect(result.events).toEqual(['MatchParsed', 'MatchLogIngested']);
    expect(result.sourceLogId).toBe(4092518);
    expect(channel.publish).toHaveBeenCalledTimes(2);
    expect(channel.publish.mock.calls[0][0]).toBe('tf2-events');
    expect(channel.publish.mock.calls[0][1]).toBe('events.MatchParsed');
  });

  test('publishDeadLetter writes to DLX', async () => {
    const channel = createMockChannel();
    const connection = createMockConnection(channel);
    const publisher = new EventPublisher(connection);

    await publisher.publishDeadLetter({
      sourceSite: 'matcha.tf',
      sourceMatchId: '201',
      correlationId: 'corr-dlq',
      stage: 'publish',
      error: 'broker down',
    });

    expect(channel.publish).toHaveBeenCalledTimes(1);
    expect(channel.publish.mock.calls[0][0]).toBe('tf2-events.dlx');
    expect(channel.publish.mock.calls[0][1]).toBe('failed.matcha.tf');
  });
});
