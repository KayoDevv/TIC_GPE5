import { defineBackground } from 'wxt/utils/define-background';
import {
  analyseFile,
  recoverInterruptedSession,
  resetSession,
  retryLastFile
} from '../src/p0/analysisRunner';
import {
  ANALYSE_MESSAGE,
  decodeFile,
  RESET_MESSAGE,
  RETRY_MESSAGE,
  type CharonMessage
} from '../src/p0/fileMessage';
import { loadSnapshot, watchSnapshot, type AnalysisSnapshot } from '../src/p0/session';
import { snapshotState, toolbarIconPaths } from '../src/ui/charonState';

function showOnToolbar(snapshot: AnalysisSnapshot): void {
  void chrome.action.setIcon({ path: toolbarIconPaths(snapshotState(snapshot)) });
}

function handle(message: CharonMessage): Promise<void> {
  if (message.type === ANALYSE_MESSAGE) {
    return analyseFile(decodeFile(message));
  }

  return message.type === RETRY_MESSAGE ? retryLastFile() : resetSession();
}

export default defineBackground(() => {
  watchSnapshot(showOnToolbar);
  void recoverInterruptedSession()
    .then(loadSnapshot)
    .then(showOnToolbar);

  chrome.runtime.onMessage.addListener((message: CharonMessage) => {
    if ([ANALYSE_MESSAGE, RETRY_MESSAGE, RESET_MESSAGE].includes(message?.type)) {
      void handle(message);
    }
  });
});
