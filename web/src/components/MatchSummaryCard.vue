<script setup>
defineProps({
  summary: {
    type: Object,
    required: true,
  },
  formatDuration: {
    type: Function,
    required: true,
  },
  formatDate: {
    type: Function,
    required: true,
  },
})
</script>

<template>
  <div class="match-summary-card">
    <h3>Summary</h3>
    <ul class="stat-list">
      <li><strong>Map:</strong> {{ summary.map_name }}</li>
      <li><strong>Winner:</strong> {{ summary.winning_team }}</li>
      <li><strong>Duration:</strong> {{ formatDuration(summary.duration_seconds) }}</li>
      <li><strong>Played:</strong> {{ formatDate(summary.date_played) }}</li>
    </ul>
  </div>
</template>
