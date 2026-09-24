<script setup lang="ts">
import type { IconState } from "~/types/icon";

const props = defineProps<{ state: IconState; color: string }>();

const out = computed(() => props.state === "threat");
</script>

<template>
  <g>
    <path
      d="M18 11 Q24 3 30 11"
      fill="none"
      :stroke="color"
      stroke-width="1.8"
      stroke-linecap="round"
    />
    <path
      d="M17.5 11 L30.5 11 L33 33.5 Q24 37.5 15 33.5 Z"
      fill="none"
      :stroke="color"
      stroke-width="1.8"
      stroke-linejoin="round"
    />

    <circle
      v-if="state === 'scan'"
      class="halo tb-center"
      cx="24"
      cy="24"
      r="8"
      fill="none"
      :stroke="color"
      stroke-width="1.4"
    />

    <path
      v-if="!out"
      class="flame tb-center"
      :data-state="state"
      d="M24 17.5 C27.5 22 28.5 25.5 24 29.5 C19.5 25.5 20.5 22 24 17.5 Z"
      :fill="state === 'clear' ? color : 'transparent'"
      :stroke="color"
      stroke-width="1.8"
      stroke-linejoin="round"
    />

    <template v-if="out">
      <path
        class="smoke"
        d="M24 29 C26.5 25.5 21.5 22.5 24 18.5"
        fill="none"
        :stroke="color"
        stroke-width="1.6"
        stroke-linecap="round"
      />
      <line
        x1="21"
        y1="31"
        x2="27"
        y2="31"
        :stroke="color"
        stroke-width="2.2"
        stroke-linecap="round"
      />
    </template>
  </g>
</template>

<style scoped>
.halo {
  animation: lantern-halo 1.3s ease-out infinite;
}
@keyframes lantern-halo {
  from {
    transform: scale(1);
    opacity: 0.7;
  }
  to {
    transform: scale(2.125);
    opacity: 0;
  }
}

.flame[data-state="rest"] {
  animation: flame-breathe 2.8s ease-in-out infinite;
}
.flame[data-state="scan"] {
  animation: flame-lean 1.1s ease-in-out infinite;
}
.flame[data-state="suspect"] {
  animation: flame-flicker 0.8s ease-in-out infinite;
}
.flame[data-state="clear"] {
  transform: scale(1.1);
}

@keyframes flame-breathe {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.85;
  }
  50% {
    transform: scale(1.08);
    opacity: 1;
  }
}
@keyframes flame-lean {
  0%,
  100% {
    transform: translateX(-1.2px) scale(1.05);
  }
  50% {
    transform: translateX(1.2px) scale(1.05);
  }
}
@keyframes flame-flicker {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  25% {
    transform: scale(0.85);
    opacity: 0.25;
  }
  50% {
    transform: scale(1);
    opacity: 0.9;
  }
  75% {
    transform: scale(0.9);
    opacity: 0.35;
  }
}

.smoke {
  animation: smoke-rise 1.8s ease-out infinite;
}
@keyframes smoke-rise {
  0% {
    transform: translateY(2px);
    opacity: 0;
  }
  50% {
    opacity: 0.8;
  }
  100% {
    transform: translateY(-3px);
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .halo,
  .flame,
  .smoke {
    animation: none;
  }
}
</style>