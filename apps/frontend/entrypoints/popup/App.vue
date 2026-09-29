<script setup lang="ts">
import { computed, ref } from 'vue';
import AnalysisErrorPanel from '../../src/ui/components/AnalysisErrorPanel.vue';
import AnalysisProgress from '../../src/ui/components/AnalysisProgress.vue';
import AnalysisTabs from '../../src/ui/components/AnalysisTabs.vue';
import FileDropZone from '../../src/ui/components/FileDropZone.vue';
import HistoryPanel from '../../src/ui/components/HistoryPanel.vue';
import PopupFooter from '../../src/ui/components/PopupFooter.vue';
import PopupHeader from '../../src/ui/components/PopupHeader.vue';
import PopupShell from '../../src/ui/components/PopupShell.vue';
import VerdictPanel from '../../src/ui/components/VerdictPanel.vue';
import { snapshotState } from '../../src/ui/charonState';
import { readExtensionVersion } from '../../src/ui/extensionVersion';
import { useAnalysisSession, type AnalysisPhase } from '../../src/ui/useAnalysisSession';
import { useTheme } from '../../src/ui/useTheme';
import { buildVerdictDetails, presentSnapshot } from '../../src/ui/verdictPresentation';
import type { AnalysisTabKey } from '../../src/ui/analysisTabs';

const STATUS_LABELS: Record<AnalysisPhase, string> = {
  idle: 'Standby',
  analyzing: 'Scanning',
  completed: 'Complete',
  failed: 'Failed'
};

const {
  snapshot,
  phase,
  file,
  verdict,
  jobId,
  errorMessage,
  progressRatio,
  history,
  analyse,
  retry,
  reset
} = useAnalysisSession();

const { theme, toggleTheme } = useTheme();

const activeTab = ref<AnalysisTabKey>('analysis');
const extensionVersion = readExtensionVersion();

const statusLabel = computed(() => STATUS_LABELS[phase.value]);

const verdictPresentation = computed(() => presentSnapshot(snapshot.value));
const charonState = computed(() => snapshotState(snapshot.value));

const verdictDetails = computed(() => buildVerdictDetails(verdict.value?.technical_summary));

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
          <FileDropZone v-if="phase === 'idle'" @select="analyse" />

          <AnalysisProgress
            v-else-if="phase === 'analyzing' && file"
            :file-name="file.name"
            :progress-ratio="progressRatio"
          />

          <VerdictPanel
            v-else-if="phase === 'completed' && verdictPresentation"
            :presentation="verdictPresentation"
            :file="file"
            :details="verdictDetails"
            :job-id="jobId"
            @restart="reset"
          />

          <AnalysisErrorPanel
            v-else-if="phase === 'failed' && errorMessage"
            :message="errorMessage"
            @retry="retry"
            @restart="reset"
          />
        </template>

        <HistoryPanel v-else :entries="history" />
      </div>

      <PopupFooter :version="extensionVersion" />
    </PopupShell>
  </main>
</template>

<style scoped>
.body {
  min-height: 110px;
  padding: 0 var(--space-xl);
}
</style>
