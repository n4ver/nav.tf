'use strict';

const { LogsTfClient } = require('../../src/adapters/logsTf/LogsTfClient');
const logsTfPayload = require('../fixtures/logs-tf-4092518.json');

describe('LogsTfClient', () => {
  test('fetchLog calls underlying HTTP client', async () => {
    const http = { getJson: jest.fn().mockResolvedValue(logsTfPayload) };
    const client = new LogsTfClient({ http, baseUrl: 'https://logs.tf/api/v1/log' });

    const data = await client.fetchLog(4092518);
    expect(data).toBe(logsTfPayload);
    expect(http.getJson).toHaveBeenCalledWith('https://logs.tf/api/v1/log/4092518');
  });

  test('fetchNormalized maps logs.tf payload', async () => {
    const http = { getJson: jest.fn().mockResolvedValue(logsTfPayload) };
    const client = new LogsTfClient({ http, baseUrl: 'https://logs.tf/api/v1/log' });

    const match = await client.fetchNormalized(4092518, {
      sourceSite: 'logs.tf',
      sourceMatchId: '4092518',
      mapName: 'cp_process_f12',
    });

    expect(match.source_log_id).toBe(4092518);
    expect(match.map_name).toBe('cp_process_f12');
    expect(match.players.length).toBeGreaterThan(0);
  });
});
