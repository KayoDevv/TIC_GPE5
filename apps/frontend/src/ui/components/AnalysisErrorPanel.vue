<script setup lang="ts">
import GlassButton from './GlassButton.vue';

defineProps<{ message: string }>();
defineEmits<{ retry: []; restart: [] }>();
</script>

<template>
  <div class="error-view">
    <div class="banner" role="alert">
      <p class="title">Analysis failed</p>
      <p class="message">{{ message }}</p>
    </div>

    <div class="actions">
      <GlassButton variant="secondary" @click="$emit('restart')">Choose another file</GlassButton>
      <GlassButton @click="$emit('retry')">Retry</GlassButton>
    </div>
  </div>
</template>

<style scoped>
.banner {
  border-radius: var(--radius-panel);
  padding: var(--space-xl);
  margin-bottom: var(--space-lg);
  background: rgba(244, 63, 94, 0.08);
  border: 1px solid rgba(244, 63, 94, 0.22);
  box-shadow: var(--shadow-inset-highlight);
}

.title {
  font-size: var(--text-size-body);
  font-weight: 600;
  color: var(--tone-blocked);
  margin-bottom: var(--space-sm);
}

.message {
  font-size: var(--text-size-small);
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.5;
}

.actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}
</style>
