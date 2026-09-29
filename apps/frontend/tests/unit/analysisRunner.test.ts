import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, runAnalysis, type AnalysisOutcome } from '../../src/p0/network';
import { resolveJwtTokenAutomatically } from '../../src/p0/tokenResolver';
import { stubChrome, type FakeChrome } from './fakeChromeStorage';

vi.mock('../../src/p0/network', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/p0/network')>();
  return { ...actual, runAnalysis: vi.fn() };
});

vi.mock('../../src/p0/tokenResolver', () => ({ resolveJwtTokenAutomatically: vi.fn() }));

const BLOCKED: AnalysisOutcome = {
  kind: 'verdict',
  jobId: 'job-1',
  verdict: {
    job_id: 'job-1',
    final_decision: 'blocked',
    technical_summary: { ml_layer_score: 94 },
    timestamp: '2026-09-29T10:00:00Z'
  }
};

function buildFile(name = 'invoice.pdf'): File {
  return new File(['payload'], name, { type: 'application/pdf' });
}

// The runner keeps module state (one analysis at a time, last file), so each test gets a fresh copy.
async function loadRunner(): Promise<typeof import('../../src/p0/analysisRunner')> {
  vi.resetModules();
  return await import('../../src/p0/analysisRunner');
}

let fake: FakeChrome;

