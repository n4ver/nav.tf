'use strict';

jest.mock('amqplib');

const amqp = require('amqplib');
const { RabbitConnection } = require('../../src/rabbitmq/connection');

function createMockChannel() {
  return {
    assertExchange: jest.fn().mockResolvedValue(undefined),
    assertQueue: jest.fn().mockResolvedValue({ queue: 'tf2-api-consumer.dlq' }),
    bindQueue: jest.fn().mockResolvedValue(undefined),
    on: jest.fn(),
    close: jest.fn().mockResolvedValue(undefined),
  };
}

describe('RabbitConnection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('connect creates channel and asserts exchanges', async () => {
    const channel = createMockChannel();
    const connection = {
      createConfirmChannel: jest.fn().mockResolvedValue(channel),
      on: jest.fn(),
      close: jest.fn().mockResolvedValue(undefined),
    };
    amqp.connect.mockResolvedValue(connection);

    const rabbit = new RabbitConnection({
      url: 'amqp://guest:guest@localhost:5672/',
      exchangeName: 'tf2-events',
      dlxName: 'tf2-events.dlx',
    });

    const result = await rabbit.connect();
    expect(result).toBe(channel);
    expect(channel.assertExchange).toHaveBeenCalledWith('tf2-events.dlx', 'topic', { durable: true });
    expect(channel.assertExchange).toHaveBeenCalledWith('tf2-events', 'topic', { durable: true });
    expect(channel.bindQueue).toHaveBeenCalled();
  });

  test('connect reuses existing channel', async () => {
    const channel = createMockChannel();
    const connection = {
      createConfirmChannel: jest.fn().mockResolvedValue(channel),
      on: jest.fn(),
      close: jest.fn().mockResolvedValue(undefined),
    };
    amqp.connect.mockResolvedValue(connection);

    const rabbit = new RabbitConnection({ url: 'amqp://localhost' });
    await rabbit.connect();
    await rabbit.connect();

    expect(amqp.connect).toHaveBeenCalledTimes(1);
  });

  test('close resets connection state', async () => {
    const channel = createMockChannel();
    const connection = {
      createConfirmChannel: jest.fn().mockResolvedValue(channel),
      on: jest.fn(),
      close: jest.fn().mockResolvedValue(undefined),
    };
    amqp.connect.mockResolvedValue(connection);

    const rabbit = new RabbitConnection({ url: 'amqp://localhost' });
    await rabbit.connect();
    await rabbit.close();

    amqp.connect.mockResolvedValue(connection);
    await rabbit.connect();
    expect(amqp.connect).toHaveBeenCalledTimes(2);
  });
});
