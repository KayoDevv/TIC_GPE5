<script setup lang="ts">
defineProps<{ label: string }>();
</script>

<template>
  <div class="flex flex-col items-center gap-1.5 sm:flex-row sm:gap-3">
    <span class="text-[10px] font-medium uppercase tracking-[0.2em] text-[var(--faint)]">
      {{ label }}
    </span>
    <div class="flex flex-wrap justify-center gap-1.5">
      <slot />
    </div>
  </div>
</template>