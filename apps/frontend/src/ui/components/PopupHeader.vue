<script setup lang="ts">
import CharonGlyph from '../icons/CharonGlyph.vue';
import type { CharonState } from '../charonState';
import type { Theme } from '../useTheme';

defineProps<{ state: CharonState; statusLabel: string; theme: Theme }>();
defineEmits<{ toggleTheme: []; close: [] }>();
</script>

<template>
  <header class="header" :class="state">
    <div class="lockup">
      <span class="glyph" role="img" :aria-label="statusLabel" :title="statusLabel">
        <CharonGlyph class="glyph-icon" :state="state" />
      </span>
      <span class="title">Charon</span>
    </div>

    <div class="actions">
      <button
        type="button"
        class="icon-button"
        :aria-label="theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
        @click="$emit('toggleTheme')"
      >
        <svg v-if="theme === 'dark'" viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <circle cx="7" cy="7" r="2.6" stroke="currentColor" stroke-width="1.1" />
          <path
            d="M7 1v1.6M7 11.4V13M1 7h1.6M11.4 7H13M2.8 2.8l1.1 1.1M10.1 10.1l1.1 1.1M11.2 2.8l-1.1 1.1M3.9 10.1l-1.1 1.1"
            stroke="currentColor"
            stroke-width="1.1"
            stroke-linecap="round"
          />
        </svg>
        <svg v-else viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <path
            d="M11.8 8.6A5.2 5.2 0 0 1 5.4 2.2a5.2 5.2 0 1 0 6.4 6.4Z"
            stroke="currentColor"
            stroke-width="1.1"
            stroke-linejoin="round"
          />
        </svg>
      </button>
      <button type="button" class="icon-button" aria-label="Close" @click="$emit('close')">
        <svg class="close-icon" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
        </svg>
      </button>
    </div>
  </header>
</template>

<style scoped>
.header {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
  padding: 2px var(--space-xl) 0;
}

.lockup {
  display: flex;
  align-items: center;
  gap: 9px;
}

.glyph {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  color: var(--state-color);
}

.glyph-icon {
  width: 16px;
  height: 16px;
}

.title {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: var(--text-size-title);
  letter-spacing: var(--tracking-title);
  text-transform: uppercase;
  color: var(--text);
  /* Recentres the lockup: the trailing letter-spacing would push it left. */
  transform: translateX(0.12em);
}

.analyzing .title,
.allowed .title,
.warning .title,
.blocked .title {
  color: var(--state-color);
}

.actions {
  position: absolute;
  top: 50%;
  right: var(--space-md);
  display: flex;
  gap: 2px;
  transform: translateY(-50%);
}

.icon-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius);
  color: var(--muted);
  cursor: pointer;
  transition:
    color var(--motion-fast),
    background-color var(--motion-fast);
}

.icon-button:hover {
  color: var(--text);
  background: var(--card-2);
}

.icon-button svg {
  width: 14px;
  height: 14px;
}

.icon-button .close-icon {
  width: 12px;
  height: 12px;
}

/* Motion grammar: idle breathes, analysis turns, suspicion wavers. */
.idle .glyph-icon {
  animation: breathe 4.5s ease-in-out infinite;
}

.analyzing .glyph-icon {
  animation: spin 1.4s linear infinite;
}

.warning .glyph {
  animation: waver 2.2s ease-in-out infinite;
}

@keyframes breathe {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.55;
    transform: scale(0.94);
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes waver {
  0%,
  100% {
    transform: rotate(0deg);
  }
  20% {
    transform: rotate(-4deg);
  }
  45% {
    transform: rotate(3deg);
  }
  60% {
    transform: rotate(-2deg);
  }
  80% {
    transform: rotate(1.5deg);
  }
}
</style>
