<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    cols?: number;
    rows?: number;
    dotSize?: number;
    gap?: number;
  }>(),
  { cols: 11, rows: 5, dotSize: 5, gap: 44 },
);

const root = ref<HTMLElement | null>(null);
const inView = useInView(root, { once: true, margin: "-100px" });

const dots = computed(() => {
  const centerX = Math.floor(props.cols / 2);
  const centerY = Math.floor(props.rows / 2);
  const maxDist = Math.hypot(centerX, centerY);
  const cells = [];
  for (let row = 0; row < props.rows; row++) {
    for (let col = 0; col < props.cols; col++) {
      const dist = Math.hypot(col - centerX, row - centerY);
      cells.push({
        key: `${col}-${row}`,
        cx: col * props.gap + props.gap / 2,
        cy: row * props.gap + props.gap / 2,
        delay: (dist / maxDist) * 0.9,
      });
    }
  }
  return cells;
});
</script>

<template>
  <div
    ref="root"
    class="flex items-center justify-center overflow-hidden"
    :style="{ width: `${cols * gap}px`, height: `${rows * gap}px` }"
  >
    <svg :width="cols * gap" :height="rows * gap">
      <circle
        v-for="dot in dots"
        :key="dot.key"
        class="dot"
        :class="{ 'dot--active': inView }"
        :cx="dot.cx"
        :cy="dot.cy"
        :r="dotSize / 2"
        fill="var(--gold)"
        :style="{ animationDelay: `${dot.delay}s`, transformOrigin: `${dot.cx}px ${dot.cy}px` }"
      />
    </svg>
  </div>
</template>

<style scoped>
.dot {
  opacity: 0.08;
  transform: scale(0.4);
}
.dot--active {
  animation: dot-pulse 6s ease-in-out infinite;
}

@keyframes dot-pulse {
  0%,
  60%,
  100% {
    opacity: 0.08;
    transform: scale(0.4);
  }
  30% {
    opacity: 0.9;
    transform: scale(1.8);
  }
}

@media (prefers-reduced-motion: reduce) {
  .dot--active {
    animation: none;
  }
}
</style>