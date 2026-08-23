<script setup lang="ts">
import { computed } from 'vue';
import ScanningOrb from './ScanningOrb.vue';
import { PIPELINE_LAYERS } from '../pipelineLayers';

const PERCENT_SCALE = 100;

const props = defineProps<{ fileName: string; progressRatio: number }>();

const progressPercent = computed(() => Math.round(props.progressRatio * PERCENT_SCALE));
</script>

<template>
  <div class="progress-view">
    <ScanningOrb />

    <p class="headline">Analysis in progress</p>
    <p class="file-name">{{ props.fileName }}</p>

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
      <span class="elapsed-label">Elapsed against deadline</span>
      <span class="elapsed-value">{{ progressPercent }}%</span>
    </div>

    <ul class="layers">
      <li v-for="layer in PIPELINE_LAYERS" :key="layer" class="layer">
        <span class="layer-name">{{ layer }}</span>
        <span class="layer-state">running</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.progress-view {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.headline {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--text-secondary);
  text-transform: uppercase;
  margin-bottom: var(--space-sm);
}

.file-name {
  font-family: var(--font-mono);
  font-size: var(--text-size-micro);
  color: rgba(255, 255, 255, 0.28);
  margin-bottom: var(--space-xl);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.track {
  width: 100%;
  height: 2px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
  margin-bottom: var(--space-md);
}

.fill {
  display: block;
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.5), rgba(255, 255, 255, 0.9));
  box-shadow: 0 0 8px rgba(255, 255, 255, 0.5);
  transition: width var(--motion-fast) linear;
}

.elapsed {
  display: flex;
  justify-content: space-between;
  width: 100%;
  margin-bottom: var(--space-xl);
  font-family: var(--font-mono);
  font-size: var(--text-size-label);
}

.elapsed-label {
  color: rgba(255, 255, 255, 0.28);
}

.elapsed-value {
  color: var(--text-secondary);
  font-weight: 600;
}

.layers {
  width: 100%;
  list-style: none;
}

.layer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-sm) 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  font-size: var(--text-size-small);
}

.layer-name {
  color: var(--text-secondary);
}

.layer-state {
  font-family: var(--font-mono);
  font-size: var(--text-size-micro);
  letter-spacing: 0.06em;
  color: var(--text-muted);
  animation: blink 1.4s ease-in-out infinite;
}

@keyframes blink {
  0%,
  100% {
    opacity: 0.35;
  }
  50% {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .layer-state {
    animation: none;
  }
}
</style>
