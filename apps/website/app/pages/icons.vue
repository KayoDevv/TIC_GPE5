<script setup lang="ts">
import { ICON_SHAPES, ICON_STATES } from "~/types/icon";
</script>

<template>
  <main class="mx-auto max-w-4xl px-6 pb-24 pt-40">
    <h1 class="font-display text-2xl text-(--text)">Banc d'essai — icônes</h1>
    <div class="mt-8 grid grid-cols-6 gap-4">
      <div />
      <p
        v-for="state in ICON_STATES"
        :key="state"
        class="text-center font-mono2 text-[10px] uppercase text-(--faint)"
      >
        {{ state }}
      </p>
      <template v-for="shape in ICON_SHAPES" :key="shape">
        <p class="self-center font-mono2 text-[10px] uppercase text-(--faint)">
          {{ shape }}
        </p>
        <div
          v-for="state in ICON_STATES"
          :key="state"
          class="grid place-items-center rounded-xl border border-(--border) bg-(--card) p-3"
        >
          <IconsAnimatedIcon :shape="shape" :state="state" :size="42" />
        </div>
      </template>
    </div>
  </main>
</template>