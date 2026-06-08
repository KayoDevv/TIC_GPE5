<script setup lang="ts">
import { computed, ref } from 'vue';
import { ApiError, runAnalysis, type VerdictDecision, type VerdictMessage } from '../../src/p0/network';
import { loadSettings } from '../../src/p0/settings';
import { resolveJwtTokenAutomatically } from '../../src/p0/tokenResolver';

const selectedFile = ref<File | null>(null);
const dragging = ref(false);
const busy = ref(false);
const status = ref('Drop a file to start.');
const verdict = ref<VerdictMessage | null>(null);
const timeout = ref(false);
const error = ref<string | null>(null);
const tokenSource = ref<'cached' | 'active-tab' | null>(null);

const statusClass = computed(() => {
  if (timeout.value) {
    return 'status status-warning';
  }

  if (!verdict.value) {
    return error.value ? 'status status-error' : 'status status-neutral';
  }

  const map: Record<VerdictDecision, string> = {
    allowed: 'status status-allowed',
    blocked: 'status status-blocked',
    warning: 'status status-warning'
  };

  return map[verdict.value.final_decision];
});

function onDrop(event: DragEvent): void {
  event.preventDefault();
  dragging.value = false;

  const file = event.dataTransfer?.files?.[0];
  if (!file) {
    return;
  }

  selectedFile.value = file;
  void startFlow();
}

function onFilePicked(event: Event): void {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];

  if (!file) {
    return;
  }

  selectedFile.value = file;
  void startFlow();
}

async function startFlow(): Promise<void> {
  if (busy.value || !selectedFile.value) {
    return;
  }

  busy.value = true;
  error.value = null;
  verdict.value = null;
  timeout.value = false;
  tokenSource.value = null;

  status.value = `Uploading ${selectedFile.value.name}...`;

  try {
    const settings = await loadSettings();
    const previousToken = settings.cachedJwtToken;
    const resolvedToken = await resolveJwtTokenAutomatically();
    tokenSource.value = previousToken === resolvedToken ? 'cached' : 'active-tab';

    status.value = 'Waiting for verdict...';

    const outcome = await runAnalysis({
      apiBaseUrl: settings.apiBaseUrl,
      jwtToken: resolvedToken,
      file: selectedFile.value
    });

    if (outcome.kind === 'timeout') {
      timeout.value = true;
      status.value = `Timed out for job ${outcome.jobId}.`;
      return;
    }

    verdict.value = outcome.verdict;
    status.value = `${outcome.verdict.final_decision.toUpperCase()} for job ${outcome.jobId}.`;
  } catch (caughtError: unknown) {
    const message =
      caughtError instanceof ApiError
        ? caughtError.message
        : caughtError instanceof Error
          ? caughtError.message
          : 'Unknown error during analysis.';

    error.value = message;
    status.value = 'Flow failed.';
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="shell">
    <h1>P0 File Analysis</h1>

    <label
      class="dropzone"
      :class="{ dragging, disabled: busy }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop="onDrop"
    >
      <input class="hidden-input" type="file" :disabled="busy" @change="onFilePicked" />
      <span v-if="!busy">Drop file here or click to choose</span>
      <span v-else>Running analysis...</span>
    </label>

    <p :class="statusClass">{{ status }}</p>
    <p v-if="tokenSource === 'active-tab'" class="meta">Token source: active tab session</p>
    <p v-else-if="tokenSource === 'cached'" class="meta">Token source: cached session token</p>

    <p v-if="selectedFile" class="meta">File: {{ selectedFile.name }}</p>

    <section v-if="verdict" class="verdict">
      <h2>Decision: {{ verdict.final_decision }}</h2>
      <p v-if="verdict.user_explanation">{{ verdict.user_explanation }}</p>
      <p class="meta">Timestamp: {{ verdict.timestamp }}</p>

      <div v-if="verdict.technical_summary" class="tech-summary">
        <h3>Technical Summary</h3>
        <ul>
          <li v-if="verdict.technical_summary.ml_layer_score != null">
            ML Layer Score: {{ verdict.technical_summary.ml_layer_score }}
          </li>
          <li v-if="verdict.technical_summary.llm_layer_malicious != null">
            LLM Layer Malicious: {{ verdict.technical_summary.llm_layer_malicious ? 'Yes' : 'No' }}
          </li>
          <li v-if="verdict.technical_summary.sandbox_layer_timeout != null">
            Sandbox Timeout: {{ verdict.technical_summary.sandbox_layer_timeout ? 'Yes' : 'No' }}
          </li>
          <li v-if="verdict.technical_summary.sandbox_layer_iocs && verdict.technical_summary.sandbox_layer_iocs.length">
            IOCs Detected: {{ verdict.technical_summary.sandbox_layer_iocs.length }}
          </li>
        </ul>
      </div>
    </section>

    <p v-if="error" class="error">{{ error }}</p>
  </main>
</template>

<style scoped>
.shell {
  width: 360px;
  padding: 12px;
  display: grid;
  gap: 10px;
}

h1 {
  font-size: 16px;
  margin: 0;
}

.dropzone {
  border: 2px dashed #94a3b8;
  border-radius: 8px;
  padding: 18px 10px;
  text-align: center;
  cursor: pointer;
  background: #ffffff;
  position: relative;
}

.dropzone.dragging {
  border-color: #2563eb;
  background: #eff6ff;
}

.dropzone.disabled {
  opacity: 0.7;
  cursor: progress;
}

.hidden-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.status {
  margin: 0;
  font-size: 12px;
  padding: 8px;
  border-radius: 6px;
}

.status-neutral {
  background: #e2e8f0;
}

.status-allowed {
  background: #dcfce7;
  color: #166534;
}

.status-blocked {
  background: #fee2e2;
  color: #991b1b;
}

.status-warning {
  background: #ffedd5;
  color: #9a3412;
}

.status-error {
  background: #f1f5f9;
  color: #334155;
}

.verdict {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 8px;
  background: #ffffff;
}

.verdict h2 {
  margin: 0 0 6px;
  font-size: 13px;
}

.meta {
  margin: 0;
  color: #64748b;
  font-size: 11px;
}

.error {
  margin: 0;
  color: #b91c1c;
  font-size: 12px;
}

.tech-summary {
  margin-top: 8px;
  border-top: 1px solid #e2e8f0;
  padding-top: 6px;
}

.tech-summary h3 {
  margin: 0 0 4px;
  font-size: 12px;
}

.tech-summary ul {
  margin: 0;
  padding-left: 16px;
  font-size: 11px;
  color: #475569;
}

.tech-summary li {
  margin-bottom: 2px;
}
</style>
