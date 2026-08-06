<script setup lang="ts">
import { GitBranch, MousePointerClick, ShieldCheck } from "lucide-vue-next";

const STEPS = [
  {
    number: "01",
    icon: MousePointerClick,
    title: "Installez l'extension",
    desc: "Un clic depuis le store. Aucun compte, aucune configuration requise.",
  },
  {
    number: "02",
    icon: GitBranch,
    title: "Choisissez votre forme",
    desc: "Œil, barque, virus, anneau ou lanterne. Position et motif personnalisables.",
  },
  {
    number: "03",
    icon: ShieldCheck,
    title: "Travaillez, c'est tout",
    desc: "Charon inspecte en arrière-plan. Vous ne le voyez que quand il a un verdict.",
  },
];
</script>

<template>
  <section
    class="relative overflow-x-clip border-t border-(--border)"
    style="background: var(--bg)"
  >
    <div class="mx-auto max-w-6xl px-6 py-24">
      <MotionScrollReveal>
        <p class="font-mono2 text-xs uppercase tracking-[0.25em]" style="color: var(--gold)">
          <MotionDecryptText text="Installation" start-on-view :duration="900" />
        </p>
        <h2 class="font-display mt-3 text-3xl text-(--text) sm:text-4xl">
          <MotionSplitText text="Opérationnel en 10 secondes." />
        </h2>
      </MotionScrollReveal>

      <div class="mt-10 grid gap-4 md:grid-cols-3">
        <MotionScrollReveal
          v-for="(step, index) in STEPS"
          :key="step.number"
          :delay="index * 0.08"
        >
          <div class="relative rounded-2xl border border-(--border) bg-(--card) p-6 shadow-sm">
            <span class="font-mono2 text-[11px] text-(--faint)">{{ step.number }}</span>
            <div
              class="mt-4 mb-3 grid h-10 w-10 place-items-center rounded-lg border"
              style="
                border-color: color-mix(in srgb, var(--gold) 25%, transparent);
                background: color-mix(in srgb, var(--gold) 8%, transparent);
              "
            >
              <component :is="step.icon" :size="18" style="color: var(--gold)" />
            </div>
            <h3 class="font-semibold text-(--text)">{{ step.title }}</h3>
            <p class="mt-1.5 text-sm leading-relaxed text-(--muted)">{{ step.desc }}</p>
          </div>
        </MotionScrollReveal>
      </div>
    </div>
  </section>
</template>