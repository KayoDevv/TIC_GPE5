<script setup lang="ts">
import type { IconState } from "~/types/icon";

defineProps<{ state: IconState; color: string }>();

const SPIKES = Array.from({ length: 8 }, (_, index) => {
  const angle = (index / 8) * Math.PI * 2;
  return {
    x1: 24 + Math.cos(angle) * 9,
    y1: 24 + Math.sin(angle) * 9,
    x2: 24 + Math.cos(angle) * 16,
    y2: 24 + Math.sin(angle) * 16,
  };
});
</script>

<template>
  <g class="rotor tb-center" :data-state="state">
    <g class="pulse tb-center" :data-state="state">
      <g v-for="(spike, index) in SPIKES" :key="index">
        <line
          :x1="spike.x1"
          :y1="spike.y1"
          :x2="spike.x2"
          :y2="spike.y2"
          :stroke="color"
          stroke-width="2"
          stroke-linecap="round"
        />
        <circle :cx="spike.x2" :cy="spike.y2" r="2" :fill="color" />
      </g>
      <circle
        cx="24"
        cy="24"
        r="9"
        :fill="state === 'clear' ? color : 'transparent'"
        :stroke="color"
        stroke-width="2"
      />
      <template v-if="state !== 'clear'">
        <circle cx="21" cy="22" r="1.6" :fill="color" />
        <circle cx="27" cy="26" r="1.6" :fill="color" />
        <circle cx="25" cy="20" r="1.2" :fill="color" />
      </template>
    </g>
  </g>
</template>

<style scoped>
.rotor[data-state="rest"] {
  animation: virus-spin 14s linear infinite;
}
.rotor[data-state="scan"] {
  animation: virus-spin 5s linear infinite;
}
.rotor[data-state="threat"] {
  animation: virus-spin 2.6s linear infinite;
}
@keyframes virus-spin {
  to {
    transform: rotate(360deg);
  }
}

.pulse[data-state="suspect"] {
  animation: virus-wobble 0.9s ease-in-out infinite;
}
.pulse[data-state="threat"] {
  animation: virus-pulse 0.7s ease-in-out infinite;
}
@keyframes virus-wobble {
  0%,
  100% {
    transform: rotate(-6deg) scale(1);
  }
  25% {
    transform: rotate(6deg) scale(1.025);
  }
  50% {
    transform: rotate(-4deg) scale(1.05);
  }
  75% {
    transform: rotate(5deg) scale(1.025);
  }
}
@keyframes virus-pulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.14);
  }
}

@media (prefers-reduced-motion: reduce) {
  .rotor,
  .pulse {
    animation: none;
  }
}
</style>