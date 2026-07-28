'use strict';

const { v4: uuidv4 } = require('uuid');
const { LogSourceAdapter } = require('../LogSourceAdapter');
const { config } = require('../../config');
const { ResilientHttpClient } = require('../../http/resilientClient');
const { LogsTfClient } = require('../logsTf/LogsTfClient');
const {
  extractLogRefs,
  extractTournament,
  extractSeriesMeta,
  selectIngestibleMatchIds,
} = require('./parseMatch');
const { child } = require('../../logger');

const log = child({ component: 'matcha-adapter' });

/**
 * matcha.tf adapter.
 *
 * Flow:
 * 1. List confirmed matches for a league/division
 * 2. Fetch match detail (maps, rosters, `logs[]`)
 * 3. Resolve each `logstfId` via logs.tf for player/class stats
 * 4. Emit one NormalizedTF2Match per map log
 */
class MatchaAdapter extends LogSourceAdapter {
  /**
   * @param {object} [options]
   * @param {number} [options.leagueId]
   * @param {number} [options.divisionId]
   * @param {string} [options.baseUrl]
   * @param {ResilientHttpClient} [options.http]
   * @param {LogsTfClient} [options.logsTf]
   * @param {string} [options.actorId]
   */
  constructor(options = {}) {
    super();
    this.leagueId = options.leagueId ?? config.matchaLeagueId;
    this.divisionId = options.divisionId ?? config.matchaDivisionId;
    this.tournamentName = options.tournamentName ?? config.matchaTournamentName;
    this.tournamentSlug = options.tournamentSlug ?? config.matchaTournamentSlug;
    this.baseUrl = (options.baseUrl || config.matchaBaseUrl).replace(/\/$/, '');
    this.actorId = options.actorId ?? config.actorId;
    this.http =
      options.http ||
      new ResilientHttpClient({
        name: 'matcha.tf',
        minDelayMs: Math.max(config.httpMinDelayMs, 500),
      });
    this.logsTf = options.logsTf || new LogsTfClient();
  }

  get sourceSite() {
    return 'matcha.tf';
  }

  async listMatchIds() {
    const url =
      `${this.baseUrl}/v1/leagues/${this.leagueId}/matches` +
      `?divisionId=${this.divisionId}`;
    const body = await this.http.getJson(url);
    const ids = selectIngestibleMatchIds(body);
    log.info({ leagueId: this.leagueId, divisionId: this.divisionId, count: ids.length }, 'listed matches');
    return ids;
  }

  /**
   * @param {string|number} sourceMatchId
   * @param {{ correlationId?: string }} [options]
   */
  async fetchNormalizedMatch(sourceMatchId, options = {}) {
    const correlationId = options.correlationId || uuidv4();
    const ingestedAt = new Date().toISOString();
    const raw = await this.fetchRawMatch(sourceMatchId);
    const logRefs = extractLogRefs(raw);
    const tournament = extractTournament(raw, {
      name: this.tournamentName,
      slug: this.tournamentSlug,
    });
    const series = extractSeriesMeta(raw);

    if (!logRefs.length) {
      log.info(
        { sourceMatchId, status: raw?.status, forfeit: raw?.forfeit, correlationId },
        'match has no logs.tf refs yet'
      );
      return [];
    }

    const normalized = [];
    const failures = [];
    for (const ref of logRefs) {
      try {
        const match = await this.logsTf.fetchNormalized(ref.logstfId, {
          sourceSite: this.sourceSite,
          sourceMatchId: String(sourceMatchId),
          correlationId,
          ingestedAt,
          actorId: this.actorId,
          mapName: ref.mapName || undefined,
          tournament,
        });
        // Attach series metadata without breaking CQRS payload shape.
        match.source.series = series;
        match.source.logstfUrl = ref.logstfUrl;
        match.source.mapIndex = ref.mapIndex;
        normalized.push(match);
      } catch (err) {
        log.error(
          {
            sourceMatchId,
            logstfId: ref.logstfId,
            correlationId,
            err: err.message,
            status: err.status,
          },
          'failed to enrich matcha log via logs.tf'
        );
        failures.push({
          logstfId: ref.logstfId,
          error: err.message,
          status: err.status ?? null,
        });
      }
    }

    if (!normalized.length) {
      const err = new Error(
        failures.length
          ? `All ${failures.length} logs.tf fetches failed for match ${sourceMatchId}`
          : `No logs.tf payloads resolved for match ${sourceMatchId}`
      );
      err.failures = failures;
      throw err;
    }

    if (failures.length) {
      log.warn(
        {
          sourceMatchId,
          correlationId,
          failures,
          ingestedLogCount: normalized.length,
        },
        'partial series ingest; some maps skipped'
      );
    }

    log.info(
      {
        sourceMatchId,
        correlationId,
        logCount: normalized.length,
        mapNames: normalized.map((m) => m.map_name),
      },
      'normalized matcha match'
    );
    return normalized;
  }

  /**
   * @param {string|number} sourceMatchId
   */
  async fetchRawMatch(sourceMatchId) {
    const url = `${this.baseUrl}/v1/matches/${sourceMatchId}`;
    return this.http.getJson(url);
  }
}

module.exports = { MatchaAdapter };
