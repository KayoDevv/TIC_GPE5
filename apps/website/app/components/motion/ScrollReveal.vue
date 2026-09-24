<script setup lang="ts">
const props = withDefaults(
  defineProps<{ delay?: number; y?: number; once?: boolean }>(),
  { delay: 0, y: 50, once: true },
);

const root = ref<HTMLElement | null>(null);
const inView = useInView(root, { once: props.once, margin: "-80px" });
</script>

<template>
  <div
    ref="root"
    class="reveal"
    :class="{ 'reveal--visible': inView }"
    :style="{ '--reveal-y': `${y}px`, '--reveal-delay': `${delay}s` }"
  >
    <slot />
  </div>
</template>

<style scoped>
.reveal {
  opacity: 0;
  transform: translateY(var(--reveal-y));
  transition:
    opacity 0.85s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.85s cubic-bezier(0.22, 1, 0.36, 1);
  transition-delay: var(--reveal-delay);
}
.reveal--visible {
  opacity: 1;
  transform: translateY(0);
}

@media (prefers-reduced-motion: reduce) {
  .reveal {
    opacity: 1;
    transform: none;
    transition: none;
  }
}
</style>