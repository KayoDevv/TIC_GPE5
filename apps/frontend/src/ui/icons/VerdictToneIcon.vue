<script setup lang="ts">
import type { VerdictTone } from '../verdictPresentation';

const TONE_PATHS: Record<VerdictTone, string> = {
  allowed: 'M5 11l4 4 8-8',
  warning: 'M11 7v5M11 15h.01',
  blocked: 'M7 7l8 8M15 7l-8 8'
};

const props = defineProps<{ tone: VerdictTone }>();
</script>

<template>
  <svg viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path
      :d="TONE_PATHS[props.tone]"
      stroke="rgba(0, 0, 0, 0.75)"
      stroke-width="2.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>
