<script setup lang="ts">
defineProps<{ active: boolean }>();
defineEmits<{ select: [] }>();
</script>

<template>
  <button
    class="chip rounded-full border px-3 py-1.5 text-xs font-medium transition-all"
    :class="{ 'chip--active': active }"
    @click="$emit('select')"
  >
    <slot />
  </button>
</template>

<style scoped>
.chip {
  background: transparent;
  color: var(--faint);
  border-color: var(--border);
}
.chip--active {
  background: var(--demo-accent);
  color: var(--demo-chip-text);
  border-color: var(--demo-accent);
}
</style>