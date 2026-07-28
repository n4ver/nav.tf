'use strict';

const { v5: uuidv5, v4: uuidv4, NIL: UUID_NIL } = require('uuid');

/** RFC-4122 URL namespace — same as Python uuid.NAMESPACE_URL */
const NAMESPACE_URL = '6ba7b810-9dad-11d1-80b4-00c04fd430c8';

const STEAM64_BASE = 76561197960265728n;

function canonicalSteamId(raw) {
  const value = String(raw || '').trim();
  if (!value) return value;
  if (/^\d{17}$/.test(value)) return value;

  const id3 = value.match(/^\[U:\d:(\d+)\]$/);
  if (id3) {
    return (BigInt(id3[1]) + STEAM64_BASE).toString();
  }

  const legacy = value.match(/^STEAM_[0-5]:([01]):(\d+)$/i);
  if (legacy) {
    const y = BigInt(legacy[1]);
    const z = BigInt(legacy[2]);
    return (z * 2n + y + STEAM64_BASE).toString();
  }

  return value;
}

const CLASS_MAP = {
  scout: 0,
  soldier: 1,
  pyro: 2,
  demoman: 3,
  heavyweapons: 4,
  engineer: 5,
  medic: 6,
  sniper: 7,
  spy: 8,
};

function normalizeClassName(raw) {
  const value = String(raw || 'unknown').trim().toLowerCase();
  const aliases = {
    heavy: 'heavyweapons',
    heavyweapons: 'heavyweapons',
    demo: 'demoman',
    demoman: 'demoman',
    med: 'medic',
    engi: 'engineer',
  };
  return aliases[value] || value || 'unknown';
}

function classIdFromName(name) {
  return CLASS_MAP[normalizeClassName(name)] ?? 0;
}

function normalizeTeam(raw) {
  const value = String(raw || '').trim().toLowerCase();
  if (value === 'blu' || value === 'blue') return 'blu';
  if (value === 'red') return 'red';
  if (value === 'home') return 'home';
  if (value === 'away') return 'away';
  return value || 'unknown';
}

