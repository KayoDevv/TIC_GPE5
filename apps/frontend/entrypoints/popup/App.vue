<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import AnalysisErrorPanel from '../../src/ui/components/AnalysisErrorPanel.vue';
import AnalysisProgress from '../../src/ui/components/AnalysisProgress.vue';
import AnalysisTabs from '../../src/ui/components/AnalysisTabs.vue';
import FileDropZone from '../../src/ui/components/FileDropZone.vue';
import HistoryPanel from '../../src/ui/components/HistoryPanel.vue';
import PopupFooter from '../../src/ui/components/PopupFooter.vue';
import PopupHeader from '../../src/ui/components/PopupHeader.vue';
import PopupShell from '../../src/ui/components/PopupShell.vue';
import VerdictPanel from '../../src/ui/components/VerdictPanel.vue';
import { connectToolbarIcon, resolveCharonState } from '../../src/ui/charonState';
import { readExtensionVersion } from '../../src/ui/extensionVersion';
import {
  useAnalysisSession,
  type AnalysisPhase,
  type TokenSource
} from '../../src/ui/useAnalysisSession';
import { useTheme } from '../../src/ui/useTheme';
import {
  buildVerdictDetails,
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
  history,
  selectFile,
  startAnalysis,
  reset
} = useAnalysisSession();

const { theme, toggleTheme } = useTheme();
const showToolbarState = connectToolbarIcon();

const activeTab = ref<AnalysisTabKey>('analysis');
const extensionVersion = readExtensionVersion();

const statusLabel = computed(() => STATUS_LABELS[phase.value]);
const sessionLabel = computed(() =>
  tokenSource.value ? TOKEN_SOURCE_LABELS[tokenSource.value] : UNRESOLVED_SESSION_LABEL
);

const verdictPresentation = computed<VerdictPresentation | null>(() => {
  if (hasTimedOut.value) {
    return TIMEOUT_PRESENTATION;
  }

  return verdict.value ? presentVerdict(verdict.value) : null;
});

const charonState = computed(() =>
  resolveCharonState(phase.value, verdictPresentation.value?.tone ?? null)
);

const verdictDetails = computed(() => buildVerdictDetails(verdict.value?.technical_summary));

watch(charonState, showToolbarState);

function analyse(file: File): void {
  selectFile(file);
  void startAnalysis();
}

function closePopup(): void {
  window.close();
}
</script>

<template>
  <main class="popup">
    <PopupShell :state="charonState">
      <PopupHeader
        :state="charonState"
        :status-label="statusLabel"
        :theme="theme"
        @toggle-theme="toggleTheme"
        @close="closePopup"
      />
      <AnalysisTabs v-model:active-tab="activeTab" />

      <div class="body">
        <template v-if="activeTab === 'analysis'">
          <FileDropZone v-if="phase === 'idle' || phase === 'selected'" @select="analyse" />

          <AnalysisProgress
            v-else-if="phase === 'analyzing' && selectedFile"
            :file-name="selectedFile.name"
            :progress-ratio="progressRatio"
          />

          <VerdictPanel
            v-else-if="phase === 'completed' && verdictPresentation"
            :presentation="verdictPresentation"
            :file="selectedFile"
            :details="verdictDetails"
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

        <HistoryPanel v-else :entries="history" />
      </div>

      <PopupFooter :version="extensionVersion" :session-label="sessionLabel" />
    </PopupShell>
  </main>
</template>

<style scoped>
.body {
  min-height: 110px;
  padding: 0 var(--space-xl);
}
</style>
