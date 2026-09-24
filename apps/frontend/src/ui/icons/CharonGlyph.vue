<script setup lang="ts">
import type { CharonState } from '../charonState';

defineProps<{ state: CharonState }>();
</script>

<template>
  <svg viewBox="0 0 13 13" fill="none" stroke="currentColor" aria-hidden="true">
    <path
      d="M1.5 6.5C3 3.8 5 2.6 6.5 2.6S10 3.8 11.5 6.5C10 9.2 8 10.4 6.5 10.4S3 9.2 1.5 6.5Z"
      stroke-width="1"
    />
    <circle v-if="state === 'allowed'" cx="6.5" cy="6.5" r="1.7" fill="currentColor" stroke="none" />
    <path
      v-else-if="state === 'blocked'"
      d="M4.5 4.5l4 4M8.5 4.5l-4 4"
      stroke-width="1.1"
      stroke-linecap="round"
    />
    <circle
      v-else-if="state === 'warning'"
      cx="6.5"
      cy="6.5"
      r="2.4"
      stroke-width="1"
      stroke-dasharray="2 2"
    />
    <path
      v-else-if="state === 'analyzing'"
      d="M6.5 3A3.5 3.5 0 0 1 10 6.5"
      stroke-width="1.2"
      stroke-linecap="round"
    />
  </svg>
</template>
