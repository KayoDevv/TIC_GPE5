export function useScrollProgress() {
  const progress = ref(0);
  let frame = 0;

  function update(): void {
    const scrollable =
      document.documentElement.scrollHeight - window.innerHeight;
    progress.value = scrollable > 0 ? window.scrollY / scrollable : 0;
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