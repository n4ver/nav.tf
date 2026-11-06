/**
 * Thin command-side store kept for tests / shared busy flags.
 * New UI should prefer `useLogIngestion` for submit + eventual-consistency polling.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ingestLogsTf, uploadLog } from '../api'

export const useMatchCommandStore = defineStore('matchCommand', () => {
  const uploading = ref(false)
  const parsing = ref(false)
  const ingestingLogsTf = ref(false)
  const lastMatchId = ref(null)
  const error = ref('')
  const statusMessage = ref('')

  const isBusy = computed(() => uploading.value || parsing.value || ingestingLogsTf.value)

  function resetStatus() {
    error.value = ''
    statusMessage.value = ''
  }

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
    resetStatus()
    lastMatchId.value = null
    try {
      const accepted = await uploadLog({
        log_data: logData,
        timestamp: input.timestamp || new Date().toISOString(),
      })
      lastMatchId.value = accepted.match_id
      statusMessage.value = 'Upload accepted'
      return { matchId: accepted.match_id, detail: null, status: accepted.status }
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    } finally {
      uploading.value = false
    }
  }

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
    resetStatus()
    lastMatchId.value = null
    try {
      const accepted = await ingestLogsTf({ logstf_id: logstfId })
      lastMatchId.value = accepted.match_id
      statusMessage.value =
        accepted.status === 'skipped'
          ? `Log ${logstfId} already ingested`
          : 'Ingest accepted'
      return { matchId: accepted.match_id, detail: null, status: accepted.status }
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    } finally {
      ingestingLogsTf.value = false
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
    resetStatus,
  }
})
