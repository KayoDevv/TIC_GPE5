<script setup lang="ts">
import { Check, Cpu, Eye, FileScan, Lock } from "lucide-vue-next";
import type { IconShape } from "~/types/icon";
import { ICON_SHAPES } from "~/types/icon";

const SHAPE_TAGS: Record<IconShape, string> = {
  eye: "eye",
  boat: "boat",
  virus: "virus",
  ring: "ring",
  lantern: "lamp",
};

const SCAN_LOG = [
  { mark: "✓", tone: "var(--safe)", file: "rapport_q3.pdf", note: "— 12ms" },
  { mark: "▲", tone: "var(--warn)", file: "facture.docm", note: "— quarantaine" },
  { mark: "✕", tone: "var(--danger)", file: "setup_flash.exe", note: "— bloqué" },
];

const PERF_METRICS = [
  { label: "Empreinte mémoire", value: "18 MB", width: "22%" },
  { label: "CPU en veille", value: "~0%", width: "4%" },
  { label: "Verdict moyen", value: "38ms", width: "12%" },
];

const PRIVACY_POINTS = [
  "Sandbox éphémère — détruite après chaque analyse",
  "Rétention 60 min maximum (GDPR) · TLS 1.3",
  "Permissions minimales — stockage et téléchargements",
];
</script>

