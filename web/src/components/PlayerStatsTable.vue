<script setup>
import { formatRating, ratingTone } from '../utils/rating'
import { formatPlayerLabel } from '../utils/steam'

defineProps({
  stats: {
    type: Object,
    required: true,
  },
  formatNumber: {
    type: Function,
    required: true,
  },
})
</script>

<template>
  <div class="player-stats-table">
    <h2>
      <strong>{{ formatPlayerLabel(stats) }}</strong>
    </h2>
    <p v-if="stats.display_name" class="status-msg mono">{{ stats.steam_id }}</p>

    <ul class="stat-list mt-3">
      <li><strong>Matches:</strong> {{ stats.matches_played }}</li>
      <li><strong>Total Kills:</strong> {{ stats.total_kills }}</li>
      <li><strong>Total Deaths:</strong> {{ stats.total_deaths }}</li>
      <li><strong>Total Assists:</strong> {{ stats.total_assists }}</li>
      <li><strong>Avg DPM:</strong> {{ formatNumber(stats.average_damage_per_minute, 1) }}</li>
      <li><strong>Healing Done:</strong> {{ stats.total_healing_done }}</li>
      <li>
        <strong>Avg Rating:</strong>
        <span class="rating-chip" :class="`tone-${ratingTone(stats.average_rating)}`">
          {{ formatRating(stats.average_rating) }}
        </span>
      </li>
    </ul>

    <div class="mt-4" v-if="stats.class_breakdown?.length">
      <h3>Class breakdown</h3>
      <table>
        <thead>
          <tr>
            <th>Class</th>
            <th>Matches</th>
            <th>K/D/A</th>
            <th>Avg DPM</th>
            <th>Healing</th>
            <th>Rating</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in stats.class_breakdown" :key="row.class_name">
            <td>{{ row.class_name }}</td>
            <td>{{ row.matches_played }}</td>
            <td>{{ row.total_kills }}/{{ row.total_deaths }}/{{ row.total_assists }}</td>
            <td>{{ formatNumber(row.average_damage_per_minute, 1) }}</td>
            <td>{{ row.total_healing_done }}</td>
            <td>
              <span class="rating-chip" :class="`tone-${ratingTone(row.average_rating)}`">
                {{ formatRating(row.average_rating) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
