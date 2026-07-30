<script setup lang="ts">
const { mode, toggle } = useTheme();
</script>

<template>
  <main class="grid min-h-screen place-content-center gap-6 text-center">
    <h1 class="font-display text-5xl" style="color: var(--gold)">Charon</h1>
    <p class="text-[var(--muted)]">Le passeur qui garde votre boîte mail.</p>
    <p class="font-mono2 text-xs text-[var(--faint)]">v2.6 · {{ mode }}</p>
    <button
      class="btn-lift mx-auto rounded-lg px-5 py-2 text-sm font-semibold"
      style="background: var(--btn-bg); color: var(--btn-text)"
      @click="toggle"
    >
      Basculer le thème
    </button>
  </main>
</template>