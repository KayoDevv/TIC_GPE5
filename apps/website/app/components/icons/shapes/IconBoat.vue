<script setup lang="ts">
import type { IconState } from "~/types/icon";

const props = defineProps<{ state: IconState; color: string }>();

const sinking = computed(() => props.state === "threat");
const filled = computed(() => props.state === "clear");

const BUBBLES = [
  { cx: 18, delay: "0s" },
  { cx: 25, delay: "0.45s" },
  { cx: 31, delay: "0.9s" },
];

const CALM_WATER = "M4 41 Q10 38 16 41 T28 41 T40 41 T52 41";
const STORM_WATER = "M3 38 Q9 33 15 38 T27 38 T39 38 T51 38";
</script>

<template>
  <g>
    <g class="hull tb-center" :data-state="state">
      <path
        d="M24 5 C20.5 11 18.6 17.5 18.1 25.5 L29.9 25.5 C29.4 17.5 27.5 11 24 5 Z M24 12.5 L27 18.5 L24 24 L21 18.5 Z"
        fill-rule="evenodd"
        :fill="filled ? color : 'transparent'"
        :stroke="color"
        stroke-width="1.8"
        stroke-linejoin="round"
      />
      <path
        d="M6 20.5 C7 17.5 10.5 17.5 11.5 20.5 C13.5 26.5 18 30 24 30 C30 30 34.5 26.5 36.5 20.5 C37.5 17.5 41 17.5 42 20.5 C40.5 29.5 33 35.5 24 35.5 C15 35.5 7.5 29.5 6 20.5 Z"
        :fill="filled ? color : 'transparent'"
        :stroke="color"
        stroke-width="1.8"
        stroke-linejoin="round"
      />
    </g>

    <template v-if="sinking">
      <circle
        v-for="bubble in BUBBLES"
        :key="bubble.cx"
        class="bubble"
        :cx="bubble.cx"
        cy="38"
        r="1.6"
        fill="none"
        :stroke="color"
        stroke-width="1.2"
        :style="{ animationDelay: bubble.delay }"
      />
    </template>

    <path
      class="water"
      :data-state="state"
      :d="sinking ? STORM_WATER : CALM_WATER"
      fill="none"
      :stroke="color"
      :stroke-width="sinking ? 2.2 : 1.6"
      stroke-linecap="round"
      opacity="0.75"
    />
  </g>
</template>

<style scoped>
.hull[data-state="rest"] {
  animation: boat-rock 3.6s ease-in-out infinite;
}
.hull[data-state="scan"] {
  animation: boat-advance 1.7s ease-in-out infinite;
}
.hull[data-state="suspect"] {
  animation: boat-swell 1.1s ease-in-out infinite;
}
.hull[data-state="threat"] {
  animation: boat-sink 1.9s ease-in forwards;
}

@keyframes boat-rock {
  0%,
  100% {
    transform: rotate(-3.5deg) translateY(0);
  }
  50% {
    transform: rotate(3.5deg) translateY(1px);
  }
}
@keyframes boat-advance {
  0%,
  100% {
    transform: rotate(-3deg) translateX(-2px);
  }
  50% {
    transform: rotate(3deg) translateX(2px);
  }
}
@keyframes boat-swell {
  0%,
  100% {
    transform: rotate(-7deg) translateY(0);
  }
  25% {
    transform: rotate(6deg) translateY(1.5px);
  }
  50% {
    transform: rotate(-5deg) translateY(0.5px);
  }
  75% {
    transform: rotate(7deg) translateY(1.5px);
  }
}
@keyframes boat-sink {
  to {
    transform: translateY(14px) rotate(-18deg);
    opacity: 0.45;
  }
}

.bubble {
  animation: bubble-rise 1.4s ease-out infinite;
}
@keyframes bubble-rise {
  0% {
    transform: translateY(0);
    opacity: 0;
  }
  50% {
    opacity: 0.9;
  }
  100% {
    transform: translateY(-12px);
    opacity: 0;
  }
}

.water {
  animation: water-drift 3s ease-in-out infinite;
}
.water[data-state="suspect"] {
  animation-duration: 1.4s;
}
.water[data-state="threat"] {
  animation-duration: 0.8s;
}
@keyframes water-drift {
  0%,
  100% {
    transform: translateX(0);
  }
  50% {
    transform: translateX(-12px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .hull,
  .bubble,
  .water {
    animation: none;
  }
}
</style>