<script setup lang="ts">
import PlaceholderIcon from '../icons/PlaceholderIcon.vue';
</script>

<template>
  <div class="coming-soon">
    <PlaceholderIcon class="icon" />
    <span class="label">Coming soon</span>
  </div>
</template>

<style scoped>
.coming-soon {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  gap: var(--space-md);
  color: rgba(255, 255, 255, 0.28);
}

.icon {
  width: 32px;
  height: 32px;
}

.label {
  font-size: var(--text-size-body);
  font-weight: 500;
}
</style>
