<script setup lang="ts">
import { computed } from 'vue';
import { formatFileSize } from '../fileSize';
import { resolveFileGlyph } from '../fileTypes';

const props = withDefaults(defineProps<{ file: File; removable?: boolean }>(), {
  removable: false
});

defineEmits<{ remove: [] }>();

const glyph = computed(() => resolveFileGlyph(props.file.name));
const size = computed(() => formatFileSize(props.file.size));
</script>

<template>
  <div class="file-card">
    <span class="glyph">{{ glyph }}</span>

    <span class="details">
      <span class="name">{{ props.file.name }}</span>
      <span class="size">{{ size }}</span>
    </span>

    <button
      v-if="props.removable"
      type="button"
      class="remove"
      aria-label="Remove selected file"
      @click="$emit('remove')"
    >
      ×
    </button>
  </div>
</template>

<style scoped>
.file-card {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  border-radius: var(--radius-control);
  background: var(--surface-raised);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-top: 1px solid rgba(255, 255, 255, 0.16);
  box-shadow: var(--shadow-inset-highlight);
}

.glyph {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-inset);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid var(--border-regular);
}

.details {
  flex: 1;
  overflow: hidden;
}

.name {
  display: block;
  font-size: var(--text-size-body);
  font-weight: 600;
  color: rgba(255, 255, 255, 0.88);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.size {
  display: block;
  font-size: var(--text-size-label);
  color: var(--text-muted);
  margin-top: 2px;
  font-family: var(--font-mono);
}

.remove {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  border: none;
  background: var(--surface-raised);
  color: rgba(255, 255, 255, 0.45);
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--motion-fast);
  flex-shrink: 0;
}

.remove:hover {
  background: var(--tone-blocked-glow);
  color: var(--tone-blocked);
}
</style>
