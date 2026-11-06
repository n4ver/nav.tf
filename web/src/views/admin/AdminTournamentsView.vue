<script setup>
import { onMounted, ref } from 'vue'
import Panel from '../../components/ui/Panel.vue'
import StateMessage from '../../components/ui/StateMessage.vue'
import SkeletonBlock from '../../components/ui/SkeletonBlock.vue'
import {
  createTournament,
  fetchEvents,
  fetchTournaments,
  linkTournamentToEvent,
  updateTournament,
} from '../../api'
import { pollUntil } from '../../utils/poll'


const name = ref('')
const slug = ref('')
const startDate = ref('')
const eventId = ref('')
const status = ref('')
const error = ref('')
const tournaments = ref([])
const events = ref([])
const loading = ref(false)
const editingId = ref('')
const editingName = ref('')
const editingSlug = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [tournamentRows, eventRows] = await Promise.all([fetchTournaments(), fetchEvents()])
    tournaments.value = Array.isArray(tournamentRows) ? tournamentRows : []
    events.value = Array.isArray(eventRows) ? eventRows : []
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load tournaments'
  } finally {
    loading.value = false
  }
}

function eventName(id) {
  const match = events.value.find((event) => String(event.event_id) === String(id))
  return match ? match.name : '—'
}

async function submitCreate() {
  status.value = ''
  error.value = ''
  try {
    const payload = {
      name: name.value.trim(),
      slug: slug.value.trim(),
    }
    if (startDate.value) payload.start_date = new Date(startDate.value).toISOString()
    if (eventId.value) payload.event_id = eventId.value
    const result = await createTournament(payload)
    await pollUntil(async () => {
      await load()
      return tournaments.value.some(
        (row) => String(row.tournament_id) === String(result.tournament_id),
      )
    })
    status.value = `Created tournament ${result.name}`
    name.value = ''
    slug.value = ''
    startDate.value = ''
    eventId.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Create failed'
  }
}

function beginEdit(tournament) {
  editingId.value = String(tournament.tournament_id)
  editingName.value = tournament.name
  editingSlug.value = tournament.slug
}

async function submitUpdate() {
  if (!editingId.value) return
  status.value = ''
  error.value = ''
  try {
    const result = await updateTournament(editingId.value, {
      name: editingName.value.trim(),
      slug: editingSlug.value.trim(),
    })
    await pollUntil(async () => {
      await load()
      const row = tournaments.value.find((item) => String(item.tournament_id) === editingId.value)
      return row && row.name === result.name
    })
    status.value = `Updated tournament ${result.name}`
    editingId.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Update failed'
  }
}

async function changeEvent(tournament, nextEventId) {
  status.value = ''
  error.value = ''
  try {
    await linkTournamentToEvent(tournament.tournament_id, {
      event_id: nextEventId || null,
    })
    await pollUntil(async () => {
      await load()
      const row = tournaments.value.find(
        (item) => String(item.tournament_id) === String(tournament.tournament_id),
      )
      const expected = nextEventId || null
      return String(row?.event_id || '') === String(expected || '')
    })
    status.value = nextEventId ? 'Linked tournament to event' : 'Unlinked tournament from event'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Link failed'
  }
}

onMounted(load)
</script>

<template>
  <Panel title="Tournaments">
    <form class="space-y-3" @submit.prevent="submitCreate">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label class="label-caps">
          Name
          <input v-model="name" type="text" required placeholder="Invite Bracket" class="field" />
        </label>
        <label class="label-caps">
          Slug
          <input v-model="slug" type="text" required placeholder="invite-bracket" class="field" />
        </label>
        <label class="label-caps">
          Start date
          <input v-model="startDate" type="datetime-local" class="field" />
        </label>
        <label class="label-caps">
          Event
          <select v-model="eventId" class="field">
            <option value="">Unlinked</option>
            <option v-for="event in events" :key="event.event_id" :value="String(event.event_id)">
              {{ event.name }}
            </option>
          </select>
        </label>
      </div>
      <button type="submit" class="btn-primary">Create tournament</button>
    </form>
    <StateMessage v-if="error" tone="error" class="mt-2">{{ error }}</StateMessage>
    <StateMessage v-if="status" tone="info" class="mt-2">{{ status }}</StateMessage>

    <div v-if="loading" class="mt-4" aria-busy="true" aria-label="Loading tournaments">
      <SkeletonBlock :rows="4" />
    </div>
    <div v-else-if="tournaments.length" class="mt-4 overflow-x-auto rounded-sm border border-line">
      <table class="w-full min-w-[720px] border-collapse text-sm">
        <thead class="bg-surface-900">
          <tr>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Name</th>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Slug</th>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Matches</th>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Event</th>
            <th class="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="tournament in tournaments"
            :key="tournament.tournament_id"
            class="border-t border-line even:bg-surface-900/40"
          >
            <td class="px-2.5 py-1.5 text-ink">
              <input
                v-if="editingId === String(tournament.tournament_id)"
                v-model="editingName"
                type="text"
                aria-label="Tournament name"
                class="field"
              />
              <template v-else>{{ tournament.name }}</template>
            </td>
            <td class="px-2.5 py-1.5 text-ink">
              <input
                v-if="editingId === String(tournament.tournament_id)"
                v-model="editingSlug"
                type="text"
                aria-label="Tournament slug"
                class="field"
              />
              <template v-else>{{ tournament.slug }}</template>
            </td>
            <td class="px-2.5 py-1.5 font-mono text-ink">{{ tournament.match_count }}</td>
            <td class="px-3 py-2">
              <select
                :value="String(tournament.event_id || '')"
                class="field"
                :aria-label="`Event for ${tournament.name}`"
                @change="changeEvent(tournament, $event.target.value)"
              >
                <option value="">Unlinked</option>
                <option v-for="event in events" :key="event.event_id" :value="String(event.event_id)">
                  {{ event.name }}
                </option>
              </select>
              <p class="mt-1 text-[0.7rem] text-ink-muted">{{ eventName(tournament.event_id) }}</p>
            </td>
            <td class="px-3 py-2">
              <button
                v-if="editingId !== String(tournament.tournament_id)"
                type="button"
                class="btn-ghost"
                @click="beginEdit(tournament)"
              >
                Edit
              </button>
              <button v-else type="button" class="btn-primary" @click="submitUpdate">Save</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <StateMessage v-else class="mt-3">No tournaments yet.</StateMessage>
  </Panel>
</template>
