/** Runs one analysis in the background worker and publishes each step as the shared snapshot. */

import { recordHistory } from './history';
import { ApiError, runAnalysis } from './network';
import {
  ANALYSIS_TIMEOUT_MS,
  IDLE_SNAPSHOT,
  loadSnapshot,
  saveSnapshot,
  type AnalysisSnapshot
} from './session';
import { loadSettings } from './settings';
import { resolveJwtTokenAutomatically } from './tokenResolver';

// Sent when no SSO token was found. The backend answers it: accepted in dev mode, 401 once SSO
// is enforced, and that error is what the user then sees.
const ANONYMOUS_TOKEN = 'anonymous';
const TIMEOUT_HISTORY_DECISION = 'warning';
const UNKNOWN_ERROR_MESSAGE = 'Unknown error during analysis.';
const INTERRUPTED_MESSAGE = 'The analysis was interrupted. Choose the file again.';
const FILE_GONE_MESSAGE = 'The file is no longer available. Choose it again.';
// Chrome stops an idle MV3 service worker after 30 s and the verdict WebSocket stays silent for
// up to 150 s; any extension API call resets that idle timer.
const KEEP_ALIVE_MS = 20_000;

let running = false;
let lastFile: File | null = null;

function describeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }

  return UNKNOWN_ERROR_MESSAGE;
}

function keepWorkerAlive(): () => void {
  if (typeof chrome === 'undefined' || !chrome.runtime?.getPlatformInfo) {
    return () => {};
  }

  const timer = setInterval(() => void chrome.runtime.getPlatformInfo(), KEEP_ALIVE_MS);
  return () => clearInterval(timer);
}

// One analysis at a time: a file sent while one runs is ignored, as the drop zones say.
export async function analyseFile(file: File): Promise<void> {
  if (running) {
    return;
  }

  running = true;
  lastFile = file;
  const started: AnalysisSnapshot = {
    ...IDLE_SNAPSHOT,
    phase: 'analyzing',
    file: { name: file.name, size: file.size },
    startedAt: Date.now()
  };
  await saveSnapshot(started);
  const release = keepWorkerAlive();

  let completed: AnalysisSnapshot;
  try {
    const settings = await loadSettings();
    const outcome = await runAnalysis({
      apiBaseUrl: settings.apiBaseUrl,
      jwtToken: (await resolveJwtTokenAutomatically()) ?? ANONYMOUS_TOKEN,
      file,
      timeoutMs: ANALYSIS_TIMEOUT_MS
    });
    completed = {
      ...started,
      phase: 'completed',
      verdict: outcome.kind === 'verdict' ? outcome.verdict : null,
      jobId: outcome.jobId,
      timedOut: outcome.kind === 'timeout'
    };
    await saveSnapshot(completed);
  } catch (error: unknown) {
    await saveSnapshot({ ...started, phase: 'failed', error: describeError(error) });
    return;
  } finally {
    release();
    running = false;
  }

  // History is a convenience: a failed write must not turn a delivered verdict into an error.
  await recordHistory({
    name: file.name,
    decision: completed.verdict?.final_decision ?? TIMEOUT_HISTORY_DECISION,
    score: completed.verdict?.technical_summary?.ml_layer_score ?? null,
    time: Date.now()
  }).catch(() => undefined);
}

export async function retryLastFile(): Promise<void> {
  if (lastFile) {
    await analyseFile(lastFile);
    return;
  }

  const snapshot = await loadSnapshot();
  await saveSnapshot({ ...snapshot, phase: 'failed', error: FILE_GONE_MESSAGE });
}

export async function resetSession(): Promise<void> {
  if (!running) {
    await saveSnapshot(IDLE_SNAPSHOT);
  }
}

// A worker that (re)starts cannot be mid-analysis: a running one is kept alive until it ends.
export async function recoverInterruptedSession(): Promise<void> {
  const snapshot = await loadSnapshot();
  if (snapshot.phase === 'analyzing') {
    await saveSnapshot({ ...snapshot, phase: 'failed', error: INTERRUPTED_MESSAGE });
  }
}
