<script setup lang="ts">
const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&$@/\\<>*+=";

const props = withDefaults(
  defineProps<{
    text: string;
    duration?: number;
    delay?: number;
    startOnView?: boolean;
  }>(),
  { duration: 1400, delay: 0, startOnView: false },
);

const root = ref<HTMLElement | null>(null);
const inView = useInView(root, { once: true, margin: "-40px" });
const display = ref(props.text);

let frame = 0;
let timeout = 0;

function randomGlyph(): string {
  return GLYPHS[Math.floor(Math.random() * GLYPHS.length)] ?? "";
}

function scramble(progress: number): string {
  const revealed = Math.floor(progress * props.text.length);
  let out = "";
  for (let i = 0; i < props.text.length; i++) {
    const char = props.text[i] ?? "";
    if (char === " ") out += " ";
    else if (i < revealed) out += char;
    else out += randomGlyph();
  }
  return out;
}

function run(): void {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) {
    display.value = props.text;
    return;
  }
  let start: number | null = null;
  let tick = 0;
  const step = (ts: number): void => {
    if (start === null) start = ts;
    const progress = Math.min((ts - start) / props.duration, 1);
    tick += 1;
    if (progress >= 1) {
      display.value = props.text;
      return;
    }
    if (tick % 3 === 0 || tick === 1) display.value = scramble(progress);
    frame = requestAnimationFrame(step);
  };
  timeout = window.setTimeout(() => {
    frame = requestAnimationFrame(step);
  }, props.delay);
}

const active = computed(() => !props.startOnView || inView.value);

watch(active, (value) => value && run(), { immediate: false });

onMounted(() => {
  if (!props.startOnView) run();
});

onUnmounted(() => {
  window.clearTimeout(timeout);
  cancelAnimationFrame(frame);
});
</script>

<template>
  <span ref="root">{{ display }}</span>
</template>