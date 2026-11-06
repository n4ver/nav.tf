'use strict';

const cron = require('node-cron');
const { startPoller } = require('../../src/triggers/poller');

jest.mock('node-cron');

describe('startPoller', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    cron.validate.mockReturnValue(true);
    cron.schedule.mockReturnValue({ stop: jest.fn() });
  });

  test('starts cron task with configured expression', () => {
    const pipeline = { pollAndIngest: jest.fn().mockResolvedValue({ status: 'accepted' }) };
    const handle = startPoller(pipeline, { cron: '*/10 * * * *' });

    expect(cron.validate).toHaveBeenCalledWith('*/10 * * * *');
    expect(cron.schedule).toHaveBeenCalled();
    expect(typeof handle.stop).toBe('function');
    handle.stop();
  });

  test('cron callback invokes pipeline.pollAndIngest', async () => {
    const pipeline = { pollAndIngest: jest.fn().mockResolvedValue({ status: 'accepted' }) };
    startPoller(pipeline, { cron: '* * * * *' });

    const callback = cron.schedule.mock.calls[0][1];
    await callback();
    expect(pipeline.pollAndIngest).toHaveBeenCalledWith('cron');
  });

  test('cron callback ignores POLL_IN_PROGRESS', async () => {
    const busy = new Error('Poll already in progress');
    busy.code = 'POLL_IN_PROGRESS';
    const pipeline = { pollAndIngest: jest.fn().mockRejectedValue(busy) };
    startPoller(pipeline, { cron: '* * * * *' });

    const callback = cron.schedule.mock.calls[0][1];
    await expect(callback()).resolves.toBeUndefined();
  });

  test('rejects invalid cron expression', () => {
    cron.validate.mockReturnValue(false);
    const pipeline = { pollAndIngest: jest.fn() };

    expect(() => startPoller(pipeline, { cron: 'not-cron' })).toThrow(/Invalid POLL_CRON/);
  });
});