beforeEach(() => {
  fake = stubChrome();
  vi.mocked(resolveJwtTokenAutomatically).mockResolvedValue('cached-token');
  vi.mocked(runAnalysis).mockResolvedValue(BLOCKED);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('analyseFile', () => {
  it('publishes the analysing state, then the verdict, and records it', async () => {
    const { analyseFile } = await loadRunner();
    const states: string[] = [];
    (globalThis as unknown as { chrome: typeof chrome }).chrome.storage.onChanged.addListener(
      (changes: Record<string, chrome.storage.StorageChange>) => {
        if (changes.charonSession) {
          states.push((changes.charonSession.newValue as { phase: string }).phase);
        }
      }
    );

    await analyseFile(buildFile());

    expect(states).toEqual(['analyzing', 'completed']);
    expect(fake.data.charonSession).toMatchObject({
      phase: 'completed',
      file: { name: 'invoice.pdf', size: 7 },
      jobId: 'job-1',
      timedOut: false,
      verdict: { final_decision: 'blocked' }
    });
    expect(fake.data.charonHistory).toMatchObject([
      { name: 'invoice.pdf', decision: 'blocked', score: 94 }
    ]);
  });

  it('sends the anonymous marker when no SSO token was found', async () => {
    vi.mocked(resolveJwtTokenAutomatically).mockResolvedValue(null);
    const { analyseFile } = await loadRunner();

    await analyseFile(buildFile());

    expect(vi.mocked(runAnalysis).mock.calls[0][0].jwtToken).toBe('anonymous');
  });

  it('records a timed-out analysis as suspicious', async () => {
    vi.mocked(runAnalysis).mockResolvedValue({ kind: 'timeout', jobId: 'job-2' });
    const { analyseFile } = await loadRunner();

    await analyseFile(buildFile());

    expect(fake.data.charonSession).toMatchObject({ phase: 'completed', timedOut: true });
    expect(fake.data.charonHistory).toMatchObject([{ decision: 'warning', score: null }]);
  });

  it('publishes the failure without recording it', async () => {
    vi.mocked(runAnalysis).mockRejectedValue(new ApiError('Too big.'));
    const { analyseFile } = await loadRunner();

    await analyseFile(buildFile());

    expect(fake.data.charonSession).toMatchObject({ phase: 'failed', error: 'Too big.' });
    expect(fake.data.charonHistory).toBeUndefined();
  });

  it('keeps a delivered verdict when the history cannot be written', async () => {
    const { analyseFile } = await loadRunner();
    const local = (globalThis as unknown as { chrome: typeof chrome }).chrome.storage.local;
    const save = local.set.bind(local);
    local.set = (async (items: Record<string, unknown>) => {
      if ('charonHistory' in items) {
        throw new Error('quota exceeded');
      }
      await save(items);
    }) as typeof local.set;

    await analyseFile(buildFile());

    expect(fake.data.charonSession).toMatchObject({ phase: 'completed' });
  });

  it('reports a generic message for a non-error rejection', async () => {
    vi.mocked(runAnalysis).mockRejectedValue('socket died');
    const { analyseFile } = await loadRunner();

    await analyseFile(buildFile());

    expect(fake.data.charonSession).toMatchObject({ error: 'Unknown error during analysis.' });
  });

  it('ignores a file sent while an analysis is running', async () => {
    let finish: (outcome: AnalysisOutcome) => void = () => {};
    vi.mocked(runAnalysis).mockReturnValue(new Promise((resolve) => (finish = resolve)));
    const { analyseFile } = await loadRunner();

    const first = analyseFile(buildFile('first.pdf'));
    await vi.waitFor(() => expect(runAnalysis).toHaveBeenCalledOnce());
    await analyseFile(buildFile('second.pdf'));
    finish(BLOCKED);
    await first;

    expect(runAnalysis).toHaveBeenCalledOnce();
    expect(fake.data.charonSession).toMatchObject({ file: { name: 'first.pdf' } });
  });

  it('keeps the service worker alive while waiting for the verdict', async () => {
    vi.useFakeTimers();
    const ping = vi.fn(async () => ({}));
    (globalThis as unknown as { chrome: { runtime: object } }).chrome.runtime = {
      getPlatformInfo: ping
    };
    let finish: (outcome: AnalysisOutcome) => void = () => {};
    vi.mocked(runAnalysis).mockReturnValue(new Promise((resolve) => (finish = resolve)));
    const { analyseFile } = await loadRunner();

    const analysis = analyseFile(buildFile());
    await vi.advanceTimersByTimeAsync(45_000);
    finish(BLOCKED);
    await analysis;
    await vi.advanceTimersByTimeAsync(45_000);

    expect(ping).toHaveBeenCalledTimes(2);
  });
});

describe('retryLastFile', () => {
  it('re-runs the last file', async () => {
    const { analyseFile, retryLastFile } = await loadRunner();
    await analyseFile(buildFile());

    await retryLastFile();

    expect(runAnalysis).toHaveBeenCalledTimes(2);
  });

  it('asks for the file again when the worker no longer has it', async () => {
    const { retryLastFile } = await loadRunner();

    await retryLastFile();

    expect(fake.data.charonSession).toMatchObject({
      phase: 'failed',
      error: 'The file is no longer available. Choose it again.'
    });
  });
});

describe('resetSession', () => {
  it('returns to idle', async () => {
    const { analyseFile, resetSession } = await loadRunner();
    await analyseFile(buildFile());

    await resetSession();

    expect(fake.data.charonSession).toMatchObject({ phase: 'idle', verdict: null });
  });

  it('never interrupts a running analysis', async () => {
    let finish: (outcome: AnalysisOutcome) => void = () => {};
    vi.mocked(runAnalysis).mockReturnValue(new Promise((resolve) => (finish = resolve)));
    const { analyseFile, resetSession } = await loadRunner();

    const analysis = analyseFile(buildFile());
    await vi.waitFor(() => expect(runAnalysis).toHaveBeenCalledOnce());
    await resetSession();

    expect(fake.data.charonSession).toMatchObject({ phase: 'analyzing' });
    finish(BLOCKED);
    await analysis;
  });
});

describe('recoverInterruptedSession', () => {
  it('fails an analysis the previous worker did not finish', async () => {
    fake = stubChrome({ charonSession: { phase: 'analyzing', file: { name: 'a', size: 1 } } });
    const { recoverInterruptedSession } = await loadRunner();

    await recoverInterruptedSession();

    expect(fake.data.charonSession).toMatchObject({ phase: 'failed', file: { name: 'a' } });
  });

  it('leaves a finished session alone', async () => {
    fake = stubChrome({ charonSession: { phase: 'completed' } });
    const { recoverInterruptedSession } = await loadRunner();

    await recoverInterruptedSession();

    expect(fake.data.charonSession).toEqual({ phase: 'completed' });
  });
});
