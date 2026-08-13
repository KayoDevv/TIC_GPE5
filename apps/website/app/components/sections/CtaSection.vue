<script setup lang="ts">
import { Cpu, Zap } from "lucide-vue-next";

const FACTS = ["Manifest V3", "18 MB RAM", "Chrome · Edge", "FR / EN"];
const { url: downloadUrl, available: downloadAvailable } = useExtensionDownload();
</script>

<template>
  <section class="relative overflow-hidden border-t border-(--border)">
    <div
      class="pointer-events-none absolute left-1/2 top-0 h-64 w-140 -translate-x-1/2 rounded-full opacity-[0.08] blur-[110px]"
      style="background: var(--gold)"
    />
    <div
      class="pointer-events-none absolute inset-0 flex items-center justify-center opacity-25"
      aria-hidden="true"
    >
      <MotionStaggerGrid />
    </div>

    <div class="relative mx-auto max-w-3xl px-6 py-24 text-center">
      <MotionScrollReveal>
        <h2 class="font-display text-3xl text-(--text) sm:text-5xl">
          <MotionSplitText text="Ajoutez le passeur." />
        </h2>
        <p class="mx-auto mt-4 max-w-md text-base text-(--muted)">
          Sans compte, sans configuration. Désinstallable en un clic —
          mais vous ne le ferez pas.
        </p>
        <div class="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <a
            v-if="downloadAvailable"
            :href="downloadUrl"
            download
            class="btn-lift flex items-center gap-2 rounded-lg px-7 py-3.5 text-sm font-semibold"
            style="background: var(--btn-bg); color: var(--btn-text)"
          >
            <Zap :size="16" /> Télécharger Charon
          </a>
          <button
            v-else
            disabled
            title="Bientôt disponible"
            class="flex cursor-not-allowed items-center gap-2 rounded-lg px-7 py-3.5 text-sm font-semibold opacity-50"
            style="background: var(--btn-bg); color: var(--btn-text)"
          >
            <Zap :size="16" /> Télécharger Charon
          </button>
          <a
            href="#architecture"
            class="flex items-center gap-2 rounded-lg border border-(--border-strong) bg-(--card)/60 px-7 py-3.5 text-sm font-medium text-(--text) transition-colors hover:border-(--text)"
          >
            <Cpu :size="16" /> Voir l'architecture
          </a>
        </div>
        <div
          class="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 font-mono2 text-[10px] uppercase tracking-wider text-(--faint)"
        >
          <template v-for="(fact, index) in FACTS" :key="fact">
            <span v-if="index > 0" style="color: var(--slash)">·</span>
            <span>{{ fact }}</span>
          </template>
        </div>
      </MotionScrollReveal>
    </div>
  </section>
</template>