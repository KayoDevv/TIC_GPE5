<script setup lang="ts">
import type { Component } from "vue";
import type { IconShape, IconState } from "~/types/icon";
import IconEye from "./shapes/IconEye.vue";
import IconBoat from "./shapes/IconBoat.vue";
import IconVirus from "./shapes/IconVirus.vue";
import IconRing from "./shapes/IconRing.vue";
import IconLantern from "./shapes/IconLantern.vue";

const props = withDefaults(
  defineProps<{
    shape: IconShape;
    state: IconState;
    size?: number;
    color?: string;
  }>(),
  { size: 48 },
);

const shapeComponents: Partial<Record<IconShape, Component>> = {
  eye: IconEye,
  boat: IconBoat,
  virus: IconVirus,
  ring: IconRing,
  lantern: IconLantern,
};

const resolvedColor = computed(() => props.color ?? stateColor(props.state));
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 48 48" fill="none" class="block">
    <component
      :is="shapeComponents[shape]"
      v-if="shapeComponents[shape]"
      :state="state"
      :color="resolvedColor"
    />
  </svg>
</template>