/** Popup state machine driving the P0 analysis flow exposed by `src/p0`. */

import { onScopeDispose, ref, type Ref } from 'vue';
import { loadHistory, recordHistory, type HistoryEntry } from '../p0/history';
import { ApiError, runAnalysis, type AnalysisOutcome, type VerdictMessage } from '../p0/network';
import { loadSettings } from '../p0/settings';
import { resolveJwtTokenAutomatically } from '../p0/tokenResolver';

export type { HistoryEntry };

export type AnalysisPhase = 'idle' | 'selected' | 'analyzing' | 'completed' | 'failed';
export type TokenSource = 'cached' | 'active-tab';

export interface AnalysisSession {
  phase: Ref<AnalysisPhase>;
  selectedFile: Ref<File | null>;
  verdict: Ref<VerdictMessage | null>;
  jobId: Ref<string | null>;
  hasTimedOut: Ref<boolean>;
  errorMessage: Ref<string | null>;
  tokenSource: Ref<TokenSource | null>;
  progressRatio: Ref<number>;
  history: Ref<HistoryEntry[]>;
  selectFile: (file: File) => void;
  startAnalysis: () => Promise<void>;
  reset: () => void;
}

interface ResolvedToken {
  token: string;
  source: TokenSource;
}

const ANALYSIS_TIMEOUT_MS = 130_000;
const PROGRESS_TICK_MS = 250;
const MAX_PENDING_PROGRESS_RATIO = 0.98;
const COMPLETED_PROGRESS_RATIO = 1;
const UNKNOWN_ERROR_MESSAGE = 'Unknown error during analysis.';
const TIMEOUT_HISTORY_DECISION = 'warning';

function describeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }

  return UNKNOWN_ERROR_MESSAGE;
}

async function resolveToken(cachedToken: string): Promise<ResolvedToken> {
  const token = await resolveJwtTokenAutomatically();
  return { token, source: token === cachedToken ? 'cached' : 'active-tab' };
}

export function useAnalysisSession(): AnalysisSession {
  const phase = ref<AnalysisPhase>('idle');
  const selectedFile = ref<File | null>(null);
  const verdict = ref<VerdictMessage | null>(null);
  const jobId = ref<string | null>(null);
  const hasTimedOut = ref(false);
  const errorMessage = ref<string | null>(null);
  const tokenSource = ref<TokenSource | null>(null);
  const progressRatio = ref(0);
  const history = ref<HistoryEntry[]>([]);

  void loadHistory().then((entries) => {
    history.value = entries;
  });

  let progressTimer: ReturnType<typeof setInterval> | null = null;

  function stopProgressTimer(): void {
    if (progressTimer !== null) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
  }

  function startProgressTimer(): void {
    stopProgressTimer();
    const startedAt = Date.now();

    progressTimer = setInterval(() => {
      const elapsedRatio = (Date.now() - startedAt) / ANALYSIS_TIMEOUT_MS;
      progressRatio.value = Math.min(elapsedRatio, MAX_PENDING_PROGRESS_RATIO);
    }, PROGRESS_TICK_MS);
  }

  function clearOutcome(): void {
    verdict.value = null;
    jobId.value = null;
    hasTimedOut.value = false;
    errorMessage.value = null;
    progressRatio.value = 0;
  }

  function selectFile(file: File): void {
    stopProgressTimer();
    clearOutcome();
    selectedFile.value = file;
    tokenSource.value = null;
    phase.value = 'selected';
  }

  function reset(): void {
    stopProgressTimer();
    clearOutcome();
    selectedFile.value = null;
    tokenSource.value = null;
    phase.value = 'idle';
  }

  function applyOutcome(file: File, outcome: AnalysisOutcome): void {
    jobId.value = outcome.jobId;
    hasTimedOut.value = outcome.kind === 'timeout';
    verdict.value = outcome.kind === 'verdict' ? outcome.verdict : null;
    progressRatio.value = COMPLETED_PROGRESS_RATIO;
    phase.value = 'completed';

    void recordHistory({
      name: file.name,
      decision: verdict.value?.final_decision ?? TIMEOUT_HISTORY_DECISION,
      score: verdict.value?.technical_summary?.ml_layer_score ?? null,
      time: Date.now()
    }).then((entries) => {
      history.value = entries;
    });
  }

  async function startAnalysis(): Promise<void> {
    const file = selectedFile.value;
    if (!file || phase.value === 'analyzing') {
      return;
    }

    clearOutcome();
    phase.value = 'analyzing';
    startProgressTimer();

    try {
      const settings = await loadSettings();
      const resolved = await resolveToken(settings.cachedJwtToken);
      tokenSource.value = resolved.source;

      applyOutcome(
        file,
        await runAnalysis({
          apiBaseUrl: settings.apiBaseUrl,
          jwtToken: resolved.token,
          file,
          timeoutMs: ANALYSIS_TIMEOUT_MS
        })
      );
    } catch (error: unknown) {
      errorMessage.value = describeError(error);
      phase.value = 'failed';
    } finally {
      stopProgressTimer();
    }
  }

  onScopeDispose(stopProgressTimer);

  return {
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
  };
}
