<script setup lang="ts">
import { ref } from 'vue';

const emit = defineEmits<{ select: [file: File] }>();

const isDragging = ref(false);

function emitFirstFile(files: FileList | null | undefined): void {
  const file = files?.[0];
  if (file) {
    emit('select', file);
  }
}

function onDrop(event: DragEvent): void {
  isDragging.value = false;
  emitFirstFile(event.dataTransfer?.files);
}

function onPicked(event: Event): void {
  const input = event.target as HTMLInputElement;
  emitFirstFile(input.files);
  input.value = '';
}
</script>

<template>
  <label
    class="drop-zone"
    :class="{ dragging: isDragging }"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="onDrop"
  >
    <input
      class="file-input"
      type="file"
      aria-label="Choose a file to analyse"
      @change="onPicked"
    />

    <span class="overline">File to examine</span>
    <span class="message">
      {{ isDragging ? 'release to analyse.' : 'drop an attachment here, or click to choose one.' }}
    </span>
  </label>
</template>

<style scoped>
.drop-zone {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-md);
  min-height: 110px;
  padding: 18px var(--space-lg);
  border: 1px dashed var(--border-2);
  border-radius: var(--radius);
  cursor: pointer;
  transition:
    border-color var(--motion-fast),
    background-color var(--motion-fast);
}

.drop-zone:hover,
.drop-zone.dragging,
.drop-zone:focus-within {
  border-color: var(--or);
  background: var(--or-soft);
}

.file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.overline {
  font-family: var(--font-display);
  font-size: var(--text-size-overline);
  font-weight: 500;
  letter-spacing: var(--tracking-overline);
  text-transform: uppercase;
  color: var(--accent-text);
}

.message {
  max-width: 250px;
  font-size: var(--text-size-body);
  font-style: italic;
  line-height: 1.6;
  text-align: center;
  color: var(--muted);
}
</style>
