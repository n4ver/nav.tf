'use strict';

/**
 * Extract logs.tf IDs referenced by a matcha.tf match detail payload.
 * Prefer the structured `logs[]` array; fall back to URLs embedded in `notes`.
 *
 * @param {object} rawMatch
 * @returns {Array<{ logstfId: number, mapName: string|null, mapIndex: number|null, logstfUrl: string|null }>}
 */
function extractLogRefs(rawMatch) {
  const refs = [];
  const seen = new Set();

  const push = (logstfId, meta = {}) => {
    const id = Number.parseInt(String(logstfId), 10);
    if (!Number.isFinite(id) || id <= 0 || seen.has(id)) return;
    seen.add(id);
    refs.push({
      logstfId: id,
      mapName: meta.mapName ?? null,
      mapIndex: meta.mapIndex ?? null,
      logstfUrl: meta.logstfUrl ?? `https://logs.tf/${id}`,
    });
  };

  for (const entry of rawMatch?.logs || []) {
    push(entry.logstfId, {
      mapName: entry.mapName || null,
      mapIndex: Number.isFinite(entry.mapIndex) ? entry.mapIndex : null,
      logstfUrl: entry.logstfUrl || null,
    });
  }

  const notes = String(rawMatch?.notes || '');
  for (const match of notes.matchAll(/logs\.tf\/(\d+)/gi)) {
    push(match[1]);
  }

  return refs;
}

/**
 * Build tournament metadata for CQRS projections.
 * Uses configured display name/slug so all matcha ingests group under one tournament.
 *
 * @param {object} rawMatch
 * @param {{ name?: string, slug?: string }} [options]
 */
function extractTournament(rawMatch, options = {}) {
  const league = rawMatch?.league || {};
  const division = rawMatch?.division || {};
  const name = options.name || league.name || `matcha-league-${rawMatch?.leagueId || 'unknown'}`;
  const slug = options.slug || name;
  const startDate = league.startDate ? `${league.startDate}T00:00:00.000Z` : null;
  return {
    name,
    slug,
    start_date: startDate,
    end_date: null,
    leagueId: league.id ?? rawMatch?.leagueId ?? null,
    leagueName: league.name || null,
    divisionId: rawMatch?.divisionId ?? division?.id ?? null,
    divisionName: division?.name ?? null,
    format: league.format ?? null,
  };
}

/**
 * Pickup / series metadata retained on the normalized source envelope.
 * @param {object} rawMatch
 */
function extractSeriesMeta(rawMatch) {
  return {
    status: rawMatch?.status || null,
    forfeit: Boolean(rawMatch?.forfeit),
    forfeitType: rawMatch?.forfeitType || null,
    homeTeam: rawMatch?.homeTeam
      ? { id: rawMatch.homeTeam.id, name: rawMatch.homeTeam.name, tag: rawMatch.homeTeam.tag || null }
      : null,
    awayTeam: rawMatch?.awayTeam
      ? { id: rawMatch.awayTeam.id, name: rawMatch.awayTeam.name, tag: rawMatch.awayTeam.tag || null }
      : null,
    homeScore: rawMatch?.homeScore ?? null,
    awayScore: rawMatch?.awayScore ?? null,
    round: rawMatch?.round || null,
    maps: Array.isArray(rawMatch?.maps)
      ? rawMatch.maps.map((m) => ({
          mapName: m.mapName || null,
          homeScore: m.homeScore ?? null,
          awayScore: m.awayScore ?? null,
          winner: m.winner || null,
          orderIndex: m.orderIndex ?? null,
        }))
      : [],
    scheduledAt: rawMatch?.scheduledAt || null,
    confirmedAt: rawMatch?.confirmedAt || null,
    serverRegion: rawMatch?.serverRegion || null,
  };
}

/**
 * Filter league match list down to ingestible IDs.
 * @param {object[]} matches
 * @returns {number[]}
 */
function selectIngestibleMatchIds(matches) {
  if (!Array.isArray(matches)) return [];
  return matches
    .filter((m) => m && m.status === 'confirmed' && !m.isTest)
    .map((m) => Number(m.id))
    .filter((id) => Number.isFinite(id) && id > 0);
}

module.exports = {
  extractLogRefs,
  extractTournament,
  extractSeriesMeta,
  selectIngestibleMatchIds,
};
