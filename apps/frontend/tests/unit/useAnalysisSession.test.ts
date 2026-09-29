import { flushPromises } from '@vue/test-utils';
import { effectScope } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { IDLE_SNAPSHOT, type AnalysisSnapshot } from '../../src/p0/session';
import { useAnalysisSession, type AnalysisSession } from '../../src/ui/useAnalysisSession';
import { stubChrome } from './fakeChromeStorage';

const BLOCKED: AnalysisSnapshot = {
  ...IDLE_SNAPSHOT,
  phase: 'completed',
  file: { name: 'invoice.pdf', size: 7 },
  verdict: { job_id: 'job-1', final_decision: 'blocked', timestamp: 't' },
  jobId: 'job-1'
};

function createSession(): { session: AnalysisSession; stop: () => void } {
  const scope = effectScope();
  const session = scope.run(() => useAnalysisSession());
  if (!session) {
    throw new Error('Analysis session was not created.');
  }

  return { session, stop: () => scope.stop() };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('useAnalysisSession', () => {
  it('shows the snapshot the background worker already published', async () => {
    stubChrome({ charonSession: BLOCKED, charonHistory: [{ name: 'a', decision: 'allowed' }] });
    const { session } = createSession();
    await flushPromises();

    expect(session.phase.value).toBe('completed');
    expect(session.file.value?.name).toBe('invoice.pdf');
    expect(session.verdict.value?.final_decision).toBe('blocked');
    expect(session.jobId.value).toBe('job-1');
    expect(session.progressRatio.value).toBe(1);
    expect(session.history.value).toHaveLength(1);
  });

  it('follows every change the worker publishes, history included', async () => {
    stubChrome();
    const { session } = createSession();
    await flushPromises();
    expect(session.phase.value).toBe('idle');

    await chrome.storage.local.set({
      charonSession: { ...IDLE_SNAPSHOT, phase: 'failed', error: 'Too big.' },
      charonHistory: [{ name: 'b', decision: 'warning' }]
    });

    expect(session.phase.value).toBe('failed');
    expect(session.errorMessage.value).toBe('Too big.');
    expect(session.history.value).toEqual([{ name: 'b', decision: 'warning' }]);
  });

  it('keeps a change that lands while the initial read is in flight', async () => {
    stubChrome();
    const { session } = createSession();

    await chrome.storage.local.set({ charonSession: BLOCKED });
    await flushPromises();

    expect(session.phase.value).toBe('completed');
  });

  it('reports elapsed progress while the analysis runs', async () => {
    vi.useFakeTimers();
    const startedAt = Date.now();
    stubChrome({ charonSession: { ...IDLE_SNAPSHOT, phase: 'analyzing', startedAt } });
    const { session, stop } = createSession();
    await flushPromises();

    await vi.advanceTimersByTimeAsync(16_000);

    expect(session.progressRatio.value).toBeCloseTo(0.1, 2);
    stop();
  });

  it('caps the pending progress below completion', async () => {
    vi.useFakeTimers();
    stubChrome({ charonSession: { ...IDLE_SNAPSHOT, phase: 'analyzing', startedAt: 0 } });
    const { session } = createSession();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(300);

    expect(session.progressRatio.value).toBe(0.98);
  });

  it('asks the background worker to analyse, retry and reset', async () => {
    const fake = stubChrome();
    const { session } = createSession();

    await session.analyse(new File(['payload'], 'invoice.pdf', { type: 'application/pdf' }));
    await session.retry();
    await session.reset();

    expect(fake.sent).toMatchObject([
      { type: 'charon:analyse', name: 'invoice.pdf', mimeType: 'application/pdf', base64: 'cGF5bG9hZA==' },
      { type: 'charon:retry' },
      { type: 'charon:reset' }
    ]);
  });
});
