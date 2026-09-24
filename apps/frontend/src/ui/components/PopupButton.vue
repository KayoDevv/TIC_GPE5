<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'primary' | 'secondary' }>(), { variant: 'primary' });
defineEmits<{ click: [] }>();
</script>

<template>
  <button type="button" class="popup-button" :class="variant" @click="$emit('click')">
    <slot />
  </button>
</template>

<style scoped>
.popup-button {
  width: 100%;
  padding: 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-family: var(--font-display);
  font-size: var(--text-size-label);
  font-weight: 500;
  letter-spacing: var(--tracking-label);
  text-transform: uppercase;
  color: var(--muted);
  cursor: pointer;
  transition:
    border-color var(--motion-fast),
    color var(--motion-fast);
}

.popup-button.primary {
  border-color: var(--or);
  color: var(--accent-text);
}

.popup-button:hover {
  border-color: var(--or);
  color: var(--accent-text);
}
</style>
