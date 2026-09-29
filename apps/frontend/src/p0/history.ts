/** Local history of the verdicts shown by the popup, newest first. */

import type { VerdictDecision } from './network';
import { canUseChromeStorage, watchStorageKey } from './storage';

export interface HistoryEntry {
  name: string;
  decision: VerdictDecision;
  score: number | null;
  time: number;
}

const HISTORY_KEY = 'charonHistory';
const HISTORY_LIMIT = 20;

export async function loadHistory(): Promise<HistoryEntry[]> {
  if (!canUseChromeStorage()) {
    return [];
  }

  const raw = (await chrome.storage.local.get([HISTORY_KEY])) as { [HISTORY_KEY]?: HistoryEntry[] };
  return Array.isArray(raw[HISTORY_KEY]) ? raw[HISTORY_KEY] : [];
}

export async function recordHistory(entry: HistoryEntry): Promise<HistoryEntry[]> {
  const history = [entry, ...(await loadHistory())].slice(0, HISTORY_LIMIT);

  if (canUseChromeStorage()) {
    await chrome.storage.local.set({ [HISTORY_KEY]: history });
  }

  return history;
}

export function watchHistory(listener: (history: HistoryEntry[]) => void): () => void {
  return watchStorageKey<HistoryEntry[]>(HISTORY_KEY, (value) =>
    listener(Array.isArray(value) ? value : [])
  );
}
