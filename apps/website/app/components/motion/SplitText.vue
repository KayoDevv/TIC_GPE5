<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    text: string;
    charLevel?: boolean;
    stagger?: number;
    duration?: number;
    once?: boolean;
    tag?: string;
  }>(),
  { charLevel: false, stagger: 0.035, duration: 0.65, once: true, tag: "span" },
);

const root = ref<HTMLElement | null>(null);
const inView = useInView(root, { once: props.once, margin: "-60px" });

const units = computed(() =>
  props.charLevel ? props.text.split("") : props.text.split(" "),
);
</script>

<template>
  <component :is="tag" ref="root" class="inline">
    <span
      v-for="(unit, index) in units"
      :key="index"
      class="inline-block overflow-hidden"
    >
      <span
        class="split-unit inline-block"
        :class="{ 'split-unit--visible': inView }"
        :style="{
          transitionDuration: `${duration}s`,
          transitionDelay: `${index * stagger}s`,
        }"
        >{{ unit }}{{ charLevel ? "" : "\u00A0" }}</span
      >
    </span>
  </component>
</template>

<style scoped>
.split-unit {
  transform: translateY(110%);
  opacity: 0;
  transition-property: transform, opacity;
  transition-timing-function: cubic-bezier(0.22, 1, 0.36, 1);
}
.split-unit--visible {
  transform: translateY(0);
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .split-unit {
    transform: none;
    opacity: 1;
    transition: none;
  }
}
</style>