function intOr(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

function floatOr(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function slugify(raw) {
  return String(raw || 'unknown')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 128) || 'unknown';
}

/**
 * Stable match UUID matching Python: uuid5(NAMESPACE_URL, `logs.tf:{logId}`).
 * @param {number|string} logstfId
 */
function stableMatchIdFromLogsTf(logstfId) {
  return uuidv5(`logs.tf:${logstfId}`, NAMESPACE_URL);
}

/** Mirrors server/cqrs/shared/tournaments.py TOURNAMENT_CATALOG slugs. */
const TOURNAMENT_CATALOG_SLUGS = {
  1: 'invite-bracket',
  2: 'qualifier-bracket',
  3: 'main-bracket',
  4: 'matcha-tf-minicup-invite',
};

/**
 * Stable tournament UUID from slug (matches command-service convention).
 * @param {string} slug
 */
function stableTournamentIdFromSlug(slug) {
  const normalized = slugify(slug) || 'default-tournament';
  for (const [catalogId, catalogSlug] of Object.entries(TOURNAMENT_CATALOG_SLUGS)) {
    if (catalogSlug === normalized) {
      return uuidv5(`tf2-tournament:${catalogId}`, NAMESPACE_URL);
    }
  }
  return uuidv5(`tf2-tournament-slug:${normalized}`, NAMESPACE_URL);
}

/**
 * @typedef {object} ClassStat
 * @property {string} class_name
 * @property {number} class_id
 * @property {number} playtime_seconds
 * @property {number} kills
 * @property {number} deaths
 * @property {number} assists
 * @property {number} dpm
 * @property {number} primary_accuracy
 * @property {number} damage_dealt
 * @property {number} damage_received
 * @property {number} heals_received
 * @property {number} captures
 * @property {number} headshots
 * @property {number} backstabs
 * @property {number} airshots
 * @property {number} ubers
 * @property {number} drops
 * @property {number} healing_done
 */

/**
 * @typedef {object} PlayerStat
 * @property {string} steam_id
 * @property {string} team
 * @property {string|null} display_name
 * @property {string[]} classes_played
 * @property {string} primary_class
 * @property {number} playtime_seconds
 * @property {number} kills
 * @property {number} deaths
 * @property {number} assists
 * @property {number} damage_per_minute
 * @property {number} healing_done
 * @property {number} damage_received
 * @property {number} heals_received
 * @property {number} ubers
 * @property {number} drops
 * @property {ClassStat[]} class_stats
 */

/**
 * Canonical match DTO shared by all LogSourceAdapter implementations.
 * Shape aligns with CQRS MatchParsed inner payload (+ source provenance).
 *
 * @typedef {object} NormalizedTF2Match
 * @property {string} match_id
 * @property {string} map_name
 * @property {number} blu_score
 * @property {number} red_score
 * @property {number} duration_seconds
 * @property {PlayerStat[]} players
 * @property {string} date_played
 * @property {object} tournament
 * @property {string} tournament.tournament_id
 * @property {string} tournament.name
 * @property {string} tournament.slug
 * @property {string|null} tournament.start_date
 * @property {string|null} tournament.end_date
 * @property {number|null} source_log_id
 * @property {string|null} actor_id
 * @property {object} source
 * @property {string} source.sourceSite
 * @property {string} source.sourceMatchId
 * @property {string|null} source.correlationId
 * @property {string} source.ingestedAt
 */

/**
 * @param {Partial<ClassStat>} partial
 * @returns {ClassStat}
 */
function createClassStat(partial = {}) {
  const className = normalizeClassName(partial.class_name);
  return {
    class_name: className,
    class_id: partial.class_id ?? classIdFromName(className),
    playtime_seconds: intOr(partial.playtime_seconds),
    kills: intOr(partial.kills),
    deaths: intOr(partial.deaths),
    assists: intOr(partial.assists),
    dpm: floatOr(partial.dpm),
    primary_accuracy: floatOr(partial.primary_accuracy),
    damage_dealt: intOr(partial.damage_dealt),
    damage_received: intOr(partial.damage_received),
    heals_received: intOr(partial.heals_received),
    captures: intOr(partial.captures),
    headshots: intOr(partial.headshots),
    backstabs: intOr(partial.backstabs),
    airshots: intOr(partial.airshots),
    ubers: intOr(partial.ubers),
    drops: intOr(partial.drops),
    healing_done: intOr(partial.healing_done),
  };
}

/**
 * @param {Partial<PlayerStat>} partial
 * @returns {PlayerStat}
 */
function createPlayerStat(partial = {}) {
  const classStats = Array.isArray(partial.class_stats)
    ? partial.class_stats.map((row) => createClassStat(row))
    : [];
  const classesPlayed =
    Array.isArray(partial.classes_played) && partial.classes_played.length
      ? partial.classes_played.map(normalizeClassName)
      : classStats.map((row) => row.class_name);
  let primary = normalizeClassName(partial.primary_class || 'unknown');
  if (primary === 'unknown' && classStats.length) {
    primary = classStats.reduce((best, row) =>
      row.playtime_seconds > best.playtime_seconds ? row : best
    ).class_name;
  }
  return {
    steam_id: canonicalSteamId(partial.steam_id || ''),
    team: normalizeTeam(partial.team),
    display_name: partial.display_name ? String(partial.display_name).trim() || null : null,
    classes_played: classesPlayed,
    primary_class: primary,
    playtime_seconds: intOr(partial.playtime_seconds),
    kills: intOr(partial.kills),
    deaths: intOr(partial.deaths),
    assists: intOr(partial.assists),
    damage_per_minute: floatOr(partial.damage_per_minute),
    healing_done: intOr(partial.healing_done),
    damage_received: intOr(partial.damage_received),
    heals_received: intOr(partial.heals_received),
    ubers: intOr(partial.ubers),
    drops: intOr(partial.drops),
    class_stats: classStats,
  };
}

/**
 * @param {Partial<NormalizedTF2Match>} partial
 * @returns {NormalizedTF2Match}
 */
function createNormalizedMatch(partial = {}) {
  const ingestedAt = partial.source?.ingestedAt || new Date().toISOString();
  const tournamentName = partial.tournament?.name || 'Default Tournament';
  const tournamentSlug = slugify(partial.tournament?.slug || tournamentName);
  return {
    match_id: partial.match_id || uuidv4(),
    map_name: String(partial.map_name || 'unknown_map'),
    blu_score: intOr(partial.blu_score),
    red_score: intOr(partial.red_score),
    duration_seconds: intOr(partial.duration_seconds, 1800),
    players: Array.isArray(partial.players)
      ? partial.players.map((p) => createPlayerStat(p))
      : [],
    date_played: partial.date_played || ingestedAt,
    tournament: {
      tournament_id:
        partial.tournament?.tournament_id || stableTournamentIdFromSlug(tournamentSlug),
      name: tournamentName,
      slug: tournamentSlug,
      start_date: partial.tournament?.start_date ?? null,
      end_date: partial.tournament?.end_date ?? null,
    },
    source_log_id:
      partial.source_log_id === undefined || partial.source_log_id === null
        ? null
        : intOr(partial.source_log_id),
    actor_id: partial.actor_id ?? null,
    source: {
      sourceSite: String(partial.source?.sourceSite || 'unknown'),
      sourceMatchId: String(partial.source?.sourceMatchId || ''),
      correlationId: partial.source?.correlationId ?? null,
      ingestedAt,
    },
  };
}

/**
 * Domain event emitted by this consumer after a log is fully normalized.
 * Wire format also publishes CQRS `MatchParsed` for the query pipeline.
 *
 * @param {NormalizedTF2Match} match
 * @param {{ correlationId?: string|null, actorId?: string|null }} [meta]
 */
function createMatchLogIngestedEvent(match, meta = {}) {
  const correlationId = meta.correlationId || match.source.correlationId || uuidv4();
  const occurredAt = new Date().toISOString();
  return {
    event_id: uuidv4(),
    event_type: 'MatchLogIngested',
    occurred_at: occurredAt,
    actor_id: meta.actorId ?? match.actor_id,
    payload: {
      sourceSite: match.source.sourceSite,
      sourceMatchId: match.source.sourceMatchId,
      ingestedAt: match.source.ingestedAt,
      correlationId,
      match,
    },
  };
}

/**
 * Strip consumer-only provenance and produce the CQRS MatchParsed payload.
 * @param {NormalizedTF2Match} match
 */
function toMatchParsedPayload(match) {
  const payload = {
    match_id: match.match_id,
    map_name: match.map_name,
    blu_score: match.blu_score,
    red_score: match.red_score,
    duration_seconds: match.duration_seconds,
    players: match.players,
    date_played: match.date_played,
    tournament: match.tournament,
    actor_id: match.actor_id,
  };
  if (match.source_log_id != null) {
    payload.source_log_id = match.source_log_id;
  }
  return payload;
}

/**
 * Idempotency key keyed by logs.tf ID — the canonical match identity in CQRS
 * (match_id = uuid5(NAMESPACE_URL, `logs.tf:{logId}`)).
 * @param {string|number} logstfId
 */
function idempotencyKey(_sourceSite, _sourceMatchId, logstfId) {
  return `logs.tf:${logstfId}`;
}

module.exports = {
  NAMESPACE_URL,
  UUID_NIL,
  CLASS_MAP,
  normalizeClassName,
  classIdFromName,
  normalizeTeam,
  intOr,
  floatOr,
  slugify,
  stableMatchIdFromLogsTf,
  stableTournamentIdFromSlug,
  canonicalSteamId,
  createClassStat,
  createPlayerStat,
  createNormalizedMatch,
  createMatchLogIngestedEvent,
  toMatchParsedPayload,
  idempotencyKey,
};
