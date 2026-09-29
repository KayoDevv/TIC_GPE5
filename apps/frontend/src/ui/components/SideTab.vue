<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import CharonGlyph from '../icons/CharonGlyph.vue';
import { snapshotState } from '../charonState';
import { requestAnalysis, useSessionSnapshot, type AnalysisPhase } from '../useAnalysisSession';
import { useStoredTheme } from '../useTheme';
import { buildVerdictDetails, presentSnapshot } from '../verdictPresentation';

const PHASE_LABELS: Record<AnalysisPhase, string> = {
  idle: 'Standby',
  analyzing: 'Analysing',
  completed: 'Complete',
  failed: 'Analysis failed'
};

const IDLE_TEXT = 'No attachment analysed yet. Drop a file on this tab to analyse it.';

const snapshot = useSessionSnapshot();
const theme = useStoredTheme();
const open = ref(false);
const dragging = ref(false);

const state = computed(() => snapshotState(snapshot.value));
const presentation = computed(() => presentSnapshot(snapshot.value));
const tiles = computed(() => buildVerdictDetails(snapshot.value.verdict?.technical_summary).tiles);
const isAnalysing = computed(() => snapshot.value.phase === 'analyzing');

const label = computed(() => presentation.value?.label ?? PHASE_LABELS[snapshot.value.phase]);

const text = computed(() => {
  const { phase, file, error } = snapshot.value;
  if (presentation.value) {
    return presentation.value.detail;
  }
  if (phase === 'analyzing' && file) {
    return `analysing “${file.name}”…`;
  }

  return phase === 'failed' && error ? error : IDLE_TEXT;
});

function carriesFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files');
}

function onPageDrag(event: DragEvent): void {
  if (carriesFiles(event)) {
    dragging.value = true;
  }
}

function onPageDragLeave(event: DragEvent): void {
  // dragleave fires between every pair of elements; only leaving the window ends the drag.
  const { clientX: x, clientY: y } = event;
  if (x <= 0 || y <= 0 || x >= innerWidth || y >= innerHeight) {
    dragging.value = false;
  }
}

function endDrag(): void {
  dragging.value = false;
}

async function onDrop(event: DragEvent): Promise<void> {
  dragging.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (!file || isAnalysing.value) {
    return;
  }

  open.value = true;
  await requestAnalysis(file);
}

onMounted(() => {
  window.addEventListener('dragenter', onPageDrag, true);
  window.addEventListener('dragover', onPageDrag, true);
  window.addEventListener('dragleave', onPageDragLeave, true);
  window.addEventListener('drop', endDrag, true);
  window.addEventListener('dragend', endDrag, true);
});

onBeforeUnmount(() => {
  window.removeEventListener('dragenter', onPageDrag, true);
  window.removeEventListener('dragover', onPageDrag, true);
  window.removeEventListener('dragleave', onPageDragLeave, true);
  window.removeEventListener('drop', endDrag, true);
  window.removeEventListener('dragend', endDrag, true);
});
</script>

<template>
  <div class="side-tab" :class="[state, { 'theme-dark': theme === 'dark', dragging, open }]">
    <button
      type="button"
      class="pin"
      :aria-label="`Charon: ${label}`"
      :aria-expanded="open"
      @click="open = !open"
      @dragover.prevent
      @drop.prevent="onDrop"
    >
      <CharonGlyph class="glyph" :state="state" />
    </button>

    <section
      v-if="open"
      class="popover"
      role="dialog"
      aria-label="Charon"
      @dragover.prevent
      @drop.prevent="onDrop"
    >
      <header class="head">
        <CharonGlyph class="head-glyph" :state="state" />
        <span class="brand">Charon</span>
        <button type="button" class="close" aria-label="Close" @click="open = false">×</button>
      </header>
      <p class="label">{{ label }}</p>
      <p class="text">{{ text }}</p>
      <ul v-if="presentation && tiles.length" class="tiles">
        <li v-for="tile in tiles" :key="tile.label" class="tile">
          <span class="tile-label">{{ tile.label }}</span>
          <span class="tile-value">{{ tile.value }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.side-tab {
  --state-color: var(--idle);
  font-family: var(--font-serif);
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
}

.side-tab.analyzing {
  --state-color: var(--or);
}

.side-tab.allowed {
  --state-color: var(--allowed);
}

.side-tab.warning {
  --state-color: var(--warning);
}

.side-tab.blocked {
  --state-color: var(--blocked);
}

.pin {
  position: fixed;
  top: calc(50% - 18px);
  right: 0;
  z-index: 2147483647;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--border);
  border-right: none;
  border-radius: 6px 0 0 6px;
  background: var(--card);
  color: var(--state-color);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
  cursor: pointer;
  transition:
    width var(--motion-fast),
    height var(--motion-fast),
    top var(--motion-fast);
}

.dragging .pin {
  top: calc(50% - 28px);
  width: 56px;
  height: 56px;
  border-color: var(--or);
  box-shadow:
    0 0 0 3px var(--or-soft),
    0 2px 8px rgba(0, 0, 0, 0.18);
}

.glyph {
  width: 15px;
  height: 15px;
}

.dragging .glyph {
  width: 24px;
  height: 24px;
}

.analyzing .glyph,
.analyzing .head-glyph {
  animation: spin 1.4s linear infinite;
}

.popover {
  position: fixed;
  top: 50%;
  right: 34px;
  z-index: 2147483647;
  width: 280px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card);
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.28);
  transform: translateY(-50%);
}

.dragging .popover {
  right: 64px;
  border-color: var(--or);
}

.head {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
  color: var(--state-color);
}

/* The frieze's gold dot, as on the mockup's popover. */
.head::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: -3px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--or);
  transform: translateX(-50%);
}

.head-glyph {
  width: 15px;
  height: 15px;
}

.brand {
  flex: 1;
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent-text);
}

.close {
  padding: 0 2px;
  border: none;
  background: none;
  font-size: 16px;
  line-height: 1;
  color: var(--muted);
  cursor: pointer;
}

.label {
  margin: 0 0 6px;
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--state-color);
}

.idle .label {
  color: var(--text);
}

.text {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: var(--text-size-small);
  line-height: 1.6;
  color: var(--text-2);
}

.tiles {
  display: flex;
  gap: 8px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.tile {
  flex: 1;
  padding: 6px 9px;
  border: 1px solid var(--border);
  border-radius: 4px;
}

.tile-label {
  display: block;
  font-family: var(--font-display);
  font-size: 7.5px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.tile-value {
  display: block;
  font-family: var(--font-mono);
  font-size: var(--text-size-small);
  color: var(--text);
}

:focus-visible {
  outline: 2px solid var(--or);
  outline-offset: 2px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .pin,
  .glyph,
  .head-glyph {
    animation: none !important;
    transition: none !important;
  }
}
</style>
