<script setup lang="ts">
const { themeClass } = useTheme();
</script>

<template>
  <div
    :class="themeClass"
    class="isolate relative min-h-screen bg-[var(--bg)] font-sans2 text-[var(--text)] antialiased transition-colors duration-500"
  >
    <LayoutRiverStyx />
    <LayoutFriseRibbon />
    <LayoutTheNavbar />
    <NuxtPage />
    <LayoutTheFooter />
  </div>
</template>