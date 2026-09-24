<script setup lang="ts">
const STATS = [
  { value: "2.4M+", label: "fichiers analysés / jour" },
  { value: "< 40ms", label: "verdict moyen" },
  { value: "0", label: "donnée envoyée au cloud" },
  { value: "4.9/5", label: "note Chrome Web Store" },
];
</script>

<template>
  <section
    class="border-y border-(--border)"
    style="background: color-mix(in srgb, var(--bg-alt) 55%, var(--bg))"
  >
    <div
      class="mx-auto grid max-w-6xl grid-cols-2 divide-x divide-(--border) px-6 md:grid-cols-4"
    >
      <div
        v-for="stat in STATS"
        :key="stat.label"
        class="flex flex-col items-center py-7 text-center"
      >
        <span class="font-display text-2xl text-(--text)">
          <MotionDecryptText :text="stat.value" start-on-view :duration="1400" />
        </span>
        <span class="mt-1 px-2 font-mono2 text-[10px] uppercase tracking-wider text-(--faint)">
          {{ stat.label }}
        </span>
      </div>
    </div>
  </section>
</template>