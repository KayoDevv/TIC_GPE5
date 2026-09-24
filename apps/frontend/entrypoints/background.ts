import { defineBackground } from 'wxt/utils/define-background';
import { POPUP_PORT_NAME, toolbarIconPaths, type CharonState } from '../src/ui/charonState';

function showState(state: CharonState): void {
  void chrome.action.setIcon({ path: toolbarIconPaths(state) });
}

export default defineBackground(() => {
  chrome.runtime.onConnect.addListener((port) => {
    if (port.name !== POPUP_PORT_NAME) {
      return;
    }

    port.onMessage.addListener((message: { state: CharonState }) => showState(message.state));
    // The analysis lives in the popup, so closing it ends the analysis: back to idle.
    port.onDisconnect.addListener(() => showState('idle'));
  });
});
