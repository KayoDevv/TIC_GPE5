<script setup lang="ts">
import { MousePointerClick } from "lucide-vue-next";
</script>

<template>
  <div id="product" class="relative mx-auto mt-14 max-w-6xl px-6">
    <div class="demo-enter relative">
      <div
        class="pointer-events-none absolute -inset-8 rounded-4xl opacity-[0.06] blur-[60px]"
        style="background: var(--gold)"
      />
      <div
        class="demo-float relative rounded-2xl border border-(--border) bg-(--card) p-4 sm:p-6"
        style="box-shadow: var(--shadow-product)"
      >
        <div class="mb-4 flex items-center justify-between">
          <div class="flex items-center gap-2 font-mono2 text-[11px] text-(--faint)">
            <MousePointerClick :size="13" style="color: var(--gold)" />
            démo interactive — cliquez sur « Télécharger »
          </div>
          <div class="hidden items-center gap-1.5 font-mono2 text-[10px] text-(--faint) sm:flex">
            <span class="h-1.5 w-1.5 rounded-full" style="background: var(--safe)" />
            live
          </div>
        </div>
        <DemoBrowserDemo />
      </div>
    </div>
  </div>
</template>

<style scoped>
.demo-enter {
  opacity: 0;
  animation: demo-enter 0.8s ease-out 0.35s forwards;
}
@keyframes demo-enter {
  from {
    opacity: 0;
    transform: translateY(40px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.demo-float {
  animation: demo-float 7s ease-in-out infinite;
}
@keyframes demo-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-6px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .demo-enter {
    animation: none;
    opacity: 1;
  }
  .demo-float {
    animation: none;
  }
}
</style>