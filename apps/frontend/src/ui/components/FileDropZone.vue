<script setup lang="ts">
import { ref } from 'vue';
import UploadIcon from '../icons/UploadIcon.vue';
import { ANALYSED_FILE_EXTENSIONS } from '../fileTypes';

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

    <span class="icon-tile"><UploadIcon class="icon" /></span>
    <span class="title">{{ isDragging ? 'Release to analyse' : 'Drop a file here' }}</span>
    <span class="subtitle">or click to browse</span>

    <span class="chips">
      <span v-for="extension in ANALYSED_FILE_EXTENSIONS" :key="extension" class="chip">
        {{ extension.toUpperCase() }}
      </span>
    </span>
  </label>
</template>

<style scoped>
.drop-zone {
  display: block;
  position: relative;
  width: 100%;
  border: 1.5px dashed var(--border-strong);
  border-radius: var(--radius-panel);
  padding: 38px 20px;
  text-align: center;
  cursor: pointer;
  background: var(--surface-subtle);
  color: inherit;
  transition: all var(--motion-base) var(--motion-spring);
}

.drop-zone:hover,
.drop-zone:focus-within {
  border-color: rgba(255, 255, 255, 0.35);
  background: var(--surface-raised);
}

.drop-zone.dragging {
  border-color: rgba(255, 255, 255, 0.55);
  background: rgba(255, 255, 255, 0.09);
  transform: scale(1.016);
  box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.06), 0 0 40px rgba(120, 80, 255, 0.15);
}

.file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.icon-tile {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-panel);
  margin: 0 auto var(--space-xl);
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0.06));
  border: 1px solid var(--border-strong);
  border-top: 1px solid rgba(255, 255, 255, 0.3);
  box-shadow: var(--shadow-raised);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: all var(--motion-base);
}

.drop-zone:hover .icon-tile,
.drop-zone.dragging .icon-tile {
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0.1));
  color: rgba(255, 255, 255, 0.85);
  transform: translateY(-2px);
}

.icon {
  width: 26px;
  height: 26px;
}

.title {
  display: block;
  font-size: var(--text-size-title);
  font-weight: 600;
  color: rgba(255, 255, 255, 0.88);
  margin-bottom: var(--space-sm);
}

.subtitle {
  display: block;
  font-size: var(--text-size-small);
  color: var(--text-muted);
}

.chips {
  display: flex;
  gap: 5px;
  justify-content: center;
  flex-wrap: wrap;
  margin-top: var(--space-xl);
}

.chip {
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  background: var(--surface-raised);
  border: 1px solid var(--border-regular);
  font-size: var(--text-size-micro);
  font-weight: 500;
  color: rgba(255, 255, 255, 0.45);
  font-family: var(--font-mono);
  letter-spacing: 0.06em;
}
</style>
