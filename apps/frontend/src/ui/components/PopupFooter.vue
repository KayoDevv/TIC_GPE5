<script setup lang="ts">
defineProps<{ version: string }>();
</script>

<template>
  <footer class="footer">
    <span class="version">CHARON v{{ version }}</span>
  </footer>
</template>

<style scoped>
.footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-md);
  margin: 12px var(--space-xl) 0;
  padding-top: 11px;
  border-top: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: var(--text-size-micro);
  letter-spacing: 0.08em;
}

.version {
  flex-shrink: 0;
  color: var(--faint);
}
</style>
