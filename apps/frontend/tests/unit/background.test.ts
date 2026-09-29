import { afterEach, describe, expect, it, vi } from 'vitest';
import background from '../../entrypoints/background';
import {
  analyseFile,
  recoverInterruptedSession,
  resetSession,
  retryLastFile
} from '../../src/p0/analysisRunner';
import { IDLE_SNAPSHOT } from '../../src/p0/session';
import { toolbarIconPaths } from '../../src/ui/charonState';
import { stubChrome } from './fakeChromeStorage';

vi.mock('../../src/p0/analysisRunner', () => ({
  analyseFile: vi.fn(async () => {}),
  retryLastFile: vi.fn(async () => {}),
  resetSession: vi.fn(async () => {}),
  recoverInterruptedSession: vi.fn(async () => {})
}));

function startBackground(initial: Record<string, unknown> = {}) {
  const fake = stubChrome(initial);
  const setIcon = vi.fn(async () => {});
  let onMessage: (message: unknown) => void = () => {};
  const chromeStub = (globalThis as unknown as { chrome: Record<string, Record<string, unknown>> })
    .chrome;
  chromeStub.action = { setIcon };
  chromeStub.runtime.onMessage = {
    addListener: (listener: typeof onMessage) => (onMessage = listener)
  };
  background.main();
  return { fake, setIcon, send: (message: unknown) => onMessage(message) };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('background worker', () => {
  it('recovers an interrupted session and shows the stored state on start', async () => {
    const { setIcon } = startBackground({
      charonSession: { ...IDLE_SNAPSHOT, phase: 'completed', timedOut: true }
    });

    await vi.waitFor(() => expect(setIcon).toHaveBeenCalled());
    expect(recoverInterruptedSession).toHaveBeenCalledOnce();
    expect(setIcon).toHaveBeenCalledWith({ path: toolbarIconPaths('warning') });
  });

  it('mirrors every published snapshot on the toolbar icon', async () => {
    const { setIcon } = startBackground();

    await chrome.storage.local.set({ charonSession: { ...IDLE_SNAPSHOT, phase: 'analyzing' } });

    expect(setIcon).toHaveBeenCalledWith({ path: toolbarIconPaths('analyzing') });
  });

  it('routes analyse, retry and reset requests to the runner', async () => {
    const { send } = startBackground();

    send({ type: 'charon:analyse', name: 'a.pdf', mimeType: 'application/pdf', base64: 'eA==' });
    send({ type: 'charon:retry' });
    send({ type: 'charon:reset' });

    expect(vi.mocked(analyseFile).mock.calls[0][0].name).toBe('a.pdf');
    expect(retryLastFile).toHaveBeenCalledOnce();
    expect(resetSession).toHaveBeenCalledOnce();
  });

  it('ignores messages that are not its own', () => {
    const { send } = startBackground();

    send({ type: 'someone-else' });
    send(undefined);

    expect(analyseFile).not.toHaveBeenCalled();
    expect(resetSession).not.toHaveBeenCalled();
  });
});
