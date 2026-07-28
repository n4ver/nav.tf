'use strict';

function env(name, fallback) {
  const value = process.env[name];
  return value === undefined || value === '' ? fallback : value;
}

function envBool(name, fallback) {
  const value = process.env[name];
  if (value === undefined || value === '') return fallback;
  return ['1', 'true', 'yes', 'on'].includes(String(value).toLowerCase());
}

function envInt(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === '') return fallback;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : fallback;
}

const config = {
  port: envInt('PORT', 8010),
  logLevel: env('LOG_LEVEL', 'info'),
  rabbitmqUrl: env('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/'),
  exchangeName: env('CQRS_EXCHANGE_NAME', 'tf2-events'),
  dlxName: env('CQRS_DLX_NAME', 'tf2-events.dlx'),
  routingPrefix: env('CQRS_ROUTING_PREFIX', 'events'),
  matchaBaseUrl: env('MATCHA_BASE_URL', 'https://matcha.tf').replace(/\/$/, ''),
  logsTfBaseUrl: env('LOGS_TF_BASE_URL', 'https://logs.tf/api/v1/log').replace(/\/$/, ''),
  matchaLeagueId: envInt('MATCHA_LEAGUE_ID', 1),
  matchaDivisionId: envInt('MATCHA_DIVISION_ID', 1),
  matchaTournamentName: env('MATCHA_TOURNAMENT_NAME', 'Matcha.tf Minicup Invite'),
  matchaTournamentSlug: env('MATCHA_TOURNAMENT_SLUG', 'matcha-tf-minicup-invite'),
  pollCron: env('POLL_CRON', '*/5 * * * *'),
  pollEnabled: envBool('POLL_ENABLED', true),
  webhookEnabled: envBool('WEBHOOK_ENABLED', true),
  httpTimeoutMs: envInt('HTTP_TIMEOUT_MS', 15000),
  httpMaxRetries: envInt('HTTP_MAX_RETRIES', 4),
  httpMinDelayMs: envInt('HTTP_MIN_DELAY_MS', 250),
  circuitErrorThreshold: envInt('CIRCUIT_ERROR_THRESHOLD', 50),
  circuitResetMs: envInt('CIRCUIT_RESET_MS', 30000),
  actorId: env('ACTOR_ID', 'api-consumer'),
  webhookApiKey: env('WEBHOOK_API_KEY', ''),
};

module.exports = { config };
