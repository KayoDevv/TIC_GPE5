<script setup lang="ts">
import { computed, ref } from 'vue';
import AnalysisErrorPanel from '../../src/ui/components/AnalysisErrorPanel.vue';
import AnalysisProgress from '../../src/ui/components/AnalysisProgress.vue';
import AnalysisTabs from '../../src/ui/components/AnalysisTabs.vue';
import ComingSoonPanel from '../../src/ui/components/ComingSoonPanel.vue';
import FileDropZone from '../../src/ui/components/FileDropZone.vue';
import GlassButton from '../../src/ui/components/GlassButton.vue';
import GlassShell from '../../src/ui/components/GlassShell.vue';
import PopupFooter from '../../src/ui/components/PopupFooter.vue';
import PopupHeader from '../../src/ui/components/PopupHeader.vue';
import SelectedFileCard from '../../src/ui/components/SelectedFileCard.vue';
import VerdictPanel from '../../src/ui/components/VerdictPanel.vue';
import { readExtensionVersion } from '../../src/ui/extensionVersion';
import {
  useAnalysisSession,
  type AnalysisPhase,
  type TokenSource
} from '../../src/ui/useAnalysisSession';
import {
  buildSummaryMetrics,
  presentVerdict,
  TIMEOUT_PRESENTATION,
  type VerdictPresentation
} from '../../src/ui/verdictPresentation';
import type { AnalysisTabKey } from '../../src/ui/analysisTabs';

const STATUS_LABELS: Record<AnalysisPhase, string> = {
  idle: 'Standby',
  selected: 'Ready',
  analyzing: 'Scanning',
  completed: 'Complete',
  failed: 'Failed'
};

const TOKEN_SOURCE_LABELS: Record<TokenSource, string> = {
  cached: 'Session token: cached',
  'active-tab': 'Session token: active tab'
};

const UNRESOLVED_SESSION_LABEL = 'Session token: not resolved';

const {
  phase,
  selectedFile,
  verdict,
  jobId,
  hasTimedOut,
  errorMessage,
  tokenSource,
  progressRatio,
  selectFile,
  startAnalysis,
  reset
} = useAnalysisSession();

const activeTab = ref<AnalysisTabKey>('file');
const extensionVersion = readExtensionVersion();

const statusLabel = computed(() => STATUS_LABELS[phase.value]);
const isPipelineActive = computed(() => phase.value === 'analyzing' || phase.value === 'completed');
const sessionLabel = computed(() =>
  tokenSource.value ? TOKEN_SOURCE_LABELS[tokenSource.value] : UNRESOLVED_SESSION_LABEL
);

const verdictPresentation = computed<VerdictPresentation | null>(() => {
  if (hasTimedOut.value) {
    return TIMEOUT_PRESENTATION;
  }

  return verdict.value ? presentVerdict(verdict.value) : null;
});

const summaryMetrics = computed(() => buildSummaryMetrics(verdict.value?.technical_summary));
</script>

<template>
  <main class="popup">
    <GlassShell>
      <PopupHeader :status-label="statusLabel" :is-active="isPipelineActive" />
      <AnalysisTabs v-model:active-tab="activeTab" />

      <div class="body">
        <template v-if="activeTab === 'file'">
          <template v-if="phase === 'idle' || phase === 'selected'">
            <FileDropZone @select="selectFile" />

            <div v-if="selectedFile" class="selection">
              <SelectedFileCard :file="selectedFile" removable @remove="reset" />
              <GlassButton @click="startAnalysis">Start analysis</GlassButton>
            </div>
          </template>

          <AnalysisProgress
            v-else-if="phase === 'analyzing' && selectedFile"
            :file-name="selectedFile.name"
            :progress-ratio="progressRatio"
          />

          <VerdictPanel
            v-else-if="phase === 'completed' && verdictPresentation"
            :presentation="verdictPresentation"
            :file="selectedFile"
            :metrics="summaryMetrics"
            :job-id="jobId"
            @restart="reset"
          />

          <AnalysisErrorPanel
            v-else-if="phase === 'failed' && errorMessage"
            :message="errorMessage"
            @retry="startAnalysis"
            @restart="reset"
          />
        </template>

        <ComingSoonPanel v-else />
      </div>

      <PopupFooter :version="extensionVersion" :session-label="sessionLabel" />
    </GlassShell>
  </main>
</template>

<style scoped>
.popup {
  display: flex;
  justify-content: center;
}

.body {
  padding: 20px var(--space-xl) var(--space-2xl);
  min-height: 260px;
}

.selection {
  display: grid;
  gap: var(--space-lg);
  margin-top: var(--space-lg);
}
</style>
