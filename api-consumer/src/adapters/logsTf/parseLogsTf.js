'use strict';

const {
  createClassStat,
  createPlayerStat,
  createNormalizedMatch,
  normalizeClassName,
  classIdFromName,
  normalizeTeam,
  intOr,
  floatOr,
  stableMatchIdFromLogsTf,
  stableTournamentIdFromSlug,
  slugify,
} = require('../../models/normalized');

function primaryAccuracy(classRow) {
  const weapon = classRow?.weapon;
  if (!weapon || typeof weapon !== 'object') return 0;
  const primary = weapon.primary;
  if (primary && typeof primary === 'object') {
    return floatOr(primary.acc);
  }
  return 0;
}

function datePlayedFromLogsTf(data) {
  const rawDate = data?.info?.date;
  if (rawDate == null) return new Date().toISOString();
  const ts = Number(rawDate);
  if (!Number.isFinite(ts)) return new Date().toISOString();
  // logs.tf dates are unix seconds
  return new Date(ts * 1000).toISOString();
}

/**
 * Map a logs.tf API document into our canonical NormalizedTF2Match.
 * Mirrors server/cqrs/command_service/app/logs_tf_parser.py.
 *
 * @param {object} data
 * @param {number} logId
 * @param {object} [context]
 * @returns {import('../../models/normalized').NormalizedTF2Match}
 */
function parseLogsTf(data, logId, context = {}) {
  const info = data?.info || {};
  const teams = data?.teams || {};
  const mapName = context.mapName || info.map || 'unknown_map';
  const bluScore = intOr(teams.Blue?.score);
  const redScore = intOr(teams.Red?.score);
  const durationSeconds = intOr(data?.length, 1800);
  const players = extractPlayers(data);

  const tournamentName = context.tournament?.name || 'Default Tournament';
  const tournamentSlug = slugify(context.tournament?.slug || tournamentName);
  const ingestedAt = context.ingestedAt || new Date().toISOString();

  return createNormalizedMatch({
    match_id: stableMatchIdFromLogsTf(logId),
    map_name: mapName,
    blu_score: bluScore,
    red_score: redScore,
    duration_seconds: durationSeconds,
    players,
    date_played: datePlayedFromLogsTf(data),
    tournament: {
      tournament_id: stableTournamentIdFromSlug(tournamentSlug),
      name: tournamentName,
      slug: tournamentSlug,
      start_date: context.tournament?.start_date ?? null,
      end_date: context.tournament?.end_date ?? null,
    },
    source_log_id: logId,
    actor_id: context.actorId ?? null,
    source: {
      sourceSite: context.sourceSite || 'logs.tf',
      sourceMatchId: String(context.sourceMatchId ?? logId),
      correlationId: context.correlationId ?? null,
      ingestedAt,
    },
  });
}

function extractPlayers(data) {
  const snapshots = [];
  const names = data?.names || {};
  for (const [steamId, player] of Object.entries(data?.players || {})) {
    const classRows = player?.class_stats || [];
    const damageReceived = intOr(player?.dt);
    const healsReceived = intOr(player?.hr);
    const healingDone = intOr(player?.heal);
    const ubers = intOr(player?.ubers);
    const drops = intOr(player?.drops);
    const rawName = names[steamId];
    const displayName = rawName ? String(rawName).trim() || null : null;

    const classStats = [];
    for (const row of classRows) {
      const className = normalizeClassName(String(row?.type || 'unknown'));
      const playtime = intOr(row?.total_time);
      const damageDealt = intOr(row?.dmg);
      const dpm = playtime > 0 ? damageDealt / (playtime / 60) : 0;
      const isMedic = className === 'medic';
      classStats.push(
        createClassStat({
          class_name: className,
          class_id: classIdFromName(className),
          playtime_seconds: playtime,
          kills: intOr(row?.kills),
          deaths: intOr(row?.deaths),
          assists: intOr(row?.assists),
          dpm: Math.round(dpm * 100) / 100,
          primary_accuracy: primaryAccuracy(row),
          damage_dealt: damageDealt,
          damage_received: damageReceived,
          heals_received: healsReceived,
          captures: intOr(row?.cpc),
          headshots: intOr(row?.headshots),
          backstabs: intOr(row?.backstabs),
          airshots: intOr(row?.as),
          ubers: isMedic ? ubers : 0,
          drops: isMedic ? drops : 0,
          healing_done: isMedic ? healingDone : 0,
        })
      );
    }

    const classesPlayed = classStats.map((item) => item.class_name);
    const totalTime = classStats.reduce((sum, item) => sum + item.playtime_seconds, 0);
    const totalDamage = classStats.reduce((sum, item) => sum + item.damage_dealt, 0);
    const dpm = totalTime > 0 ? totalDamage / (totalTime / 60) : 0;
    let primary = 'unknown';
    if (classStats.length) {
      primary = classStats.reduce((best, row) =>
        row.playtime_seconds > best.playtime_seconds ? row : best
      ).class_name;
    } else if (classesPlayed.length) {
      primary = classesPlayed[0];
    }

    snapshots.push(
      createPlayerStat({
        steam_id: steamId,
        team: normalizeTeam(player?.team),
        display_name: displayName,
        classes_played: classesPlayed,
        primary_class: primary,
        playtime_seconds: totalTime,
        kills: intOr(player?.kills),
        deaths: intOr(player?.deaths),
        assists: intOr(player?.assists),
        damage_per_minute: Math.round(dpm * 100) / 100,
        healing_done: healingDone,
        damage_received: damageReceived,
        heals_received: healsReceived,
        ubers,
        drops,
        class_stats: classStats,
      })
    );
  }
  return snapshots;
}

module.exports = { parseLogsTf, extractPlayers, datePlayedFromLogsTf };
