<script setup>
import { onMounted, ref } from 'vue'
import Panel from '../../components/ui/Panel.vue'
import StateMessage from '../../components/ui/StateMessage.vue'
import SkeletonBlock from '../../components/ui/SkeletonBlock.vue'
import { createEvent, fetchEvents, updateEvent } from '../../api'
import { pollUntil } from '../../utils/poll'


const name = ref('')
const slug = ref('')
const startDate = ref('')
const endDate = ref('')
const status = ref('')
const error = ref('')
const events = ref([])
const loading = ref(false)
const editingId = ref('')
const editingName = ref('')
const editingSlug = ref('')

async function loadEvents() {
  loading.value = true
  error.value = ''
  try {
    const rows = await fetchEvents()
    events.value = Array.isArray(rows) ? rows : []
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load events'
  } finally {
    loading.value = false
  }
}

function payloadFromForm() {
  const body = {
    name: name.value.trim(),
    slug: slug.value.trim(),
  }
  if (startDate.value) body.start_date = new Date(startDate.value).toISOString()
  if (endDate.value) body.end_date = new Date(endDate.value).toISOString()
  return body
}

async function submitCreate() {
  status.value = ''
  error.value = ''
  try {
    const result = await createEvent(payloadFromForm())
    await pollUntil(async () => {
      await loadEvents()
      return events.value.some((row) => String(row.event_id) === String(result.event_id))
    })
    status.value = `Created event ${result.name}`
    name.value = ''
    slug.value = ''
    startDate.value = ''
    endDate.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Create failed'
  }
}

function beginEdit(event) {
  editingId.value = String(event.event_id)
  editingName.value = event.name
  editingSlug.value = event.slug
}

async function submitUpdate() {
  if (!editingId.value) return
  status.value = ''
  error.value = ''
  try {
    const result = await updateEvent(editingId.value, {
      name: editingName.value.trim(),
      slug: editingSlug.value.trim(),
    })
    await pollUntil(async () => {
      await loadEvents()
      const row = events.value.find((item) => String(item.event_id) === editingId.value)
      return row && row.name === result.name
    })
    status.value = `Updated event ${result.name}`
    editingId.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Update failed'
  }
}

onMounted(loadEvents)
</script>

<template>
  <Panel title="Events">
    <form class="space-y-3" @submit.prevent="submitCreate">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label class="label-caps">
          Name
          <input v-model="name" type="text" required placeholder="Matcha Mini" class="field" />
        </label>
        <label class="label-caps">
          Slug
          <input v-model="slug" type="text" required placeholder="matcha-mini" class="field" />
        </label>
        <label class="label-caps">
          Start date
          <input v-model="startDate" type="datetime-local" class="field" />
        </label>
        <label class="label-caps">
          End date
          <input v-model="endDate" type="datetime-local" class="field" />
        </label>
      </div>
      <button type="submit" class="btn-primary">Create event</button>
    </form>
    <StateMessage v-if="error" tone="error" class="mt-2">{{ error }}</StateMessage>
    <StateMessage v-if="status" tone="info" class="mt-2">{{ status }}</StateMessage>

    <div v-if="loading" class="mt-4" aria-busy="true" aria-label="Loading events">
      <SkeletonBlock :rows="4" />
    </div>
    <div v-else-if="events.length" class="mt-4 overflow-x-auto rounded-sm border border-line">
      <table class="w-full min-w-[640px] border-collapse text-sm">
        <thead class="bg-surface-900">
          <tr>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Name</th>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Slug</th>
            <th class="px-2.5 py-1.5 text-left text-[0.7rem] font-bold uppercase tracking-wide text-ink-muted">Tournaments</th>
            <th class="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="event in events"
            :key="event.event_id"
            class="border-t border-line even:bg-surface-900/40"
          >
            <td class="px-2.5 py-1.5 text-ink">
              <input
                v-if="editingId === String(event.event_id)"
                v-model="editingName"
                type="text"
                aria-label="Event name"
                class="field"
              />
              <template v-else>{{ event.name }}</template>
            </td>
            <td class="px-2.5 py-1.5 text-ink">
              <input
                v-if="editingId === String(event.event_id)"
                v-model="editingSlug"
                type="text"
                aria-label="Event slug"
                class="field"
              />
              <template v-else>{{ event.slug }}</template>
            </td>
            <td class="px-2.5 py-1.5 font-mono text-ink">{{ event.tournament_count || 0 }}</td>
            <td class="px-3 py-2">
              <button
                v-if="editingId !== String(event.event_id)"
                type="button"
                class="btn-ghost"
                @click="beginEdit(event)"
              >
                Edit
              </button>
              <button v-else type="button" class="btn-primary" @click="submitUpdate">Save</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <StateMessage v-else class="mt-3">No events yet.</StateMessage>
  </Panel>
</template>
