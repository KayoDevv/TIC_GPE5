<script setup lang="ts">
import GlassButton from './GlassButton.vue';
import SelectedFileCard from './SelectedFileCard.vue';
import VerdictToneIcon from '../icons/VerdictToneIcon.vue';
import type { SummaryMetric, VerdictPresentation } from '../verdictPresentation';

const props = defineProps<{
  presentation: VerdictPresentation;
  file: File | null;
  metrics: SummaryMetric[];
  jobId: string | null;
}>();

defineEmits<{ restart: [] }>();
</script>

<template>
  <div class="verdict-view">
    <div class="verdict" :class="props.presentation.tone">
      <span class="glow" />
      <span class="dot"><VerdictToneIcon class="dot-icon" :tone="props.presentation.tone" /></span>
      <p class="label">{{ props.presentation.label }}</p>
      <p class="detail">{{ props.presentation.detail }}</p>
    </div>

    <SelectedFileCard v-if="props.file" class="file" :file="props.file" />

    <ul v-if="props.metrics.length" class="metrics">
      <li v-for="metric in props.metrics" :key="metric.label" class="metric">
        <span class="metric-label">{{ metric.label }}</span>
        <span class="metric-value">{{ metric.value }}</span>
      </li>
    </ul>

    <p v-if="props.jobId" class="job">Job {{ props.jobId }}</p>

    <GlassButton @click="$emit('restart')">Analyse another file</GlassButton>
  </div>
</template>

<style scoped>
.verdict {
  --tone: var(--text-primary);
  --tone-glow: rgba(255, 255, 255, 0.2);

  border-radius: var(--radius-panel);
  padding: var(--space-2xl) var(--space-xl);
  text-align: center;
  margin-bottom: var(--space-lg);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-top: 1px solid var(--border-strong);
  background: rgba(255, 255, 255, 0.05);
  box-shadow: var(--shadow-inset-highlight);
  position: relative;
  overflow: hidden;
}

.verdict.allowed {
  --tone: var(--tone-allowed);
  --tone-glow: var(--tone-allowed-glow);
}

.verdict.warning {
  --tone: var(--tone-warning);
  --tone-glow: var(--tone-warning-glow);
}

.verdict.blocked {
  --tone: var(--tone-blocked);
  --tone-glow: var(--tone-blocked-glow);
}

.glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.6;
  background: radial-gradient(ellipse 200px 120px at 50% 50%, var(--tone-glow), transparent);
}

.dot {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  margin: 0 auto var(--space-md);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  background: radial-gradient(circle at 35% 30%, var(--tone), var(--tone-glow) 60%, transparent);
  box-shadow: 0 0 30px var(--tone-glow);
}

.dot-icon {
  width: 20px;
  height: 20px;
}

.label {
  position: relative;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: var(--space-xs);
  color: var(--tone);
  text-shadow: 0 0 20px var(--tone-glow);
}

.detail {
  position: relative;
  font-size: var(--text-size-small);
  color: rgba(255, 255, 255, 0.45);
}

.file {
  margin-bottom: var(--space-md);
}

.metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
  list-style: none;
}

.metric {
  padding: var(--space-md) 13px;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-top: 1px solid var(--border-regular);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.05) inset;
}

.metric-label {
  display: block;
  font-size: var(--text-size-micro);
  color: rgba(255, 255, 255, 0.28);
  font-family: var(--font-mono);
  letter-spacing: var(--tracking-label);
  text-transform: uppercase;
  margin-bottom: 5px;
}

.metric-value {
  display: block;
  font-size: 16px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.85);
}

.job {
  font-family: var(--font-mono);
  font-size: var(--text-size-micro);
  color: var(--text-faint);
  margin-bottom: var(--space-md);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

</style>
