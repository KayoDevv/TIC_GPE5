/** The single visual state shared by the popup lockup and the toolbar icon. */

import type { AnalysisPhase } from './useAnalysisSession';
import type { VerdictTone } from './verdictPresentation';

export type CharonState = 'idle' | 'analyzing' | VerdictTone;

export const POPUP_PORT_NAME = 'charon-popup';

const ICON_SIZES = [16, 32, 48, 128] as const;

const ICON_FILE_STATES: Record<CharonState, string> = {
  idle: 'idle',
  analyzing: 'analyzing',
  allowed: 'safe',
  warning: 'warn',
  blocked: 'danger'
};

export function resolveCharonState(phase: AnalysisPhase, tone: VerdictTone | null): CharonState {
  if (phase === 'analyzing') {
    return 'analyzing';
  }

  return phase === 'completed' && tone ? tone : 'idle';
}

export function toolbarIconPaths(state: CharonState): Record<number, string> {
  const fileState = ICON_FILE_STATES[state];
  return Object.fromEntries(ICON_SIZES.map((size) => [size, `icons/eye/icon${size}-${fileState}.png`]));
}

export function connectToolbarIcon(): (state: CharonState) => void {
  if (typeof chrome === 'undefined' || !chrome.runtime?.connect) {
    return () => {};
  }

  const port = chrome.runtime.connect({ name: POPUP_PORT_NAME });
  return (state) => port.postMessage({ state });
}
