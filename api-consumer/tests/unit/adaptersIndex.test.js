'use strict';

const { createAdapter, MatchaAdapter } = require('../../src/adapters');
const { LogSourceAdapter } = require('../../src/adapters/LogSourceAdapter');

describe('createAdapter', () => {
  test('returns MatchaAdapter for matcha.tf', () => {
    const adapter = createAdapter('matcha.tf', {
      http: { getJson: jest.fn() },
      logsTf: { fetchNormalized: jest.fn() },
    });
    expect(adapter).toBeInstanceOf(MatchaAdapter);
  });

  test('throws for unknown source site', () => {
    expect(() => createAdapter('unknown-site')).toThrow(/Unknown log source adapter/);
  });
});

describe('LogSourceAdapter base class', () => {
  test('default methods throw not-implemented errors', () => {
    class StubAdapter extends LogSourceAdapter {}
    const adapter = new StubAdapter();

    expect(() => adapter.sourceSite).toThrow(/sourceSite/);
    expect(adapter.listMatchIds()).rejects.toThrow(/listMatchIds/);
    expect(adapter.fetchNormalizedMatch(1)).rejects.toThrow(/fetchNormalizedMatch/);
  });
});
