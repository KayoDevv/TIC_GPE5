import type { Ref } from "vue";

export function useInView(
  target: Ref<HTMLElement | null>,
  options: { once?: boolean; margin?: string } = {},
) {
  const { once = true, margin = "-80px" } = options;
  const inView = ref(false);
  let observer: IntersectionObserver | undefined;

  onMounted(() => {
    if (!target.value) return;
    observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry) return;
        if (entry.isIntersecting) {
          inView.value = true;
          if (once) observer?.disconnect();
        } else if (!once) {
          inView.value = false;
        }
      },
      { rootMargin: margin },
    );
    observer.observe(target.value);
  });

  onUnmounted(() => {
    observer?.disconnect();
  });

  return inView;
}