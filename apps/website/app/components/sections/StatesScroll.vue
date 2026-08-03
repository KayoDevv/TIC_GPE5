<script setup lang="ts">
import type { IconState } from "~/types/icon";
import { ICON_SHAPES } from "~/types/icon";

const STAGES: {
  state: IconState;
  label: string;
  desc: string;
  from: number;
}[] = [
  {
    state: "rest",
    label: "VEILLE",
    desc: "L'icône respire. Le fleuve est calme.",
    from: 0,
  },
  {
    state: "scan",
    label: "ANALYSE",
    desc: "Un fichier traverse. L'icône balaie, cherche.",
    from: 0.2,
  },
  {
    state: "suspect",
    label: "SUSPICION",
    desc: "Quelque chose cloche. L'icône hésite, tremble.",
    from: 0.4,
  },
  {
    state: "clear",
    label: "SÛR",
    desc: "Verdict rendu. L'icône se fige, pleine et immobile.",
    from: 0.6,
  },
  {
    state: "threat",
    label: "DANGER",
    desc: "Menace confirmée. Rupture. Le passage est barré.",
    from: 0.8,
  },
];

const root = ref<HTMLElement | null>(null);
const progress = useElementScrollProgress(root);

const activeStage = computed(
  () => [...STAGES].reverse().find((s) => progress.value >= s.from) ?? STAGES[0]!,
);

const activeColor = computed(() => stateColor(activeStage.value.state));
</script>

<template>
  <section id="states" class="states-band">
    <div ref="root" class="relative h-[350vh]">
      <div class="sticky top-0 flex h-screen flex-col items-center justify-center">
        <div class="mb-12 flex items-end gap-6 sm:gap-10">
          <div
            v-for="shape in ICON_SHAPES"
            :key="shape"
            class="grid place-items-center rounded-2xl border p-4 transition-all duration-500"
            :style="{
              borderColor: `color-mix(in srgb, ${activeColor} 27%, transparent)`,
              boxShadow: `0 0 30px color-mix(in srgb, ${activeColor} 13%, transparent)`,
              background: 'var(--card)',
            }"
          >
            <IconsAnimatedIcon :shape="shape" :state="activeStage.state" :size="56" />
          </div>
        </div>

        <Transition name="stage" mode="out-in">
          <div :key="activeStage.state" class="text-center">
            <div class="flex items-center justify-center gap-3">
              <span class="h-3 w-3 rounded-full" :style="{ background: activeColor }" />
              <span
                class="font-display text-3xl tracking-[0.25em]"
                :style="{ color: activeColor }"
              >
                {{ activeStage.label }}
              </span>
            </div>
            <p class="mx-auto mt-4 max-w-md text-lg leading-relaxed text-[var(--muted)]">
              {{ activeStage.desc }}
            </p>
          </div>
        </Transition>

        <div class="mt-10 h-1 w-64 overflow-hidden rounded-full bg-[var(--border)]">
          <div
            class="h-full rounded-full transition-[width] duration-150"
            :style="{ width: `${progress * 100}%`, background: activeColor }"
          />
        </div>

        <div class="mt-4 flex gap-3">
          <div
            v-for="stage in STAGES"
            :key="stage.state"
            class="h-2 w-2 rounded-full transition-all duration-300"
            :style="{
              background:
                progress >= stage.from ? stateColor(stage.state) : 'var(--border-strong)',
              transform:
                activeStage.state === stage.state ? 'scale(1.5)' : 'scale(1)',
            }"
          />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.states-band {
  background: linear-gradient(
    180deg,
    transparent 0%,
    color-mix(in srgb, var(--bg-alt) 55%, transparent) 6%,
    color-mix(in srgb, var(--bg-alt) 55%, transparent) 94%,
    transparent 100%
  );
}

.stage-enter-active {
  transition:
    opacity 0.5s ease,
    transform 0.5s ease;
}
.stage-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.stage-enter-from {
  opacity: 0;
  transform: translateY(20px);
}
.stage-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .stage-enter-active,
  .stage-leave-active {
    transition: none;
  }
}
</style>