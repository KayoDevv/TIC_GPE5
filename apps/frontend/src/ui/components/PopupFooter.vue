<script setup lang="ts">
defineProps<{ version: string; sessionLabel: string }>();
</script>

<template>
  <footer class="footer">
    <span class="version">Charon v{{ version }}</span>
    <span class="session">{{ sessionLabel }}</span>
  </footer>
</template>

<style scoped>
.footer {
  padding: var(--space-md) var(--space-xl);
  border-top: 1px solid var(--border-soft);
  background: var(--surface-sunken);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-md);
  font-family: var(--font-mono);
  font-size: var(--text-size-micro);
  letter-spacing: 0.06em;
}

.version {
  color: var(--text-faint);
  flex-shrink: 0;
}

.session {
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
