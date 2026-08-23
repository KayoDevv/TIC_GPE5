<script setup lang="ts">
import ShieldIcon from '../icons/ShieldIcon.vue';
</script>

<template>
  <div class="orb" role="presentation">
    <span class="ring first" />
    <span class="ring second" />
    <span class="halo" />
    <span class="core"><ShieldIcon class="core-icon" /></span>
    <span class="scan"><span class="scan-line" /></span>
  </div>
</template>

<style scoped>
.orb {
  position: relative;
  width: 130px;
  height: 130px;
  margin: var(--space-lg) auto var(--space-xl);
  display: flex;
  align-items: center;
  justify-content: center;
}

.ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.28);
}

.ring.first {
  animation: pulse-outer 1.5s ease-out infinite;
}

.ring.second {
  animation: pulse-inner 1.5s ease-out infinite;
}

.halo {
  position: absolute;
  inset: var(--space-lg);
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: radial-gradient(circle, rgba(255, 255, 255, 0.08) 0%, transparent 70%);
}

.core {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: radial-gradient(
    circle at 35% 30%,
    rgba(255, 255, 255, 0.35) 0%,
    rgba(255, 255, 255, 0.12) 50%,
    transparent 80%
  );
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-top: 1px solid rgba(255, 255, 255, 0.5);
  box-shadow: 0 0 40px rgba(255, 255, 255, 0.15), 0 0 80px rgba(120, 80, 255, 0.2);
  animation: heartbeat 1.5s ease-in-out infinite;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.8);
}

.core-icon {
  width: 18px;
  height: 18px;
}

.scan {
  position: absolute;
  inset: var(--space-lg);
  border-radius: 50%;
  overflow: hidden;
  pointer-events: none;
}

.scan-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.55), transparent);
  animation: sweep 1.8s linear infinite;
}

@keyframes heartbeat {
  0% {
    transform: scale(1);
    opacity: 0.72;
  }
  14% {
    transform: scale(1.11);
    opacity: 1;
  }
  28% {
    transform: scale(1);
    opacity: 0.72;
  }
  42% {
    transform: scale(1.06);
    opacity: 0.9;
  }
  100% {
    transform: scale(1);
    opacity: 0.72;
  }
}

@keyframes pulse-outer {
  0% {
    transform: scale(0.74);
    opacity: 0.55;
  }
  14% {
    transform: scale(1.65);
    opacity: 0;
  }
  100% {
    transform: scale(0.74);
    opacity: 0;
  }
}

@keyframes pulse-inner {
  0% {
    transform: scale(0.74);
    opacity: 0;
  }
  42% {
    transform: scale(0.74);
    opacity: 0.45;
  }
  70% {
    transform: scale(1.55);
    opacity: 0;
  }
  100% {
    transform: scale(0.74);
    opacity: 0;
  }
}

@keyframes sweep {
  0% {
    top: 0%;
    opacity: 0.55;
  }
  50% {
    top: 100%;
    opacity: 0.22;
  }
  100% {
    top: 0%;
    opacity: 0.55;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ring,
  .core,
  .scan-line {
    animation: none;
  }
}
</style>
