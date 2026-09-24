<script setup lang="ts">
import type { IconState } from "~/types/icon";

defineProps<{ state: IconState; color: string }>();
</script>

<template>
  <g>
    <g class="lid tb-center" :data-state="state">
      <path
        d="M3 24 C 14 11, 34 11, 45 24 C 34 37, 14 37, 3 24 Z"
        fill="none"
        :stroke="color"
        stroke-width="2"
        stroke-linejoin="round"
      />
      <circle
        v-if="state !== 'threat'"
        class="iris tb-center"
        :data-state="state"
        cx="24"
        cy="24"
        :r="state === 'clear' ? 6.5 : 6"
        :fill="state === 'clear' ? color : 'transparent'"
        :stroke="color"
        stroke-width="2"
      />
      <circle
        v-if="state === 'rest' || state === 'scan' || state === 'suspect'"
        class="pupil tb-center"
        :data-state="state"
        cx="24"
        cy="24"
        r="2.4"
        :fill="color"
      />
    </g>
    <g v-if="state === 'threat'" class="cross tb-center">
      <line x1="16" y1="16" x2="32" y2="32" :stroke="color" stroke-width="2.6" stroke-linecap="round" />
      <line x1="32" y1="16" x2="16" y2="32" :stroke="color" stroke-width="2.6" stroke-linecap="round" />
    </g>
  </g>
</template>

<style scoped>
.lid[data-state="rest"] {
  animation: eye-blink 4.5s ease-in-out infinite;
}
.lid[data-state="suspect"] {
  animation: eye-squint 1.2s ease-in-out infinite;
}

@keyframes eye-blink {
  0%,
  90% {
    transform: scaleY(1);
  }
  94% {
    transform: scaleY(0.08);
  }
  98%,
  100% {
    transform: scaleY(1);
  }
}
@keyframes eye-squint {
  0%,
  100% {
    transform: scaleY(0.62);
  }
  25% {
    transform: scaleY(0.55);
  }
  50% {
    transform: scaleY(0.66);
  }
  75% {
    transform: scaleY(0.58);
  }
}

.iris[data-state="scan"],
.pupil[data-state="scan"] {
  animation: eye-sweep 1.6s ease-in-out infinite;
}
.iris[data-state="suspect"],
.pupil[data-state="suspect"] {
  animation: eye-dart 1s ease-in-out infinite;
}

@keyframes eye-sweep {
  0%,
  100% {
    transform: translateX(-8px);
  }
  50% {
    transform: translateX(8px);
  }
}
@keyframes eye-dart {
  0%,
  100% {
    transform: translateX(-4px);
  }
  25% {
    transform: translateX(5px);
  }
  50% {
    transform: translateX(-3px);
  }
  75% {
    transform: translateX(4px);
  }
}

.cross {
  animation: eye-cross-pop 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}
@keyframes eye-cross-pop {
  from {
    transform: scale(0) rotate(-30deg);
    opacity: 0;
  }
  to {
    transform: scale(1) rotate(0deg);
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .lid,
  .iris,
  .pupil,
  .cross {
    animation: none;
  }
  .cross {
    opacity: 1;
  }
}
</style>