/** The analysis in flight, written by the background worker and read by the popup and side tab. */

import type { VerdictMessage } from './network';
import { canUseChromeStorage, watchStorageKey } from './storage';

export type SessionPhase = 'idle' | 'analyzing' | 'completed' | 'failed';

export interface SessionFile {
  name: string;
  size: number;
}

export interface AnalysisSnapshot {
  phase: SessionPhase;
  file: SessionFile | null;
  startedAt: number | null;
  verdict: VerdictMessage | null;
  jobId: string | null;
  timedOut: boolean;
  error: string | null;
}

// Longer than the backend's 150 s so the backend's own 4008 timeout is what the user sees.
export const ANALYSIS_TIMEOUT_MS = 160_000;

export const IDLE_SNAPSHOT: AnalysisSnapshot = {
  phase: 'idle',
  file: null,
  startedAt: null,
  verdict: null,
  jobId: null,
  timedOut: false,
  error: null
};

const SESSION_KEY = 'charonSession';

export async function loadSnapshot(): Promise<AnalysisSnapshot> {
  if (!canUseChromeStorage()) {
    return IDLE_SNAPSHOT;
  }

  const raw = (await chrome.storage.local.get([SESSION_KEY])) as {
    [SESSION_KEY]?: AnalysisSnapshot;
  };
  return raw[SESSION_KEY] ?? IDLE_SNAPSHOT;
}

export async function saveSnapshot(snapshot: AnalysisSnapshot): Promise<void> {
  if (canUseChromeStorage()) {
    await chrome.storage.local.set({ [SESSION_KEY]: snapshot });
  }
}

export function watchSnapshot(listener: (snapshot: AnalysisSnapshot) => void): () => void {
  return watchStorageKey<AnalysisSnapshot>(SESSION_KEY, (value) =>
    listener(value ?? IDLE_SNAPSHOT)
  );
}
