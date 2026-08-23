<script setup lang="ts">
import ShieldIcon from '../icons/ShieldIcon.vue';

defineProps<{ statusLabel: string; isActive: boolean }>();
</script>

<template>
  <header class="header">
    <div class="identity">
      <span class="logo"><ShieldIcon class="logo-icon" /></span>
      <span>
        <span class="title">Charon</span>
        <span class="subtitle">Malware analysis</span>
      </span>
    </div>

    <div class="status">
      <span class="status-dot" :class="{ active: isActive }" />
      <span class="status-label">{{ statusLabel }}</span>
    </div>
  </header>
</template>

<style scoped>
.header {
  padding: var(--space-lg) var(--space-xl);
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border-soft);
  background: rgba(255, 255, 255, 0.04);
}

.identity {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.logo {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.18), rgba(255, 255, 255, 0.06));
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-top: 1px solid rgba(255, 255, 255, 0.35);
  box-shadow: var(--shadow-raised);
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.8);
  flex-shrink: 0;
}

.logo-icon {
  width: 16px;
  height: 16px;
}

.title {
  display: block;
  font-size: var(--text-size-title);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.subtitle {
  display: block;
  font-size: var(--text-size-micro);
  color: var(--text-muted);
  font-family: var(--font-mono);
  letter-spacing: var(--tracking-label);
  text-transform: uppercase;
}

.status {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-pill);
  background: var(--surface-raised);
  border: 1px solid var(--border-regular);
}

.status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.3);
  transition: all var(--motion-base);
}

.status-dot.active {
  background: var(--tone-allowed);
  box-shadow: 0 0 6px var(--tone-allowed-glow);
}

.status-label {
  font-size: var(--text-size-micro);
  color: var(--text-muted);
  font-family: var(--font-mono);
  letter-spacing: var(--tracking-label);
  text-transform: uppercase;
}
</style>