<template>
  <section id="features" class="relative overflow-x-clip">
    <div class="mx-auto max-w-6xl px-6 py-24">
      <MotionScrollReveal>
        <p class="font-mono2 text-xs uppercase tracking-[0.25em]" style="color: var(--gold)">
          <MotionDecryptText text="Fonctionnalités" start-on-view :duration="900" />
        </p>
        <h2 class="font-display mt-3 max-w-xl text-3xl leading-snug text-(--text) sm:text-4xl">
          <MotionSplitText text="Conçu comme un outil." />
          <br />
          <span class="text-(--muted)">
            <MotionSplitText text="Pensé comme un instrument." :stagger="0.045" />
          </span>
        </h2>
      </MotionScrollReveal>

      <div class="mt-10 grid gap-4 md:grid-cols-3">
        <MotionScrollReveal class="md:col-span-2">
          <UiBentoCard class="h-full">
            <div class="flex items-start justify-between">
              <div>
                <h3 class="font-semibold text-(--text)">Cinq formes, un protocole</h3>
                <p class="mt-1.5 max-w-sm text-sm leading-relaxed text-(--muted)">
                  Œil, barque, virus, anneau, lanterne. Chaque forme parle le même
                  langage d'états : veille, analyse, suspicion, sûr, danger.
                </p>
              </div>
              <Eye :size="18" class="shrink-0" style="color: var(--gold)" />
            </div>
            <div class="mt-6 flex flex-wrap gap-3">
              <div
                v-for="shape in ICON_SHAPES"
                :key="shape"
                class="flex flex-col items-center gap-1.5"
              >
                <div class="rounded-xl border border-(--border) bg-(--card-inset) p-3">
                  <IconsIconCycler :shape="shape" :size="38" />
                </div>
                <span class="font-mono2 text-[9px] uppercase tracking-wider text-(--faint)">
                  {{ SHAPE_TAGS[shape] }}
                </span>
              </div>
            </div>
          </UiBentoCard>
        </MotionScrollReveal>

        <MotionScrollReveal :delay="0.08">
          <UiBentoCard class="h-full">
            <h3 class="font-semibold text-(--text)">Ancrable partout</h3>
            <p class="mt-1.5 text-sm leading-relaxed text-(--muted)">
              Haut, bas, gauche, droite. La languette se place où vous la voulez.
            </p>
            <div
              class="relative mx-auto mt-5 h-28 w-40 rounded-lg border border-(--border) bg-(--card-inset)"
            >
              <div class="orbit-tab absolute h-3 w-6 rounded-sm" style="background: var(--gold)" />
            </div>
          </UiBentoCard>
        </MotionScrollReveal>

        <MotionScrollReveal :delay="0.05">
          <UiBentoCard class="h-full">
            <div class="flex items-start justify-between">
              <h3 class="font-semibold text-(--text)">Scan en temps réel</h3>
              <FileScan :size="18" class="shrink-0" style="color: var(--gold)" />
            </div>
            <p class="mt-1.5 text-sm leading-relaxed text-(--muted)">
              Pièces jointes, téléchargements, macros. Inspection heuristique
              avant que le fichier ne touche le disque.
            </p>
            <div
              class="mt-4 rounded-lg border border-(--border) bg-(--card-inset) p-3 font-mono2 text-[10.5px] leading-relaxed text-(--muted)"
            >
              <p v-for="line in SCAN_LOG" :key="line.file">
                <span :style="{ color: line.tone }">{{ line.mark }}</span>
                {{ line.file }}
                <span class="text-(--faint)">{{ line.note }}</span>
              </p>
            </div>
          </UiBentoCard>
        </MotionScrollReveal>

        <MotionScrollReveal :delay="0.1">
          <UiBentoCard class="h-full">
            <div class="flex items-start justify-between">
              <h3 class="font-semibold text-(--text)">Léger, natif, rapide</h3>
              <Cpu :size="18" class="shrink-0" style="color: var(--gold)" />
            </div>
            <p class="mt-1.5 text-sm leading-relaxed text-(--muted)">
              WASM + moteur local. Aucun impact perceptible sur la navigation.
            </p>
            <div class="mt-4 space-y-2.5">
              <div v-for="metric in PERF_METRICS" :key="metric.label">
                <div class="mb-1 flex justify-between font-mono2 text-[10px] text-(--faint)">
                  <span>{{ metric.label }}</span>
                  <span class="text-(--text-2)">{{ metric.value }}</span>
                </div>
                <div class="h-1 rounded-full bg-(--border)">
                  <div
                    class="h-full rounded-full opacity-80"
                    :style="{ width: metric.width, background: 'var(--gold)' }"
                  />
                </div>
              </div>
            </div>
          </UiBentoCard>
        </MotionScrollReveal>

        <MotionScrollReveal :delay="0.15" class="md:col-span-2">
          <UiBentoCard class="h-full">
            <div id="privacy" class="grid gap-6 sm:grid-cols-2">
              <div>
                <div class="flex items-start justify-between">
                  <h3 class="font-semibold text-(--text)">Privé par architecture</h3>
                  <Lock :size="18" class="shrink-0 sm:hidden" style="color: var(--gold)" />
                </div>
                <p class="mt-1.5 text-sm leading-relaxed text-(--muted)">
                  Chaque pièce jointe est analysée dans une enclave isolée,
                  puis effacée. Aucun compte, aucune télémétrie, aucune donnée
                  conservée au-delà de l'analyse.
                </p>
                <ul class="mt-4 space-y-2 text-sm text-(--text-2)">
                  <li v-for="point in PRIVACY_POINTS" :key="point" class="flex items-center gap-2">
                    <Check :size="14" class="shrink-0" style="color: var(--safe)" />
                    {{ point }}
                  </li>
                </ul>
              </div>
              <div
                class="rounded-lg border border-(--border) bg-(--card-inset) p-4 font-mono2 text-[11px] leading-relaxed text-(--text-2)"
              >
                <p class="text-(--faint)">// manifest.json</p>
                <p><span style="color: var(--gold)">"permissions"</span>: [</p>
                <p class="pl-4" style="color: var(--safe)">"storage", "downloads"</p>
                <p>],</p>
                <p><span style="color: var(--gold)">"optional_host_permissions"</span>: [</p>
                <p class="pl-4" style="color: var(--safe)">"http://*/*", "https://*/*"</p>
                <p>]</p>
              </div>
            </div>
          </UiBentoCard>
        </MotionScrollReveal>
      </div>
    </div>
  </section>
</template>

<style scoped>
.orbit-tab {
  animation: tab-orbit 8s ease-in-out infinite;
}
@keyframes tab-orbit {
  0%,
  100% {
    top: -6px;
    left: 50%;
    transform: translate(-50%, 0);
  }
  25% {
    top: 50%;
    left: calc(100% - 12px);
    transform: translate(0, -50%);
  }
  50% {
    top: calc(100% - 6px);
    left: 50%;
    transform: translate(-50%, 0);
  }
  75% {
    top: 50%;
    left: -12px;
    transform: translate(0, -50%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .orbit-tab {
    animation: none;
    top: 50%;
    left: calc(100% - 12px);
    transform: translate(0, -50%);
  }
}
</style>