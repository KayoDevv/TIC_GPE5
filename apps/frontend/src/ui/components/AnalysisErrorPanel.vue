<script setup lang="ts">
import PopupButton from './PopupButton.vue';

defineProps<{ message: string }>();
defineEmits<{ retry: []; restart: [] }>();
</script>

<template>
  <div class="error-view">
    <div class="banner" role="alert">
      <span class="overline">Analysis failed</span>
      <p class="message">{{ message }}</p>
    </div>

    <div class="actions">
      <PopupButton variant="secondary" @click="$emit('restart')">Choose another file</PopupButton>
      <PopupButton @click="$emit('retry')">Retry</PopupButton>
    </div>
  </div>
</template>

<style scoped>
.overline {
  display: block;
  margin-bottom: var(--space-sm);
  font-family: var(--font-display);
  font-size: var(--text-size-overline);
  font-weight: 500;
  letter-spacing: var(--tracking-overline);
  text-transform: uppercase;
  color: var(--blocked);
}

.message {
  margin-bottom: var(--space-lg);
  padding: 2px 0 2px 12px;
  border-left: 2px solid var(--blocked);
  overflow-wrap: anywhere;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--text-2);
}

.actions {
  display: flex;
  flex-direction: column-reverse;
  gap: 8px;
}
</style>
