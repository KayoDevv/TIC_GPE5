<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'primary' | 'secondary' }>(), { variant: 'primary' });
</script>

<template>
  <button type="button" class="glass-button" :class="variant">
    <slot />
  </button>
</template>

<style scoped>
.glass-button {
  width: 100%;
  border-radius: var(--radius-control);
  cursor: pointer;
  font-size: var(--text-size-body);
  letter-spacing: 0.02em;
  transition: all var(--motion-fast);
}

.glass-button.primary {
  padding: 13px;
  border: none;
  border-top: 1px solid var(--border-specular);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0.1));
  box-shadow: var(--shadow-raised);
  color: var(--text-primary);
  font-weight: 600;
}

.glass-button.primary:hover {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.28), rgba(255, 255, 255, 0.14));
  transform: translateY(-1px);
}

.glass-button.secondary {
  padding: var(--space-md);
  border: 1px solid var(--border-regular);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: var(--text-size-small);
  font-weight: 500;
}

.glass-button.secondary:hover {
  background: var(--surface-hover);
  color: rgba(255, 255, 255, 0.8);
}
</style>
