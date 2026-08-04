<script setup lang="ts">
import type { IconState } from "~/types/icon";
import { ICON_SHAPES } from "~/types/icon";

const STAGES: {
  state: IconState;
  code: string;
  label: string;
  desc: string;
  from: number;
}[] = [
  {
    state: "rest",
    code: "IDLE",
    label: "Veille",
    desc: "Mouvement lent et régulier. Rien à signaler.",
    from: 0,
  },
  {
    state: "scan",
    code: "SCAN",
    label: "Analyse",
    desc: "Balayage continu. Un fichier est inspecté.",
    from: 0.2,
  },
  {
    state: "suspect",
    code: "WARN",
    label: "Suspicion",
    desc: "Signaux ambigus. Fichier mis en quarantaine.",
    from: 0.4,
  },
  {
    state: "clear",
    code: "PASS",
    label: "Sûr",
    desc: "Forme pleine, immobile. Verdict positif.",
    from: 0.6,
  },
  {
    state: "threat",
    code: "KILL",
    label: "Danger",
    desc: "Rupture. Menace bloquée avant le disque.",
    from: 0.8,
  },
];

const SEGMENT_SPAN = 0.2;

const root = ref<HTMLElement | null>(null);
const progress = useElementScrollProgress(root);

const activeIndex = computed(() => {
  const index = STAGES.findLastIndex((stage) => progress.value >= stage.from);
  return index === -1 ? 0 : index;
});

const activeStage = computed(() => STAGES[activeIndex.value]!);
const activeColor = computed(() => stateColor(activeStage.value.state));

function segmentFill(index: number): number {
  const local = (progress.value - STAGES[index]!.from) / SEGMENT_SPAN;
  return Math.min(Math.max(local, 0), 1) * 100;
}
</script>

<template>
  <section id="states" class="states-band">
    <div ref="root" class="relative h-[350vh]">
      <div class="sticky top-0 flex h-screen flex-col items-center justify-center px-6">
        <p class="font-mono2 text-xs uppercase tracking-[0.25em]" style="color: var(--gold)">
          Machine à états
        </p>
        <h2
          class="font-display mt-3 text-center text-3xl text-(--text) sm:text-4xl"
        >
          Un verdict lisible en périphérie.
        </h2>
        <p class="mt-3 max-w-lg text-center text-(--muted)">
          Scrollez — les cinq formes traversent le cycle complet :
          IDLE → SCAN → WARN → PASS → KILL.
        </p>

        <div class="mt-10 flex items-end gap-3 sm:gap-4">
          <div
            v-for="shape in ICON_SHAPES"
            :key="shape"
            class="grid place-items-center rounded-2xl border p-4 transition-all duration-500"
            :style="{
              borderColor: `color-mix(in srgb, ${activeColor} 22%, transparent)`,
              boxShadow: `0 0 26px color-mix(in srgb, ${activeColor} 11%, transparent)`,
              background: 'var(--card)',
            }"
          >
            <IconsAnimatedIcon :shape="shape" :state="activeStage.state" :size="46" />
          </div>
        </div>

        <Transition name="stage" mode="out-in">
          <div :key="activeStage.state" class="mt-8 text-center">
            <div class="flex items-center justify-center gap-2.5">
              <span
                class="rounded border px-2 py-0.5 font-mono2 text-[10px] tracking-[0.14em]"
                :style="{
                  color: activeColor,
                  borderColor: `color-mix(in srgb, ${activeColor} 45%, transparent)`,
                }"
              >
                {{ activeStage.code }}
              </span>
              <span class="font-mono2 text-[11px] text-(--faint)">
                state[{{ activeIndex }}]
              </span>
            </div>
            <p class="font-display mt-4 text-2xl text-(--text)">
              {{ activeStage.label }}
            </p>
            <p class="mt-2 text-(--muted)">{{ activeStage.desc }}</p>
          </div>
        </Transition>

        <div class="mt-9 flex gap-2">
          <div
            v-for="(stage, index) in STAGES"
            :key="stage.state"
            class="h-0.75 w-12 overflow-hidden rounded-full bg-(--border) sm:w-14"
          >
            <div
              class="h-full rounded-full transition-[width] duration-150"
              :style="{
                width: `${segmentFill(index)}%`,
                background: stateColor(stage.state),
              }"
            />
          </div>
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
    opacity 0.4s ease,
    transform 0.4s ease;
}
.stage-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}
.stage-enter-from {
  opacity: 0;
  transform: translateY(14px);
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