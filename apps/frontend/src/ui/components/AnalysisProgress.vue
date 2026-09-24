<script setup lang="ts">
import { computed } from 'vue';
import { PIPELINE_LAYERS } from '../pipelineLayers';

const PERCENT_SCALE = 100;

const props = defineProps<{ fileName: string; progressRatio: number }>();

const progressPercent = computed(() => Math.round(props.progressRatio * PERCENT_SCALE));
</script>

<template>
  <div class="progress-view">
    <div class="panel">
      <span class="overline">Analysis in progress</span>
      <p class="message">analysing “{{ props.fileName }}”…</p>
    </div>

    <div
      class="track"
      role="progressbar"
      :aria-valuenow="progressPercent"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <span class="fill" :style="{ width: `${progressPercent}%` }" />
    </div>

    <div class="elapsed">
      <span>Elapsed against deadline</span>
      <span>{{ progressPercent }}%</span>
    </div>

    <ul class="layers">
      <li v-for="layer in PIPELINE_LAYERS" :key="layer" class="layer">
        <span class="layer-dot" />
        <span class="layer-name">{{ layer }}</span>
        <span class="layer-state">running</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-md);
  min-height: 110px;
  padding: 18px var(--space-lg);
  border: 1px dashed var(--or);
  border-radius: var(--radius);
  background: var(--or-soft);
}

.overline {
  font-family: var(--font-display);
  font-size: var(--text-size-overline);
  font-weight: 500;
  letter-spacing: var(--tracking-overline);
  text-transform: uppercase;
  color: var(--accent-text);
}

.message {
  max-width: 250px;
  overflow-wrap: anywhere;
  font-size: var(--text-size-body);
  font-style: italic;
  line-height: 1.6;
  text-align: center;
  color: var(--text-2);
}

.track {
  height: 2px;
  margin-top: var(--space-lg);
  background: var(--border);
  overflow: hidden;
}

.fill {
  display: block;
  height: 100%;
  background: var(--or);
  transition: width 250ms linear;
}

.elapsed {
  display: flex;
  justify-content: space-between;
  margin: var(--space-sm) 0 var(--space-md);
  font-family: var(--font-mono);
  font-size: var(--text-size-micro);
  letter-spacing: 0.08em;
  color: var(--faint);
}

.layers {
  display: flex;
  flex-direction: column;
  gap: 5px;
  list-style: none;
}

.layer {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card-2);
}

.layer-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--or);
  animation: pulse 1.4s ease-in-out infinite;
}

.layer-name {
  flex: 1;
  font-size: 11.5px;
  color: var(--text-2);
}

.layer-state {
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: var(--faint);
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}
</style>
