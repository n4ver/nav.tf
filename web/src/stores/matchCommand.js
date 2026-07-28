import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchMatchDetail, ingestLogsTf, uploadLog } from '../api'

const DEFAULT_POLL_INTERVAL_MS = 750
const DEFAULT_POLL_TIMEOUT_MS = 30_000

/**
 * Map Axios-style error messages into admin-facing copy.
 * @param {unknown} err
 * @param {string} fallback
 */
function formatCommandError(err, fallback = 'Request failed') {
  const message = err instanceof Error ? err.message : String(err || fallback)
  if (/^401\b/.test(message)) {
    return '401 Unauthorized — sign in again as an admin'
  }
  if (/^403\b/.test(message)) {
    return '403 Forbidden — admin role required'
  }
  if (/^404\b/.test(message)) {
    return '404 Not Found — logs.tf ID is invalid or missing'
  }
  return message || fallback
}

/**
 * Command-side store: log upload mutation + MatchParsed readiness polling.
 */
export const useMatchCommandStore = defineStore('matchCommand', () => {
  const uploading = ref(false)
  const parsing = ref(false)
  const ingestingLogsTf = ref(false)
  const lastMatchId = ref(null)
  const error = ref('')
  const statusMessage = ref('')

  let pollTimer = null
  let pollDeadline = 0

  const isBusy = computed(() => uploading.value || parsing.value || ingestingLogsTf.value)

  function clearPoll() {
    if (pollTimer != null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  function resetStatus() {
    error.value = ''
    statusMessage.value = ''
  }

  /**
   * Poll the Query service until the match projection exists with scored ratings.
   * @returns {Promise<object>} match detail payload
   */
  function waitForMatchParsed(matchId, {
    intervalMs = DEFAULT_POLL_INTERVAL_MS,
    timeoutMs = DEFAULT_POLL_TIMEOUT_MS,
  } = {}) {
    clearPoll()
    parsing.value = true
    statusMessage.value = 'Waiting for ratings…'
    pollDeadline = Date.now() + timeoutMs

    return new Promise((resolve, reject) => {
      const tick = async () => {
        try {
          const detail = await fetchMatchDetail(matchId)
          const ratingsReady = detail?.match_summary?.ratings_ready === true
          if (!ratingsReady) {
            if (Date.now() >= pollDeadline) {
              parsing.value = false
              clearPoll()
              reject(new Error('Timed out waiting for rating projection'))
              return
            }
            pollTimer = setTimeout(tick, intervalMs)
            return
          }
          parsing.value = false
          statusMessage.value = 'Match ready'
          clearPoll()
          resolve(detail)
        } catch (err) {
          const isNotFound = err instanceof Error && /^404\b/.test(err.message)
          if (!isNotFound) {
            parsing.value = false
            clearPoll()
            reject(err)
            return
          }
          if (Date.now() >= pollDeadline) {
            parsing.value = false
            clearPoll()
            reject(new Error('Timed out waiting for MatchParsed projection'))
            return
          }
          pollTimer = setTimeout(tick, intervalMs)
        }
      }

      tick()
    })
  }

  /**
   * POST RawLogUpload → 202 Accepted → poll Query until match is readable.
   * @param {{ log_data: string, timestamp?: string }} input
   */
  async function submitLogUpload(input) {
    if (isBusy.value) {
      return null
    }

    const logData = String(input.log_data || '').trim()
    if (!logData) {
      error.value = 'Log data cannot be empty'
      return null
    }

    uploading.value = true
    parsing.value = false
    resetStatus()
    lastMatchId.value = null

    const payload = {
      log_data: logData,
      timestamp: input.timestamp || new Date().toISOString(),
    }

    try {
      const accepted = await uploadLog(payload)
      lastMatchId.value = accepted.match_id
      statusMessage.value = 'Upload accepted — waiting for parse...'
      uploading.value = false

      const detail = await waitForMatchParsed(accepted.match_id)
      return { matchId: accepted.match_id, detail, status: accepted.status }
    } catch (err) {
      error.value = formatCommandError(err, 'Upload failed')
      statusMessage.value = ''
      return null
    } finally {
      uploading.value = false
    }
  }

  /**
   * POST IngestLogsTfCommand → 202 Accepted → poll Query until match is readable.
   * Bearer JWT is attached by the Axios interceptor.
   * @param {number} logId
   */
  async function ingestFromLogsTf(logId) {
    if (isBusy.value) {
      return null
    }

    const logstfId = Number(logId)
    if (!Number.isInteger(logstfId) || logstfId <= 0) {
      error.value = 'Enter a valid logs.tf ID'
      return null
    }

    ingestingLogsTf.value = true
    parsing.value = false
    resetStatus()
    lastMatchId.value = null

    try {
      const accepted = await ingestLogsTf({ logstf_id: logstfId })
      lastMatchId.value = accepted.match_id

      if (accepted.status === 'skipped') {
        statusMessage.value = `Log ${logstfId} already ingested`
        return { matchId: accepted.match_id, detail: null, status: 'skipped' }
      }

      statusMessage.value = 'Ingest accepted — waiting for projection...'
      ingestingLogsTf.value = false

      const detail = await waitForMatchParsed(accepted.match_id)
      return { matchId: accepted.match_id, detail, status: accepted.status }
    } catch (err) {
      error.value = formatCommandError(err, 'logs.tf ingest failed')
      statusMessage.value = ''
      return null
    } finally {
      ingestingLogsTf.value = false
    }
  }

  function cancelParsing() {
    clearPoll()
    parsing.value = false
    if (statusMessage.value === 'Parsing in progress...' || statusMessage.value === 'Waiting for ratings…') {
      statusMessage.value = 'Parsing cancelled'
    }
  }

  return {
    uploading,
    parsing,
    ingestingLogsTf,
    isBusy,
    lastMatchId,
    error,
    statusMessage,
    submitLogUpload,
    ingestFromLogsTf,
    waitForMatchParsed,
    cancelParsing,
    resetStatus,
  }
})
