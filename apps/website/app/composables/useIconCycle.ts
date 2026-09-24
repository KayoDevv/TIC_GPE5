import type { IconState } from "~/types/icon";

const CYCLE: IconState[] = [
  "rest",
  "scan",
  "suspect",
  "clear",
  "rest",
  "scan",
  "threat",
];

export function useIconCycle(intervalMs = 2400) {
  const index = ref(0);
  let timer: number | undefined;

  onMounted(() => {
    timer = window.setInterval(() => {
      index.value = (index.value + 1) % CYCLE.length;
    }, intervalMs);
  });

  onUnmounted(() => {
    window.clearInterval(timer);
  });

  return computed<IconState>(() => CYCLE[index.value] ?? "rest");
}