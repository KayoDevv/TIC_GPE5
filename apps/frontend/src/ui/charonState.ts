/** The single visual state shared by the popup lockup, the side tab and the toolbar icon. */

import type { AnalysisSnapshot } from '../p0/session';
import type { VerdictTone } from './verdictPresentation';

export type CharonState = 'idle' | 'analyzing' | VerdictTone;

const ICON_SIZES = [16, 32, 48, 128] as const;

const ICON_FILE_STATES: Record<CharonState, string> = {
  idle: 'idle',
  analyzing: 'analyzing',
  allowed: 'safe',
  warning: 'warn',
  blocked: 'danger'
};

// A timed-out analysis has no verdict but is presented as suspicious.
const TIMEOUT_STATE: CharonState = 'warning';

export function snapshotState(snapshot: AnalysisSnapshot): CharonState {
  if (snapshot.phase === 'analyzing') {
    return 'analyzing';
  }

  if (snapshot.phase !== 'completed') {
    return 'idle';
  }

  return snapshot.timedOut ? TIMEOUT_STATE : (snapshot.verdict?.final_decision ?? 'idle');
}

export function toolbarIconPaths(state: CharonState): Record<number, string> {
  const fileState = ICON_FILE_STATES[state];
  return Object.fromEntries(
    ICON_SIZES.map((size) => [size, `icons/eye/icon${size}-${fileState}.png`])
  );
}
