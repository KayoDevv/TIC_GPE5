<script setup lang="ts">
import type { IconShape } from "~/types/icon";

withDefaults(defineProps<{ shape: IconShape; size?: number }>(), { size: 44 });

const state = useIconCycle();
</script>

<template>
  <IconsAnimatedIcon :shape="shape" :state="state" :size="size" />
</template>