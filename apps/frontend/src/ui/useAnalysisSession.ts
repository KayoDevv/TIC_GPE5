/** Live view of the background worker's analysis, shared by the popup and the side tab. */

import { computed, onScopeDispose, ref, watch, type ComputedRef, type Ref } from 'vue';
import {
  encodeFile,
  RESET_MESSAGE,
  RETRY_MESSAGE,
  sendToBackground
} from '../p0/fileMessage';
import { loadHistory, watchHistory, type HistoryEntry } from '../p0/history';
import type { VerdictMessage } from '../p0/network';
import {
  ANALYSIS_TIMEOUT_MS,
  IDLE_SNAPSHOT,
  loadSnapshot,
  watchSnapshot,
  type AnalysisSnapshot,
  type SessionFile,
  type SessionPhase
} from '../p0/session';

export type { HistoryEntry, SessionFile };
export type AnalysisPhase = SessionPhase;

export interface AnalysisSession {
  snapshot: Ref<AnalysisSnapshot>;
  phase: ComputedRef<AnalysisPhase>;
  file: ComputedRef<SessionFile | null>;
  verdict: ComputedRef<VerdictMessage | null>;
  jobId: ComputedRef<string | null>;
  hasTimedOut: ComputedRef<boolean>;
  errorMessage: ComputedRef<string | null>;
  progressRatio: ComputedRef<number>;
  history: Ref<HistoryEntry[]>;
  analyse: (file: File) => Promise<void>;
  retry: () => Promise<void>;
  reset: () => Promise<void>;
}

const PROGRESS_TICK_MS = 250;
const MAX_PENDING_PROGRESS_RATIO = 0.98;
const COMPLETED_PROGRESS_RATIO = 1;

export async function requestAnalysis(file: File): Promise<void> {
  await sendToBackground(await encodeFile(file));
}

export function useSessionSnapshot(): Ref<AnalysisSnapshot> {
  const snapshot = ref<AnalysisSnapshot>(IDLE_SNAPSHOT);
  let changed = false;

  const stop = watchSnapshot((value) => {
    changed = true;
    snapshot.value = value;
  });
  void loadSnapshot().then((value) => {
    // A change that arrived while storage was being read is the newer state.
    if (!changed) {
      snapshot.value = value;
    }
  });
  onScopeDispose(stop);

  return snapshot;
}

export function useAnalysisSession(): AnalysisSession {
  const snapshot = useSessionSnapshot();
  const history = ref<HistoryEntry[]>([]);
  const now = ref(Date.now());
  let ticker: ReturnType<typeof setInterval> | null = null;

  void loadHistory().then((entries) => {
    history.value = entries;
  });
  const stopHistory = watchHistory((entries) => {
    history.value = entries;
  });

  const phase = computed(() => snapshot.value.phase);

  function stopTicker(): void {
    if (ticker !== null) {
      clearInterval(ticker);
      ticker = null;
    }
  }

  watch(
    phase,
    (value) => {
      stopTicker();
      if (value === 'analyzing') {
        now.value = Date.now();
        ticker = setInterval(() => (now.value = Date.now()), PROGRESS_TICK_MS);
      }
    },
    { immediate: true }
  );

  onScopeDispose(() => {
    stopTicker();
    stopHistory();
  });

  const progressRatio = computed(() => {
    if (phase.value === 'completed') {
      return COMPLETED_PROGRESS_RATIO;
    }

    const startedAt = snapshot.value.startedAt;
    if (phase.value !== 'analyzing' || startedAt === null) {
      return 0;
    }

    return Math.min((now.value - startedAt) / ANALYSIS_TIMEOUT_MS, MAX_PENDING_PROGRESS_RATIO);
  });

  return {
    snapshot,
    phase,
    file: computed(() => snapshot.value.file),
    verdict: computed(() => snapshot.value.verdict),
    jobId: computed(() => snapshot.value.jobId),
    hasTimedOut: computed(() => snapshot.value.timedOut),
    errorMessage: computed(() => snapshot.value.error),
    progressRatio,
    history,
    analyse: requestAnalysis,
    retry: () => sendToBackground({ type: RETRY_MESSAGE }),
    reset: () => sendToBackground({ type: RESET_MESSAGE })
  };
}
