<script setup lang="ts">
import { computed, ref } from 'vue';
import PopupButton from './PopupButton.vue';
import { formatFileSize } from '../fileSize';
import {
  hasVerdictDetails,
  type VerdictDetails,
  type VerdictPresentation
} from '../verdictPresentation';

const props = defineProps<{
  presentation: VerdictPresentation;
  file: File | null;
  details: VerdictDetails;
  jobId: string | null;
}>();

defineEmits<{ restart: [] }>();

const detailsOpen = ref(false);
const canShowDetails = computed(() => hasVerdictDetails(props.details));
</script>

<template>
  <div class="verdict" :class="props.presentation.tone">
    <span class="overline">The verdict</span>
    <p class="label">{{ props.presentation.label }}</p>
    <p v-if="props.file" class="file">
      {{ props.file.name }} · {{ formatFileSize(props.file.size) }}
    </p>
    <p class="explanation">{{ props.presentation.detail }}</p>

    <button
      v-if="canShowDetails"
      type="button"
      class="details-toggle"
      :aria-expanded="detailsOpen"
      @click="detailsOpen = !detailsOpen"
    >
      {{ detailsOpen ? 'Hide details' : 'Show details' }}
    </button>

    <div v-if="detailsOpen" class="details">
      <ul v-if="props.details.tiles.length" class="tiles">
        <li v-for="tile in props.details.tiles" :key="tile.label" class="tile">
          <span class="tile-label">{{ tile.label }}</span>
          <span class="tile-value">{{ tile.value }}</span>
        </li>
      </ul>

      <ul v-if="props.details.indicators.length" class="indicators">
        <li v-for="(indicator, index) in props.details.indicators" :key="index" class="indicator">
          <span class="indicator-code">{{ indicator.code }}</span>
          <span class="indicator-text">{{ indicator.text }}</span>
        </li>
      </ul>

      <ul v-if="props.details.badges.length" class="badges">
        <li
          v-for="badge in props.details.badges"
          :key="badge.label"
          class="badge"
          :class="badge.tone"
        >
          {{ badge.label }}
        </li>
      </ul>
    </div>

    <p v-if="props.jobId" class="job">Job {{ props.jobId }}</p>

    <PopupButton @click="$emit('restart')">Analyse another file</PopupButton>
  </div>
</template>

<style scoped>
.verdict {
  display: flex;
  flex-direction: column;
}

.verdict.allowed {
  --tone: var(--allowed);
  animation: settle 380ms ease-out;
}

.verdict.warning {
  --tone: var(--warning);
  animation: waver 450ms ease-out;
}

.verdict.blocked {
  --tone: var(--blocked);
  animation: rupture 300ms ease-in;
}

.overline {
  margin-bottom: var(--space-sm);
  font-family: var(--font-display);
  font-size: var(--text-size-overline);
  font-weight: 500;
  letter-spacing: var(--tracking-overline);
  text-transform: uppercase;
  color: var(--faint);
}

.label {
  margin-bottom: 2px;
  font-family: var(--font-display);
  font-size: var(--text-size-verdict);
  font-weight: 600;
  line-height: 1.15;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--tone);
}

.file {
  margin-bottom: 12px;
  overflow-wrap: anywhere;
  font-size: var(--text-size-small);
  font-style: italic;
  line-height: 1.6;
  color: var(--muted);
}

.explanation {
  margin-bottom: var(--space-lg);
  padding: 2px 0 2px 12px;
  border-left: 2px solid var(--or);
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--text-2);
}

.details-toggle {
  width: 100%;
  padding: 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-family: var(--font-display);
  font-size: 9.5px;
  font-weight: 500;
  letter-spacing: var(--tracking-label);
  text-transform: uppercase;
  color: var(--muted);
  cursor: pointer;
  transition:
    border-color var(--motion-fast),
    color var(--motion-fast);
}

.details-toggle:hover,
.details-toggle[aria-expanded='true'] {
  border-color: var(--or);
  color: var(--accent-text);
}

.details {
  margin-top: 12px;
}

.details ul {
  list-style: none;
}

.tiles {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: var(--space-md);
}

.tile {
  padding: 9px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card-2);
}

.tile-label {
  display: block;
  margin-bottom: var(--space-xs);
  font-family: var(--font-display);
  font-size: var(--text-size-micro);
  font-weight: 500;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--faint);
}

.tile-value {
  display: block;
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--text);
}

.indicators {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: var(--space-md);
}

.indicator {
  display: flex;
  align-items: baseline;
  gap: 9px;
  padding: 7px var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card-2);
}

.indicator-code {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--accent-text);
}

.indicator-text {
  overflow-wrap: anywhere;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-2);
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  margin-bottom: var(--space-xs);
}

.badge {
  padding: var(--space-xs) 9px;
  border: 1px solid var(--border-2);
  border-radius: 2px;
  font-family: var(--font-mono);
  font-size: 8.5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}

.badge.blocked {
  border-color: var(--blocked);
  background: var(--blocked-bg);
  color: var(--blocked);
}

.badge.warning {
  border-color: var(--warning);
  background: var(--warning-bg);
  color: var(--warning);
}

.job {
  margin-top: 12px;
  overflow-wrap: anywhere;
  font-family: var(--font-mono);
  font-size: var(--text-size-micro);
  letter-spacing: 0.04em;
  color: var(--faint);
}

.popup-button {
  margin-top: 12px;
}

/* Motion grammar for verdict entries: allowed settles, warning wavers, blocked ruptures. */
@keyframes settle {
  from {
    opacity: 0;
    transform: scale(0.965);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes waver {
  0% {
    opacity: 0;
    transform: translateX(-5px);
  }
  40% {
    opacity: 1;
    transform: translateX(3px);
  }
  70% {
    transform: translateX(-2px);
  }
  100% {
    transform: translateX(0);
  }
}

@keyframes rupture {
  0% {
    opacity: 0;
    transform: translateY(-7px);
  }
  78% {
    opacity: 1;
    transform: translateY(1.5px);
  }
  100% {
    transform: translateY(0);
  }
}
</style>
