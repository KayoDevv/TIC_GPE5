<template>
  <section class="glass-shell">
    <slot />
  </section>
</template>

<style scoped>
.glass-shell {
  width: var(--shell-width);
  border-radius: var(--radius-shell);
  background: var(--surface-shell);
  backdrop-filter: var(--blur-glass);
  -webkit-backdrop-filter: var(--blur-glass);
  border: 1px solid var(--border-strong);
  border-top: 1px solid var(--border-specular);
  box-shadow: var(--shadow-shell);
  overflow: hidden;
  position: relative;
}

.glass-shell::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 5%,
    rgba(255, 255, 255, 0.28) 40%,
    rgba(255, 255, 255, 0.18) 60%,
    transparent 95%
  );
  z-index: 1;
  pointer-events: none;
}
</style>
