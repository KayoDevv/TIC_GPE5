import type { Ref } from "vue";

export function useElementScrollProgress(target: Ref<HTMLElement | null>) {
  const progress = ref(0);
  let frame = 0;

  function update(): void {
    const el = target.value;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const scrollable = rect.height - window.innerHeight;
    if (scrollable <= 0) {
      progress.value = 0;
      return;
    }
    progress.value = Math.min(Math.max(-rect.top / scrollable, 0), 1);
  }

  function onScroll(): void {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(update);
  }

  onMounted(() => {
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
  });

  onUnmounted(() => {
    cancelAnimationFrame(frame);
    window.removeEventListener("scroll", onScroll);
    window.removeEventListener("resize", onScroll);
  });

  return progress;
}