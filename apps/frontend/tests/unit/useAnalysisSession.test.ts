import { effectScope } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, runAnalysis, type AnalysisOutcome } from '../../src/p0/network';
import { loadSettings } from '../../src/p0/settings';
import { resolveJwtTokenAutomatically } from '../../src/p0/tokenResolver';
import { useAnalysisSession, type AnalysisSession } from '../../src/ui/useAnalysisSession';

vi.mock('../../src/p0/network', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/p0/network')>();
  return { ...actual, runAnalysis: vi.fn() };
});

vi.mock('../../src/p0/settings', () => ({ loadSettings: vi.fn() }));

vi.mock('../../src/p0/tokenResolver', () => ({ resolveJwtTokenAutomatically: vi.fn() }));

const CACHED_TOKEN = 'cached-token';

const VERDICT_OUTCOME: AnalysisOutcome = {
  kind: 'verdict',
  jobId: 'job-1',
  verdict: {
    job_id: 'job-1',
    final_decision: 'blocked',
    timestamp: '2026-08-13T10:00:00Z'
  }
};

function buildFile(): File {
  return new File(['payload'], 'sample.pdf', { type: 'application/pdf' });
}

function createSession(): AnalysisSession {
  const scope = effectScope();
  const session = scope.run(() => useAnalysisSession());

  if (!session) {
    throw new Error('Analysis session was not created.');
  }

  return session;
}

describe('useAnalysisSession', () => {
  beforeEach(() => {
    vi.mocked(loadSettings).mockResolvedValue({
      apiBaseUrl: 'http://localhost:8000',
      cachedJwtToken: CACHED_TOKEN
    });
    vi.mocked(resolveJwtTokenAutomatically).mockResolvedValue(CACHED_TOKEN);
    vi.mocked(runAnalysis).mockResolvedValue(VERDICT_OUTCOME);
  });

  it('starts idle and becomes ready once a file is selected', () => {
    const session = createSession();
    expect(session.phase.value).toBe('idle');

    session.selectFile(buildFile());

    expect(session.phase.value).toBe('selected');
    expect(session.selectedFile.value?.name).toBe('sample.pdf');
  });

  it('ignores an analysis request while no file is selected', async () => {
    const session = createSession();

    await session.startAnalysis();

    expect(runAnalysis).not.toHaveBeenCalled();
    expect(session.phase.value).toBe('idle');
  });

  it('publishes the verdict returned by the analysis flow', async () => {
    const session = createSession();
    session.selectFile(buildFile());

    await session.startAnalysis();

    expect(session.phase.value).toBe('completed');
    expect(session.verdict.value?.final_decision).toBe('blocked');
    expect(session.jobId.value).toBe('job-1');
    expect(session.hasTimedOut.value).toBe(false);
    expect(session.progressRatio.value).toBe(1);
    expect(session.tokenSource.value).toBe('cached');
  });

  it('reports a token discovered on the active tab', async () => {
    vi.mocked(resolveJwtTokenAutomatically).mockResolvedValue('fresh-token');
    const session = createSession();
    session.selectFile(buildFile());

    await session.startAnalysis();

    expect(session.tokenSource.value).toBe('active-tab');
  });

  it('flags a timed-out analysis without a verdict', async () => {
    vi.mocked(runAnalysis).mockResolvedValue({ kind: 'timeout', jobId: 'job-2' });
    const session = createSession();
    session.selectFile(buildFile());

    await session.startAnalysis();

    expect(session.phase.value).toBe('completed');
    expect(session.hasTimedOut.value).toBe(true);
    expect(session.verdict.value).toBeNull();
  });

  it('surfaces the backend error message', async () => {
    vi.mocked(runAnalysis).mockRejectedValue(new ApiError('Analyze request failed (413).', 413));
    const session = createSession();
    session.selectFile(buildFile());

    await session.startAnalysis();

    expect(session.phase.value).toBe('failed');
    expect(session.errorMessage.value).toBe('Analyze request failed (413).');
  });

  it('surfaces a generic message for non-error rejections', async () => {
    vi.mocked(runAnalysis).mockRejectedValue('socket died');
    const session = createSession();
    session.selectFile(buildFile());

    await session.startAnalysis();

    expect(session.errorMessage.value).toBe('Unknown error during analysis.');
  });

  it('reports elapsed progress while the analysis is pending', async () => {
    vi.useFakeTimers();
    let releaseOutcome: (outcome: AnalysisOutcome) => void = () => {};
    vi.mocked(runAnalysis).mockReturnValue(
      new Promise<AnalysisOutcome>((resolve) => {
        releaseOutcome = resolve;
      })
    );

    const session = createSession();
    session.selectFile(buildFile());
    const analysis = session.startAnalysis();
    await vi.advanceTimersByTimeAsync(13_000);

    expect(session.phase.value).toBe('analyzing');
    expect(session.progressRatio.value).toBeGreaterThan(0);
    expect(session.progressRatio.value).toBeLessThan(1);

    releaseOutcome(VERDICT_OUTCOME);
    await analysis;
    vi.useRealTimers();
  });

  it('clears the session on reset', async () => {
    const session = createSession();
    session.selectFile(buildFile());
    await session.startAnalysis();

    session.reset();

    expect(session.phase.value).toBe('idle');
    expect(session.selectedFile.value).toBeNull();
    expect(session.verdict.value).toBeNull();
    expect(session.jobId.value).toBeNull();
    expect(session.tokenSource.value).toBeNull();
    expect(session.progressRatio.value).toBe(0);
  });
});
