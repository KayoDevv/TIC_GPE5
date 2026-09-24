<script setup lang="ts">
import type { IconState } from "~/types/icon";

defineProps<{ state: IconState; color: string }>();
</script>

<template>
  <g>
    <circle
      v-if="state === 'rest'"
      class="ring-breathe tb-center"
      cx="24"
      cy="24"
      r="12"
      fill="none"
      :stroke="color"
      stroke-width="2.4"
    />
    <g v-else-if="state === 'scan'" class="ring-spin tb-center">
      <circle cx="24" cy="24" r="12" fill="none" :stroke="color" stroke-width="2.4" opacity="0.25" />
      <path d="M24 12 A 12 12 0 0 1 36 24" fill="none" :stroke="color" stroke-width="2.6" stroke-linecap="round" />
    </g>
    <g v-else-if="state === 'suspect'" class="ring-jitter tb-center">
      <circle cx="24" cy="24" r="12" fill="none" :stroke="color" stroke-width="2.4" stroke-dasharray="4 5" />
      <line x1="24" y1="17" x2="24" y2="26" :stroke="color" stroke-width="2.6" stroke-linecap="round" />
      <circle cx="24" cy="30.5" r="1.7" :fill="color" />
    </g>
    <g v-else-if="state === 'clear'" class="ring-pop tb-center">
      <circle cx="24" cy="24" r="12" :fill="color" />
    </g>
    <g v-else class="ring-pop-threat tb-center">
      <circle cx="24" cy="24" r="12" fill="none" :stroke="color" stroke-width="2.4" />
      <line x1="16" y1="16" x2="32" y2="32" :stroke="color" stroke-width="2.6" stroke-linecap="round" />
      <line x1="32" y1="16" x2="16" y2="32" :stroke="color" stroke-width="2.6" stroke-linecap="round" />
    </g>
  </g>
</template>

<style scoped>
.ring-breathe {
  animation: ring-breathe 3.2s ease-in-out infinite;
}
@keyframes ring-breathe {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.05);
  }
}

.ring-spin {
  animation: ring-spin 1.2s linear infinite;
}
@keyframes ring-spin {
  to {
    transform: rotate(360deg);
  }
}

.ring-jitter {
  animation: ring-jitter 1.1s ease-in-out infinite;
}
@keyframes ring-jitter {
  0%,
  100% {
    transform: scale(1) rotate(0deg);
  }
  25% {
    transform: scale(0.93) rotate(4deg);
  }
  50% {
    transform: scale(1.02) rotate(-3deg);
  }
  75% {
    transform: scale(0.95) rotate(3deg);
  }
}

.ring-pop {
  animation: ring-pop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}
@keyframes ring-pop {
  from {
    transform: scale(0.4);
  }
  to {
    transform: scale(1);
  }
}

.ring-pop-threat {
  animation: ring-pop-threat 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}
@keyframes ring-pop-threat {
  from {
    transform: scale(0.4) rotate(-20deg);
  }
  to {
    transform: scale(1) rotate(0deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .ring-breathe,
  .ring-spin,
  .ring-jitter,
  .ring-pop,
  .ring-pop-threat {
    animation: none;
  }
}
</style>