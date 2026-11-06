import { ref, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { uploadLog, ingestLogsTf, fetchMatchDetail } from '../api'

const INITIAL_INTERVAL_MS = 500
const MAX_INTERVAL_MS = 3000
const TIMEOUT_MS = 45_000

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
 * Submit a log to the Command API, then poll the Query API until the
 * MatchParsed projection (with ratings) is ready before navigating.
 */
export function useLogIngestion() {
  const router = useRouter()
  const phase = ref('idle') // idle | submitting | polling | ready | error
  const statusMessage = ref('')
  const error = ref('')
  const matchId = ref(null)
  const submitMode = ref(null) // 'upload' | 'ingest-logstf' | null

  let timer = null
  let deadline = 0
  let intervalMs = INITIAL_INTERVAL_MS
  let aborted = false

  function cleanup() {
    aborted = true
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
  }

  onUnmounted(cleanup)

  function sleep(ms) {
    return new Promise((resolve) => {
      timer = setTimeout(resolve, ms)
    })
  }

  /**
   * Poll until match_summary.ratings_ready === true (exponential backoff).
   * @param {string} id
   * @returns {Promise<object>}
   */
  async function waitForProjection(id) {
    phase.value = 'polling'
    statusMessage.value = 'Waiting for match projection…'
    deadline = Date.now() + TIMEOUT_MS
    intervalMs = INITIAL_INTERVAL_MS

    while (!aborted && Date.now() < deadline) {
      try {
        const detail = await fetchMatchDetail(id)
        if (detail?.match_summary?.ratings_ready === true) {
          phase.value = 'ready'
          statusMessage.value = 'Match ready'
          return detail
        }
      } catch (err) {
        const is404 = err instanceof Error && /^404\b/.test(err.message)
        if (!is404) {
          throw err
        }
      }
      await sleep(intervalMs)
      intervalMs = Math.min(intervalMs * 1.5, MAX_INTERVAL_MS)
    }

    throw new Error('Timed out waiting for match projection')
  }

  /**
   * @param {{
   *   mode: 'upload' | 'ingest-logstf',
   *   payload: object,
   *   onReady?: (ctx: { matchId: string, detail: object|null, status: string }) => Promise<void>|void,
   *   navigate?: boolean,
   * }} options
   */
  async function submitAndNavigate({ mode, payload, onReady, navigate = true } = {}) {
    cleanup()
    aborted = false
    error.value = ''
    statusMessage.value = ''
    matchId.value = null
    submitMode.value = mode
    phase.value = 'submitting'

    try {
      const accepted =
        mode === 'upload' ? await uploadLog(payload) : await ingestLogsTf(payload)

      matchId.value = accepted.match_id

      if (accepted.status === 'skipped') {
        phase.value = 'ready'
        statusMessage.value = 'Already ingested'
        const result = { matchId: accepted.match_id, status: 'skipped', detail: null }
        await onReady?.(result)
        if (navigate) {
          await router.push({
            name: 'match-stats',
            params: { matchId: String(accepted.match_id) },
          })
        }
        return result
      }

      statusMessage.value =
        mode === 'upload'
          ? 'Upload accepted — waiting for parse...'
          : 'Ingest accepted — waiting for projection...'

      const detail = await waitForProjection(accepted.match_id)
      const result = {
        matchId: accepted.match_id,
        status: accepted.status,
        detail,
      }
      await onReady?.(result)
      if (navigate) {
        await router.push({
          name: 'match-stats',
          params: { matchId: String(accepted.match_id) },
        })
      }
      return result
    } catch (err) {
      phase.value = 'error'
      error.value = formatCommandError(
        err,
        mode === 'upload' ? 'Upload failed' : 'logs.tf ingest failed',
      )
      statusMessage.value = ''
      return null
    }
  }

  const isBusy = computed(
    () => phase.value === 'submitting' || phase.value === 'polling',
  )
  const uploading = computed(
    () => phase.value === 'submitting' && submitMode.value === 'upload',
  )
  const ingestingLogsTf = computed(
    () => phase.value === 'submitting' && submitMode.value === 'ingest-logstf',
  )
  const parsing = computed(() => phase.value === 'polling')

  return {
    phase,
    statusMessage,
    error,
    matchId,
    lastMatchId: matchId,
    isBusy,
    uploading,
    parsing,
    ingestingLogsTf,
    submitAndNavigate,
    waitForProjection,
    cancel: cleanup,
  }
}
