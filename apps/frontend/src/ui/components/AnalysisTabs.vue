<script setup lang="ts">
import { ANALYSIS_TABS, type AnalysisTabKey } from '../analysisTabs';

defineProps<{ activeTab: AnalysisTabKey }>();
defineEmits<{ 'update:activeTab': [tab: AnalysisTabKey] }>();
</script>

<template>
  <nav class="tabs" role="tablist">
    <button
      v-for="tab in ANALYSIS_TABS"
      :key="tab.key"
      type="button"
      role="tab"
      class="tab"
      :class="{ active: tab.key === activeTab }"
      :aria-selected="tab.key === activeTab"
      @click="$emit('update:activeTab', tab.key)"
    >
      {{ tab.label }}
    </button>
  </nav>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: var(--space-sm);
  margin: var(--space-lg) var(--space-xl);
  border-bottom: 1px solid var(--border);
}

.tab {
  flex: 1;
  margin-bottom: -1px;
  padding: 8px var(--space-xs) 9px;
  border-bottom: 1.5px solid transparent;
  font-family: var(--font-display);
  font-size: var(--text-size-label);
  font-weight: 500;
  letter-spacing: var(--tracking-label);
  text-transform: uppercase;
  color: var(--muted);
  cursor: pointer;
  transition:
    color var(--motion-fast),
    border-color var(--motion-fast);
}

.tab:hover {
  color: var(--text);
}

.tab.active {
  color: var(--accent-text);
  border-bottom-color: var(--or);
}
</style>
