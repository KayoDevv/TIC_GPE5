<script setup lang="ts">
import { ANALYSIS_TABS, type AnalysisTabKey } from '../analysisTabs';

defineProps<{ activeTab: AnalysisTabKey }>();
defineEmits<{ 'update:activeTab': [tab: AnalysisTabKey] }>();
</script>

<template>
  <nav class="tabs">
    <button
      v-for="tab in ANALYSIS_TABS"
      :key="tab.key"
      type="button"
      class="tab"
      :class="{ active: tab.key === activeTab }"
      :aria-current="tab.key === activeTab"
      @click="$emit('update:activeTab', tab.key)"
    >
      {{ tab.label }}
    </button>
  </nav>
</template>

<style scoped>
.tabs {
  display: flex;
  padding: 0 var(--space-xl);
  border-bottom: 1px solid var(--border-soft);
}

.tab {
  padding: 11px var(--space-lg);
  font-size: var(--text-size-small);
  font-weight: 500;
  color: var(--text-muted);
  background: none;
  border: none;
  border-bottom: 1.5px solid transparent;
  margin-bottom: -1px;
  cursor: pointer;
  transition: color var(--motion-fast);
}

.tab:hover {
  color: var(--text-secondary);
}

.tab.active {
  color: var(--text-primary);
  border-bottom-color: rgba(255, 255, 255, 0.7);
}
</style>
