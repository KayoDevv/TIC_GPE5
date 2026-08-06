<template>
  <section id="architecture" class="border-t border-(--border)">
    <div class="mx-auto max-w-6xl px-6 py-24">
      <MotionScrollReveal class="text-center">
        <p class="font-mono2 text-xs uppercase tracking-[0.25em]" style="color: var(--gold)">
          <MotionDecryptText text="Sous le capot" start-on-view :duration="900" />
        </p>
        <h2 class="font-display mt-3 text-3xl text-(--text) sm:text-4xl">
          <MotionSplitText text="Trois passeurs, un seul verdict." />
        </h2>
        <p class="mx-auto mt-3 max-w-md text-sm text-(--muted)">
          Analyse statique, détonation en sandbox, lecture sémantique —
          chaque spécimen emprunte les canaux jusqu'au moteur de verdict.
        </p>
      </MotionScrollReveal>

      <div class="mt-10 grid gap-4 md:grid-cols-5">
        <MotionScrollReveal :delay="0.05" class="md:col-span-2">
          <div
            class="flex h-full flex-col justify-between rounded-2xl border border-(--border) bg-(--card) p-6 shadow-sm"
          >
            <UiCharonLayers class="mx-auto max-w-85" />
            <p
              class="mt-4 text-center font-mono2 text-[10px] uppercase tracking-[0.14em] text-(--faint)"
            >
              PL. V — Les couches · ML &amp; sandbox en parallèle · le saga tranche
            </p>
          </div>
        </MotionScrollReveal>

        <MotionScrollReveal :delay="0.12" class="md:col-span-3">
          <div
            class="flex h-full flex-col justify-between rounded-2xl border border-(--border) bg-(--card) p-6 shadow-sm sm:p-8"
          >
            <UiCharonArchitecture />
            <p
              class="mt-4 text-center font-mono2 text-[10px] uppercase tracking-[0.14em] text-(--faint)"
            >
              PL. IV — La machinerie · scatter-gather · ML &lt; 500 ms · sandbox &lt; 120 s · LLM 3–5 s
            </p>
          </div>
        </MotionScrollReveal>
      </div>
    </div>
  </section>
</template>