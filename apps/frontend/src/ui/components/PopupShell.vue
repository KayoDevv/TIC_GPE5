<script setup lang="ts">
import type { CharonState } from '../charonState';

defineProps<{ state: CharonState }>();
</script>

<template>
  <div class="popup-shell" :class="state">
    <div class="frieze" aria-hidden="true" />
    <slot />
  </div>
</template>

<style scoped>
.popup-shell {
  --state-color: var(--idle);
  position: relative;
  width: var(--shell-width);
  padding-bottom: 12px;
  background: var(--card);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.popup-shell.analyzing {
  --state-color: var(--or);
}

.popup-shell.allowed {
  --state-color: var(--allowed);
}

.popup-shell.warning {
  --state-color: var(--warning);
}

.popup-shell.blocked {
  --state-color: var(--blocked);
}

/* The Greek key: one gold frieze per surface, edge to edge. */
.frieze {
  height: 14px;
  margin-bottom: var(--space-lg);
  background-color: var(--or);
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M0 11 H12 M1.8 11 V1.8 H10.3 V7.3 H5.3 V5 H7.7' fill='none' stroke='%23000' stroke-width='1.6'/%3E%3C/svg%3E")
    repeat-x left bottom / 14px 14px;
}
</style>
