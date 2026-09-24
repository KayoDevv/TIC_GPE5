<script setup lang="ts">
import type { HistoryEntry } from '../useAnalysisSession';

defineProps<{ entries: HistoryEntry[] }>();
</script>

<template>
  <ul v-if="entries.length" class="history">
    <li v-for="entry in entries" :key="`${entry.time}-${entry.name}`" class="row">
      <span class="dot" :class="entry.decision" :title="entry.decision" />
      <span class="name">{{ entry.name }}</span>
      <span v-if="entry.score !== null" class="score">{{ entry.score }}/100</span>
    </li>
  </ul>
  <p v-else class="empty">no analysis yet.</p>
</template>

<style scoped>
.history {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-height: 110px;
  list-style: none;
}

.row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card-2);
  transition: border-color var(--motion-fast);
}

.row:hover {
  border-color: var(--border-2);
}

.dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
}

.dot.allowed {
  background: var(--allowed);
}

.dot.warning {
  background: var(--warning);
}

.dot.blocked {
  background: var(--blocked);
}

.name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11.5px;
  color: var(--text-2);
}

.score {
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--faint);
}

.empty {
  min-height: 110px;
  padding-top: 38px;
  font-size: 12.5px;
  font-style: italic;
  line-height: 1.6;
  text-align: center;
  color: var(--muted);
}
</style>
