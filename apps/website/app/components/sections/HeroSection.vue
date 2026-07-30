<script setup lang="ts">
import { MousePointerClick } from "lucide-vue-next";

const BROWSER_FACTS = [
  "Chrome",
  "Firefox",
  "Edge",
  "Brave",
  "0 télémétrie",
  "<3MB",
];
</script>

<template>
  <section class="relative overflow-hidden pt-32 pb-10">
    <div class="pointer-events-none absolute inset-0">
      <div
        class="absolute left-1/2 top-[-180px] h-[420px] w-[720px] -translate-x-1/2 rounded-full opacity-[0.09] blur-[140px]"
        style="background: var(--gold)"
      />
      <div class="hero-grid absolute inset-0 opacity-[0.5]" />
    </div>

    <SectionsEngravingHands />

    <div class="relative mx-auto max-w-6xl px-6 text-center">
      <h1
        class="hero-rise font-display mx-auto max-w-3xl pt-6 text-4xl leading-[1.12] text-[var(--text)] sm:text-6xl"
        style="--rise-delay: 0.08s"
      >
        La sécurité mail,
        <br />
        <span class="hero-gradient bg-clip-text text-transparent">
          en périphérie de votre vision.
        </span>
      </h1>

      <p
        class="hero-rise mx-auto mt-6 max-w-xl text-base leading-relaxed text-[var(--muted)] sm:text-lg"
        style="--rise-delay: 0.16s"
      >
        Charon est une extension navigateur qui inspecte chaque pièce jointe et
        téléchargement. Pas de popups, pas d'alertes — une icône vivante sur le bord
        de l'écran qui change de forme selon le verdict.
      </p>

      <div
        class="hero-rise mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row"
        style="--rise-delay: 0.24s"
      >
        <a
          href="/charon-extension-v2.0.0.zip"
          download
          class="btn-lift flex items-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold"
          style="background: var(--btn-bg); color: var(--btn-text)"
        >
          + Télécharger l'extension — gratuit
        </a>
        <a
          href="#product"
          class="flex items-center gap-2 rounded-lg border border-[var(--border-strong)] bg-[var(--card)]/60 px-6 py-3 text-sm font-medium text-[var(--text)] transition-colors hover:border-[var(--text)]"
        >
          <MousePointerClick :size="16" /> Voir la démo
        </a>
      </div>

      <div
        class="hero-fade mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 font-mono2 text-[11px] text-[var(--faint)]"
        style="--fade-delay: 0.4s"
      >
        <template v-for="(fact, index) in BROWSER_FACTS" :key="fact">
          <span v-if="index > 0" style="color: var(--slash)">/</span>
          <span>{{ fact }}</span>
        </template>
      </div>
      <p
        class="hero-fade mt-3 font-mono2 text-[10px] text-[var(--faint)]"
        style="--fade-delay: 0.5s"
      >
        v2.0.0 · zip — décompressez puis chrome://extensions → mode développeur →
        « Charger l'extension non empaquetée »
      </p>
    </div>
  </section>
</template>

<style scoped>
.hero-grid {
  background-image:
    linear-gradient(var(--grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
  background-size: 56px 56px;
  mask-image: radial-gradient(ellipse 70% 55% at 50% 0%, black, transparent);
}

.hero-gradient {
  background-image: linear-gradient(
    to right,
    var(--gold),
    var(--gold-2),
    var(--gold)
  );
}

.hero-rise {
  opacity: 0;
  animation: hero-rise 0.6s ease-out forwards;
  animation-delay: var(--rise-delay, 0s);
}
@keyframes hero-rise {
  from {
    opacity: 0;
    transform: translateY(18px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.hero-fade {
  opacity: 0;
  animation: hero-fade 0.8s ease-out forwards;
  animation-delay: var(--fade-delay, 0s);
}
@keyframes hero-fade {
  to {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero-rise,
  .hero-fade {
    animation: none;
    opacity: 1;
  }
}
</style>