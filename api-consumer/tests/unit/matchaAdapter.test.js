'use strict';

const {
  extractLogRefs,
  extractTournament,
  selectIngestibleMatchIds,
} = require('../../src/adapters/matcha/parseMatch');
const { parseLogsTf } = require('../../src/adapters/logsTf/parseLogsTf');
const {
  createMatchLogIngestedEvent,
  toMatchParsedPayload,
  stableMatchIdFromLogsTf,
  idempotencyKey,
} = require('../../src/models/normalized');

const matchaMatch = require('../fixtures/matcha-match-201.json');
const logsTfPayload = require('../fixtures/logs-tf-4092518.json');
const leagueMatches = require('../fixtures/matcha-league-matches.json');

describe('matcha.tf → normalized MatchLogIngested payload', () => {
  test('extracts logstfIds from match detail logs[]', () => {
    const refs = extractLogRefs(matchaMatch);
    expect(refs.map((r) => r.logstfId)).toEqual([4092518, 4092532, 4092546]);
    expect(refs[0].mapName).toBe('cp_process_f12');
  });

  test('selects confirmed non-test matches from league listing', () => {
    const ids = selectIngestibleMatchIds(leagueMatches);
    expect(ids).toContain(201);
    expect(ids).toContain(4);
    expect(ids.every((id) => Number.isFinite(id))).toBe(true);
  });

  test('maps logs.tf JSON + matcha tournament into canonical event payload', () => {
    const tournament = extractTournament(matchaMatch, {
      name: 'Matcha.tf Minicup Invite',
      slug: 'matcha-tf-minicup-invite',
    });
    const logRef = extractLogRefs(matchaMatch)[0];

    const normalized = parseLogsTf(logsTfPayload, logRef.logstfId, {
      sourceSite: 'matcha.tf',
      sourceMatchId: String(matchaMatch.id),
      correlationId: 'corr-test-001',
      ingestedAt: '2026-07-28T08:00:00.000Z',
      actorId: 'api-consumer',
      mapName: logRef.mapName,
      tournament,
    });

    expect(normalized.match_id).toBe(stableMatchIdFromLogsTf(4092518));
    expect(normalized.map_name).toBe('cp_process_f12');
    expect(normalized.blu_score).toBe(0);
    expect(normalized.red_score).toBe(5);
    expect(normalized.duration_seconds).toBe(960);
    expect(normalized.source_log_id).toBe(4092518);
    expect(normalized.source.sourceSite).toBe('matcha.tf');
    expect(normalized.source.sourceMatchId).toBe('201');
    expect(normalized.source.correlationId).toBe('corr-test-001');
    expect(normalized.tournament.name).toBe('Matcha.tf Minicup Invite');
    expect(normalized.tournament.slug).toBe('matcha-tf-minicup-invite');
    expect(normalized.players.length).toBeGreaterThan(0);

    const medic = normalized.players.find((p) => p.primary_class === 'medic');
    expect(medic).toBeTruthy();
    expect(medic.ubers).toBeGreaterThan(0);
    expect(medic.class_stats[0].healing_done).toBeGreaterThan(0);
    expect(medic.captures).toBeGreaterThan(0);
    expect(medic.class_stats[0].primary_accuracy).toBeGreaterThan(0);

    const scout = normalized.players.find((p) => p.display_name === 'hezy');
    expect(scout).toBeTruthy();
    expect(scout.kills).toBe(15);
    expect(scout.deaths).toBe(8);
    expect(scout.damage_per_minute).toBeGreaterThan(0);
    expect(scout.captures).toBeGreaterThan(0);
    expect(scout.class_stats.some((c) => c.primary_accuracy > 0)).toBe(true);

    const soldierWithAir = normalized.players.find((p) => p.airshots > 0);
    expect(soldierWithAir).toBeTruthy();

    const event = createMatchLogIngestedEvent(normalized, {
      correlationId: 'corr-test-001',
      actorId: 'api-consumer',
    });

    expect(event.event_type).toBe('MatchLogIngested');
    expect(event.payload.sourceSite).toBe('matcha.tf');
    expect(event.payload.sourceMatchId).toBe('201');
    expect(event.payload.correlationId).toBe('corr-test-001');
    expect(event.payload.ingestedAt).toBe('2026-07-28T08:00:00.000Z');
    expect(event.payload.match.match_id).toBe(normalized.match_id);

    const cqrsPayload = toMatchParsedPayload(normalized);
    expect(cqrsPayload).toMatchObject({
      match_id: normalized.match_id,
      map_name: 'cp_process_f12',
      blu_score: 0,
      red_score: 5,
      source_log_id: 4092518,
    });
    expect(cqrsPayload.source).toBeUndefined();
  });

  test('idempotency key is stable for repeated fetches of the same log', () => {
    const a = idempotencyKey('matcha.tf', 201, 4092518);
    const b = idempotencyKey('matcha.tf', 201, 4092518);
    expect(a).toBe(b);
    expect(a).toBe('logs.tf:4092518');
  });

  test('handles missing notes/logs without throwing', () => {
    expect(extractLogRefs({})).toEqual([]);
    expect(extractLogRefs({ notes: null, logs: null })).toEqual([]);
    expect(extractLogRefs({ notes: 'see https://logs.tf/4074002#abc' })).toEqual([
      {
        logstfId: 4074002,
        mapName: null,
        mapIndex: null,
        logstfUrl: 'https://logs.tf/4074002',
      },
    ]);
  });
});

describe('MatchaAdapter partial series ingest', () => {
  const { MatchaAdapter } = require('../../src/adapters/matcha/MatchaAdapter');

  test('returns successful maps when one logs.tf fetch fails', async () => {
    const adapter = new MatchaAdapter({
      http: {
        getJson: async (url) => {
          if (String(url).includes('/v1/matches/')) {
            return matchaMatch;
          }
          throw new Error(`unexpected url ${url}`);
        },
      },
      logsTf: {
        fetchNormalized: async (logstfId) => {
          if (logstfId === 4092518) {
            return parseLogsTf(logsTfPayload, logstfId, {
              sourceSite: 'matcha.tf',
              sourceMatchId: '201',
              correlationId: 'corr-partial',
              ingestedAt: '2026-07-28T08:00:00.000Z',
              actorId: 'api-consumer',
              mapName: 'cp_process_f12',
              tournament: extractTournament(matchaMatch, {
                name: 'Matcha.tf Minicup Invite',
                slug: 'matcha-tf-minicup-invite',
              }),
            });
          }
          const err = new Error('logs.tf unavailable');
          err.status = 502;
          throw err;
        },
      },
    });

    const matches = await adapter.fetchNormalizedMatch(201, { correlationId: 'corr-partial' });
    expect(matches).toHaveLength(1);
    expect(matches[0].source_log_id).toBe(4092518);
  });
});
